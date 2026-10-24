import importlib

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction

import talkaitive.settings
from accounts.models import PracticeLanguage, User
from conversations.models import Conversation, Message, Mistake
from conversations.services import surprise_topic_key
from conversations.topics import TOPICS, get_topic


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


@pytest.fixture
def lukasz(db) -> User:
    return User.objects.create_user("lukasz@example.de", "pass-12345-xyz")


def make_conversation(user: User, topic: str = "bakery", **fields: str) -> Conversation:
    return Conversation.objects.create(
        user=user,
        topic=topic,
        topic_title="Bakery",
        topic_scenario="You are a baker.",
        language=PracticeLanguage.GERMAN,
        **fields,
    )


@pytest.mark.django_db
def test_for_user_hides_other_users_conversations(anna: User, lukasz: User) -> None:
    anna_conversation = make_conversation(anna)

    assert list(Conversation.objects.for_user(anna)) == [anna_conversation]
    assert not Conversation.objects.for_user(lukasz).exists()


@pytest.mark.django_db
def test_second_active_conversation_of_same_user_raises(anna: User) -> None:
    make_conversation(anna)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_conversation(anna)


@pytest.mark.django_db
def test_new_active_conversation_after_ended_one_is_allowed(anna: User) -> None:
    make_conversation(anna, status=Conversation.Status.ENDED)

    active = make_conversation(anna)

    assert active.status == Conversation.Status.ACTIVE


@pytest.mark.django_db
def test_two_users_can_each_have_an_active_conversation(
    anna: User, lukasz: User
) -> None:
    make_conversation(anna)
    make_conversation(lukasz)

    assert Conversation.objects.filter(status=Conversation.Status.ACTIVE).count() == 2


@pytest.mark.django_db
def test_deleting_user_deletes_their_conversations_and_messages(
    anna: User, lukasz: User
) -> None:
    anna_conversation = make_conversation(anna)
    Message.objects.create(
        conversation=anna_conversation, role=Message.Role.USER, text="Hallo"
    )
    lukasz_conversation = make_conversation(lukasz)
    Message.objects.create(
        conversation=lukasz_conversation, role=Message.Role.USER, text="Hi"
    )

    anna.delete()

    assert list(Conversation.objects.all()) == [lukasz_conversation]
    assert Message.objects.count() == 1


def make_mistake(conversation: Conversation, position: int = 1) -> Mistake:
    return Mistake.objects.create(
        user=conversation.user,
        conversation=conversation,
        position=position,
        category=Mistake.Category.GRAMMAR,
        wrong="Ich habe gegangen",
        correct="Ich bin gegangen",
        sentence="Gestern ich habe gegangen nach Hause.",
        explanation="Gehen bildet das Perfekt mit sein.",
    )


@pytest.mark.django_db
def test_deleting_user_deletes_their_mistakes(anna: User, lukasz: User) -> None:
    make_mistake(make_conversation(anna))
    lukasz_mistake = make_mistake(make_conversation(lukasz))

    anna.delete()

    assert list(Mistake.objects.all()) == [lukasz_mistake]


@pytest.mark.django_db
def test_deleting_conversation_deletes_its_mistakes(anna: User) -> None:
    ended = make_conversation(anna, status=Conversation.Status.ENDED)
    make_mistake(ended)
    kept = make_mistake(make_conversation(anna))

    ended.delete()

    assert list(Mistake.objects.all()) == [kept]


@pytest.mark.django_db
def test_mistakes_for_user_hides_other_users_mistakes(anna: User, lukasz: User) -> None:
    anna_mistake = make_mistake(make_conversation(anna))

    assert list(Mistake.objects.for_user(anna)) == [anna_mistake]
    assert not Mistake.objects.for_user(lukasz).exists()
    assert not Mistake.objects.for_user(AnonymousUser()).exists()


@pytest.mark.django_db
def test_mistakes_are_ordered_by_position(anna: User) -> None:
    conversation = make_conversation(anna)
    second = make_mistake(conversation, position=2)
    first = make_mistake(conversation, position=1)

    assert list(conversation.mistakes.all()) == [first, second]
    assert first.occurrences == 1


