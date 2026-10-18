"""The AI eval's scorer and cost meter (scripts/eval/), without a model or network.

Model results (`FoundMistake`, `AnalysisResult`, `TurnResult`) are written by hand
in each test. Expected numbers are hand-written literals with the arithmetic in a
comment, never computed with the scorer's own functions.

Sources: the hard rules and limits of the prompts in conversations/llm.py (only the
learner's messages, `sentence` unchanged, no typos, at most 5 facts and 8 notes, one
question at a time, `end_conversation` only after a confirmed goodbye) and the
decisions of context/changes/testing-ai-eval-layer/plan.md (tolerant one-to-one
matching by message number and keywords, metrics, paired comparison with a 95%
interval, cost counted like the app's budget). Prices pinned below (gpt-5.4 per 1M
tokens: input 2.50, cached input 0.25, output 15.00; estimates 0.03 per turn and
0.07 per analysis) as in test-plan §6.4.
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from conversations.llm import (
    AnalysisResult,
    CallUsage,
    FoundMistake,
    LLMError,
    TurnResult,
)
from scripts.eval.cost import CostMeter
from scripts.eval.golden import (
    AnalysisCase,
    GoldMistake,
    MemoryCase,
    Neutral,
    TurnCase,
    Typo,
)
from scripts.eval.scoring import (
    VERDICT_DIFFERENCE,
    VERDICT_NOISE,
    Finding,
    Score,
    Violation,
    aggregate,
    compare,
    score_analysis,
    score_memory,
    score_turn,
)

M1 = "Ich habe ins Kino gegangen."
M2 = "Ich mag der Film sehr, er war spanend."
M3 = "Ich glaube das er hat einen Preis gewonnen."
M4 = "Danach bin ich nach Hause gefahren."

CASE = AnalysisCase(
    id="kino",
    history=(
        ("assistant", "Hallo! Was hast du am Wochenende gemacht?"),
        ("user", M1),
        ("assistant", "Toll! Ich war gestern in Kino. Welchen Film hast du gesehen?"),
        ("user", M2),
        ("assistant", "Das klingt gut."),
        ("user", M3),
        ("user", M4),
    ),
    mistakes=(
        GoldMistake(1, "habe", "bin", frozenset({"grammar"}), "Perfekt mit sein", "t1"),
        GoldMistake(
            2, "der film", "den film", frozenset({"grammar"}), "Akkusativ", "t1"
        ),
        GoldMistake(
            3,
            "er hat",
            "gewonnen hat",
            frozenset({"word_order", "grammar"}),
            "Verb am Ende im Nebensatz",
            "t1",
        ),
    ),
    typos=(Typo(2, "spanend", "t1"),),
    neutrals=(Neutral(3, "das", "t1"),),
    correct_messages=(4,),
    partner_questions=(("weekend", "wochenende"), ("film", "movie")),
)


def item(
    number: int, wrong: str, correct: str, sentence: str, category: str = "grammar"
) -> FoundMistake:
    return FoundMistake(
        message_number=number,
        category=category,  # type: ignore[arg-type]
        wrong=wrong,
        correct=correct,
        sentence=sentence,
        explanation="Explanation.",
    )


def analysis(
    *items: FoundMistake, facts: int = 0, notes: tuple[str, ...] = ()
) -> AnalysisResult:
    return AnalysisResult(
        mistakes=list(items),
        learner_facts=[f"Fact {n}." for n in range(facts)],
        scene_notes=list(notes),
        model="gpt-5.4",
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
    )


def kinds(score: Score) -> list[str]:
    return [finding.kind for finding in score.findings]


# --- analysis: matching ---------------------------------------------------------


def test_longer_wrong_with_gap_matches_the_gold_keywords() -> None:
    score = score_analysis(
        CASE, analysis(item(1, "habe ... gegangen", "bin ... gegangen", M1))
    )

    assert score.findings == ()
    assert score.extras == ()
    assert score.metrics == {
        "recall": pytest.approx(1 / 3),  # 1 matched of 3 gold mistakes
        "category_accuracy": 1.0,  # 1 right category of 1 matched
        "extras": 0.0,
        "typo_free": 1.0,
        "notes_questions": 0.0,  # 0 of 2 question groups (no notes)
    }


def test_same_item_in_another_message_is_not_matched() -> None:
    """Message 2 has the same words, but the gold mistake is in message 1."""
    case = replace(
        CASE,
        history=(("user", M1), ("user", "Ich habe ins Theater gegangen.")),
        mistakes=CASE.mistakes[:1],
        typos=(),
        neutrals=(),
        correct_messages=(),
    )
    wrong_message = item(
        2, "habe ... gegangen", "bin ... gegangen", "Ich habe ins Theater gegangen."
    )

    score = score_analysis(case, analysis(wrong_message))

    assert score.findings == ()
    assert score.extras == (wrong_message,)
    assert score.metrics["recall"] == 0.0  # 0 matched of 1


def test_two_items_for_one_gold_mistake_match_once_and_the_other_is_extra() -> None:
    first = item(1, "habe gegangen", "bin gegangen", M1)
    second = item(1, "habe", "bin", M1)

    score = score_analysis(CASE, analysis(first, second))

    assert score.extras == (second,)
    assert score.metrics["recall"] == pytest.approx(1 / 3)  # 1 matched of 3
    assert score.metrics["extras"] == 1.0


def test_gold_keyword_matches_whole_words_only() -> None:
    """The key "habe" is not the word "haben": a misquoted item is not matched."""
    misquoted = item(1, "haben ... gegangen", "bin ... gegangen", M1)

    score = score_analysis(CASE, analysis(misquoted))

    assert score.metrics["recall"] == 0.0  # 0 matched of 3
    assert score.extras == (misquoted,)


def test_neutral_token_matches_whole_words_only() -> None:
    """The neutral "das" (for "dass") is not the word "dasselbe".

    "dasselbe" -> "das gleiche" is a doubtful correction the model may report; it
    stays an extra for review instead of being absorbed as neutral.
    """
    sentence = "Ich glaube das wir haben dasselbe Hobby."
    case = replace(
        CASE,
        history=(("user", sentence),),
        mistakes=(
            GoldMistake(
                1,
                "wir haben",
                "hobby haben",
                frozenset({"word_order"}),
                "Verb am Ende im Nebensatz",
                "t1",
            ),
        ),
        typos=(),
        neutrals=(Neutral(1, "das", "t1"),),
        correct_messages=(),
    )
    doubtful = item(
        1, "dasselbe Hobby", "das gleiche Hobby", sentence, category="vocabulary"
    )

    score = score_analysis(case, analysis(doubtful))

    assert score.neutral == ()
    assert score.extras == (doubtful,)


# --- analysis: hard rules -------------------------------------------------------


def test_item_from_partner_text_and_number_out_of_range_are_a1() -> None:
    from_partner = item(1, "war gestern in Kino", "war gestern im Kino", M1)
    out_of_range = item(5, "habe", "bin", M1)

    score = score_analysis(CASE, analysis(from_partner, out_of_range))

    assert kinds(score) == ["A1", "A1"]
    assert score.extras == (from_partner, out_of_range)


def test_changed_sentence_is_a2() -> None:
    changed = item(1, "habe ... gegangen", "bin ... gegangen", "Ich bin ins Kino.")

    score = score_analysis(CASE, analysis(changed))

    assert kinds(score) == ["A2"]
    # Still matched: the rule breach does not hide the found mistake.
    assert score.metrics["recall"] == pytest.approx(1 / 3)


def test_sentence_with_an_added_final_period_is_not_a2() -> None:
    """The learner wrote no period; the model's `sentence` ends with one."""
    message = "Ich habe ins Kino gegangen"
    case = replace(
        CASE,
        history=(("user", message),),
        mistakes=CASE.mistakes[:1],
        typos=(),
        neutrals=(),
        correct_messages=(),
    )
    found = item(1, "habe ... gegangen", "bin ... gegangen", message + ".")

    score = score_analysis(case, analysis(found))

    assert score.findings == ()


