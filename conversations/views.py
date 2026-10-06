"""Conversation screens. Thin: the turn logic lives in `services`.

Every conversation is fetched through `for_user`, so another user's conversation is
a 404. POST views always redirect (POST -> redirect -> GET).
"""

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import services
from .budget import is_exhausted, next_reset
from .llm import LLMError
from .models import Conversation
from .services import ConversationError
from .topics import TOPICS


def _get_conversation(request: HttpRequest, pk: int) -> Conversation:
    return get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)


def _to_detail(conversation: Conversation) -> HttpResponse:
    return redirect("conversation_detail", pk=conversation.pk)


@require_GET
def home(request: HttpRequest) -> HttpResponse:
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
def conversation_start(request: HttpRequest) -> HttpResponse:
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
def conversation_detail(request: HttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
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
            "reset_at": reset_at,
            "budget_time_zone": settings.BUDGET_TIME_ZONE,
        },
    )


@require_POST
def conversation_send(request: HttpRequest, pk: int) -> HttpResponse:
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
def conversation_retry(request: HttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    try:
        services.run_agent_turn(conversation, timezone.now())
    except ConversationError as exc:
        messages.error(request, str(exc))
    except LLMError:
        pass  # The page still shows the error and "Try again".
    return _to_detail(conversation)


@require_POST
def conversation_end(request: HttpRequest, pk: int) -> HttpResponse:
    conversation = _get_conversation(request, pk)
    services.end_conversation(conversation, Conversation.EndReason.USER, timezone.now())
    return _to_detail(conversation)
