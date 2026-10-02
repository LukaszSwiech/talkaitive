import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client

User = get_user_model()


@pytest.fixture
def admin_client(db) -> Client:
    User.objects.create_superuser("boss@example.de", "pass-12345-xyz")
    client = Client()
    assert client.login(username="boss@example.de", password="pass-12345-xyz")
    return client


@pytest.mark.django_db
def test_create_user_lowercases_email() -> None:
    user = User.objects.create_user("Anna@Example.DE", "pass-12345-xyz")
    assert user.email == "anna@example.de"


@pytest.mark.django_db
def test_duplicate_email_different_case_raises() -> None:
    User.objects.create_user("anna@example.de", "pass-12345-xyz")
    with pytest.raises(IntegrityError):
        User.objects.create_user("ANNA@example.de", "pass-12345-xyz")


@pytest.mark.django_db
def test_get_by_natural_key_is_case_insensitive() -> None:
    user = User.objects.create_user("anna@example.de", "pass-12345-xyz")
    assert User.objects.get_by_natural_key("ANNA@example.de") == user


@pytest.mark.django_db
def test_create_superuser_sets_flags() -> None:
    user = User.objects.create_superuser("root@example.de", "pass-12345-xyz")
    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_createsuperuser_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "pass-12345-xyz")
    call_command("createsuperuser", interactive=False, email="Cmd@example.de")
    user = User.objects.get(email="cmd@example.de")
    assert user.is_superuser
    assert user.check_password("pass-12345-xyz")


@pytest.mark.django_db
def test_admin_pages_load_and_add_creates_lowercase_user(admin_client: Client) -> None:
    assert admin_client.get("/admin/accounts/user/").status_code == 200
    assert admin_client.get("/admin/accounts/user/add/").status_code == 200

    response = admin_client.post(
        "/admin/accounts/user/add/",
        {
            "email": "Neu@Example.DE",
            "usable_password": "true",
            "password1": "pass-12345-xyz",
            "password2": "pass-12345-xyz",
        },
    )
    assert response.status_code == 302
    assert User.objects.filter(email="neu@example.de").exists()


@pytest.mark.django_db
def test_admin_add_duplicate_email_shows_form_error(admin_client: Client) -> None:
    User.objects.create_user("anna@example.de", "pass-12345-xyz")
    count = User.objects.count()

    response = admin_client.post(
        "/admin/accounts/user/add/",
        {
            "email": "ANNA@example.de",
            "usable_password": "true",
            "password1": "pass-12345-xyz",
            "password2": "pass-12345-xyz",
        },
    )
    assert response.status_code == 200
    assert response.context["adminform"].form.errors
    assert User.objects.count() == count
