from .settings import *  # noqa: F403

# Fast hasher; tests do not need a secure one.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The manifest storage needs collectstatic; tests use plain static storage.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Throwaway app with a model used only to test the UserOwned pattern.
INSTALLED_APPS = [*INSTALLED_APPS, "tests.ownership_testapp"]  # noqa: F405
