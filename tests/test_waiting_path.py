"""The waiting path end to end: a hung provider, the error page and "Try again".

Nothing replaces our code here: the views, the services and `llm.generate_turn` run
as in production, and only the provider under the SDK is scripted
(`fake_provider`). Success is proven by the database, the number of requests the
provider got and the page the user sees, never by an HTTP status alone.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from conversations import services
from conversations.llm import FoundMistake
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


# --- how long the waiting can last ----------------------------------------------
#
# Numbers written out by hand, never computed from `services`:
# - 120 s: the longest `Retry-After` the SDK honours (`MAX_RETRY_AFTER_DELAY` in
#   openai/_constants.py), pinned by
#   tests/test_llm.py::test_turn_honours_retry_after_of_exactly_120_s and
#   ::test_turn_does_not_retry_when_retry_after_exceeds_120_s.
# - 300 s: the Railway proxy cuts an HTTP request after 5 minutes
#   (docs.railway.com, "Specs & Limits", read 2026-10-15; decision P4).
# - 30 s margin on the "in progress" markers: decision P3 (2026-10-15).

SDK_MAX_RETRY_AFTER_SECONDS = 120
RAILWAY_PROXY_TIMEOUT_SECONDS = 300

# 1 attempt x 150 s (`LLM_ANALYSIS_TIMEOUT_SECONDS = 150`,
# `LLM_ANALYSIS_MAX_RETRIES = 0` in talkaitive/settings.py) + 0 x 120 s + 30 s.
ANALYSIS_MARKER_LIFETIME = timedelta(seconds=180)


@pytest.mark.parametrize(
    ("age", "in_progress"),
    [
        (ANALYSIS_MARKER_LIFETIME - timedelta(microseconds=1), True),
        (ANALYSIS_MARKER_LIFETIME, False),
    ],
    ids=["180s-minus-1us", "exactly-180s"],
)
def test_analysis_marker_lives_as_long_as_the_sdk_can_wait_plus_a_margin(
    age: timedelta, in_progress: bool
) -> None:
    """With the default settings, the analysis marker lives 180 s.

    Here, not in tests/test_analysis.py: that module overrides the analysis timeout
    for all its tests. Source: see `ANALYSIS_MARKER_LIFETIME`; test-plan §2 risk #1.
    """
    started = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    conversation = Conversation(analysis_started_at=started)

    assert services.analysis_in_progress(conversation, started + age) is in_progress


ANALYSIS_START = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("fields", "age", "failed"),
    [
        ({}, timedelta(0), False),
        ({"analysis_failed_at": ANALYSIS_START}, timedelta(0), True),
        ({"analysis_started_at": ANALYSIS_START}, ANALYSIS_MARKER_LIFETIME, True),
        (
            {"analysis_started_at": ANALYSIS_START},
            ANALYSIS_MARKER_LIFETIME - timedelta(microseconds=1),
            False,
        ),
        (
            {
                "analysis_started_at": ANALYSIS_START,
                "analysis_failed_at": ANALYSIS_START - timedelta(minutes=5),
            },
            timedelta(seconds=10),
            False,
        ),
        (
            {"analysis_started_at": ANALYSIS_START, "analyzed_at": ANALYSIS_START},
            ANALYSIS_MARKER_LIFETIME,
            False,
        ),
        (
            {"analysis_failed_at": ANALYSIS_START, "analyzed_at": ANALYSIS_START},
            timedelta(0),
            False,
        ),
    ],
    ids=[
        "never-started",
        "failure-recorded",
        "marker-expired-without-result",
        "marker-still-valid",
        "retry-in-progress-after-a-failure",
        "analysed-with-a-leftover-marker",
        "analysed-after-a-failure",
    ],
)
def test_analysis_failed_when_a_failure_was_recorded_or_the_marker_expired(
    fields: dict[str, datetime], age: timedelta, failed: bool
) -> None:
    """The analysis failed: no result, no live marker, and an attempt was made.

    An expired marker without a result means the worker died during the analysis;
    the page must then offer "Try again" instead of starting a new paid call by
    itself. A never-started analysis is not a failure: it still starts on its own.
    Source: decision P6 (plan testing-waiting-path-recovery, 2026-10-15); test-plan
    §2 risk #1; the 180 s lifetime: see `ANALYSIS_MARKER_LIFETIME`.
    """
    conversation = Conversation(**fields)

    assert services.analysis_failed(conversation, ANALYSIS_START + age) is failed


@pytest.mark.parametrize(
    ("timeout_setting", "retries_setting"),
    [
        ("LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES"),
        ("LLM_ANALYSIS_TIMEOUT_SECONDS", "LLM_ANALYSIS_MAX_RETRIES"),
    ],
    ids=["turn", "analysis"],
)
def test_longest_model_wait_fits_in_the_platforms_request_limit(
    settings, timeout_setting: str, retries_setting: str
) -> None:
    """A POST that waits for the model must end before the proxy cuts it.

    Cut by the proxy, the user gets a platform error page instead of our message
    and "Try again" (the class of the interview Q2 incident). The longest wait is
    every attempt hanging until its timeout plus the longest `Retry-After` before
    each retry (SDK behaviour pinned in tests/test_llm.py). Fails when someone
    raises a timeout or a retry count past the limit. Source: decision P4;
    test-plan §2 risk #1 (the timeout path: SDK client, gunicorn, Railway proxy).
    """
    timeout = getattr(settings, timeout_setting)
    retries = getattr(settings, retries_setting)

    longest_wait = timeout * (retries + 1) + retries * SDK_MAX_RETRY_AFTER_SECONDS

    assert longest_wait < RAILWAY_PROXY_TIMEOUT_SECONDS


@pytest.mark.django_db
def test_turn_after_a_503_with_retry_after_saves_and_shows_the_reply(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    """The provider asks to wait 56 s once; the SDK waits and the reply arrives.

    Source: test-plan §2 risk #1 (an error from the provider still ends with the
    reply or a message, in finite time).
    """
    fake_provider.reply("Guten Tag! Was darf es sein?")
    anna_client.post(START_URL, {"topic": "bakery"})
    conversation = Conversation.objects.get(status=Conversation.Status.ACTIVE)
    before_message = len(fake_provider.requests)

    fake_provider.fail(503, retry_after=56).reply("Gerne, drei Brezeln.")
    response = anna_client.post(
        f"/conversations/{conversation.pk}/messages/",
        {"text": "Drei Brezeln, bitte."},
        follow=True,
    )

    conversation.refresh_from_db()
    # The 503, then the SDK's one retry after sleeping the server's 56 s.
    assert len(fake_provider.requests) - before_message == 2
    assert fake_provider.sleeps == [56]
    assert agent_texts(conversation) == [
        "Guten Tag! Was darf es sein?",
        "Gerne, drei Brezeln.",
    ]
    assert not conversation.awaiting_agent_reply
    assert conversation.agent_turn_started_at is None
    page = response.content.decode()
    assert "Gerne, drei Brezeln." in page
    assert "Try again" not in page
    assert "The agent could not reply" not in page


# --- the analysis after the conversation ----------------------------------------
#
# Oracle: decision P6 (plan, 2026-10-15) and test-plan §2 risk #1: a failed or
# abandoned analysis ends with a message and "Try again", and the click really
# starts one new analysis whose list then appears on the page.

ANALYSIS_FAILED = "We could not prepare your list of mistakes. Please try again."

PERFEKT_MISTAKE = FoundMistake(
    message_number=1,
    category="grammar",
    wrong="habe gegangen",
    correct="bin gegangen",
    sentence="Ich habe gegangen.",
    explanation="Gehen takes sein in the Perfekt.",
)


def analysis_url(conversation: Conversation) -> str:
    return f"/conversations/{conversation.pk}/analysis/"


def auto_submit_form(conversation: Conversation) -> str:
    # The form itself: base.html's script also mentions `data-auto-submit`.
    return f'action="{analysis_url(conversation)}" data-auto-submit'


def ended_conversation(client: Client, fake_provider: FakeProvider) -> Conversation:
    """An ended conversation with one learner message, not analysed yet."""
    fake_provider.reply("Guten Tag! Was haben Sie gestern gemacht?")
    client.post(START_URL, {"topic": "bakery"})
    conversation = Conversation.objects.get(status=Conversation.Status.ACTIVE)
    fake_provider.reply("Ah, schön. Und dann?")
    client.post(
        f"/conversations/{conversation.pk}/messages/", {"text": "Ich habe gegangen."}
    )
    client.post(f"/conversations/{conversation.pk}/end/")
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ENDED
    return conversation


def assert_shows_the_list(page: str) -> None:
    assert "Your mistakes" in page
    assert "bin gegangen" in page
    assert "Gehen takes sein in the Perfekt." in page
    assert "Try again" not in page
    assert ANALYSIS_FAILED not in page


@pytest.mark.django_db
def test_expired_analysis_marker_shows_try_again_and_the_retry_brings_the_list(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    """The worker died during the analysis: the marker is 190 s old, no result.

    The page offers "Try again" (it does not start a paid call by itself); one
    click makes exactly one new request and shows the list.
    """
    conversation = ended_conversation(anna_client, fake_provider)
    Conversation.objects.filter(pk=conversation.pk).update(
        analysis_started_at=timezone.now() - timedelta(seconds=190)
    )
    before_retry = len(fake_provider.requests)

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert ANALYSIS_FAILED in page
    assert auto_submit_form(conversation) not in page

    fake_provider.analysis(mistakes=[PERFEKT_MISTAKE])
    retried = anna_client.post(analysis_url(conversation), follow=True)

    conversation.refresh_from_db()
    assert len(fake_provider.requests) - before_retry == 1
    assert conversation.analyzed_at is not None
    assert conversation.analysis_failed_at is None
    assert conversation.analysis_started_at is None
    assert list(conversation.mistakes.values_list("wrong", "correct")) == [
        ("habe gegangen", "bin gegangen")
    ]
    assert retried.redirect_chain[-1][0] == detail_url(conversation)
    assert_shows_the_list(retried.content.decode())


@pytest.mark.django_db
def test_hung_analysis_shows_try_again_and_the_retry_brings_the_list(
    anna_client: Client, fake_provider: FakeProvider
) -> None:
    """The provider hangs during the analysis (one attempt, no SDK retry).

    The page shows the message and "Try again"; the click with a working provider
    shows the list. Two analysis requests in total.
    """
    conversation = ended_conversation(anna_client, fake_provider)
    before_analysis = len(fake_provider.requests)

    fake_provider.hang()
    failed = anna_client.post(analysis_url(conversation), follow=True)

    conversation.refresh_from_db()
    assert len(fake_provider.requests) - before_analysis == 1
    assert conversation.analyzed_at is None
    assert conversation.analysis_failed_at is not None
    assert conversation.analysis_started_at is None
    page = failed.content.decode()
    assert ANALYSIS_FAILED in page
    assert f'action="{analysis_url(conversation)}"' in page
    assert auto_submit_form(conversation) not in page
    assert 'http-equiv="refresh"' not in page

    fake_provider.analysis(mistakes=[PERFEKT_MISTAKE])
    retried = anna_client.post(analysis_url(conversation), follow=True)

    conversation.refresh_from_db()
    assert len(fake_provider.requests) - before_analysis == 2
    assert conversation.analyzed_at is not None
    assert conversation.analysis_failed_at is None
    assert_shows_the_list(retried.content.decode())
