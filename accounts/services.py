"""Account deletion: the one place with the rules (FR-013).

`delete_account` removes the user and everything the application keeps about them:
the ORM cascade from `User` takes the conversations, messages, mistakes and memory
fields (they live on the conversation) and the admin log entries the user wrote.
Two things are not reached by the cascade: the user's sessions (the session table
stores the id inside an encoded blob, not as a foreign key) and the admin log
entries ABOUT the user (`LogEntry.object_id` is text, not a foreign key).
`remove_sessions_and_log_entries_about_user` removes them. It is a `pre_delete`
receiver for `User`, connected in `AccountsConfig.ready`, so it runs on every ORM
deletion of a user (`Model.delete()` / `QuerySet.delete()`): the account page, the
admin's delete page and its "Delete selected" action (a queryset `delete()` sends
`pre_delete` for every user) and `manage.py shell`. Raw SQL (e.g. a database console)
and data migrations through a historical model skip it. It runs inside the
deletion's transaction, through the ORM, never raw SQL.

Not covered, because it is outside the application: copies held by OpenAI (up to 30
days for abuse monitoring) and database backups. See the PRD, NFR "Usuwanie danych".
"""

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

from .models import User


class AccountDeletionError(Exception):
    """A refused deletion; the message is shown to the user as it is."""


def remove_sessions_and_log_entries_about_user(
    sender: type[User], instance: User, **kwargs: object
) -> None:
    """Remove what the cascade from `User` misses: the user's sessions and the
    admin log entries about the user.

    A `pre_delete` receiver for `User`, so `instance.pk` is still set here (after
    `delete()` it is None).
    """
    user_id = str(instance.pk)
    # Expired sessions are included: they still hold the user id.
    for session in Session.objects.iterator():
        if session.get_decoded().get("_auth_user_id") == user_id:
            session.delete()
    LogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(User),
        object_id=user_id,
    ).delete()


@sensitive_variables("password")
def delete_account(user: User, password: str) -> None:
    """Delete `user` with all their data, after checking the password.

    Raises `AccountDeletionError` for a superuser or a wrong password; nothing is
    deleted then.
    """
    if user.is_superuser:
        raise AccountDeletionError(
            "The owner account cannot be deleted here. "
            "Delete it through /admin/ or manage.py."
        )
    if not user.check_password(password):
        raise AccountDeletionError("Incorrect password.")

    # `user.delete()` also removes the user's sessions and the admin log entries
    # about the user (the `pre_delete` receiver above).
    with transaction.atomic():
        user.delete()
