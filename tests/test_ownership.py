import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group

from accounts.models import User as AccountsUser
from tests.ownership_testapp.models import OwnedNote

User = get_user_model()

ADMIN_ALLOWED_MODELS = {AccountsUser, Group}


@pytest.fixture
def anna(db):
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


@pytest.fixture
def lukasz(db):
    return User.objects.create_user("lukasz@example.de", "pass-12345-xyz")


@pytest.mark.django_db
def test_for_user_returns_only_own_notes(anna, lukasz) -> None:
    anna_note = OwnedNote.objects.create(user=anna, text="Annas Notiz")
    lukasz_note = OwnedNote.objects.create(user=lukasz, text="Lukasz Notiz")

    assert list(OwnedNote.objects.for_user(anna)) == [anna_note]
    assert list(OwnedNote.objects.for_user(lukasz)) == [lukasz_note]


@pytest.mark.django_db
def test_for_user_anonymous_returns_nothing(anna) -> None:
    OwnedNote.objects.create(user=anna, text="Annas Notiz")

    assert not OwnedNote.objects.for_user(AnonymousUser()).exists()


@pytest.mark.django_db
def test_deleting_user_deletes_only_their_notes(anna, lukasz) -> None:
    OwnedNote.objects.create(user=anna, text="Annas Notiz")
    lukasz_note = OwnedNote.objects.create(user=lukasz, text="Lukasz Notiz")

    anna.delete()

    assert list(OwnedNote.objects.all()) == [lukasz_note]


def test_admin_registry_has_only_allowed_models() -> None:
    registered = set(admin.site._registry)
    assert registered <= ADMIN_ALLOWED_MODELS, (
        f"Per-user data must not be registered in the admin: "
        f"{registered - ADMIN_ALLOWED_MODELS}"
    )
