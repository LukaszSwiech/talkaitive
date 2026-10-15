"""Conversation screens. Thin: the turn logic lives in `services`.

Every conversation is fetched through `for_user`, so another user's conversation is
a 404. POST views always redirect (POST -> redirect -> GET).
"""

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.http import AuthenticatedHttpRequest

from . import services
from .budget import is_exhausted, next_reset
from .llm import LLMError
from .models import Conversation, Mistake
from .services import AnalysisNotNeeded, ConversationError
from .topics import TOPICS


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
    try:
        conversation = services.start_conversation(
            request.user, request.POST.get("topic", ""), timezone.now()
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
            "analysis_failed": services.analysis_failed(conversation, now),
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
