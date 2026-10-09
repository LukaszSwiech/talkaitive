"""Request types shared by the views of all apps."""

from django.http import HttpRequest

from .models import User


class AuthenticatedHttpRequest(HttpRequest):
    """A request behind LoginRequiredMiddleware: `user` is always a signed-in `User`."""

    user: User
