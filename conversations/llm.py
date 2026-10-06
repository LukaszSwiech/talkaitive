"""The only module that imports `openai`.

Builds the prompt from the topic, the language and the history, calls the Responses
API with structured output and returns a plain `TurnResult` or raises one error type
(`LLMError`) that views know how to show.

Prompt caching: the instructions are fixed text first, then the language and the
scenario; the variable "final turn" instruction is a separate message at the very end
of `input`, so it does not break the cached prefix.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from django.conf import settings
from openai import APIError, OpenAI
from openai.types.responses import EasyInputMessageParam
from pydantic import BaseModel

from accounts.models import PracticeLanguage

from .topics import Topic

logger = logging.getLogger(__name__)

_INSTRUCTIONS = """\
You are a conversation partner in a role-play scene that helps a learner practise \
speaking. Stay in your role in the scene described below.

Language and level:
- Speak only in the practice language given below, at CEFR level B1-B2.
- Keep your turns short and natural, and ask one question at a time.

Corrections:
- When the learner's message contains mistakes, work the correct form of at most \
the 1-2 most important ones (grammar, vocabulary, word order) naturally into your \
reply. Do not explain rules and do not list mistakes.
- Ignore typos and punctuation unless they change the meaning.
- Never interrupt the conversation with a lecture.

Ending the conversation:
- When the learner says goodbye, answer in the scene and briefly ask whether they \
want to end the conversation.
- Set end_conversation to true only after the learner has clearly confirmed that \
they want to end it. Otherwise set it to false.
"""

_OPENING_MESSAGE = "Open the scene: speak first and start the conversation."

_FINAL_TURN_MESSAGE = (
    "This is your last reply. Answer briefly, say goodbye naturally in the scene "
    "and tell the learner that the daily conversation limit has been reached."
)


class AgentTurn(BaseModel):
    reply: str
    end_conversation: bool


@dataclass(frozen=True)
class TurnResult:
    reply: str
    end_conversation: bool
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """Any failure of the model call that the user can only retry later."""


def _get_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise LLMError("OPENAI_API_KEY is not configured.")
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def _language_name(language: str) -> str:
    try:
        return PracticeLanguage(language).label
    except ValueError:
        return language


def _build_instructions(topic: Topic, language: str) -> str:
    return (
        f"{_INSTRUCTIONS}\n"
        f"Practice language: {_language_name(language)}\n\n"
        f"Scene: {topic.scenario}"
    )


def _build_input(
    history: Sequence[tuple[str, str]], final_turn: bool
) -> list[EasyInputMessageParam]:
    messages: list[EasyInputMessageParam] = [
        {"role": "assistant" if role == "assistant" else "user", "content": text}
        for role, text in history
    ]
    if not messages:
        messages.append({"role": "user", "content": _OPENING_MESSAGE})
    if final_turn:
        messages.append({"role": "developer", "content": _FINAL_TURN_MESSAGE})
    return messages


def generate_turn(
    *,
    topic: Topic,
    language: str,
    history: Sequence[tuple[str, str]],
    final_turn: bool,
) -> TurnResult:
    """One agent turn. `history` is a list of `(role, text)`, oldest first."""
    client = _get_client()
    try:
        response = client.responses.parse(
            model=settings.LLM_MODEL,
            instructions=_build_instructions(topic, language),
            input=_build_input(history, final_turn),
            text_format=AgentTurn,
            reasoning={"effort": settings.LLM_REASONING_EFFORT},
            store=False,
        )
    except APIError as exc:
        # Base class of timeout, connection, rate limit and status errors.
        # Log the error type and status only, never the conversation text.
        logger.error(
            "LLM call failed: %s (status %s)",
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        raise LLMError("The model call failed.") from exc

    parsed = response.output_parsed
    if parsed is None:
        # A refusal or an empty answer: nothing usable came back.
        logger.error("LLM returned no parsed output (refusal or empty answer).")
        raise LLMError("The model returned no usable answer.")
    if response.usage is None:
        logger.error("LLM response has no usage; the turn cannot be priced.")
        raise LLMError("The model response has no token usage.")

    usage = response.usage
    return TurnResult(
        reply=parsed.reply,
        end_conversation=parsed.end_conversation,
        model=settings.LLM_MODEL,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.input_tokens_details.cached_tokens,
        output_tokens=usage.output_tokens,
    )
