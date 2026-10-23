"""Conversation flow: starting, sending, the agent's turn and ending.

Views stay thin and call these functions. The model call (`generate_turn`) always
runs outside a database transaction. Before it, a row-locked check marks the turn as
started (`agent_turn_started_at`), so a refresh shows "Agent is typing" and a
parallel retry is refused instead of paying for a second call. The agent's reply is
saved in a short transaction that first re-checks, under the lock, that the
conversation still waits for it (the user may have ended it meanwhile).

Memory from earlier conversations is a snapshot from the start: `start_conversation`
selects and formats it once into `memory_prompt`, and every turn (also "Try again")
sends that same text. It is never recomputed, not even when the analysis of another
conversation finishes meanwhile, so the cached prompt prefix stays the same.

The post-conversation analysis (`analyze_conversation`) follows the same pattern
with its own marker (`analysis_started_at`): a locked check, the model call
(`analyze_mistakes`) outside any transaction, then a locked save only if the
conversation is still not analysed. It runs once per ended conversation, whatever
ended it and whatever is left of the budget. The model's raw list is turned into
list positions here: chronological order, identical pairs merged into one item.
The same analysis returns notes for later conversations (`learner_facts`,
`scene_notes`); they are saved together with the list, in the same locked block, so
a late result drops them too.

Every model call that most likely cost money counts towards the day's budget. A
saved turn keeps its cost in `Message.cost_usd` and a saved analysis in
`analysis_cost_usd`; a call that saved neither goes to the `LLMCharge` ledger: a
late result is dropped, but its cost is counted, and so is a timeout (estimated),
an unusable answer (its usage) and an analysis whose save failed.

The hard ceiling: once today's sum reached the limit (`limit_reached`), no new paid
call starts. Sending a message and retrying the agent's turn are refused and the
conversation ends by the daily limit; the day can go over the limit only by a turn
that started below it. The analysis is different: the first attempt runs whatever
is left; a retry waits for the reset once the limit is reached.
"""

import logging
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User

from .budget import (
    is_exhausted,
    is_final_turn,
    limit_reached,
    next_turn_estimate,
    turn_cost,
)
from .llm import (
    AnalysisResult,
    CallUsage,
    FoundMistake,
    LLMError,
    TurnResult,
    analyze_mistakes,
    format_memory,
    generate_turn,
)
from .memory import select_memory
from .models import Conversation, LLMCharge, Message, Mistake
from .topics import TOPICS, Topic, get_topic

logger = logging.getLogger(__name__)

# Chat turns are short. The cap keeps one pasted text from eating the daily budget
# or overflowing the model's context (which would make every retry fail).
MAX_MESSAGE_LENGTH = 2000

DAILY_LIMIT_REACHED = "You have used today's conversation limit."


class ConversationError(Exception):
    """A refused action; the message is shown to the user as it is."""


class AnalysisNotNeeded(ConversationError):
    """The analysis is already done or still running; views may skip the notice."""


def _lock(conversation: Conversation) -> Conversation:
    """Re-read the conversation with a row lock; call inside `transaction.atomic`."""
    return (
        Conversation.objects.for_user(conversation.user)
        .select_for_update()
        .get(pk=conversation.pk)
    )


def _agent_turn_timeout() -> timedelta:
    # Longer than the SDK can wait: every attempt up to its timeout, the longest
    # Retry-After before each retry, plus 30 s. A live call is never taken for a
    # dead one, and a marker left by a killed worker still expires.
    # Assumes a non-streaming call: httpx applies the timeout per phase and per
    # read, so only a body that arrives at once makes it the length of an attempt.
    attempts = settings.LLM_MAX_RETRIES + 1
    waits = settings.LLM_MAX_RETRIES * settings.LLM_MAX_RETRY_AFTER_SECONDS
    return timedelta(seconds=waits + settings.LLM_TIMEOUT_SECONDS * attempts + 30)


def agent_turn_in_progress(conversation: Conversation, now: datetime) -> bool:
    """True while the model is (or may still be) generating the agent's turn."""
    started = conversation.agent_turn_started_at
    return started is not None and now - started < _agent_turn_timeout()


