from collections.abc import Callable

import pytest
from django.apps import apps
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import models
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conversations.models import Conversation, LLMCharge, Message, Mistake
from tests.fakes import add_charge
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
        (LLMCharge, "user"),
        (LLMCharge, "conversation"),
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


# Decision for user data: deleted with the account by ON DELETE CASCADE.
CASCADE = "CASCADE"

# One deletion decision for every model of the project's own apps (not `django.*`).
# Written out by hand, never computed from the registry: the guard below compares
# the registry with this literal. The value is `CASCADE` (user data, deleted with
# the account; `User` is the root) or the reason why the model holds no user data.
MODEL_DECISIONS: dict[type[models.Model], str] = {
    User: CASCADE,
    Conversation: CASCADE,
    Message: CASCADE,
    Mistake: CASCADE,
    LLMCharge: CASCADE,
    OwnedNote: CASCADE,
}


def app_models() -> set[type[models.Model]]:
    """Every installed model whose app is not part of Django itself."""
    return {
        model
        for model in apps.get_models()
        if not model._meta.app_config.name.startswith("django.")
    }


def test_every_app_model_has_a_deletion_decision() -> None:
    """Every model of the project's apps has a decision in `MODEL_DECISIONS`.

    A new model without a decision fails here, so nobody adds a data model without
    deciding what deleting an account does with it. A model decided as `CASCADE`
    must really be reached by the cascade from `User`.
    Source: PRD FR-013 and NFR "Usuwanie danych" (deleting the account removes all
    of the user's data); test-plan.md §2 #6 (a new data model without a conscious
    decision fails the test).
    """
    found = app_models()

    assert found == set(MODEL_DECISIONS), (
        "Models of the project's apps without a deletion decision (or decisions "
        f"for models that are gone): {sorted(m.__name__ for m in found ^ set(MODEL_DECISIONS))}. "
        "If the model holds user data, give it a ForeignKey with on_delete=CASCADE "
        "to User (or to a model deleted with it), add it to MODEL_DECISIONS as "
        "CASCADE and add a factory to FACTORIES below. Otherwise add it to "
        "MODEL_DECISIONS with the reason why it holds no user data."
    )
    not_reached = {
        model.__name__
        for model, decision in MODEL_DECISIONS.items()
        if decision == CASCADE and model not in user_data_models()
    }
    assert not_reached == set(), (
        f"Decided as CASCADE, but deleting a user does not cascade to them: "
        f"{sorted(not_reached)}. Give each a ForeignKey with on_delete=CASCADE to "
        "User or to a model deleted with it."
    )
    no_reason = {
        model.__name__
        for model, decision in MODEL_DECISIONS.items()
        if decision != CASCADE and not decision.strip()
    }
    assert no_reason == set(), (
        f"A model that holds no user data needs the reason written out: {no_reason}"
    )


def make_conversation_rows(user: User) -> list[models.Model]:
    return [make_analysed_conversation(user)]


def make_message_rows(user: User) -> list[models.Model]:
    return list(make_analysed_conversation(user).messages.all())


def make_mistake_rows(user: User) -> list[models.Model]:
    return list(make_analysed_conversation(user).mistakes.all())


def make_llm_charge_rows(user: User) -> list[models.Model]:
    return [add_charge(make_analysed_conversation(user), "0.03", timezone.now())]


def make_owned_note_rows(user: User) -> list[models.Model]:
    return [OwnedNote.objects.create(user=user, text="A note.")]


def make_log_entry_rows(user: User) -> list[models.Model]:
    # Written BY the user about their own conversation, not about the user: the
    # service removes entries about the user by hand, so only the CASCADE on
    # `LogEntry.user` can remove this one.
    conversation = make_analysed_conversation(user)
    entry = LogEntry.objects.create(
        user=user,
        content_type=ContentType.objects.get_for_model(Conversation),
        object_id=str(conversation.pk),
        object_repr=str(conversation),
        action_flag=CHANGE,
        change_message="Changed.",
    )
    return [entry]


# For every model of user data: builds at least one row of that model for the given
# user and returns those rows. Written out by hand; the guard below compares its
# keys with `user_data_models()`.
FACTORIES: dict[type[models.Model], Callable[[User], list[models.Model]]] = {
    User: lambda user: [user],
    Conversation: make_conversation_rows,
    Message: make_message_rows,
    Mistake: make_mistake_rows,
    LLMCharge: make_llm_charge_rows,
    OwnedNote: make_owned_note_rows,
    LogEntry: make_log_entry_rows,
}


def test_every_user_data_model_has_a_factory() -> None:
    """Every model deleted with a user (the CASCADE closure) is in `FACTORIES`.

    A new model of user data without a factory fails here, so the "no row is left"
    test below always covers every such model.
    Source: PRD FR-013 and NFR "Usuwanie danych"; test-plan.md §2 #6.
    """
    found = user_data_models()

    assert found == set(FACTORIES), (
        "Models deleted with a user without a factory in FACTORIES (or factories "
        f"for models no longer deleted with a user): "
        f"{sorted(m.__name__ for m in found ^ set(FACTORIES))}. Add a factory that "
        "builds at least one row of the model for the given user."
    )


