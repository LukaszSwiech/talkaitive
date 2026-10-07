from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import PracticeLanguage, User
from conversations import services
from conversations.llm import AnalysisResult, FoundMistake, LLMError, TurnResult
from conversations.models import Conversation, Message, Mistake
from conversations.topics import get_topic

START_URL = "/conversations/start/"

Outcome = TurnResult | Exception | Callable[..., TurnResult]


def make_result(reply: str = "Guten Tag!", end: bool = False) -> TurnResult:
    # With the test prices: 600 * 2.00 + 400 * 0.50 + 200 * 10.00 = 3400 / 1M.
    return TurnResult(
        reply=reply,
        end_conversation=end,
        model="test-model",
        input_tokens=1000,
        cached_input_tokens=400,
        output_tokens=200,
    )


TURN_COST = Decimal("0.0034")


class FakeGenerateTurn:
    """Stands in for `llm.generate_turn`; nothing in these tests touches the network.

    Each call takes the next queued outcome (a result, an exception to raise, or a
    function called with the same kwargs); with an empty queue it returns a plain
    reply.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[Outcome] = []

    def __call__(self, **kwargs: Any) -> TurnResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else make_result()
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, TurnResult):
            return outcome
        return outcome(**kwargs)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeGenerateTurn:
    fake = FakeGenerateTurn()
    monkeypatch.setattr(services, "generate_turn", fake)
    return fake


class FakeAnalyzeMistakes:
    """Stands in for `llm.analyze_mistakes`; queued results or exceptions, else none."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[AnalysisResult | Exception] = []

    def __call__(self, **kwargs: Any) -> AnalysisResult:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else make_analysis()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_analysis(*mistakes: FoundMistake) -> AnalysisResult:
    return AnalysisResult(
        mistakes=list(mistakes),
        model="test-model",
        input_tokens=1000,
        cached_input_tokens=400,
        output_tokens=200,
    )


@pytest.fixture(autouse=True)
def fake_analysis(monkeypatch: pytest.MonkeyPatch) -> FakeAnalyzeMistakes:
    # Autouse: no test in this module may reach the network through the analysis.
    fake = FakeAnalyzeMistakes()
    monkeypatch.setattr(services, "analyze_mistakes", fake)
    return fake


@pytest.fixture(autouse=True)
def pinned_budget(settings) -> None:
    settings.DAILY_BUDGET_USD = Decimal("1.00")
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_PRICES_USD_PER_MTOK = {
        "test-model": {
            "input": Decimal("2.00"),
            "cached_input": Decimal("0.50"),
            "output": Decimal("10.00"),
        }
    }


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


@pytest.fixture
def lukasz(db) -> User:
    return User.objects.create_user("lukasz@example.de", "pass-12345-xyz")


@pytest.fixture
def anna_client(client: Client, anna: User) -> Client:
    client.force_login(anna)
    return client


def detail_url(conversation: Conversation) -> str:
    return f"/conversations/{conversation.pk}/"


def start(client: Client, topic: str = "bakery") -> Conversation:
    response = client.post(START_URL, {"topic": topic})
    assert response.status_code == 302
    conversation = Conversation.objects.get(status=Conversation.Status.ACTIVE)
    assert response["Location"] == detail_url(conversation)
    return conversation


def send(client: Client, conversation: Conversation, text: str, **kwargs: Any) -> Any:
    return client.post(
        f"/conversations/{conversation.pk}/messages/", {"text": text}, **kwargs
    )


def roles(conversation: Conversation) -> list[str]:
    return list(conversation.messages.values_list("role", flat=True))