def test_reported_typo_is_a3_and_not_an_extra() -> None:
    typo = item(2, "spanend", "spannend", M2, category="vocabulary")

    score = score_analysis(CASE, analysis(typo))

    assert kinds(score) == ["A3"]
    assert score.extras == ()
    assert score.metrics["typo_free"] == 0.0
    assert score.metrics["extras"] == 0.0


def test_item_in_a_correct_message_is_a4() -> None:
    in_correct = item(4, "bin ich nach Hause", "bin ich heim", M4)

    score = score_analysis(CASE, analysis(in_correct))

    assert kinds(score) == ["A4"]
    assert score.extras == (in_correct,)


def test_six_facts_and_nine_notes_are_two_a5() -> None:
    notes = tuple(f"Note {n}." for n in range(9))

    score = score_analysis(CASE, analysis(facts=6, notes=notes))

    assert kinds(score) == ["A5", "A5"]


def test_five_facts_and_eight_notes_are_within_the_limits() -> None:
    notes = tuple(f"Note {n}." for n in range(8))

    score = score_analysis(CASE, analysis(facts=5, notes=notes))

    assert score.findings == ()


def test_neutral_item_is_neither_extra_nor_violation() -> None:
    neutral = item(3, "das", "dass", M3)

    score = score_analysis(CASE, analysis(neutral))

    assert score.findings == ()
    assert score.neutral == (neutral,)
    assert score.extras == ()
    assert score.metrics["extras"] == 0.0


