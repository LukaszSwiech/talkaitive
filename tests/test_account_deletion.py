import pytest
from django.apps import apps
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import models
from django.test import Client
from django.utils import timezone

from accounts.models import User
from conversations.models import Conversation, Message, Mistake
from tests.ownership_testapp.models import OwnedNote

PASSWORD = "pass-12345-xyz"
DELETE_URL = "/account/delete/"


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", PASSWORD)


@pytest.fixture
def lukasz(db) -> User:
    return User.objects.create_user("lukasz@example.de", PASSWORD)


@pytest.fixture
def owner(db) -> User:
    return User.objects.create_superuser("owner@example.de", PASSWORD)


def make_analysed_conversation(user: User) -> Conversation:
    """An ended, analysed conversation with messages, a mistake and memory fields."""
    conversation = Conversation.objects.create(
        user=user,
        topic="bakery",
        topic_title="At the bakery",
        topic_scenario="You buy bread.",
        memory_prompt="Earlier: the learner has a dog called Rex.",
        language="de",
        status=Conversation.Status.ENDED,
        end_reason=Conversation.EndReason.USER,
        ended_at=timezone.now(),
        analyzed_at=timezone.now(),
        learner_facts=["Has a dog called Rex."],
        scene_notes=["Talked about rye bread."],
    )
    Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, text="Guten Tag!"
    )
    Message.objects.create(
        conversation=conversation, role=Message.Role.USER, text="Ich habe Brot kaufen."
    )
    Mistake.objects.create(
        user=user,
        conversation=conversation,
        position=1,
        category=Mistake.Category.GRAMMAR,
        wrong="habe Brot kaufen",
        correct="möchte Brot kaufen",
        sentence="Ich habe Brot kaufen.",
        explanation="Use a modal verb.",
    )
    return conversation


def make_log_entry(author: User, about: User) -> LogEntry:
    return LogEntry.objects.create(
        user=author,
        content_type=ContentType.objects.get_for_model(User),
        object_id=str(about.pk),
        object_repr=str(about),
        action_flag=CHANGE,
        change_message="Changed.",
    )


def login_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_deleting_account_removes_all_data_of_that_user_only(
    anna: User, lukasz: User
) -> None:
    make_analysed_conversation(anna)
    lukasz_conversation = make_analysed_conversation(lukasz)

    response = login_client(anna).post(DELETE_URL, {"password": PASSWORD})

    assert response.status_code == 302
    assert not User.objects.filter(pk=anna.pk).exists()
    assert Conversation.objects.count() == 1
    assert Message.objects.count() == 2
    assert Mistake.objects.count() == 1
    assert list(Conversation.objects.values_list("pk", flat=True)) == [
        lukasz_conversation.pk
    ]
    lukasz_conversation.refresh_from_db()
    assert lukasz_conversation.user == lukasz
    assert lukasz_conversation.memory_prompt
    assert lukasz_conversation.learner_facts == ["Has a dog called Rex."]
    assert lukasz_conversation.scene_notes == ["Talked about rye bread."]
    assert User.objects.filter(pk=lukasz.pk).exists()


def user_data_models() -> set[type[models.Model]]:
    """`User` and every model whose rows deleting a user removes by CASCADE."""
    reached: set[type[models.Model]] = {User}
    grew = True
    while grew:
        grew = False
        for model in apps.get_models():
            if model in reached:
                continue
            for field in model._meta.get_fields():
                if (
                    field.concrete
                    and field.is_relation
                    and field.related_model in reached
                    and field.remote_field.on_delete is models.CASCADE
                ):
                    reached.add(model)
                    grew = True
                    break
    return reached


def test_every_relation_to_user_data_is_known_and_cascades() -> None:
    user_data = user_data_models()
    found: dict[tuple[type[models.Model], str], models.Field] = {}
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if field.auto_created or not field.is_relation:
                continue
            if field.related_model in user_data and (
                field.many_to_one or field.one_to_one or field.many_to_many
            ):
                found[(model, field.name)] = field

    expected = {
        (Conversation, "user"),
        (Mistake, "user"),
        (Mistake, "conversation"),
        (Message, "conversation"),
        (LogEntry, "user"),
        (OwnedNote, "user"),
    }
    assert set(found) == expected, (
        "A model has a relation to user data (User or a model deleted with it) "
        "that deleting an account does not know about. Check that its rows "
        "disappear with the account (ON DELETE CASCADE, or removal in "
        "accounts/services.py), cover it in tests/test_account_deletion.py, then "
        f"add it to the list above: {set(found) ^ expected}"
    )
    for (model, name), field in found.items():
        if field.many_to_many:
            # No on_delete: deleting either side removes only the link rows.
            continue
        assert field.remote_field.on_delete is models.CASCADE, (
            f"{model.__name__}.{name} must use on_delete=CASCADE so that deleting "
            "an account removes these rows."
        )