@pytest.mark.django_db
def test_start_creates_conversation_with_opening_turn(
    anna_client: Client, anna: User, fake_llm: FakeGenerateTurn
) -> None:
    anna.practice_language = PracticeLanguage.ENGLISH
    anna.save()
    topic = get_topic("bakery")
    assert topic is not None

    conversation = start(anna_client)

    assert conversation.user == anna
    assert conversation.topic == "bakery"
    assert conversation.topic_title == topic.title
    assert conversation.topic_scenario == topic.scenario
    assert conversation.language == "en"
    opening = conversation.messages.get()
    assert opening.role == Message.Role.ASSISTANT
    assert opening.text == "Guten Tag!"
    assert opening.model == "test-model"
    assert (opening.input_tokens, opening.cached_input_tokens) == (1000, 400)
    assert opening.output_tokens == 200
    assert opening.cost_usd == TURN_COST

    [call] = fake_llm.calls
    assert call["history"] == []
    assert call["language"] == "en"
    assert call["final_turn"] is False
    assert call["topic"].scenario == topic.scenario

    page = anna_client.get(detail_url(conversation))
    assert page.status_code == 200
    assert "Guten Tag!" in page.content.decode()


@pytest.mark.django_db
def test_start_with_unknown_topic_is_refused_without_model_call(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    response = anna_client.post(START_URL, {"topic": "no-such-topic"}, follow=True)

    assert response.redirect_chain == [("/", 302)]
    assert "Unknown topic" in response.content.decode()
    assert not Conversation.objects.exists()
    assert fake_llm.calls == []


@pytest.mark.django_db
def test_send_saves_both_messages_and_cost(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    fake_llm.outcomes.append(make_result("Gerne! Wie viele Brötchen?"))

    response = send(anna_client, conversation, "  Ich möchte Brötchen.  ")

    assert response.status_code == 302
    assert response["Location"] == detail_url(conversation)
    assert roles(conversation) == ["assistant", "user", "assistant"]
    user_message = conversation.messages.get(role=Message.Role.USER)
    assert user_message.text == "Ich möchte Brötchen."
    assert user_message.cost_usd == 0
    reply = conversation.messages.last()
    assert reply is not None
    assert reply.text == "Gerne! Wie viele Brötchen?"
    assert reply.cost_usd == TURN_COST
    assert fake_llm.calls[1]["history"] == [
        ("assistant", "Guten Tag!"),
        ("user", "Ich möchte Brötchen."),
    ]
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ACTIVE


@pytest.mark.django_db
def test_turn_uses_the_conversations_copy_of_the_topic(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    Conversation.objects.filter(pk=conversation.pk).update(
        topic_title="Old title", topic_scenario="Old scenario."
    )

    send(anna_client, conversation, "Hallo")

    topic = fake_llm.calls[1]["topic"]
    assert (topic.key, topic.title, topic.scenario) == (
        "bakery",
        "Old title",
        "Old scenario.",
    )


@pytest.mark.django_db
def test_agent_goodbye_ends_the_conversation(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    fake_llm.outcomes.append(make_result("Tschüss!", end=True))

    send(anna_client, conversation, "Ja, ich möchte das Gespräch beenden.")

    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ENDED
    assert conversation.end_reason == Conversation.EndReason.AGENT_GOODBYE
    assert conversation.ended_at is not None
    page = anna_client.get(detail_url(conversation)).content.decode()
    assert "Agent said goodbye" in page
    assert "Try again" not in page


@pytest.mark.django_db
def test_turn_that_exhausts_the_budget_is_final_and_ends_by_daily_limit(
    anna_client: Client, fake_llm: FakeGenerateTurn, settings
) -> None:
    conversation = start(anna_client)
    # Spent 0.0034, the last turn cost 0.0034 -> 0.0068 >= 0.005: final turn.
    settings.DAILY_BUDGET_USD = Decimal("0.005")

    send(anna_client, conversation, "Noch eine Frage.")

    assert fake_llm.calls[1]["final_turn"] is True
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ENDED
    assert conversation.end_reason == Conversation.EndReason.DAILY_LIMIT
    assert roles(conversation) == ["assistant", "user", "assistant"]
    detail = anna_client.get(detail_url(conversation)).content.decode()
    assert "00:00 (Europe/Berlin)" in detail
    home = anna_client.get("/").content.decode()
    assert "00:00 (Europe/Berlin)" in home
    assert "Choose a topic" not in home


@pytest.mark.django_db
def test_start_with_exhausted_budget_is_refused_and_home_shows_reset(
    anna_client: Client, fake_llm: FakeGenerateTurn, settings
) -> None:
    # Nothing spent, but one estimated turn (0.03) does not fit into the budget.
    settings.DAILY_BUDGET_USD = Decimal("0.03")

    response = anna_client.post(START_URL, {"topic": "bakery"}, follow=True)

    assert response.redirect_chain == [("/", 302)]
    assert not Conversation.objects.exists()
    assert fake_llm.calls == []
    page = response.content.decode()
    assert "00:00 (Europe/Berlin)" in page
    assert "Choose a topic" not in page


@pytest.mark.django_db
def test_second_active_conversation_is_impossible(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    response = anna_client.post(START_URL, {"topic": "pharmacy"}, follow=True)

    assert response.redirect_chain == [("/", 302)]
    assert list(Conversation.objects.all()) == [conversation]
    assert len(fake_llm.calls) == 1
    page = response.content.decode()
    assert "Continue conversation" in page
    assert detail_url(conversation) in page


@pytest.mark.django_db
def test_home_lists_topics_without_active_conversation(
    anna_client: Client, anna: User
) -> None:
    page = anna_client.get("/").content.decode()

    assert "Signed in as anna@example.de" in page
    assert "Choose a topic" in page
    assert "Bakery: ordering breakfast rolls" in page
    assert "Continue conversation" not in page


@pytest.mark.django_db
def test_llm_error_keeps_user_message_and_retry_finishes_the_turn(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    fake_llm.outcomes.append(LLMError("down"))

    response = send(anna_client, conversation, "Hallo", follow=True)

    assert roles(conversation) == ["assistant", "user"]
    assert "Try again" in response.content.decode()

    fake_llm.outcomes.append(make_result("Entschuldigung, hallo!"))
    retry = anna_client.post(f"/conversations/{conversation.pk}/retry/", follow=True)

    assert roles(conversation) == ["assistant", "user", "assistant"]
    assert not conversation.awaiting_agent_reply
    page = retry.content.decode()
    assert "Entschuldigung, hallo!" in page
    assert "Try again" not in page


@pytest.mark.django_db
def test_llm_error_on_start_leaves_a_conversation_waiting_for_retry(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    fake_llm.outcomes.append(LLMError("down"))

    response = anna_client.post(START_URL, {"topic": "bakery"})

    conversation = Conversation.objects.get()
    assert response["Location"] == detail_url(conversation)
    assert not conversation.messages.exists()
    assert "Try again" in anna_client.get(detail_url(conversation)).content.decode()


@pytest.mark.django_db
def test_retry_without_waiting_does_not_call_the_model(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    anna_client.post(f"/conversations/{conversation.pk}/retry/")

    assert len(fake_llm.calls) == 1
    assert roles(conversation) == ["assistant"]


@pytest.mark.django_db
def test_send_to_ended_conversation_does_not_call_the_model(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    anna_client.post(f"/conversations/{conversation.pk}/end/")

    response = send(anna_client, conversation, "Hallo?", follow=True)

    assert len(fake_llm.calls) == 1
    assert roles(conversation) == ["assistant"]
    assert "This conversation has ended." in response.content.decode()


@pytest.mark.django_db
def test_send_to_waiting_conversation_does_not_call_the_model(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    fake_llm.outcomes.append(LLMError("down"))
    send(anna_client, conversation, "Hallo")

    send(anna_client, conversation, "Hallo noch einmal")

    assert len(fake_llm.calls) == 2
    assert roles(conversation) == ["assistant", "user"]


@pytest.mark.django_db
def test_empty_message_does_not_call_the_model_and_shows_a_notice(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    response = send(anna_client, conversation, "   ", follow=True)

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    assert "Please write a message first." in response.content.decode()
    assert len(fake_llm.calls) == 1
    assert roles(conversation) == ["assistant"]


@pytest.mark.django_db
def test_too_long_message_does_not_call_the_model_and_shows_a_notice(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    page = anna_client.get(detail_url(conversation)).content.decode()
    assert f'maxlength="{services.MAX_MESSAGE_LENGTH}"' in page

    response = send(
        anna_client, conversation, "a" * (services.MAX_MESSAGE_LENGTH + 1), follow=True
    )

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    assert "Please keep your message under" in response.content.decode()
    assert len(fake_llm.calls) == 1
    assert roles(conversation) == ["assistant"]


@pytest.mark.django_db
def test_reply_is_dropped_when_another_request_already_answered(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    def parallel_answer(**kwargs: Any) -> TurnResult:
        # A parallel retry saves its reply while this model call is still running.
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            text="Parallel reply",
            cost_usd=TURN_COST,
        )
        return make_result("Late reply")

    fake_llm.outcomes.append(parallel_answer)

    send(anna_client, conversation, "Hallo")

    assert roles(conversation) == ["assistant", "user", "assistant"]
    assert conversation.messages.last().text == "Parallel reply"
    assert not conversation.messages.filter(text="Late reply").exists()


@pytest.mark.django_db
def test_page_shows_agent_typing_while_a_turn_is_running(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    fake_llm.outcomes.append(LLMError("down"))
    send(anna_client, conversation, "Hallo")
    retry_url = f"/conversations/{conversation.pk}/retry/"
    # Another request is generating the agent's turn right now.
    Conversation.objects.filter(pk=conversation.pk).update(
        agent_turn_started_at=timezone.now()
    )

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert '<div class="typing">' in page
    assert 'http-equiv="refresh"' in page
    assert "Try again" not in page

    response = anna_client.post(retry_url, follow=True)

    assert len(fake_llm.calls) == 2
    assert roles(conversation) == ["assistant", "user"]
    assert "The agent is still replying." in response.content.decode()

    # A marker left behind by a killed worker expires.
    Conversation.objects.filter(pk=conversation.pk).update(
        agent_turn_started_at=timezone.now() - timedelta(minutes=2)
    )
    page = anna_client.get(detail_url(conversation)).content.decode()

    assert "Try again" in page
    assert 'http-equiv="refresh"' not in page


@pytest.mark.django_db
def test_retry_while_the_model_is_replying_does_not_call_it_again(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    def parallel_retry(**kwargs: Any) -> TurnResult:
        # A refresh + "Try again" arrives while this model call is still running.
        with pytest.raises(services.ConversationError, match="still replying"):
            services.run_agent_turn(
                Conversation.objects.get(pk=conversation.pk), timezone.now()
            )
        return make_result("The only reply")

    fake_llm.outcomes.append(parallel_retry)

    send(anna_client, conversation, "Hallo")

    assert len(fake_llm.calls) == 2
    assert roles(conversation) == ["assistant", "user", "assistant"]
    assert conversation.messages.last().text == "The only reply"
    conversation.refresh_from_db()
    assert conversation.agent_turn_started_at is None


@pytest.mark.django_db
def test_end_button_ends_with_user_reason_and_is_idempotent(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)
    end_url = f"/conversations/{conversation.pk}/end/"

    response = anna_client.post(end_url)

    assert response["Location"] == detail_url(conversation)
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ENDED
    assert conversation.end_reason == Conversation.EndReason.USER
    ended_at = conversation.ended_at
    assert ended_at is not None

    anna_client.post(end_url)
    conversation.refresh_from_db()
    assert conversation.ended_at == ended_at
    assert "Choose a topic" in anna_client.get("/").content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("post", "messages/"),
        ("post", "retry/"),
        ("post", "end/"),
        ("post", "analysis/"),
    ],
)
def test_other_user_gets_404_on_every_conversation_url(
    client: Client,
    anna: User,
    lukasz: User,
    fake_llm: FakeGenerateTurn,
    fake_analysis: FakeAnalyzeMistakes,
    method: str,
    suffix: str,
) -> None:
    client.force_login(anna)
    conversation = start(client)
    client.force_login(lukasz)
    url = f"{detail_url(conversation)}{suffix}"

    response = getattr(client, method)(
        url, {"text": "Hallo"} if method == "post" else {}
    )

    assert response.status_code == 404
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ACTIVE
    assert roles(conversation) == ["assistant"]
    assert len(fake_llm.calls) == 1
    assert fake_analysis.calls == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/"),
        ("post", START_URL),
        ("get", "/conversations/1/"),
        ("post", "/conversations/1/messages/"),
        ("post", "/conversations/1/retry/"),
        ("post", "/conversations/1/end/"),
        ("post", "/conversations/1/analysis/"),
    ],
)
def test_anonymous_is_redirected_to_login(
    client: Client, fake_llm: FakeGenerateTurn, method: str, url: str
) -> None:
    response = getattr(client, method)(url)

    assert response.status_code == 302
    assert response["Location"].startswith("/login/?next=")
    assert fake_llm.calls == []


def analysis_url(conversation: Conversation) -> str:
    return f"/conversations/{conversation.pk}/analysis/"


def auto_submit_form(conversation: Conversation) -> str:
    return f'action="{analysis_url(conversation)}" data-auto-submit'


def ended(client: Client) -> Conversation:
    """An ended conversation with one learner message, not analysed yet."""
    conversation = start(client)
    send(client, conversation, "Ich habe gegangen.")
    client.post(f"/conversations/{conversation.pk}/end/")
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.ENDED
    return conversation


def add_mistake(conversation: Conversation, position: int, **fields: Any) -> None:
    values: dict[str, Any] = {
        "category": Mistake.Category.GRAMMAR,
        "wrong": f"wrong {position}",
        "correct": f"correct {position}",
        "sentence": f"Sentence {position}.",
        "explanation": f"Explanation {position}.",
    } | fields
    Mistake.objects.create(
        user=conversation.user, conversation=conversation, position=position, **values
    )


def mark_analyzed(conversation: Conversation) -> None:
    Conversation.objects.filter(pk=conversation.pk).update(analyzed_at=timezone.now())


@pytest.mark.django_db
def test_get_on_analysis_url_is_not_allowed(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)

    assert anna_client.get(analysis_url(conversation)).status_code == 405


@pytest.mark.django_db
def test_not_analysed_conversation_page_submits_the_analysis_itself(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert auto_submit_form(conversation) in page
    assert "Show my mistakes" in page
    assert 'http-equiv="refresh"' not in page
    assert "Back to the home page" in page


@pytest.mark.django_db
def test_analysis_in_progress_page_shows_spinner_and_refreshes(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)
    # Also failed before: "in progress" wins, so no second "Try again".
    Conversation.objects.filter(pk=conversation.pk).update(
        analysis_started_at=timezone.now(), analysis_failed_at=timezone.now()
    )

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert 'http-equiv="refresh"' in page
    assert '<span role="status">Preparing your list of mistakes…</span>' in page
    assert analysis_url(conversation) not in page
    assert "Try again" not in page


@pytest.mark.django_db
def test_failed_analysis_page_offers_try_again_without_auto_submit(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)
    Conversation.objects.filter(pk=conversation.pk).update(
        analysis_failed_at=timezone.now()
    )

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert "We could not prepare your list of mistakes. Please try again." in page
    assert "Try again" in page
    assert f'action="{analysis_url(conversation)}"' in page
    assert auto_submit_form(conversation) not in page
    assert 'http-equiv="refresh"' not in page


@pytest.mark.django_db
def test_analysed_page_lists_mistakes_in_order(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)
    # Created out of order: the page follows `position`.
    add_mistake(conversation, 2, category=Mistake.Category.WORD_ORDER)
    add_mistake(
        conversation, 1, wrong="habe gegangen", correct="bin gegangen", occurrences=2
    )
    mark_analyzed(conversation)

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert "Your mistakes" in page
    assert page.index("habe gegangen") < page.index("wrong 2")
    assert "bin gegangen" in page
    assert "×2" in page
    assert "×1" not in page
    assert "Word order" in page
    assert "Sentence 1." in page and "Explanation 1." in page
    assert analysis_url(conversation) not in page
    assert 'http-equiv="refresh"' not in page
    # The list comes after the transcript.
    assert page.index('class="transcript"') < page.index("Your mistakes")


@pytest.mark.django_db
def test_analysed_page_without_mistakes_says_so(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = ended(anna_client)
    mark_analyzed(conversation)

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert "No mistakes found in this conversation." in page
    assert analysis_url(conversation) not in page


@pytest.mark.django_db
def test_active_conversation_page_shows_no_analysis(
    anna_client: Client, fake_llm: FakeGenerateTurn
) -> None:
    conversation = start(anna_client)

    page = anna_client.get(detail_url(conversation)).content.decode()

    assert analysis_url(conversation) not in page
    assert "Your mistakes" not in page
    assert "Show my mistakes" not in page
    assert "We could not prepare your list of mistakes" not in page
    assert '<span role="status">Preparing your list of mistakes…</span>' not in page


@pytest.mark.django_db
def test_analysis_of_active_conversation_shows_an_error(
    anna_client: Client, fake_llm: FakeGenerateTurn, fake_analysis: FakeAnalyzeMistakes
) -> None:
    conversation = start(anna_client)

    response = anna_client.post(analysis_url(conversation), follow=True)

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    assert "This conversation has not ended yet." in response.content.decode()
    assert fake_analysis.calls == []


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["analyzed", "in_progress"])
def test_analysis_not_needed_redirects_without_a_notice(
    anna_client: Client,
    fake_llm: FakeGenerateTurn,
    fake_analysis: FakeAnalyzeMistakes,
    state: str,
) -> None:
    conversation = ended(anna_client)
    field = "analyzed_at" if state == "analyzed" else "analysis_started_at"
    Conversation.objects.filter(pk=conversation.pk).update(**{field: timezone.now()})

    response = anna_client.post(analysis_url(conversation), follow=True)

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    assert 'class="flash' not in response.content.decode()
    assert fake_analysis.calls == []


@pytest.mark.django_db
def test_failed_analysis_redirects_to_the_failure_state(
    anna_client: Client, fake_llm: FakeGenerateTurn, fake_analysis: FakeAnalyzeMistakes
) -> None:
    conversation = ended(anna_client)
    fake_analysis.outcomes.append(LLMError("down"))

    response = anna_client.post(analysis_url(conversation), follow=True)

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    page = response.content.decode()
    assert "We could not prepare your list of mistakes." in page
    assert 'class="flash' not in page


@pytest.mark.django_db
def test_full_flow_from_end_to_the_list_of_mistakes(
    anna_client: Client, fake_llm: FakeGenerateTurn, fake_analysis: FakeAnalyzeMistakes
) -> None:
    conversation = ended(anna_client)
    page = anna_client.get(detail_url(conversation)).content.decode()
    assert auto_submit_form(conversation) in page

    fake_analysis.outcomes.append(
        make_analysis(
            FoundMistake(
                message_number=1,
                category="grammar",
                wrong="habe gegangen",
                correct="bin gegangen",
                sentence="Ich habe gegangen.",
                explanation="Gehen takes sein in the Perfekt.",
            )
        )
    )
    response = anna_client.post(analysis_url(conversation), follow=True)

    assert response.redirect_chain == [(detail_url(conversation), 302)]
    page = response.content.decode()
    assert "Your mistakes" in page
    assert "bin gegangen" in page
    assert "Gehen takes sein in the Perfekt." in page
    assert auto_submit_form(conversation) not in page
    [call] = fake_analysis.calls
    assert ("user", "Ich habe gegangen.") in call["history"]