# --- analysis: metrics ----------------------------------------------------------


def test_category_accuracy_counts_right_wrong_and_borderline_categories() -> None:
    right = item(1, "habe", "bin", M1, category="grammar")
    wrong = item(2, "der Film", "den Film", M2, category="vocabulary")
    borderline = item(
        3,
        "er hat einen Preis gewonnen",
        "er einen Preis gewonnen hat",
        M3,
        category="word_order",
    )

    score = score_analysis(CASE, analysis(right, wrong, borderline))

    assert score.metrics["recall"] == 1.0  # 3 matched of 3
    # grammar in {grammar}, vocabulary not in {grammar}, word_order in
    # {word_order, grammar}: 2 of 3.
    assert score.metrics["category_accuracy"] == pytest.approx(2 / 3)


def test_borderline_mistake_accepts_its_second_category() -> None:
    borderline = item(
        3, "er hat einen Preis gewonnen", "er einen Preis gewonnen hat", M3
    )

    score = score_analysis(CASE, analysis(borderline))

    assert score.metrics["category_accuracy"] == 1.0  # grammar in {word_order, grammar}


def test_empty_list_has_zero_recall_no_violations_and_no_category_accuracy() -> None:
    score = score_analysis(CASE, analysis())

    assert score.findings == ()
    assert score.metrics["recall"] == 0.0  # 0 of 3
    assert score.metrics["category_accuracy"] is None  # 0 matched
    assert score.metrics["typo_free"] == 1.0


def test_notes_questions_counts_one_of_two_groups() -> None:
    notes = (
        "The partner asked about the learner's weekend.",
        "They talked about the cinema.",
    )

    score = score_analysis(CASE, analysis(notes=notes))

    assert score.metrics["notes_questions"] == 0.5  # "weekend" hit, film/movie not


# --- turn -----------------------------------------------------------------------

TURN = TurnCase(
    id="kino-turn",
    topic_key="bakery",
    history=(("assistant", "Was hast du gestern gemacht?"), ("user", M1)),
    wrong_form="habe ins Kino gegangen",
    correct_forms=("bist ins Kino gegangen", "bin ins Kino gegangen"),
    category="grammar",
    rule="Perfekt mit sein",
    source="t1",
)


def turn(reply: str, end_conversation: bool = False) -> TurnResult:
    return TurnResult(
        reply=reply,
        end_conversation=end_conversation,
        model="gpt-5.4",
        input_tokens=0,
        cached_input_tokens=0,
        output_tokens=0,
    )


def test_turn_with_the_correct_form_woven_in() -> None:
    score = score_turn(
        TURN, turn("Ah, du bist ins Kino gegangen! Welchen Film hast du gesehen?")
    )

    assert score.findings == ()
    assert score.metrics == {"recast": 1.0, "lecture_free": 1.0, "one_question": 1.0}


def test_turn_that_repeats_the_wrong_form_is_no_recast() -> None:
    score = score_turn(
        TURN, turn("Du habe ins Kino gegangen? Ich bin ins Kino gegangen.")
    )

    assert score.metrics["recast"] == 0.0


@pytest.mark.parametrize(
    ("reply", "markers"),
    [
        ("Richtig wäre: bin gegangen. Welchen Film?", ("richtig wäre",)),
        ("Es heißt „bin gegangen“. Und dann?", ("es heißt",)),
        ("With gegangen we use sein, that is grammar.", ("grammar",)),
        ("Auf Deutsch sagt man „bin gegangen“.", ("sagt man",)),
        # Prefix: the start of a compound.
        ("Hier brauchst du die Dativform: dem Mann.", ("Dativ",)),
        # Suffix: the end of a compound.
        ("Kleiner Tippfehler, aber kein Problem!", ("Fehler",)),
        # Phrases first, then prefixes.
        ("Im Nebensatz steht das Verb am Ende.", ("Verb", "Nebensatz")),
    ],
)
def test_turn_with_a_lecture_marker(reply: str, markers: tuple[str, ...]) -> None:
    score = score_turn(TURN, turn(reply))

    assert score.metrics["lecture_free"] == 0.0
    assert score.markers == markers