def _mark_turn_started(conversation: Conversation, now: datetime) -> None:
    """Call inside `transaction.atomic`, on a locked conversation."""
    conversation.agent_turn_started_at = now
    conversation.save(update_fields=["agent_turn_started_at"])


def _clear_turn_marker(conversation: Conversation, started_at: datetime) -> None:
    # Only our own marker: once it has expired, another request may have set a new one.
    Conversation.objects.for_user(conversation.user).filter(
        pk=conversation.pk, agent_turn_started_at=started_at
    ).update(agent_turn_started_at=None)


def surprise_topic_key(user: User) -> str:
    """A random topic key for "Surprise me", other than the user's last topic.

    The last conversation counts whether it has ended or not. Without one, when its
    topic is no longer in `TOPICS`, or when no other topic is left, every topic can
    be drawn.
    """
    keys = [topic.key for topic in TOPICS]
    last = Conversation.objects.for_user(user).order_by("-created_at", "-id").first()
    candidates = [key for key in keys if last is None or key != last.topic]
    return random.choice(candidates or keys)


def start_conversation(user: User, topic_key: str, now: datetime) -> Conversation:
    """Create the user's active conversation and let the agent open the scene.

    Raises `ConversationError` when the start is refused and `LLMError` when the
    opening turn fails (the conversation then exists and waits for a retry).
    """
    topic = get_topic(topic_key)
    if topic is None:
        raise ConversationError("Unknown topic. Please choose one from the list.")
    if is_exhausted(user, now):
        raise ConversationError(DAILY_LIMIT_REACHED)
    memory_prompt = format_memory(
        select_memory(user, topic.key, user.practice_language)
    )
    try:
        # Without its own atomic block, the caught IntegrityError would break the
        # surrounding transaction (TransactionManagementError on the next query).
        with transaction.atomic():
            conversation = Conversation.objects.create(
                user=user,
                topic=topic.key,
                topic_title=topic.title,
                topic_scenario=topic.scenario,
                memory_prompt=memory_prompt,
                language=user.practice_language,
                agent_turn_started_at=now,
            )
    except IntegrityError:
        raise ConversationError(
            "You already have a conversation in progress."
        ) from None
    _generate_and_save(conversation, now)
    return conversation


def send_message(conversation: Conversation, text: str, now: datetime) -> None:
    """Save the user's message and get the agent's reply.

    Only for an active conversation that does not wait for the agent; the check, the
    save and the turn marker happen under one row lock, so a double submit cannot
    save two messages and a parallel retry cannot start a second model call.
    Once today's sum reached the limit, the message is not saved and the
    conversation ends by the daily limit.
    """
    text = text.strip()
    if not text:
        raise ConversationError("Please write a message first.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ConversationError(
            f"Please keep your message to {MAX_MESSAGE_LENGTH} characters or fewer."
        )
    with transaction.atomic():
        locked = _lock(conversation)
        if locked.status != Conversation.Status.ACTIVE:
            raise ConversationError("This conversation has ended.")
        if locked.awaiting_agent_reply:
            raise ConversationError("Please wait for the agent's reply.")
        at_ceiling = limit_reached(locked.user, now)
        if at_ceiling:
            end_conversation(locked, Conversation.EndReason.DAILY_LIMIT, now)
        else:
            Message.objects.create(
                conversation=locked, role=Message.Role.USER, text=text
            )
            _mark_turn_started(locked, now)
    # Refused only after the commit: raising inside the block would undo the end.
    if at_ceiling:
        raise ConversationError(DAILY_LIMIT_REACHED)
    _generate_and_save(locked, now)


def run_agent_turn(conversation: Conversation, now: datetime) -> None:
    """Retry the agent's turn of a conversation that waits for it.

    Refused while another request is still generating that turn. Once today's sum
    reached the limit, refused and the conversation ends by the daily limit.
    `LLMError` propagates and nothing is saved.
    """
    with transaction.atomic():
        locked = _lock(conversation)
        if not locked.awaiting_agent_reply:
            raise ConversationError("There is nothing to retry.")
        if agent_turn_in_progress(locked, now):
            raise ConversationError("The agent is still replying. Please wait.")
        at_ceiling = limit_reached(locked.user, now)
        if at_ceiling:
            end_conversation(locked, Conversation.EndReason.DAILY_LIMIT, now)
        else:
            _mark_turn_started(locked, now)
    # Refused only after the commit: raising inside the block would undo the end.
    if at_ceiling:
        conversation.refresh_from_db()
        raise ConversationError(DAILY_LIMIT_REACHED)
    _generate_and_save(locked, now)
    conversation.refresh_from_db()