@pytest.mark.django_db
def test_messages_are_ordered_by_creation(anna: User) -> None:
    conversation = make_conversation(anna)
    first = Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, text="Guten Tag!"
    )
    second = Message.objects.create(
        conversation=conversation, role=Message.Role.USER, text="Hallo"
    )

    assert list(conversation.messages.all()) == [first, second]


@pytest.mark.django_db
def test_awaiting_agent_reply(anna: User) -> None:
    conversation = make_conversation(anna)
    assert conversation.awaiting_agent_reply

    Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, text="Guten Tag!"
    )
    assert not conversation.awaiting_agent_reply

    Message.objects.create(
        conversation=conversation, role=Message.Role.USER, text="Hallo"
    )
    assert conversation.awaiting_agent_reply

    conversation.status = Conversation.Status.ENDED
    assert not conversation.awaiting_agent_reply


@pytest.mark.django_db
def test_practice_language_defaults_to_german(anna: User) -> None:
    anna.refresh_from_db()
    assert anna.practice_language == PracticeLanguage.GERMAN == "de"


def test_topics_have_20_unique_keys() -> None:
    keys = [topic.key for topic in TOPICS]
    assert len(keys) == 20
    assert len(set(keys)) == 20


def test_get_topic_returns_known_topic_and_none_for_unknown() -> None:
    topic = get_topic("bakery")
    assert topic is not None
    assert topic.key == "bakery"
    assert topic.title
    assert topic.scenario
    assert get_topic("does-not-exist") is None


ALL_KEYS = [topic.key for topic in TOPICS]


@pytest.fixture
def drawn_from(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The candidate lists `surprise_topic_key` draws from; it picks the first."""
    calls: list[list[str]] = []

    def choice(candidates: list[str]) -> str:
        calls.append(list(candidates))
        return candidates[0]

    monkeypatch.setattr("conversations.services.random.choice", choice)
    return calls


@pytest.mark.django_db
def test_surprise_without_history_draws_from_every_topic(
    anna: User, drawn_from: list[list[str]]
) -> None:
    assert surprise_topic_key(anna) == ALL_KEYS[0]
    assert drawn_from == [ALL_KEYS]


@pytest.mark.django_db
def test_surprise_skips_the_last_topic(anna: User, drawn_from: list[list[str]]) -> None:
    make_conversation(anna, topic="bakery")

    surprise_topic_key(anna)

    [candidates] = drawn_from
    assert len(candidates) == len(ALL_KEYS) - 1
    assert "bakery" not in candidates
    assert candidates == [key for key in ALL_KEYS if key != "bakery"]


@pytest.mark.django_db
def test_surprise_skips_only_the_newest_topic(
    anna: User, drawn_from: list[list[str]]
) -> None:
    make_conversation(anna, topic="dog-walk", status=Conversation.Status.ENDED)
    make_conversation(anna, topic="bakery")

    surprise_topic_key(anna)

    [candidates] = drawn_from
    assert "dog-walk" in candidates
    assert candidates == [key for key in ALL_KEYS if key != "bakery"]


@pytest.mark.django_db
def test_surprise_ignores_another_users_last_topic(
    anna: User, lukasz: User, drawn_from: list[list[str]]
) -> None:
    """Source: PRD Prywatność (Guardrails); the last topic is read through `for_user`."""
    make_conversation(anna, topic="dog-walk", status=Conversation.Status.ENDED)
    make_conversation(lukasz, topic="bakery")

    surprise_topic_key(anna)

    assert drawn_from == [[key for key in ALL_KEYS if key != "dog-walk"]]


@pytest.mark.django_db
def test_surprise_after_a_removed_topic_draws_from_every_topic(
    anna: User, drawn_from: list[list[str]]
) -> None:
    make_conversation(anna, topic="removed-topic")

    surprise_topic_key(anna)

    assert drawn_from == [ALL_KEYS]


def test_llm_model_has_a_price_entry() -> None:
    prices = settings.LLM_PRICES_USD_PER_MTOK[settings.LLM_MODEL]
    assert set(prices) == {"input", "cached_input", "output"}


def test_unpriced_llm_model_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "model-without-prices")
    try:
        with pytest.raises(ImproperlyConfigured):
            importlib.reload(talkaitive.settings)
    finally:
        monkeypatch.undo()
        importlib.reload(talkaitive.settings)
