"""The AI eval's golden set (scripts/eval/golden.py) is internally consistent.

No model and no corpus: the checks only read the data. Keys and tokens must occur
as whole words because the scorer matches them that way (`contains_phrase`), and
the gold keys of one message must not share a word, because matching is greedy
(an item that fits two gold mistakes takes the first). Source of the rules:
context/changes/testing-ai-eval-layer/plan.md, phase 2, golden set and its tests.
"""

import re

import pytest

from conversations.topics import get_topic
from scripts.eval import golden
from scripts.eval.golden import (
    ANALYSIS_CASES,
    CATEGORIES,
    LATENCY_CASE,
    MEMORY_CASES,
    PARTNER_PLANTS,
    TURN_CASES,
    AnalysisCase,
)
from scripts.eval.scoring import contains_phrase, learner_messages, normalize

# Set when the golden set was built: 17 grammar, 12 vocabulary and 13 word-order
# gold mistakes (a borderline one counts for both its categories). A smaller set
# would make the per-category numbers too noisy to compare.
MIN_GOLD_PER_CATEGORY = 12
MIN_TURN_CASES_PER_CATEGORY = 6
# A MERLIN Author ID, e.g. "1023_0001416".
MERLIN_ID = re.compile(r"^\d{4}_\d{7}$")
MERLIN_HANDLE = "http://hdl.handle.net/20.500.12124/6"


def partner_messages(case: AnalysisCase) -> list[str]:
    return [text for role, text in case.history if role == "assistant"]


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", normalize(text)))


def test_case_ids_are_unique() -> None:
    ids = [case.id for case in (*ANALYSIS_CASES, *TURN_CASES, *MEMORY_CASES)]

    assert len(ids) == len(set(ids))


def test_docstring_has_the_licence_and_the_merlin_handle() -> None:
    assert golden.__doc__ is not None
    assert "CC BY-SA 4.0" in golden.__doc__
    assert MERLIN_HANDLE in golden.__doc__


# --- analysis -------------------------------------------------------------------


@pytest.mark.parametrize("case", ANALYSIS_CASES, ids=lambda case: case.id)
def test_analysis_case_is_consistent(case: AnalysisCase) -> None:
    messages = learner_messages(case.history)
    numbers = range(1, len(messages) + 1)
    assert 4 <= len(messages) <= 6

    for gold in case.mistakes:
        assert gold.message in numbers
        assert contains_phrase(messages[gold.message - 1], gold.wrong_key), gold
        assert normalize(gold.correct_key) != normalize(gold.wrong_key), gold
        assert gold.categories <= CATEGORIES, gold
        assert 1 <= len(gold.categories) <= 2, gold
        assert gold.rule.strip(), gold
        assert MERLIN_ID.match(gold.source), gold
    for token in (*case.typos, *case.neutrals):
        assert token.message in numbers
        assert contains_phrase(messages[token.message - 1], token.token), token
        assert MERLIN_ID.match(token.source), token
    for number in case.correct_messages:
        assert number in numbers

    assert case.typos, "at least one typo per chat"
    assert case.correct_messages, "at least one correct message per chat"


@pytest.mark.parametrize("case", ANALYSIS_CASES, ids=lambda case: case.id)
def test_gold_keys_of_one_message_share_no_word(case: AnalysisCase) -> None:
    for number in {gold.message for gold in case.mistakes}:
        keys = [gold.wrong_key for gold in case.mistakes if gold.message == number]
        seen: set[str] = set()
        for key in keys:
            assert not words(key) & seen, (number, keys)
            seen |= words(key)


@pytest.mark.parametrize("case", ANALYSIS_CASES, ids=lambda case: case.id)
def test_correct_messages_have_no_gold_typo_or_neutral(case: AnalysisCase) -> None:
    marked = {item.message for item in (*case.mistakes, *case.typos, *case.neutrals)}

    assert not marked & set(case.correct_messages)


@pytest.mark.parametrize("case", ANALYSIS_CASES, ids=lambda case: case.id)
def test_partner_questions_are_in_the_partner_messages(case: AnalysisCase) -> None:
    partner = partner_messages(case)

    assert len(case.partner_questions) == 2
    for group in case.partner_questions:
        assert any(
            contains_phrase(text, keyword) for text in partner for keyword in group
        ), group


def test_planted_partner_mistakes_are_only_in_partner_messages() -> None:
    by_id = {case.id: case for case in ANALYSIS_CASES}

    assert len(PARTNER_PLANTS) >= 2
    for case_id, fragment in PARTNER_PLANTS:
        case = by_id[case_id]
        assert any(contains_phrase(t, fragment) for t in partner_messages(case))
        assert not any(
            contains_phrase(t, fragment) for t in learner_messages(case.history)
        )


def test_every_category_has_enough_gold_mistakes() -> None:
    golds = [gold for case in ANALYSIS_CASES for gold in case.mistakes]

    for category in CATEGORIES:
        count = sum(1 for gold in golds if category in gold.categories)
        assert count >= MIN_GOLD_PER_CATEGORY, (category, count)


# --- turn -----------------------------------------------------------------------


@pytest.mark.parametrize("case", TURN_CASES, ids=lambda case: case.id)
def test_turn_case_is_consistent(case: golden.TurnCase) -> None:
    role, last = case.history[-1]

    assert role == "user"
    assert case.wrong_forms
    assert contains_phrase(last, case.wrong_forms[0])
    assert case.correct_forms
    for correct in case.correct_forms:
        for wrong in case.wrong_forms:
            assert not contains_phrase(correct, wrong), (correct, wrong)
    assert get_topic(case.topic_key) is not None
    assert case.category in CATEGORIES
    assert case.rule.strip()
    assert MERLIN_ID.match(case.source)


def test_turn_categories_are_balanced() -> None:
    for category in CATEGORIES:
        count = sum(1 for case in TURN_CASES if case.category == category)
        assert count >= MIN_TURN_CASES_PER_CATEGORY, (category, count)


# --- memory and latency ---------------------------------------------------------


@pytest.mark.parametrize("case", MEMORY_CASES, ids=lambda case: case.id)
def test_memory_case_is_consistent(case: golden.MemoryCase) -> None:
    assert get_topic(case.topic_key) is not None
    assert case.scene_notes and all(case.scene_notes)
    assert 2 <= len(case.forbidden) <= 3
    assert all(case.forbidden)


def test_memory_cases_use_different_scenes() -> None:
    keys = [case.topic_key for case in MEMORY_CASES]

    assert len(keys) == len(set(keys))


def test_latency_case_is_a_long_conversation() -> None:
    assert len(LATENCY_CASE) >= 40
    assert len(learner_messages(LATENCY_CASE)) >= 20
    assert {role for role, _ in LATENCY_CASE} == {"user", "assistant"}