@pytest.mark.django_db
def test_deleting_account_ends_all_sessions_of_that_user_only(
    anna: User, lukasz: User
) -> None:
    first, second, other = login_client(anna), login_client(anna), login_client(lukasz)
    assert Session.objects.count() == 3

    first.post(DELETE_URL, {"password": PASSWORD})

    remaining = [s.get_decoded().get("_auth_user_id") for s in Session.objects.all()]
    assert str(anna.pk) not in remaining
    assert remaining == [str(lukasz.pk)]
    response = second.get("/")
    assert response.status_code == 302
    assert response["Location"] == "/login/?next=/"
    assert other.get("/").status_code == 200


@pytest.mark.django_db
def test_deleting_account_removes_admin_log_entries_about_that_user(
    anna: User, lukasz: User, owner: User
) -> None:
    make_log_entry(owner, about=anna)
    about_lukasz = make_log_entry(owner, about=lukasz)

    login_client(anna).post(DELETE_URL, {"password": PASSWORD})

    assert list(LogEntry.objects.all()) == [about_lukasz]


@pytest.mark.django_db
def test_successful_deletion_logs_out_and_shows_message(anna: User) -> None:
    client = login_client(anna)

    response = client.post(DELETE_URL, {"password": PASSWORD})

    assert response.status_code == 302
    assert response["Location"] == "/login/"
    assert "_auth_user_id" not in client.session
    # Only logout() deletes the session cookie; the service alone leaves it behind.
    assert response.cookies["sessionid"].value == ""
    page = client.get("/login/")
    assert "Your account has been deleted." in page.content.decode()


@pytest.mark.django_db
def test_wrong_password_keeps_account_and_data(anna: User) -> None:
    make_analysed_conversation(anna)
    client = login_client(anna)

    response = client.post(DELETE_URL, {"password": "wrong-pass"})

    assert response.status_code == 302
    assert response["Location"] == DELETE_URL
    assert User.objects.filter(pk=anna.pk).exists()
    assert Conversation.objects.filter(user=anna).exists()
    assert Mistake.objects.filter(user=anna).exists()
    assert client.session["_auth_user_id"] == str(anna.pk)
    page = client.get(DELETE_URL)
    assert "Incorrect password." in page.content.decode()


@pytest.mark.django_db
def test_missing_password_is_refused(anna: User) -> None:
    response = login_client(anna).post(DELETE_URL)

    assert response.status_code == 302
    assert response["Location"] == DELETE_URL
    assert User.objects.filter(pk=anna.pk).exists()


@pytest.mark.django_db
def test_superuser_page_has_no_password_field(owner: User) -> None:
    response = login_client(owner).get(DELETE_URL)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="password"' not in content
    assert "owner account" in content


@pytest.mark.django_db
def test_superuser_cannot_delete_account_even_with_correct_password(
    owner: User,
) -> None:
    client = login_client(owner)

    response = client.post(DELETE_URL, {"password": PASSWORD})

    assert response.status_code == 302
    assert response["Location"] == DELETE_URL
    assert User.objects.filter(pk=owner.pk).exists()
    page = client.get(DELETE_URL)
    assert "The owner account cannot be deleted here." in page.content.decode()


@pytest.mark.django_db
def test_regular_user_page_has_password_field_and_openai_notice(anna: User) -> None:
    response = login_client(anna).get(DELETE_URL)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="password"' in content
    assert "OpenAI" in content


@pytest.mark.django_db
def test_anonymous_is_redirected_to_login(client: Client) -> None:
    response = client.get(DELETE_URL)

    assert response.status_code == 302
    assert response["Location"] == "/login/?next=/account/delete/"


@pytest.mark.django_db
def test_home_links_to_account_deletion(anna: User) -> None:
    home = login_client(anna).get("/")

    assert 'href="/account/delete/"' in home.content.decode()
