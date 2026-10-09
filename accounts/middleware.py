"""Signed-in pages stay out of the browser's cache.

Without this, Back after logging out or deleting the account can show the previous
page (the email, a whole conversation) from the cache without asking the server,
which matters on a shared computer (PRD, NFR "Prywatność").
"""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.utils.cache import add_never_cache_headers


class NeverCacheSignedInMiddleware:
    """Send never_cache headers (no-store, private) on every signed-in response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
