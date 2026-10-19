"""Deterministic scoring of the AI eval (no model, no database).

From a model result and its golden case it finds the hard-rule violations and the
per-case metrics, aggregates the repetitions of a run and compares two runs case by
case.

- Analysis (`score_analysis`): each reported mistake is matched to the first still
  unmatched `GoldMistake` with the same message number whose keywords occur as whole
  words in its `wrong` and `correct` (one item to one gold mistake); typo and
  neutral tokens are found the same way. Hard rules from
  the analysis prompt (`conversations/llm.py`, `_ANALYSIS_INSTRUCTIONS`): A1 the
  message number is outside `1..N` or the words of `wrong` are not in that learner
  message (nothing from the partner), A2 `sentence` is not a fragment of that learner
  message, A3 an unmatched item contains a known typo of that message, A4 an item in
  a message without mistakes, A5 more than 5 learner facts or more than 8 scene
  notes. Other unmatched items are neutral (they contain a `Neutral` token) or
  extras (listed for review).
- Turn (`score_turn`): a correct form is woven into the reply and no wrong form
  (the learner's own or its echo) is repeated (recast), no lecture markers, at most one question; T1 the turn ends
  the conversation. Lecture markers are metalinguistic terms and phrases of explicit
  correction (the feedback types of Lyster and Ranta 1997: recast vs explicit
  correction vs metalinguistic feedback): phrases as whole words, grammar terms also
  at the start of a compound ("Dativform"), "Fehler" also at its end ("Tippfehler").
- Memory (`score_memory`): no question from the scene notes is asked again; T1.

A metric is a float (a share or a count), `None` when it cannot be computed (e.g.
category accuracy without any matched item).
"""

import math
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from conversations.llm import AnalysisResult, FoundMistake, TurnResult

from .golden import AnalysisCase, GoldMistake, History, MemoryCase, TurnCase

# Limits from the analysis prompt ("at most 5", "at most 8").
MAX_LEARNER_FACTS = 5
MAX_SCENE_NOTES = 8

# Two-sided 95% interval of the paired mean difference.
INTERVAL_Z = 1.96
VERDICT_DIFFERENCE = "difference"
VERDICT_NOISE = "within noise"

# Metalinguistic terms and explicit-correction phrases, German and English. A proxy:
# a hit is a signal for review, not proof of a lecture. Left out on purpose because
# a natural partner reply uses them: "du meinst" / "Sie meinen" (a clarification
# request, "Sie meinen das Roggenbrot?"), "man sagt" ("Man sagt, das Café ist gut"),
# a bare "Perfekt" ("Perfekt, bis morgen!").
# Matched as whole words or phrases.
LECTURE_MARKERS: tuple[str, ...] = (
    "es heißt",
    "richtig wäre",
    "richtig heißt es",
    "besser wäre",
    "korrekt wäre",
    "sagt man",
    "man sagt nicht",
    "auf Deutsch heißt es",
    "du meinst wohl",
    "Sie meinen wohl",
    "die richtige Form",
    "die korrekte Form",
    "im Perfekt",
    "Perfekt mit",
    "Verb",
    "Verben",
    "Endung",
    "Plural",
    "Singular",
    "grammar",
    "mistake",
    "correct form",
    "you mean",
    "should be",
    "word order",
    "tense",
)
# Matched at the start of a word, so compounds count too ("Dativform",
# "Akkusativobjekt", "grammatikalisch"; English "dative" via "Dativ").
LECTURE_PREFIXES: tuple[str, ...] = (
    "Grammatik",
    "Dativ",
    "Akkusativ",
    "Genitiv",
    "Nominativ",
    "Konjunktiv",
    "Präteritum",
    "Partizip",
    "Hilfsverb",
    "Präposition",
    "Konjugation",
    "Korrektur",
    "korrigier",
    "Nebensatz",
    "Nebensätze",
    "Wortstellung",
    "Satzstellung",
)
# Matched at the end of a word ("Grammatikfehler", "Tippfehler"; not "fehlerfrei").
LECTURE_SUFFIXES: tuple[str, ...] = ("Fehler",)

Metrics = dict[str, float | None]
# Case id -> metric name -> value (one run, aggregated over its repetitions).
CaseMetrics = Mapping[str, Mapping[str, float | None]]


@dataclass(frozen=True)
class Finding:
    """A hard-rule violation in one scored result."""

    kind: str
    detail: str


@dataclass(frozen=True)
class Score:
    """The score of one repetition of one case."""

    metrics: Metrics
    findings: tuple[Finding, ...] = ()
    # Unmatched analysis items that are neither a reported typo nor neutral.
    extras: tuple[FoundMistake, ...] = ()
    neutral: tuple[FoundMistake, ...] = ()
    # Lecture markers found in a turn reply, for review.
    markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    kind: str
    case_id: str
    # 1 for the first repetition.
    repetition: int
    detail: str


