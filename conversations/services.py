"""Conversation flow: starting, sending, the agent's turn and ending.

Views stay thin and call these functions. The model call (`generate_turn`) always
runs outside a database transaction. Before it, a row-locked check marks the turn as
started (`agent_turn_started_at`), so a refresh shows "Agent is typing" and a
parallel retry is refused instead of paying for a second call. The agent's reply is
saved in a short transaction that first re-checks, under the lock, that the
conversation still waits for it (the user may have ended it meanwhile).
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User

from .budget import is_exhausted, is_final_turn, turn_cost
from .llm import TurnResult, generate_turn
from .models import Conversation, Message
from .topics import Topic, get_topic

# Chat turns are short. The cap keeps one pasted text from eating the daily budget
# or overflowing the model's context (which would make every retry fail).
MAX_MESSAGE_LENGTH = 2000


class ConversationError(Exception):
    """A refused action; the message is shown to the user as it is."""


def _lock(conversation: Conversation) -> Conversation:
    """Re-read the conversation with a row lock; call inside `transaction.atomic`."""
    return (
        Conversation.objects.for_user(conversation.user)
        .select_for_update()
        .get(pk=conversation.pk)
    )


def _agent_turn_timeout() -> timedelta:
    # Longer than the SDK can wait (timeout x attempts): a live call is never taken
    # for a dead one, and a marker left by a killed worker still expires.
    attempts = settings.LLM_MAX_RETRIES + 1
    return timedelta(seconds=settings.LLM_TIMEOUT_SECONDS * attempts + 30)


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


def start_conversation(user: User, topic_key: str, now: datetime) -> Conversation:
    """Create the user's active conversation and let the agent open the scene.

    Raises `ConversationError` when the start is refused and `LLMError` when the
    opening turn fails (the conversation then exists and waits for a retry).
    """
    topic = get_topic(topic_key)
    if topic is None:
        raise ConversationError("Unknown topic. Please choose one from the list.")
    if is_exhausted(user, now):
        raise ConversationError("You have used today's conversation limit.")
    try:
        # Without its own atomic block, the caught IntegrityError would break the
        # surrounding transaction (TransactionManagementError on the next query).
        with transaction.atomic():
            conversation = Conversation.objects.create(
                user=user,
                topic=topic.key,
                topic_title=topic.title,
                topic_scenario=topic.scenario,
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
    """
    text = text.strip()
    if not text:
        raise ConversationError("Please write a message first.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ConversationError(
            f"Please keep your message under {MAX_MESSAGE_LENGTH} characters."
        )
    with transaction.atomic():
        locked = _lock(conversation)
        if locked.status != Conversation.Status.ACTIVE:
            raise ConversationError("This conversation has ended.")
        if locked.awaiting_agent_reply:
            raise ConversationError("Please wait for the agent's reply.")
        Message.objects.create(conversation=locked, role=Message.Role.USER, text=text)
        _mark_turn_started(locked, now)
    _generate_and_save(locked, now)


def run_agent_turn(conversation: Conversation, now: datetime) -> None:
    """Retry the agent's turn of a conversation that waits for it.

    Refused while another request is still generating that turn. `LLMError`
    propagates and nothing is saved.
    """
    with transaction.atomic():
        locked = _lock(conversation)
        if not locked.awaiting_agent_reply:
            raise ConversationError("There is nothing to retry.")
        if agent_turn_in_progress(locked, now):
            raise ConversationError("The agent is still replying. Please wait.")
        _mark_turn_started(locked, now)
    _generate_and_save(locked, now)
    conversation.refresh_from_db()


def _generate_and_save(conversation: Conversation, now: datetime) -> None:
    """Generate one agent turn and save it; the turn marker must be set to `now`.

    A reply that is no longer needed when it arrives (the user ended the
    conversation meanwhile) is dropped, and its cost is not counted.
    """
    final = is_final_turn(conversation.user, conversation, now)
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
        )
    except Exception:
        # Free the conversation at once, so "Try again" works right away.
        _clear_turn_marker(conversation, now)
        raise

    with transaction.atomic():
        locked = _lock(conversation)
        if locked.awaiting_agent_reply:
            _save_agent_turn(locked, result, final, now)
        _clear_turn_marker(locked, now)
    conversation.refresh_from_db()


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
