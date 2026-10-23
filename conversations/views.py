"""Conversation screens. Thin: the turn logic lives in `services`.

Every conversation is fetched through `for_user`, so another user's conversation is
a 404. POST views always redirect (POST -> redirect -> GET).
`ui_kitchen_sink` is a DEBUG-only page with every shared UI component in every state.
"""

from datetime import UTC, datetime

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.http import AuthenticatedHttpRequest

from . import services
from .budget import is_exhausted, limit_reached, next_reset
from .llm import LLMError
from .models import Conversation, Mistake
from .services import AnalysisNotNeeded, ConversationError
from .topics import TOPICS

# The kitchen sink's "now" for its reset notice; see ui_kitchen_sink.
KITCHEN_SINK_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def _get_conversation(request: AuthenticatedHttpRequest, pk: int) -> Conversation:
    return get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)


def _to_detail(conversation: Conversation) -> HttpResponse:
    return redirect("conversation_detail", pk=conversation.pk)


@require_GET
def home(request: AuthenticatedHttpRequest) -> HttpResponse:
    now = timezone.now()
    active = (
        Conversation.objects.for_user(request.user)
        .filter(status=Conversation.Status.ACTIVE)
        .first()
    )
    exhausted = active is None and is_exhausted(request.user, now)
    return render(
        request,
        "conversations/home.html",
        {
            "active_conversation": active,
            "exhausted": exhausted,
            "topics": TOPICS,
            "reset_at": next_reset(now),
            "budget_time_zone": settings.BUDGET_TIME_ZONE,
        },
    )


@require_POST
def conversation_start(request: AuthenticatedHttpRequest) -> HttpResponse:
    return _start(request, request.POST.get("topic", ""))


@require_POST
def conversation_start_random(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Start "Surprise me": a random topic, other than the user's last one."""
    return _start(request, services.surprise_topic_key(request.user))


def _start(request: AuthenticatedHttpRequest, topic_key: str) -> HttpResponse:
    try:
        conversation = services.start_conversation(
            request.user, topic_key, timezone.now()
        )
    except ConversationError as exc:
        messages.error(request, str(exc))
        return redirect("home")
    except LLMError:
        # The conversation exists and waits for the agent; its page offers a retry.
        active = (
            Conversation.objects.for_user(request.user)
            .filter(status=Conversation.Status.ACTIVE)
            .first()
        )
        return _to_detail(active) if active is not None else redirect("home")
    return _to_detail(conversation)


@require_GET
def conversation_detail(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    now = timezone.now()
    reset_at = (
        next_reset(conversation.ended_at)
        if conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
        and conversation.ended_at is not None
        else None
    )
    analysis_failed = services.analysis_failed(conversation, now)
    # A failed analysis is retried only after the reset once the limit is reached.
    analysis_retry_reset_at = (
        next_reset(now)
        if analysis_failed and limit_reached(request.user, now)
        else None
    )
    return render(
        request,
        "conversations/detail.html",
        {
            "conversation": conversation,
            # Not "messages": that name belongs to django.contrib.messages.
            "transcript": conversation.messages.all(),
            "awaiting_agent_reply": conversation.awaiting_agent_reply,
            "agent_turn_in_progress": services.agent_turn_in_progress(
                conversation, now
            ),
            "mistakes": Mistake.objects.for_user(request.user).filter(
                conversation=conversation
            ),
            "analysis_in_progress": services.analysis_in_progress(conversation, now),
            "analysis_failed": analysis_failed,
            "analysis_retry_reset_at": analysis_retry_reset_at,
            "reset_at": reset_at,
            "budget_time_zone": settings.BUDGET_TIME_ZONE,
            "max_message_length": services.MAX_MESSAGE_LENGTH,
        },
    )


@require_POST
def conversation_send(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    try:
        services.send_message(
            conversation, request.POST.get("text", ""), timezone.now()
        )
    except ConversationError as exc:
        messages.error(request, str(exc))
    except LLMError:
        pass  # The page shows the error and "Try again".
    return _to_detail(conversation)


@require_POST
def conversation_retry(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    try:
        services.run_agent_turn(conversation, timezone.now())
    except ConversationError as exc:
        messages.error(request, str(exc))
    except LLMError:
        pass  # The page still shows the error and "Try again".
    return _to_detail(conversation)


@require_POST
def conversation_end(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    services.end_conversation(conversation, Conversation.EndReason.USER, timezone.now())
    return _to_detail(conversation)


@require_POST
def conversation_analyze(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    try:
        services.analyze_conversation(conversation, timezone.now())
    except AnalysisNotNeeded:
        pass  # Usually a stale page that submitted itself; the page shows the state.
    except ConversationError as exc:
        messages.error(request, str(exc))
    except LLMError:
        pass  # The page shows the error and "Try again".
    return _to_detail(conversation)


@require_GET
def ui_kitchen_sink(request: AuthenticatedHttpRequest) -> HttpResponse:
    """Every component of `ui/css/components.css` in every state, for looking at the UI.

    Only in DEBUG; elsewhere the page does not exist. It reads no user data: the
    mistakes are unsaved samples rendered through the real `_mistakes.html`.
    """
    if not settings.DEBUG:
        raise Http404
    sample_mistakes = [
        Mistake(
            category=Mistake.Category.GRAMMAR,
            wrong="Ich habe gegangen",
            correct="Ich bin gegangen",
            sentence="Gestern habe ich in den Park gegangen.",
            explanation="Verbs of movement form the Perfekt with sein.",
            occurrences=2,
        ),
        Mistake(
            category=Mistake.Category.WORD_ORDER,
            wrong="weil ich habe keine Zeit",
            correct="weil ich keine Zeit habe",
            sentence="Ich komme nicht, weil ich habe keine Zeit.",
            explanation="In a clause with weil the verb goes to the end.",
        ),
    ]
    return render(
        request,
        "accounts/ui_kitchen_sink.html",
        {
            "topics": TOPICS[:3],
            "mistakes": sample_mistakes,
            # A fixed sample instant, not now(): the page stays the same every day,
            # so its screenshots (tests/e2e/ui-home.spec.ts) do too.
            "reset_at": next_reset(KITCHEN_SINK_NOW),
            "budget_time_zone": settings.BUDGET_TIME_ZONE,
        },
    )
