"""Account screens. Thin: the deletion rules live in `services`.

Login and logout use Django's LoginView and LogoutView (urls.py). The home page lives
in `conversations.views.home`. POST views always redirect (POST -> redirect -> GET).
`ui_kitchen_sink` is a DEBUG-only page with every shared UI component in every state.
"""

from datetime import UTC, datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from conversations.budget import next_reset
from conversations.models import Mistake
from conversations.topics import TOPICS

from .http import AuthenticatedHttpRequest
from .services import AccountDeletionError, delete_account

# The kitchen sink's "now" for its reset notice; see ui_kitchen_sink.
KITCHEN_SINK_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


@sensitive_post_parameters("password")
@require_http_methods(["GET", "POST"])
def account_delete(request: AuthenticatedHttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(
            request,
            "accounts/account_delete.html",
            {"can_delete": not request.user.is_superuser},
        )
    try:
        delete_account(request.user, request.POST.get("password", ""))
    except AccountDeletionError as exc:
        messages.error(request, str(exc))
        return redirect("account_delete")
    # The service already deleted the session row, but logout() still has to run:
    # it makes request.user anonymous for the rest of this request and empties the
    # session, so the stale session cookie is deleted and a later write would start
    # a new session instead of failing on the deleted row (SessionInterrupted).
    logout(request)
    messages.success(request, "Your account has been deleted.")
    return redirect("login")


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
