"""Memory for a new conversation, chosen from the user's past conversations.

The rules, in one place (no LLM involved):

- Source: only the user's own conversations that have ended, have been analysed
  (`analyzed_at` set) and are in the same practice language, newest first
  (`-ended_at`, then `-id`).
- Mistakes: from the `MISTAKE_WINDOW_CONVERSATIONS` newest conversations. Pairs
  (`wrong`, `correct`) are grouped after collapsing whitespace and `casefold`.
  A pair seen in more conversations ranks higher (`occurrences` inside one
  conversation does not count); ties go to the pair from the newer conversation,
  then to the lower `position` in that conversation. The first `MAX_MISTAKES`
  are kept, with the spelling and explanation of the newest occurrence.
- Learner facts: from the `FACT_WINDOW_CONVERSATIONS` newest conversations of
  any topic, newest first; a repeated fact (same text after collapsing
  whitespace and `casefold`) is kept once, in its newest version. This window
  is a stopgap: after the MVP a learner profile in the style of Observational
  Memory (compression that, according to its authors, keeps most of the
  information) replaces it.
- Scene notes: from the `SCENE_NOTE_CONVERSATIONS` newest conversations with the
  same topic key, one list per conversation, newest first, empty ones skipped.

`select_memory` makes a fixed number of queries, however many conversations
the user has. This module imports only models, so `services` and `llm` may
import it.
"""

from dataclasses import dataclass, field

from accounts.models import User
from conversations.models import Conversation, Mistake

MISTAKE_WINDOW_CONVERSATIONS = 20
MAX_MISTAKES = 10
FACT_WINDOW_CONVERSATIONS = 10
SCENE_NOTE_CONVERSATIONS = 5


@dataclass
class PastMistake:
    wrong: str
    correct: str
    explanation: str
    # Number of different conversations with this pair.
    conversations: int


@dataclass
class Memory:
    learner_facts: list[str] = field(default_factory=list)
    # One list per earlier conversation, newest first.
    scene_notes: list[list[str]] = field(default_factory=list)
    mistakes: list[PastMistake] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.learner_facts or self.scene_notes or self.mistakes)


def _key(text: str) -> str:
    """Whitespace collapsed (as `services._normalize`) and case folded.

    Repeated here because `services` imports this module.
    """
    return " ".join(text.split()).casefold()


@dataclass
class _Group:
    mistake: PastMistake
    # Index of the newest conversation with the pair (0 = newest overall).
    newest_rank: int
    position: int
    conversation_ids: set[int]


def select_memory(user: User, topic_key: str, language: str) -> Memory:
    """The memory for the user's new conversation on `topic_key` in `language`."""
    past = (
        Conversation.objects.for_user(user)
        .filter(
            status=Conversation.Status.ENDED,
            analyzed_at__isnull=False,
            language=language,
        )
        .order_by("-ended_at", "-id")
    )
    window = max(MISTAKE_WINDOW_CONVERSATIONS, FACT_WINDOW_CONVERSATIONS)
    recent = list(past.values_list("id", "learner_facts")[:window])
    scene_lists = past.filter(topic=topic_key).values_list("scene_notes", flat=True)[
        :SCENE_NOTE_CONVERSATIONS
    ]
    return Memory(
        learner_facts=_learner_facts(
            [facts for _, facts in recent[:FACT_WINDOW_CONVERSATIONS]]
        ),
        scene_notes=[list(notes) for notes in scene_lists if notes],
        mistakes=_mistakes(
            user, [pk for pk, _ in recent[:MISTAKE_WINDOW_CONVERSATIONS]]
        ),
    )


def _learner_facts(fact_lists: list[list[str]]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for fact_list in fact_lists:
        for fact in fact_list:
            key = _key(fact)
            if key and key not in seen:
                seen.add(key)
                facts.append(fact)
    return facts


def _mistakes(user: User, conversation_ids: list[int]) -> list[PastMistake]:
    if not conversation_ids:
        return []
    rank = {pk: index for index, pk in enumerate(conversation_ids)}
    rows = Mistake.objects.for_user(user).filter(conversation_id__in=conversation_ids)
    groups: dict[tuple[str, str], _Group] = {}
    for row in rows.values_list(
        "conversation_id", "position", "wrong", "correct", "explanation"
    ):
        conversation_id, position, wrong, correct, explanation = row
        key = (_key(wrong), _key(correct))
        order = (rank[conversation_id], position)
        group = groups.get(key)
        if group is None:
            groups[key] = _Group(
                mistake=PastMistake(wrong, correct, explanation, conversations=0),
                newest_rank=order[0],
                position=order[1],
                conversation_ids={conversation_id},
            )
            continue
        group.conversation_ids.add(conversation_id)
        if order < (group.newest_rank, group.position):
            group.newest_rank, group.position = order
            group.mistake.wrong = wrong
            group.mistake.correct = correct
            group.mistake.explanation = explanation
    for group in groups.values():
        group.mistake.conversations = len(group.conversation_ids)
    ranked = sorted(
        groups.values(),
        key=lambda g: (-len(g.conversation_ids), g.newest_rank, g.position),
    )
    return [group.mistake for group in ranked[:MAX_MISTAKES]]