@pytest.mark.django_db
def test_deleting_account_leaves_no_row_of_that_user_in_any_model(
    anna: User, lukasz: User
) -> None:
    """After Anna deletes her account no row of hers is left in any model of user
    data, and every row of Łukasz is still there.

    Source: PRD FR-013 and NFR "Usuwanie danych" (all of the user's data is removed
    from the app's database right after confirmation); PRD Guardrails (another
    user's data is not touched); test-plan.md §2 #6.
    """
    rows_of_anna = {model: make(anna) for model, make in FACTORIES.items()}
    rows_of_lukasz = {model: make(lukasz) for model, make in FACTORIES.items()}

    response = login_client(anna).post(DELETE_URL, {"password": PASSWORD})

    assert response.status_code == 302
    for model in FACTORIES:
        anna_pks = {row.pk for row in rows_of_anna[model]}
        lukasz_pks = {row.pk for row in rows_of_lukasz[model]}
        assert anna_pks and lukasz_pks, f"{model.__name__}: the factory built no rows"
        remaining = set(model._default_manager.values_list("pk", flat=True))
        assert remaining & anna_pks == set(), (
            f"{model.__name__}: rows of the deleted user are left"
        )
        assert lukasz_pks <= remaining, (
            f"{model.__name__}: rows of another user were deleted"
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


def delete_on_admin_delete_page(client: Client, user: User) -> HttpResponse:
    """The owner confirms on the user's "Delete" page in the admin."""
    return client.post(
        reverse("admin:accounts_user_delete", args=[user.pk]), {"post": "yes"}
    )


def delete_with_admin_bulk_action(client: Client, user: User) -> HttpResponse:
    """The owner ticks the user in the admin user list and confirms "Delete selected"."""
    return client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "delete_selected", "_selected_action": [user.pk], "post": "yes"},
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "delete_in_admin",
    [delete_on_admin_delete_page, delete_with_admin_bulk_action],
    ids=["delete-page", "bulk-delete-selected"],
)
def test_deleting_user_in_admin_removes_sessions_and_log_entries_about_them(
    delete_in_admin: Callable[[Client, User], HttpResponse],
    anna: User,
    lukasz: User,
    owner: User,
) -> None:
    """When the owner deletes Anna in `/admin/`, nothing about her is left: no
    session, no admin log entry about her (not even the entry about this deletion,
    whose text is her e-mail) and no row of her data. The sessions of Łukasz and the
    owner, Łukasz's data and the log entry about Łukasz stay.

    The admin never calls `delete_account`, so only cleanup that runs on every
    deletion of a `User` covers this path. Source: PRD FR-013 and NFR "Usuwanie
    danych" (all of the user's data is removed); test-plan.md §2 #6; the path was
    found in the research of testing-privacy-and-deletion-boundaries, §6.3.
    """
    rows_of_anna = {model: make(anna) for model, make in FACTORIES.items()}
    rows_of_lukasz = {model: make(lukasz) for model, make in FACTORIES.items()}
    make_log_entry(owner, about=anna)
    about_lukasz = make_log_entry(owner, about=lukasz)
    login_client(anna)
    login_client(lukasz)
    owner_client = login_client(owner)
    anna_id = str(anna.pk)

    response = delete_in_admin(owner_client, anna)

    assert response.status_code == 302
    assert not User.objects.filter(pk=anna.pk).exists()
    session_users = {
        s.get_decoded().get("_auth_user_id") for s in Session.objects.all()
    }
    assert session_users == {str(lukasz.pk), str(owner.pk)}, (
        "Sessions of the deleted user are left, or sessions of other users ended"
    )
    user_type = ContentType.objects.get_for_model(User)
    about_anna = [
        entry
        for entry in LogEntry.objects.all()
        if (entry.content_type_id == user_type.pk and entry.object_id == anna_id)
        or anna.email in entry.object_repr
    ]
    assert about_anna == [], (
        "Admin log entries about the deleted user are left (older ones or the "
        "entry about this deletion)"
    )
    assert LogEntry.objects.filter(pk=about_lukasz.pk).exists(), (
        "The admin log entry about another user was deleted"
    )
    for model in FACTORIES:
        anna_pks = {row.pk for row in rows_of_anna[model]}
        lukasz_pks = {row.pk for row in rows_of_lukasz[model]}
        assert anna_pks and lukasz_pks, f"{model.__name__}: the factory built no rows"
        remaining = set(model._default_manager.values_list("pk", flat=True))
        assert remaining & anna_pks == set(), (
            f"{model.__name__}: rows of the deleted user are left"
        )
        assert lukasz_pks <= remaining, (
            f"{model.__name__}: rows of another user were deleted"
        )


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


@pytest.mark.django_db
def test_home_account_deletion_link_is_below_the_top_bar(anna: User) -> None:
    """The link sits at the end of the page, away from "Log out" in the top bar."""
    content = login_client(anna).get("/").content.decode()

    assert content.index('href="/account/delete/"') > content.index("</header>")
