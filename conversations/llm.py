"""The only module that imports `openai`.

Two calls to the Responses API, both with structured output:

- `generate_turn` builds the prompt from the topic, the language, the memory block
  and the history and returns a plain `TurnResult`.
- `analyze_mistakes` sends the whole transcript after the conversation and returns
  an `AnalysisResult` with the learner's mistakes and, from the same call, short
  notes for later conversations (facts about the learner, notes about the scene).

Both raise one error type (`LLMError`) that views know how to show, and never log
conversation text.

Prompt caching: the instructions are fixed text first, then the language, the
scenario and the memory block (`format_memory`; computed once at the start and fixed
for the whole conversation); the variable "final turn" instruction is a separate message at the very end
of `input`, so it does not break the cached prefix. The analysis instructions are
fixed text first, then only the language.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from django.conf import settings
from openai import APIError, APITimeoutError, OpenAI
from openai.types.responses import EasyInputMessageParam
from pydantic import BaseModel, ValidationError

from accounts.models import PracticeLanguage

from .memory import Memory
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


@dataclass(frozen=True)
class CallUsage:
    """Tokens of a call that returned no usable answer; priced by the budget."""

    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """Any failure of the model call that the user can only retry later.

    It also tells what is known about the call's cost, without any prices: `usage`
    when the answer came with token usage but nothing usable, `billed_without_usage`
    when the call most likely cost money but its usage is unknown (a timeout, a
    malformed or usage-less answer). Neither means the call cost nothing (the
    provider refused it at once, or there is no API key).
    """

    def __init__(
        self,
        message: str,
        *,
        usage: CallUsage | None = None,
        billed_without_usage: bool = False,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.billed_without_usage = billed_without_usage


def _call_usage(response: Any) -> CallUsage | None:
    usage = response.usage
    if usage is None:
        return None
    return CallUsage(
        model=settings.LLM_MODEL,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.input_tokens_details.cached_tokens,
        output_tokens=usage.output_tokens,
    )


def _no_usable_answer(response: Any) -> LLMError:
    """The answer came but is unusable; it was paid for whether or not usage is known."""
    usage = _call_usage(response)
    return LLMError(
        "The model returned no usable answer.",
        usage=usage,
        billed_without_usage=usage is None,
    )


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


def format_memory(memory: Memory) -> str:
    """The memory as a prompt block; `""` when there is nothing to remember.

    Only non-empty sections are included.
    """
    if memory.is_empty:
        return ""
    sections = ["Memory from earlier conversations with this learner:"]
    if memory.learner_facts:
        sections.append(
            "What you know about the learner (newer facts first; when two facts "
            "contradict each other, trust the newer one). Use a fact only when it "
            "fits the scene naturally:\n"
            + "\n".join(f"- {fact}" for fact in memory.learner_facts)
        )
    if memory.scene_notes:
        conversations = []
        for number, notes in enumerate(memory.scene_notes, start=1):
            label = " (the most recent)" if number == 1 else ""
            lines = "\n".join(f"- {note}" for note in notes)
            conversations.append(f"Conversation {number}{label}:\n{lines}")
        sections.append(
            "Earlier conversations in this same scene (the most recent first). You "
            "are the same person as in them: refer back to them when it feels "
            "natural, and do not ask again questions that were already asked.\n"
            + "\n".join(conversations)
        )
    if memory.mistakes:
        sections.append(
            "Constructions the learner got wrong before (the most important "
            "first):\n"
            + "\n".join(
                f"- {m.wrong} → {m.correct}: {m.explanation}" for m in memory.mistakes
            )
            + "\nPick at most one of them: the highest on the list among those that "
            "fit the scene naturally. Create a natural chance for the learner to use "
            "it. Never say that this is an exercise or that the learner made this "
            "mistake before. If none of them fits the scene, ignore this list."
        )
    return "\n\n".join(sections)


def _build_instructions(topic: Topic, language: str, memory: str) -> str:
    instructions = (
        f"{_INSTRUCTIONS}\n"
        f"Practice language: {_language_name(language)}\n\n"
        f"Scene: {topic.scenario}"
    )
    if memory:
        instructions += f"\n\n{memory}"
    return instructions


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
    memory: str,
) -> TurnResult:
    """One agent turn. `history` is a list of `(role, text)`, oldest first.

    `memory` is the conversation's memory block (`format_memory`), `""` for none.
    """
    client = _get_client(
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )
    try:
        response = client.responses.parse(
            model=settings.LLM_MODEL,
            instructions=_build_instructions(topic, language, memory),
            input=_build_input(history, final_turn),
            text_format=AgentTurn,
            reasoning={"effort": settings.LLM_REASONING_EFFORT},
            store=False,
        )
    except APITimeoutError as exc:
        # Before `APIError`, its base class. The provider may have generated (and
        # billed) the answer that never arrived.
        logger.error("LLM call failed: %s (status None)", type(exc).__name__)
        raise LLMError("The model call failed.", billed_without_usage=True) from exc
    except APIError as exc:
        # Base class of connection, rate limit and status errors.
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
        raise LLMError(
            "The model returned no usable answer.", billed_without_usage=True
        ) from None

    parsed = response.output_parsed
    if parsed is None:
        # A refusal or an empty answer: nothing usable came back.
        logger.error("LLM returned no parsed output (refusal or empty answer).")
        raise _no_usable_answer(response)
    if parsed.reply.strip() == "":
        # A blank reply is no answer either. Log only the fact, never the text.
        logger.error("LLM returned a blank agent reply.")
        raise _no_usable_answer(response)
    if response.usage is None:
        logger.error("LLM response has no usage; the turn cannot be priced.")
        raise LLMError(
            "The model response has no token usage.", billed_without_usage=True
        )

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
    except APITimeoutError as exc:
        # Before `APIError`, its base class; the analysis may have been billed.
        logger.error("LLM analysis call failed: %s (status None)", type(exc).__name__)
        raise LLMError("The model call failed.", billed_without_usage=True) from exc
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
        raise LLMError(
            "The model returned no usable answer.", billed_without_usage=True
        ) from None

    parsed = response.output_parsed
    if parsed is None:
        logger.error("LLM analysis returned no parsed output (refusal or empty).")
        raise _no_usable_answer(response)
    if response.usage is None:
        logger.error("LLM analysis response has no usage; it cannot be priced.")
        raise LLMError(
            "The model response has no token usage.", billed_without_usage=True
        )

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
