"""The golden set of the AI eval: one data shape for every series.

The scorer (`scoring.py`), its tests and the eval script read these types. Message
numbers count only the learner's messages, from 1, as in the analysis transcript
(`conversations/llm.py`, `_build_transcript`): every history entry whose role is
not `"assistant"` is a learner message.

The cases themselves are added with their data source and licence in a later step;
until then the case lists are empty.
"""

from dataclasses import dataclass

# One history entry: (role, text), role "user" for the learner, "assistant" for
# the partner, oldest first (as `llm.generate_turn` and `llm.analyze_mistakes`).
History = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class GoldMistake:
    """A known mistake in one learner message.

    `wrong_key` / `correct_key` are the shortest keywords of the mistake and of its
    correction; `categories` allows 1-2 categories for borderline cases; `source`
    is the id of the corpus text.
    """

    message: int
    wrong_key: str
    correct_key: str
    categories: frozenset[str]
    rule: str
    source: str


@dataclass(frozen=True)
class Typo:
    """Spelling, capitalisation or punctuation the analysis must not report."""

    message: int
    token: str
    source: str


@dataclass(frozen=True)
class Neutral:
    """An ambiguous correction (e.g. `dass` / `das`): neither a hit nor an extra."""

    message: int
    token: str
    source: str


@dataclass(frozen=True)
class AnalysisCase:
    """A short conversation for the post-conversation analysis.

    `partner_questions` holds one group of keywords per question the partner
    asked; a group is found when any of its keywords occurs in a scene note.
    """

    id: str
    history: History
    mistakes: tuple[GoldMistake, ...]
    typos: tuple[Typo, ...]
    neutrals: tuple[Neutral, ...]
    correct_messages: tuple[int, ...]
    partner_questions: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class TurnCase:
    """An agent turn; the last history message is the learner's, with one mistake."""

    id: str
    topic_key: str
    history: History
    wrong_form: str
    correct_forms: tuple[str, ...]
    category: str
    rule: str
    source: str


@dataclass(frozen=True)
class MemoryCase:
    """An opening turn with scene notes of questions that were already asked.

    `forbidden` holds one group of German keywords per such question; a group is
    hit when any of its keywords occurs in the reply.
    """

    id: str
    topic_key: str
    scene_notes: tuple[tuple[str, ...], ...]
    forbidden: tuple[tuple[str, ...], ...]


ANALYSIS_CASES: tuple[AnalysisCase, ...] = ()
TURN_CASES: tuple[TurnCase, ...] = ()
MEMORY_CASES: tuple[MemoryCase, ...] = ()
# One long conversation for timing the analysis; it has no gold mistakes.
LATENCY_CASE: History = ()