def _generate_and_save(conversation: Conversation, now: datetime) -> None:
    """Generate one agent turn and save it; the turn marker must be set to `now`.

    A reply that is no longer needed when it arrives (the user ended the
    conversation meanwhile) is dropped, but its cost is counted. A failed call that
    most likely cost money is counted too (see `_charge_failed_call`).
    """
    final = is_final_turn(conversation.user, conversation, now)
    # The same estimate as the final-turn forecast; charged if the call times out.
    estimate = next_turn_estimate(conversation.user, conversation)
    history = list(conversation.messages.values_list("role", "text"))
    # The topic comes from the conversation's own copy, not from TOPICS.
    topic = Topic(
        key=conversation.topic,
        title=conversation.topic_title,
        scenario=conversation.topic_scenario,
    )
    try:
        result = generate_turn(
            topic=topic,
            language=conversation.language,
            history=history,
            final_turn=final,
            memory=conversation.memory_prompt,
        )
    except Exception as error:
        # Free the conversation at once, so "Try again" works right away.
        _clear_turn_marker(conversation, now)
        if isinstance(error, LLMError):
            _charge_failed_call(conversation, LLMCharge.Kind.TURN, error, estimate, now)
        raise

    with transaction.atomic():
        locked = _lock(conversation)
        if locked.awaiting_agent_reply:
            _save_agent_turn(locked, result, final, now)
        else:
            # A late turn: dropped, but paid for.
            _charge(
                locked,
                LLMCharge.Kind.TURN,
                LLMCharge.Reason.LATE_RESULT,
                _result_cost(result),
                now,
            )
        _clear_turn_marker(locked, now)
    conversation.refresh_from_db()


def _result_cost(result: TurnResult | AnalysisResult | CallUsage) -> Decimal:
    return turn_cost(
        result.model,
        result.input_tokens,
        result.cached_input_tokens,
        result.output_tokens,
    )


def _charge(
    conversation: Conversation,
    kind: LLMCharge.Kind,
    reason: LLMCharge.Reason,
    cost: Decimal,
    now: datetime,
) -> None:
    """Count a paid call that left no agent turn and no analysis result."""
    LLMCharge.objects.create(
        user=conversation.user,
        conversation=conversation,
        kind=kind,
        reason=reason,
        cost_usd=cost,
        charged_at=now,
    )


def _charge_failed_call(
    conversation: Conversation,
    kind: LLMCharge.Kind,
    error: LLMError,
    estimate: Decimal,
    now: datetime,
) -> None:
    """Count a failed call at its real usage, at `estimate`, or not at all.

    The real usage when the answer carried it; `estimate` when the call most likely
    cost money but its usage is unknown (a timeout, a malformed answer); nothing
    when the provider refused it at once.
    """
    if error.usage is not None:
        cost = _result_cost(error.usage)
        _charge(conversation, kind, LLMCharge.Reason.NO_USABLE_ANSWER, cost, now)
    elif error.billed_without_usage:
        _charge(conversation, kind, LLMCharge.Reason.ESTIMATE, estimate, now)


def _save_agent_turn(
    conversation: Conversation, result: TurnResult, final: bool, now: datetime
) -> None:
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        text=result.reply,
        model=result.model,
        input_tokens=result.input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=turn_cost(
            result.model,
            result.input_tokens,
            result.cached_input_tokens,
            result.output_tokens,
        ),
    )
    if final:
        end_conversation(conversation, Conversation.EndReason.DAILY_LIMIT, now)
    elif result.end_conversation:
        end_conversation(conversation, Conversation.EndReason.AGENT_GOODBYE, now)


