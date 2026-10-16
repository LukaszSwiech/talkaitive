from django.apps import AppConfig
from django.db.models.signals import pre_delete


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        # Imported here: models cannot load before the app registry is ready.
        from .models import User
        from .services import remove_sessions_and_log_entries_about_user

        # Every ORM deletion of a user (the account page, the admin, the shell)
        # also removes their sessions and the admin log entries about them.
        pre_delete.connect(
            remove_sessions_and_log_entries_about_user,
            sender=User,
            dispatch_uid="accounts.remove_sessions_and_log_entries_about_user",
        )