@dataclass(frozen=True)
class Summary:
    """One series of a run: per-case means of the repetitions and the run mean."""

    cases: dict[str, Metrics]
    run: Metrics
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class MetricComparison:
    metric: str
    # Cases with a value in both runs.
    n: int
    mean_a: float | None
    mean_b: float | None
    mean_delta: float | None
    # Standard error of the mean difference; `None` below two cases.
    se: float | None
    low: float | None
    high: float | None
    verdict: str
    # (case id, b - a) for every case whose value changed, largest change first.
    changed: tuple[tuple[str, float], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Comparison:
    metrics: tuple[MetricComparison, ...]
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]


def normalize(text: str) -> str:
    """Case folded, whitespace collapsed, without the gap marks `...` / `…`."""
    without_gaps = text.replace("…", " ").replace("...", " ")
    return " ".join(without_gaps.casefold().split())


def contains_phrase(text: str, phrase: str) -> bool:
    """Whether the normalised `phrase` occurs in `text` as whole words."""
    needle = normalize(phrase)
    if not needle:
        return False
    pattern = rf"(?<!\w){re.escape(needle)}(?!\w)"
    return re.search(pattern, normalize(text)) is not None


def lecture_markers(reply: str) -> tuple[str, ...]:
    """The lecture markers in `reply`: phrases, then prefixes, then suffixes."""
    text = normalize(reply)
    return (
        tuple(marker for marker in LECTURE_MARKERS if contains_phrase(reply, marker))
        + tuple(
            prefix
            for prefix in LECTURE_PREFIXES
            if re.search(rf"(?<!\w){re.escape(normalize(prefix))}", text)
        )
        + tuple(
            suffix
            for suffix in LECTURE_SUFFIXES
            if re.search(rf"{re.escape(normalize(suffix))}(?!\w)", text)
        )
    )


def learner_messages(history: History) -> list[str]:
    """The learner's messages in order; message number n is index n - 1."""
    return [text for role, text in history if role != "assistant"]


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", normalize(text)))


def _fragment(sentence: str) -> str:
    """`sentence` normalised, without the end punctuation the model may add."""
    return normalize(sentence).rstrip(".!?")


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _matches(gold: GoldMistake, item: FoundMistake) -> bool:
    return (
        gold.message == item.message_number
        and contains_phrase(item.wrong, gold.wrong_key)
        and contains_phrase(item.correct, gold.correct_key)
    )


def _match(
    golds: Sequence[GoldMistake], items: Sequence[FoundMistake]
) -> dict[int, GoldMistake]:
    """Item index -> its gold mistake; each gold mistake matches at most one item."""
    taken: set[int] = set()
    matched: dict[int, GoldMistake] = {}
    for index, item in enumerate(items):
        for gold_index, gold in enumerate(golds):
            if gold_index not in taken and _matches(gold, item):
                taken.add(gold_index)
                matched[index] = gold
                break
    return matched


def score_analysis(case: AnalysisCase, result: AnalysisResult) -> Score:
    messages = learner_messages(case.history)
    matched = _match(case.mistakes, result.mistakes)
    findings: list[Finding] = []
    extras: list[FoundMistake] = []
    neutral: list[FoundMistake] = []
    for index, item in enumerate(result.mistakes):
        number = item.message_number
        label = f"item {index + 1} (message {number}, wrong {item.wrong!r})"
        if not 1 <= number <= len(messages):
            findings.append(
                Finding("A1", f"{label}: message number outside 1..{len(messages)}")
            )
            extras.append(item)
            continue
        message = messages[number - 1]
        if not _words(item.wrong) <= _words(message):
            findings.append(Finding("A1", f"{label}: words not in the message"))
        if _fragment(item.sentence) not in normalize(message):
            findings.append(Finding("A2", f"{label}: sentence not in the message"))
        if number in case.correct_messages:
            findings.append(Finding("A4", f"{label}: the message has no mistakes"))
        if index in matched:
            continue
        typos = [typo for typo in case.typos if typo.message == number]
        neutrals = [token for token in case.neutrals if token.message == number]
        if any(contains_phrase(item.wrong, typo.token) for typo in typos):
            findings.append(Finding("A3", f"{label}: reports a typo"))
        elif any(contains_phrase(item.wrong, token.token) for token in neutrals):
            neutral.append(item)
        else:
            extras.append(item)
    if len(result.learner_facts) > MAX_LEARNER_FACTS:
        findings.append(
            Finding("A5", f"{len(result.learner_facts)} learner facts (at most 5)")
        )
    if len(result.scene_notes) > MAX_SCENE_NOTES:
        findings.append(
            Finding("A5", f"{len(result.scene_notes)} scene notes (at most 8)")
        )

    right_category = sum(
        1
        for index, gold in matched.items()
        if result.mistakes[index].category in gold.categories
    )
    found_questions = sum(
        1
        for group in case.partner_questions
        if any(
            contains_phrase(note, keyword)
            for note in result.scene_notes
            for keyword in group
        )
    )
    metrics: Metrics = {
        "recall": _ratio(len(matched), len(case.mistakes)),
        "category_accuracy": _ratio(right_category, len(matched)),
        "extras": float(len(extras)),
        "typo_free": 0.0 if any(f.kind == "A3" for f in findings) else 1.0,
        "notes_questions": _ratio(found_questions, len(case.partner_questions)),
    }
    return Score(
        metrics=metrics,
        findings=tuple(findings),
        extras=tuple(extras),
        neutral=tuple(neutral),
    )


