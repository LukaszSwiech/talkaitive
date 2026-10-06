from typing import Any

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def canonical_email(email: str) -> str:
    return email.strip().lower()


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(
        self, email: str, password: str | None, **extra_fields: Any
    ) -> "User":
        if not email:
            raise ValueError("The email must be set.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email: str | None) -> "User":
        return self.get(email=canonical_email(email or ""))


class PracticeLanguage(models.TextChoices):
    ENGLISH = "en", "English"
    GERMAN = "de", "German"


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email address", unique=True)
    # db_default keeps a DEFAULT in the column, so reverting the code without
    # reverting the migration does not break creating users (NOT NULL).
    practice_language = models.CharField(
        max_length=2,
        choices=PracticeLanguage,
        default="de",
        db_default="de",
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="accounts_user_email_ci_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def _normalize_email(self) -> None:
        self.email = canonical_email(self.email)

    def clean(self) -> None:
        super().clean()
        self._normalize_email()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalize_email()
        super().save(*args, **kwargs)
