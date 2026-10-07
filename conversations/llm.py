"""The only module that imports `openai`.

Two calls to the Responses API, both with structured output:

- `generate_turn` builds the prompt from the topic, the language and the history and
  returns a plain `TurnResult`.
- `analyze_mistakes` sends the whole transcript after the conversation and returns
  an `AnalysisResult` with the learner's mistakes and, from the same call, short
  notes for later conversations (facts about the learner, notes about the scene).

Both raise one error type (`LLMError`) that views know how to show, and never log
conversation text.

Prompt caching: the instructions are fixed text first, then the language and the
scenario; the variable "final turn" instruction is a separate message at the very end
of `input`, so it does not break the cached prefix. The analysis instructions are
fixed text first, then only the language.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from openai import APIError, OpenAI
from openai.types.responses import EasyInputMessageParam
from pydantic import BaseModel, ValidationError

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


_ANALYSIS_INSTRUCTIONS = """\
You review a finished conversation between a language learner and a conversation \
partner. Find the learner's mistakes so the learner can study them.

What to analyse:
- Analyse only the learner's messages, marked "[n] Learner:". The partner's \
messages are context only; never report anything from them.
- Report only mistakes in these categories: grammar, vocabulary, word_order.
- Ignore typos, capitalisation and punctuation unless they change the meaning.

How to report each mistake:
- message_number: the number n of the learner message that contains it.
- category: grammar, vocabulary or word_order.
- wrong: the shortest fragment of the learner's text that shows the mistake, \
e.g. "habe ... gegangen".
- correct: the corrected version of that same fragment, e.g. "bin ... gegangen".
- sentence: the learner's whole original sentence that contains the mistake, \
unchanged.
- explanation: one short sentence in English.
- Report every occurrence separately with its own message number, even when the \
same mistake repeats.
- If the learner made no mistakes, return an empty list.

Notes for later conversations:
- learner_facts: at most 5 lasting facts the learner said about themselves, e.g. \
their dog's name and breed, their job, their family, where they live. Only what \
the learner actually said; never guess.
- scene_notes: at most 8 notes about this conversation: what was talked about, \
what questions the partner asked, and what the partner said about their own \
character, e.g. how the hairdresser cut the learner's hair.
- Write each note as one short sentence in English.
- Notes never describe mistakes or the learner's language level.
- Empty lists are fine when there is nothing worth noting.
"""


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


class FoundMistake(BaseModel):
    message_number: int
    category: Literal["grammar", "vocabulary", "word_order"]
    wrong: str
    correct: str
    sentence: str
    explanation: str


class MistakeReport(BaseModel):
    mistakes: list[FoundMistake]
    learner_facts: list[str]
    scene_notes: list[str]


@dataclass(frozen=True)
class AnalysisResult:
    mistakes: list[FoundMistake]
    learner_facts: list[str]
    scene_notes: list[str]
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """Any failure of the model call that the user can only retry later."""


def _get_client(*, timeout: float, max_retries: int) -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise LLMError("OPENAI_API_KEY is not configured.")
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=timeout,
        max_retries=max_retries,
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
    client = _get_client(
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )
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
    except ValidationError:
        # Truncated or malformed structured output. The error text quotes the
        # model's output, so log only that it happened.
        logger.error("LLM output does not match the AgentTurn schema.")
        raise LLMError("The model returned no usable answer.") from None

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


def _build_analysis_instructions(language: str) -> str:
    return f"{_ANALYSIS_INSTRUCTIONS}\nPractice language: {_language_name(language)}"


def _build_transcript(history: Sequence[tuple[str, str]]) -> str:
    """One text: learner messages numbered from 1, partner messages unnumbered."""
    lines: list[str] = []
    learner_number = 0
    for role, text in history:
        if role == "assistant":
            lines.append(f"Partner: {text}")
        else:
            learner_number += 1
            lines.append(f"[{learner_number}] Learner: {text}")
    return "\n\n".join(lines)


def analyze_mistakes(
    *, language: str, history: Sequence[tuple[str, str]]
) -> AnalysisResult:
    """The learner's mistakes in a finished conversation. `history` is oldest first.

    `message_number` in each mistake counts only the learner's messages, from 1.
    """
    client = _get_client(
        timeout=settings.LLM_ANALYSIS_TIMEOUT_SECONDS,
        max_retries=settings.LLM_ANALYSIS_MAX_RETRIES,
    )
    try:
        response = client.responses.parse(
            model=settings.LLM_MODEL,
            instructions=_build_analysis_instructions(language),
            input=_build_transcript(history),
            text_format=MistakeReport,
            reasoning={"effort": settings.LLM_ANALYSIS_REASONING_EFFORT},
            store=False,
        )
    except APIError as exc:
        # Log the error type and status only, never the conversation text.
        logger.error(
            "LLM analysis call failed: %s (status %s)",
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        raise LLMError("The model call failed.") from exc
    except ValidationError:
        # The error text quotes the model's output, so log only that it happened.
        logger.error("LLM output does not match the MistakeReport schema.")
        raise LLMError("The model returned no usable answer.") from None

    parsed = response.output_parsed
    if parsed is None:
        logger.error("LLM analysis returned no parsed output (refusal or empty).")
        raise LLMError("The model returned no usable answer.")
    if response.usage is None:
        logger.error("LLM analysis response has no usage; it cannot be priced.")
        raise LLMError("The model response has no token usage.")

    usage = response.usage
    return AnalysisResult(
        mistakes=list(parsed.mistakes),
        learner_facts=list(parsed.learner_facts),
        scene_notes=list(parsed.scene_notes),
        model=settings.LLM_MODEL,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.input_tokens_details.cached_tokens,
        output_tokens=usage.output_tokens,
    )
