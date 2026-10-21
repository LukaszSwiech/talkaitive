"""Account screens. Thin: the deletion rules live in `services`.

Login and logout use Django's LoginView and LogoutView (urls.py). The home page lives
in `conversations.views.home`. POST views always redirect (POST -> redirect -> GET).
"""

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .http import AuthenticatedHttpRequest
from .services import AccountDeletionError, delete_account


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
