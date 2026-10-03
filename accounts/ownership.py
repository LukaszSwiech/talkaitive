"""Pattern for per-user data (conversations, errors, memory).

Models that belong to a user inherit from `UserOwned`. Views read them only
through `Model.objects.for_user(request.user)`. These models are never
registered in the admin.
"""

from typing import Self

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import models


class UserOwnedQuerySet(models.QuerySet):
    def for_user(self, user: AbstractBaseUser | AnonymousUser) -> Self:
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)


class UserOwned(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )

    objects = UserOwnedQuerySet.as_manager()

    class Meta:
        abstract = True