def end_conversation(
    conversation: Conversation, reason: Conversation.EndReason, now: datetime
) -> None:
    """End an active conversation; ending an ended one changes nothing."""
    Conversation.objects.for_user(conversation.user).filter(
        pk=conversation.pk, status=Conversation.Status.ACTIVE
    ).update(status=Conversation.Status.ENDED, end_reason=reason, ended_at=now)
    conversation.refresh_from_db()


def _analysis_timeout() -> timedelta:
    # Like `_agent_turn_timeout`: longer than the SDK can wait for the analysis.
    attempts = settings.LLM_ANALYSIS_MAX_RETRIES + 1
    waits = settings.LLM_ANALYSIS_MAX_RETRIES * settings.LLM_MAX_RETRY_AFTER_SECONDS
    return timedelta(
        seconds=waits + settings.LLM_ANALYSIS_TIMEOUT_SECONDS * attempts + 30
    )


def analysis_in_progress(conversation: Conversation, now: datetime) -> bool:
    """True while the model is (or may still be) analysing the conversation."""
    started = conversation.analysis_started_at
    return started is not None and now - started < _analysis_timeout()


def analysis_failed(conversation: Conversation, now: datetime) -> bool:
    """True when the last analysis attempt ended without a list of mistakes.

    Either the failure was recorded, or the marker expired without a result (the
    worker died meanwhile). The page then offers "Try again" instead of starting a
    new paid analysis by itself.
    """
    if conversation.analyzed_at is not None or analysis_in_progress(conversation, now):
        return False
    return (
        conversation.analysis_failed_at is not None
        or conversation.analysis_started_at is not None
    )


def _clear_analysis_marker(conversation: Conversation, started_at: datetime) -> None:
    # Only our own marker: once it has expired, another request may have set a new one.
    Conversation.objects.for_user(conversation.user).filter(
        pk=conversation.pk, analysis_started_at=started_at
    ).update(analysis_started_at=None)


def analyze_conversation(conversation: Conversation, now: datetime) -> None:
    """Find the learner's mistakes in an ended conversation and save the list.

    Runs at most once per conversation. Raises `ConversationError` for an active
    conversation and for a retry once today's sum reached the limit, and
    `AnalysisNotNeeded` when the list is ready or still being prepared. `LLMError` propagates; the conversation is then marked as failed and
    can be analysed again.
    """
    with transaction.atomic():
        locked = _lock(conversation)
        if locked.status != Conversation.Status.ENDED:
            raise ConversationError("This conversation has not ended yet.")
        if locked.analyzed_at is not None:
            raise AnalysisNotNeeded("The list of mistakes is already ready.")
        if analysis_in_progress(locked, now):
            raise AnalysisNotNeeded(
                "The list of mistakes is still being prepared. Please wait."
            )
        history = list(locked.messages.values_list("role", "text"))
        learner_messages = sum(
            1 for role, _ in history if role != Message.Role.ASSISTANT
        )
        if learner_messages == 0:
            # Nothing to analyse: an empty list, without a model call.
            locked.analyzed_at = now
            locked.analysis_cost_usd = 0
            locked.analysis_started_at = None
            locked.analysis_failed_at = None
            locked.save(
                update_fields=[
                    "analyzed_at",
                    "analysis_cost_usd",
                    "analysis_started_at",
                    "analysis_failed_at",
                ]
            )
            conversation.refresh_from_db()
            return
        if analysis_failed(locked, now) and limit_reached(locked.user, now):
            # The first attempt runs whatever is left; a retry waits for the reset.
            raise ConversationError(
                "You have used today's limit. "
                "You can get your list of mistakes after the reset."
            )
        locked.analysis_started_at = now
        locked.save(update_fields=["analysis_started_at"])

    try:
        result = analyze_mistakes(language=locked.language, history=history)
    except Exception as error:
        _mark_analysis_failed(conversation, now)
        if isinstance(error, LLMError):
            _charge_failed_call(
                conversation,
                LLMCharge.Kind.ANALYSIS,
                error,
                settings.LLM_ANALYSIS_COST_ESTIMATE_USD,
                now,
            )
        raise

    cost = _result_cost(result)
    try:
        with transaction.atomic():
            locked = _lock(conversation)
            if locked.analyzed_at is not None:
                # A late result (a parallel request finished first): dropped, but
                # paid for.
                _charge(
                    locked,
                    LLMCharge.Kind.ANALYSIS,
                    LLMCharge.Reason.LATE_RESULT,
                    cost,
                    now,
                )
            else:
                _save_mistakes(
                    locked, _merge_mistakes(result.mistakes, learner_messages)
                )
                locked.learner_facts = _clean_notes(result.learner_facts)
                locked.scene_notes = _clean_notes(result.scene_notes)
                locked.analyzed_at = now
                locked.analysis_cost_usd = cost
                locked.analysis_failed_at = None
                locked.save(
                    update_fields=[
                        "analyzed_at",
                        "analysis_cost_usd",
                        "analysis_failed_at",
                        "learner_facts",
                        "scene_notes",
                    ]
                )
            _clear_analysis_marker(locked, now)
    except Exception:
        # The save failed after a paid call: show "Try again", not a silent re-run,
        # and count the cost outside the failed transaction.
        _mark_analysis_failed(conversation, now)
        try:
            _charge(
                conversation,
                LLMCharge.Kind.ANALYSIS,
                LLMCharge.Reason.SAVE_FAILED,
                cost,
                now,
            )
        except Exception as charge_error:
            # The database may be down; the original error matters more.
            logger.error(
                "Could not count the cost of an unsaved analysis: %s",
                type(charge_error).__name__,
            )
        raise
    conversation.refresh_from_db()


