"""Conversation flow: starting, sending, the agent's turn and ending.

Views stay thin and call these functions. The model call (`generate_turn`) always
runs outside a database transaction; the agent's reply is saved in a short
transaction that first re-checks, under a row lock, that the conversation still
waits for it (a parallel send or retry may have answered already).
"""

from datetime import datetime

from django.db import IntegrityError, transaction

from accounts.models import User

from .budget import is_exhausted, is_final_turn, turn_cost
from .llm import TurnResult, generate_turn
from .models import Conversation, Message
from .topics import Topic, get_topic


class ConversationError(Exception):
    """A refused action; the message is shown to the user as it is."""


def _lock(conversation: Conversation) -> Conversation:
    """Re-read the conversation with a row lock; call inside `transaction.atomic`."""
    return (
        Conversation.objects.for_user(conversation.user)
        .select_for_update()
        .get(pk=conversation.pk)
    )


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
            )
    except IntegrityError:
        raise ConversationError(
            "You already have a conversation in progress."
        ) from None
    run_agent_turn(conversation, now)
    return conversation


def send_message(conversation: Conversation, text: str, now: datetime) -> None:
    """Save the user's message and get the agent's reply.

    Only for an active conversation that does not wait for the agent; the check and
    the save happen under a row lock, so a double submit cannot save two messages.
    """
    text = text.strip()
    if not text:
        raise ConversationError("Please write a message first.")
    with transaction.atomic():
        locked = _lock(conversation)
        if locked.status != Conversation.Status.ACTIVE:
            raise ConversationError("This conversation has ended.")
        if locked.awaiting_agent_reply:
            raise ConversationError("Please wait for the agent's reply.")
        Message.objects.create(conversation=locked, role=Message.Role.USER, text=text)
    run_agent_turn(locked, now)


def run_agent_turn(conversation: Conversation, now: datetime) -> None:
    """Generate and save one agent turn; end the conversation when needed.

    `LLMError` propagates and nothing is saved. A reply that is no longer needed
    when it arrives (another request already answered) is dropped, and its cost is
    not counted.
    """
    if not conversation.awaiting_agent_reply:
        raise ConversationError("There is nothing to retry.")
    user = conversation.user
    final = is_final_turn(user, conversation, now)
    history = list(conversation.messages.values_list("role", "text"))
    # The topic comes from the conversation's own copy, not from TOPICS.
    topic = Topic(
        key=conversation.topic,
        title=conversation.topic_title,
        scenario=conversation.topic_scenario,
    )
    result = generate_turn(
        topic=topic,
        language=conversation.language,
        history=history,
        final_turn=final,
    )

    with transaction.atomic():
        locked = _lock(conversation)
        if locked.awaiting_agent_reply:
            _save_agent_turn(locked, result, final, now)
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