def _ended(result: TurnResult) -> tuple[Finding, ...]:
    if result.end_conversation:
        return (Finding("T1", "end_conversation is true"),)
    return ()


def score_turn(case: TurnCase, result: TurnResult) -> Score:
    reply = result.reply
    recast = any(
        contains_phrase(reply, form) for form in case.correct_forms
    ) and not any(contains_phrase(reply, form) for form in case.wrong_forms)
    markers = lecture_markers(reply)
    metrics: Metrics = {
        "recast": 1.0 if recast else 0.0,
        "lecture_free": 0.0 if markers else 1.0,
        "one_question": 1.0 if reply.count("?") <= 1 else 0.0,
    }
    return Score(metrics=metrics, findings=_ended(result), markers=markers)


def score_memory(case: MemoryCase, result: TurnResult) -> Score:
    repeated = [
        group
        for group in case.forbidden
        if any(contains_phrase(result.reply, keyword) for keyword in group)
    ]
    metrics: Metrics = {"no_repeat": 0.0 if repeated else 1.0}
    return Score(metrics=metrics, findings=_ended(result))


def _mean(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def aggregate(scores: Mapping[str, Sequence[Score]]) -> Summary:
    """`scores` maps a case id to the scores of its repetitions, the first first."""
    cases: dict[str, Metrics] = {}
    violations: list[Violation] = []
    for case_id, repetitions in scores.items():
        names = dict.fromkeys(name for s in repetitions for name in s.metrics)
        cases[case_id] = {
            name: _mean(s.metrics.get(name) for s in repetitions) for name in names
        }
        for repetition, score in enumerate(repetitions, start=1):
            violations.extend(
                Violation(f.kind, case_id, repetition, f.detail) for f in score.findings
            )
    names = dict.fromkeys(name for metrics in cases.values() for name in metrics)
    run = {name: _mean(m.get(name) for m in cases.values()) for name in names}
    return Summary(cases=cases, run=run, violations=tuple(violations))


def _compare_metric(
    name: str, a: CaseMetrics, b: CaseMetrics, common: Sequence[str]
) -> MetricComparison:
    pairs: list[tuple[str, float, float]] = []
    for case_id in common:
        value_a = a[case_id].get(name)
        value_b = b[case_id].get(name)
        if value_a is not None and value_b is not None:
            pairs.append((case_id, value_a, value_b))
    n = len(pairs)
    if n == 0:
        return MetricComparison(
            name, 0, None, None, None, None, None, None, VERDICT_NOISE
        )
    deltas = [value_b - value_a for _, value_a, value_b in pairs]
    mean_delta = statistics.fmean(deltas)
    se = statistics.stdev(deltas) / math.sqrt(n) if n >= 2 else None
    low = mean_delta - INTERVAL_Z * se if se is not None else None
    high = mean_delta + INTERVAL_Z * se if se is not None else None
    difference = low is not None and high is not None and (low > 0 or high < 0)
    changed = sorted(
        (
            (case_id, delta)
            for (case_id, _, _), delta in zip(pairs, deltas, strict=True)
            if delta != 0
        ),
        key=lambda pair: (-abs(pair[1]), pair[0]),
    )
    return MetricComparison(
        metric=name,
        n=n,
        mean_a=statistics.fmean(value_a for _, value_a, _ in pairs),
        mean_b=statistics.fmean(value_b for _, _, value_b in pairs),
        mean_delta=mean_delta,
        se=se,
        low=low,
        high=high,
        verdict=VERDICT_DIFFERENCE if difference else VERDICT_NOISE,
        changed=tuple(changed),
    )


def compare(a: CaseMetrics, b: CaseMetrics) -> Comparison:
    """Paired comparison of two runs: for each metric, b - a over the shared cases."""
    common = [case_id for case_id in a if case_id in b]
    names = dict.fromkeys(
        name for run in (a, b) for case_id in common for name in run[case_id]
    )
    return Comparison(
        metrics=tuple(_compare_metric(name, a, b, common) for name in names),
        only_in_a=tuple(case_id for case_id in a if case_id not in b),
        only_in_b=tuple(case_id for case_id in b if case_id not in a),
    )