def _mark_analysis_failed(conversation: Conversation, started_at: datetime) -> None:
    # Free the conversation at once, so "Try again" works right away.
    _clear_analysis_marker(conversation, started_at)
    # A newer request that took over the expired marker decides the state.
    Conversation.objects.for_user(conversation.user).filter(
        pk=conversation.pk, analyzed_at__isnull=True, analysis_started_at__isnull=True
    ).update(analysis_failed_at=started_at)
    conversation.refresh_from_db()


def _clean_notes(notes: Sequence[str]) -> list[str]:
    """Trimmed notes in the model's order, without empty ones."""
    return [note.strip() for note in notes if note.strip()]


@dataclass
class _ListItem:
    mistake: FoundMistake
    occurrences: int


def _normalize(text: str) -> str:
    """Trim and collapse whitespace; letter case still matters."""
    return " ".join(text.split())


def _merge_mistakes(
    found: Sequence[FoundMistake], learner_messages: int
) -> list[_ListItem]:
    """The model's raw list as list items: chronological, identical pairs merged.

    Entries with an empty `wrong` or `correct`, or with `wrong == correct`, are
    dropped. Message numbers outside `1..learner_messages` go to the end in the
    model's order. A repeated (`wrong`, `correct`) pair counts towards the first
    occurrence and keeps its category, sentence and explanation.
    """

    def order(mistake: FoundMistake) -> tuple[int, int]:
        if 1 <= mistake.message_number <= learner_messages:
            return (0, mistake.message_number)
        return (1, 0)

    items: dict[tuple[str, str], _ListItem] = {}
    for mistake in sorted(found, key=order):  # `sorted` is stable.
        wrong, correct = _normalize(mistake.wrong), _normalize(mistake.correct)
        if not wrong or not correct or wrong == correct:
            continue
        item = items.get((wrong, correct))
        if item is None:
            items[(wrong, correct)] = _ListItem(mistake=mistake, occurrences=1)
        else:
            item.occurrences += 1
    return list(items.values())


def _save_mistakes(conversation: Conversation, items: Sequence[_ListItem]) -> None:
    """Call inside `transaction.atomic`, on a locked conversation."""
    Mistake.objects.bulk_create(
        Mistake(
            user=conversation.user,
            conversation=conversation,
            position=position,
            category=item.mistake.category,
            wrong=_normalize(item.mistake.wrong),
            correct=_normalize(item.mistake.correct),
            sentence=item.mistake.sentence.strip(),
            explanation=item.mistake.explanation.strip(),
            occurrences=item.occurrences,
        )
        for position, item in enumerate(items, start=1)
    )
