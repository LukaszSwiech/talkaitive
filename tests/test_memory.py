from datetime import UTC, datetime, timedelta

import pytest

from accounts.models import PracticeLanguage, User
from conversations.memory import Memory, PastMistake, select_memory
from conversations.models import Conversation, Mistake

START = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
DE = PracticeLanguage.GERMAN


@pytest.fixture
def anna(db) -> User:
    return User.objects.create_user("anna@example.de", "pass-12345-xyz")


def make_conversation(
    user: User,
    day: int,
    topic: str = "bakery",
    language: str = DE,
    status: Conversation.Status = Conversation.Status.ENDED,
    analyzed: bool = True,
    facts: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> Conversation:
    """A conversation ended on `day` days after START (a later day is newer)."""
    ended = status == Conversation.Status.ENDED
    at = START + timedelta(days=day)
    return Conversation.objects.create(
        user=user,
        topic=topic,
        topic_title=topic.title(),
        topic_scenario="Scene.",
        language=language,
        status=status,
        ended_at=at if ended else None,
        analyzed_at=at if ended and analyzed else None,
        learner_facts=list(facts),
        scene_notes=list(notes),
    )


def add_mistake(
    conversation: Conversation,
    position: int,
    wrong: str,
    correct: str,
    occurrences: int = 1,
    explanation: str = "Explanation.",
) -> Mistake:
    return Mistake.objects.create(
        user=conversation.user,
        conversation=conversation,
        position=position,
        category=Mistake.Category.GRAMMAR,
        wrong=wrong,
        correct=correct,
        sentence="Sentence.",
        explanation=explanation,
        occurrences=occurrences,
    )


def pairs(memory: Memory) -> list[tuple[str, str, int]]:
    return [(m.wrong, m.correct, m.conversations) for m in memory.mistakes]


def test_pair_in_more_conversations_ranks_above_pair_repeated_in_one(
    anna: User,
) -> None:
    older = make_conversation(anna, day=1)
    newer = make_conversation(anna, day=2)
    add_mistake(newer, 1, "a", "A", occurrences=4)
    add_mistake(newer, 2, "b", "B")
    add_mistake(older, 1, "b", "B")

    memory = select_memory(anna, "bakery", DE)

    assert pairs(memory) == [("b", "B", 2), ("a", "A", 1)]


def test_tie_goes_to_pair_from_newer_conversation_then_lower_position(
    anna: User,
) -> None:
    older = make_conversation(anna, day=1)
    newer = make_conversation(anna, day=2)
    add_mistake(older, 1, "old", "OLD")
    add_mistake(newer, 2, "second", "SECOND")
    add_mistake(newer, 1, "first", "FIRST")

    memory = select_memory(anna, "bakery", DE)

    assert [m.wrong for m in memory.mistakes] == ["first", "second", "old"]


def test_pairs_differing_in_spaces_and_case_are_one_with_newest_spelling(
    anna: User,
) -> None:
    older = make_conversation(anna, day=1)
    newer = make_conversation(anna, day=2)
    add_mistake(older, 1, "habe  gegangen", "bin gegangen", explanation="Old.")
    add_mistake(newer, 1, "Habe gegangen", "Bin gegangen", explanation="New.")

    memory = select_memory(anna, "bakery", DE)

    assert memory.mistakes == [
        PastMistake("Habe gegangen", "Bin gegangen", "New.", conversations=2)
    ]


def test_pair_only_in_21st_newest_conversation_is_left_out(anna: User) -> None:
    oldest = make_conversation(anna, day=0)
    add_mistake(oldest, 1, "too old", "TOO OLD")
    for day in range(1, 21):
        make_conversation(anna, day=day)

    assert select_memory(anna, "bakery", DE).mistakes == []


def test_at_most_ten_mistakes(anna: User) -> None:
    conversation = make_conversation(anna, day=1)
    for position in range(1, 13):
        add_mistake(conversation, position, f"w{position}", f"c{position}")

    memory = select_memory(anna, "bakery", DE)

    assert [m.wrong for m in memory.mistakes] == [f"w{n}" for n in range(1, 11)]


def test_other_language_active_and_unanalysed_conversations_are_skipped(
    anna: User,
) -> None:
    english = make_conversation(
        anna, day=1, language=PracticeLanguage.ENGLISH, facts=("F1",), notes=("N1",)
    )
    unanalysed = make_conversation(anna, day=2, analyzed=False, facts=("F2",))
    active = make_conversation(
        anna, day=3, status=Conversation.Status.ACTIVE, facts=("F3",)
    )
    for conversation in (english, unanalysed, active):
        add_mistake(conversation, 1, "x", "X")

    assert select_memory(anna, "bakery", DE).is_empty


def test_other_users_data_never_appears(anna: User) -> None:
    ben = User.objects.create_user("ben@example.de", "pass-12345-xyz")
    theirs = make_conversation(ben, day=1, facts=("Ben fact.",), notes=("Ben note.",))
    add_mistake(theirs, 1, "ben", "BEN")

    assert select_memory(anna, "bakery", DE).is_empty
    assert not select_memory(ben, "bakery", DE).is_empty


def test_scene_notes_from_same_topic_only_at_most_five_newest_first(
    anna: User,
) -> None:
    make_conversation(anna, day=0, notes=("Too old.",))
    for day in range(1, 6):
        make_conversation(anna, day=day, notes=(f"Bakery {day}.",))
    make_conversation(anna, day=6, topic="doctor", notes=("Doctor.",))

    memory = select_memory(anna, "bakery", DE)

    assert memory.scene_notes == [[f"Bakery {day}."] for day in range(5, 0, -1)]


def test_conversation_without_scene_notes_is_skipped_but_counts(anna: User) -> None:
    make_conversation(anna, day=0, notes=("Too old.",))
    for day in range(1, 5):
        make_conversation(anna, day=day, notes=(f"Bakery {day}.",))
    make_conversation(anna, day=5, notes=())

    memory = select_memory(anna, "bakery", DE)

    assert memory.scene_notes == [[f"Bakery {day}."] for day in range(4, 0, -1)]


def test_facts_from_any_topic_at_most_ten_conversations_duplicates_once(
    anna: User,
) -> None:
    make_conversation(anna, day=0, facts=("Too old.",))
    make_conversation(anna, day=1, facts=("My dog is  called Bello.", "Old fact."))
    for day in range(2, 10):
        make_conversation(anna, day=day)
    make_conversation(
        anna, day=10, topic="doctor", facts=("I am a nurse.", "my dog is called bello.")
    )

    memory = select_memory(anna, "bakery", DE)

    assert memory.learner_facts == [
        "I am a nurse.",
        "my dog is called bello.",
        "Old fact.",
    ]


def test_no_data_is_empty(anna: User) -> None:
    memory = select_memory(anna, "bakery", DE)

    assert memory == Memory(learner_facts=[], scene_notes=[], mistakes=[])
    assert memory.is_empty


def test_query_count_does_not_depend_on_number_of_conversations(
    anna: User, django_assert_num_queries
) -> None:
    for day in range(25):
        conversation = make_conversation(anna, day=day, facts=("F.",), notes=("N.",))
        add_mistake(conversation, 1, f"w{day}", "c")

    with django_assert_num_queries(3):
        select_memory(anna, "bakery", DE)