@pytest.mark.parametrize(
    "reply",
    [
        # A clarification request in a formal scene, not a lecture.
        "Sie meinen das Roggenbrot? Das ist heute ganz frisch.",
        # Hearsay, not a correction.
        "Man sagt, das Café am Markt ist sehr gut.",
        # "Perfekt" as "great".
        "Perfekt, dann sehen wir uns morgen!",
    ],
)
def test_natural_reply_is_not_a_lecture(reply: str) -> None:
    score = score_turn(TURN, turn(reply))

    assert score.markers == ()
    assert score.metrics["lecture_free"] == 1.0


def test_marker_inside_another_word_is_not_a_hit() -> None:
    """ "Fehler" is a marker, but "fehlerfrei" is not the word "Fehler"."""
    score = score_turn(TURN, turn("Du bist ins Kino gegangen, ein fehlerfreier Tag!"))

    assert score.markers == ()
    assert score.metrics["lecture_free"] == 1.0


def test_turn_with_two_questions() -> None:
    score = score_turn(
        TURN, turn("Du bist ins Kino gegangen? Welchen Film hast du gesehen?")
    )

    assert score.metrics["one_question"] == 0.0


def test_turn_that_ends_the_conversation_is_t1() -> None:
    score = score_turn(
        TURN, turn("Du bist ins Kino gegangen. Tschüss!", end_conversation=True)
    )

    assert kinds(score) == ["T1"]


# --- memory ---------------------------------------------------------------------

MEMORY = MemoryCase(
    id="kino-memory",
    topic_key="bakery",
    scene_notes=(("The partner asked which film the learner saw.",),),
    forbidden=(("welchen Film", "welcher Film"), ("Lieblingsfilm",)),
)


def test_memory_reply_that_asks_a_question_again() -> None:
    score = score_memory(MEMORY, turn("Hallo! Welchen Film hast du gesehen?"))

    assert score.metrics == {"no_repeat": 0.0}
    assert score.findings == ()


def test_memory_reply_with_a_new_question() -> None:
    score = score_memory(MEMORY, turn("Schön, dich wiederzusehen! Wie war die Woche?"))

    assert score.metrics == {"no_repeat": 1.0}


def test_memory_reply_that_ends_the_conversation_is_t1() -> None:
    score = score_memory(MEMORY, turn("Hallo und tschüss!", end_conversation=True))

    assert kinds(score) == ["T1"]


# --- aggregation and comparison -------------------------------------------------


def test_aggregate_three_repetitions() -> None:
    summary = aggregate(
        {
            "a": [
                Score({"recall": 1.0, "category_accuracy": 1.0}),
                Score(
                    {"recall": 0.5, "category_accuracy": None},
                    findings=(Finding("A3", "typo"),),
                ),
                Score({"recall": 0.0, "category_accuracy": 0.5}),
            ],
            "b": [
                Score({"recall": 0.25, "category_accuracy": None}),
                Score({"recall": 0.25, "category_accuracy": None}),
                Score({"recall": 0.25, "category_accuracy": None}),
            ],
        }
    )

    assert summary.cases == {
        "a": {
            "recall": 0.5,  # (1.0 + 0.5 + 0.0) / 3
            "category_accuracy": 0.75,  # (1.0 + 0.5) / 2, None skipped
        },
        "b": {"recall": 0.25, "category_accuracy": None},  # all None
    }
    assert summary.run == {
        "recall": 0.375,  # (0.5 + 0.25) / 2
        "category_accuracy": 0.75,  # only case a has a value
    }
    assert summary.violations == (Violation("A3", "a", 2, "typo"),)


