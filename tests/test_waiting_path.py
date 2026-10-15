"""The waiting path end to end: a hung provider, the error page and "Try again".

Nothing replaces our code here: the views, the services and `llm.generate_turn` run
as in production, and only the provider under the SDK is scripted
(`fake_provider`). Success is proven by the database, the number of requests the
provider got and the page the user sees, never by an HTTP status alone.
"""

from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import User
from conversations.models import Conversation, Message
from tests.fake_provider import FakeProvider

START_URL = "/conversations/start/"


@pytest.fixture(autouse=True)
def pinned_budget(settings) -> None:
    # Room for many turns, whatever the environment says.
    settings.DAILY_BUDGET_USD = Decimal("1.00")
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


@pytest.fixture
def anna_client(client: Client, anna: User) -> Client:
    client.force_login(anna)
    return client


def detail_url(conversation: Conversation) -> str:
    return f"/conversations/{conversation.pk}/"


def agent_texts(conversation: Conversation) -> list[str]:
    return list(
        conversation.messages.filter(role=Message.Role.ASSISTANT).values_list(
            "text", flat=True
        )
    )


@pytest.mark.django_db
def test_hung_provider_shows_try_again_and_the_retry_brings_the_reply(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    """Risk #1: the provider hangs at both attempts of a turn.

    The user keeps their message and gets "Try again"; one click makes one new
    request and the reply appears. A turn has 2 attempts (`LLM_MAX_RETRIES = 1`).
    """
    fake_provider.reply("Guten Tag! Was darf es sein?")
    anna_client.post(START_URL, {"topic": "bakery"})
    conversation = Conversation.objects.get(status=Conversation.Status.ACTIVE)
    assert agent_texts(conversation) == ["Guten Tag! Was darf es sein?"]
    # The opening turn took one request; count the message's requests from here.
    before_message = len(fake_provider.requests)

    fake_provider.hang(times=2)
    failed = anna_client.post(
        f"/conversations/{conversation.pk}/messages/",
        {"text": "Zwei Brötchen, bitte."},
        follow=True,
    )

    conversation.refresh_from_db()
    assert len(fake_provider.requests) - before_message == 2
    assert fake_provider.read_timeouts[before_message:] == [30, 30]
    assert list(conversation.messages.values_list("role", "text")) == [
        ("assistant", "Guten Tag! Was darf es sein?"),
        ("user", "Zwei Brötchen, bitte."),
    ]
    assert conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    page = failed.content.decode()
    assert "Zwei Brötchen, bitte." in page
    assert "The agent could not reply" in page
    assert f'action="/conversations/{conversation.pk}/retry/"' in page
    assert "Try again" in page
    # Not stuck in "Agent is typing": that state reloads the page by itself.
    # (base.html always carries a hidden "Agent is typing" overlay for JS.)
    assert 'http-equiv="refresh"' not in page

    fake_provider.reply("Gerne, zwei Brötchen. Sonst noch etwas?")
    retried = anna_client.post(f"/conversations/{conversation.pk}/retry/", follow=True)

    conversation.refresh_from_db()
    # The retry is exactly one new request: 2 for the hung message, then 3.
    assert len(fake_provider.requests) - before_message == 3
    assert agent_texts(conversation) == [
        "Guten Tag! Was darf es sein?",
        "Gerne, zwei Brötchen. Sonst noch etwas?",
    ]
    assert not conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    assert retried.redirect_chain[-1][0] == detail_url(conversation)
    page = retried.content.decode()
    assert "Gerne, zwei Brötchen. Sonst noch etwas?" in page
    assert "Try again" not in page
    assert "The agent could not reply" not in page


# --- empty agent reply ----------------------------------------------------------
#
# Oracle: test-plan.md §2 risk #1 guidance ("empty result -> message and Try
# again") and decision P2 of testing-waiting-path-recovery (plan, 2026-10-15): a
# blank reply is a failed turn; nothing is saved and the page offers "Try again".

BLANK_REPLY = " \n\t "


def assert_waits_for_retry(page: str, conversation: Conversation) -> None:
    assert "The agent could not reply" in page
    assert f'action="/conversations/{conversation.pk}/retry/"' in page
    assert "Try again" in page


@pytest.mark.django_db
def test_blank_reply_to_a_message_shows_try_again_and_the_retry_brings_the_reply(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    fake_provider.reply("Guten Tag! Was darf es sein?")
    anna_client.post(START_URL, {"topic": "bakery"})
    conversation = Conversation.objects.get(status=Conversation.Status.ACTIVE)
    before_message = len(fake_provider.requests)

    fake_provider.reply(BLANK_REPLY)
    failed = anna_client.post(
        f"/conversations/{conversation.pk}/messages/",
        {"text": "Ein Brot, bitte."},
        follow=True,
    )

    conversation.refresh_from_db()
    assert agent_texts(conversation) == ["Guten Tag! Was darf es sein?"]
    assert list(conversation.messages.values_list("role", flat=True)) == [
        "assistant",
        "user",
    ]
    assert conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    assert_waits_for_retry(failed.content.decode(), conversation)

    fake_provider.reply("Gerne, ein Brot.")
    retried = anna_client.post(f"/conversations/{conversation.pk}/retry/", follow=True)

    conversation.refresh_from_db()
    # Counted from after the opening turn: 1 request with the blank reply (a 200,
    # so the SDK does not retry it) + 1 request for "Try again" = 2.
    assert len(fake_provider.requests) - before_message == 2
    assert agent_texts(conversation) == [
        "Guten Tag! Was darf es sein?",
        "Gerne, ein Brot.",
    ]
    assert not conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    page = retried.content.decode()
    assert "Gerne, ein Brot." in page
    assert "Try again" not in page


@pytest.mark.django_db
def test_blank_opening_reply_leaves_the_conversation_waiting_for_retry(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    fake_provider.reply(BLANK_REPLY)

    started = anna_client.post(START_URL, {"topic": "bakery"}, follow=True)

    conversation = Conversation.objects.get()
    assert started.redirect_chain[-1][0] == detail_url(conversation)
    assert not conversation.messages.exists()
    assert conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    assert_waits_for_retry(started.content.decode(), conversation)

    fake_provider.reply("Guten Tag!")
    retried = anna_client.post(f"/conversations/{conversation.pk}/retry/", follow=True)

    conversation.refresh_from_db()
    assert len(fake_provider.requests) == 2
    assert agent_texts(conversation) == ["Guten Tag!"]
    assert not conversation.awaiting_agent_reply
    assert "Guten Tag!" in retried.content.decode()
    assert "Try again" not in retried.content.decode()
