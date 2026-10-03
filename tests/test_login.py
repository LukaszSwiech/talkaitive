import pytest
from django.test import Client

from accounts.models import User

PASSWORD = "pass-12345-xyz"


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", PASSWORD)


@pytest.mark.django_db
def test_anonymous_home_redirects_to_login(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/login/?next=/"


@pytest.mark.django_db
def test_anonymous_healthz_is_ok(client: Client) -> None:
    response = client.get("/healthz/")
    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_anonymous_login_page_loads(client: Client) -> None:
    assert client.get("/login/").status_code == 200


@pytest.mark.django_db
def test_anonymous_admin_is_not_served(client: Client) -> None:
    assert client.get("/admin/").status_code == 302


@pytest.mark.django_db
def test_login_is_case_insensitive_and_shows_email(client: Client, anna: User) -> None:
    response = client.post(
        "/login/", {"username": "Anna@Example.DE", "password": PASSWORD}
    )
    assert response.status_code == 302
    assert response["Location"] == "/"

    home = client.get("/")
    assert home.status_code == 200
    assert "anna@example.de" in home.content.decode()


@pytest.mark.django_db
def test_login_wrong_password_shows_error(client: Client, anna: User) -> None:
    response = client.post(
        "/login/", {"username": "anna@example.de", "password": "wrong-pass"}
    )
    assert response.status_code == 200
    assert response.context["form"].non_field_errors()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_inactive_user_cannot_log_in(client: Client, anna: User) -> None:
    anna.is_active = False
    anna.save()
    response = client.post(
        "/login/", {"username": "anna@example.de", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_logged_in_login_page_redirects_home(client: Client, anna: User) -> None:
    assert client.login(username="anna@example.de", password=PASSWORD)
    response = client.get("/login/")
    assert response.status_code == 302
    assert response["Location"] == "/"