def test_compare_pairs_cases_and_gives_the_interval_and_verdict() -> None:
    a = {
        "c1": {"recall": 0.0, "typo_free": 0.5, "category_accuracy": 0.5},
        "c2": {"recall": 0.25, "typo_free": 1.0, "category_accuracy": None},
        "c3": {"recall": 0.0, "typo_free": 1.0},
        "only_a": {"recall": 1.0},
    }
    b = {
        "c1": {"recall": 0.25, "typo_free": 1.0, "category_accuracy": 1.0},
        "c2": {"recall": 0.75, "typo_free": 1.0, "category_accuracy": 1.0},
        "c3": {"recall": 0.75, "typo_free": 0.75},
        "only_b": {"recall": 0.0},
    }

    result = compare(a, b)

    assert result.only_in_a == ("only_a",)
    assert result.only_in_b == ("only_b",)
    by_name = {m.metric: m for m in result.metrics}

    # recall deltas 0.25, 0.5, 0.75: mean 0.5; squared deviations 0.0625, 0,
    # 0.0625, sum 0.125 / (3 - 1) = 0.0625, stdev 0.25, SE 0.25 / sqrt(3) =
    # 0.144338; 0.5 -+ 1.96 * 0.144338 = [0.217098, 0.782902], zero outside.
    recall = by_name["recall"]
    assert recall.n == 3
    assert recall.mean_a == pytest.approx(0.25 / 3)  # (0 + 0.25 + 0) / 3
    assert recall.mean_b == pytest.approx(1.75 / 3)  # (0.25 + 0.75 + 0.75) / 3
    assert recall.mean_delta == pytest.approx(0.5)
    assert recall.se == pytest.approx(0.144338, abs=1e-6)
    assert recall.low == pytest.approx(0.217098, abs=1e-6)
    assert recall.high == pytest.approx(0.782902, abs=1e-6)
    assert recall.verdict == VERDICT_DIFFERENCE
    assert recall.changed == (("c3", 0.75), ("c2", 0.5), ("c1", 0.25))

    # typo_free deltas 0.5, 0, -0.25: mean 0.25 / 3 = 0.083333; squared deviations
    # 0.173611, 0.006944, 0.111111, sum 0.291667 / 2 = 0.145833, stdev 0.381881,
    # SE 0.381881 / sqrt(3) = 0.220479; 0.083333 -+ 0.432139 = [-0.348806,
    # 0.515473] contains zero.
    typo_free = by_name["typo_free"]
    assert typo_free.mean_delta == pytest.approx(0.25 / 3)
    assert typo_free.se == pytest.approx(0.220479, abs=1e-6)
    assert typo_free.low == pytest.approx(-0.348806, abs=1e-6)
    assert typo_free.high == pytest.approx(0.515473, abs=1e-6)
    assert typo_free.verdict == VERDICT_NOISE
    assert typo_free.changed == (("c1", 0.5), ("c3", -0.25))

    # category_accuracy has a value in both runs only for c1: one pair, no SE.
    category = by_name["category_accuracy"]
    assert category.n == 1
    assert category.mean_delta == 0.5  # 1.0 - 0.5
    assert category.se is None
    assert category.verdict == VERDICT_NOISE


# --- cost meter -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def pinned_prices(settings) -> None:
    settings.LLM_PRICES_USD_PER_MTOK = {
        "gpt-5.4": {
            "input": Decimal("2.50"),
            "cached_input": Decimal("0.25"),
            "output": Decimal("15.00"),
        }
    }
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_ANALYSIS_COST_ESTIMATE_USD = Decimal("0.07")


def test_meter_counts_results_and_errors_like_the_app() -> None:
    meter = CostMeter(Decimal("5"))
    result = replace(
        turn("Hallo"), input_tokens=1000, cached_input_tokens=400, output_tokens=200
    )
    with_usage = LLMError(
        "no usable answer",
        usage=CallUsage(
            model="gpt-5.4",
            input_tokens=1200,
            cached_input_tokens=1000,
            output_tokens=40,
        ),
    )

    # 600 * 2.50 + 400 * 0.25 + 200 * 15.00 = 4600 per 1M = 0.0046
    assert meter.charge_result(result) == Decimal("0.0046")
    # 200 * 2.50 + 1000 * 0.25 + 40 * 15.00 = 1350 per 1M = 0.00135
    assert meter.charge_error(with_usage, "turn") == Decimal("0.00135")
    # Billed without usage: the analysis estimate.
    assert meter.charge_error(
        LLMError("timeout", billed_without_usage=True), "analysis"
    ) == Decimal("0.07")
    # Billed without usage: the turn estimate.
    assert meter.charge_error(
        LLMError("timeout", billed_without_usage=True), "turn"
    ) == Decimal("0.03")
    # Refused at once: nothing.
    assert meter.charge_error(LLMError("refused"), "analysis") == Decimal(0)
    # 0.0046 + 0.00135 + 0.07 + 0.03 + 0 = 0.10595
    assert meter.spent == Decimal("0.10595")


def test_call_may_start_when_it_reaches_the_cap_exactly() -> None:
    meter = CostMeter(Decimal("0.10"))
    meter.charge_error(LLMError("timeout", billed_without_usage=True), "turn")

    # 0.03 spent + 0.07 analysis estimate = 0.10 <= 0.10
    assert meter.can_start("analysis")


def test_call_may_not_start_when_it_would_pass_the_cap() -> None:
    meter = CostMeter(Decimal("0.099999"))
    meter.charge_error(LLMError("timeout", billed_without_usage=True), "turn")

    # 0.03 spent + 0.07 analysis estimate = 0.10 > 0.099999
    assert not meter.can_start("analysis")
    # 0.03 spent + 0.03 turn estimate = 0.06 <= 0.099999
    assert meter.can_start("turn")
