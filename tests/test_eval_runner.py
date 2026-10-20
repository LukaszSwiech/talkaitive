"""The AI eval script (scripts/eval/run_eval.py) without a model or network.

`llm.generate_turn` / `llm.analyze_mistakes` are replaced in every test: by stand-ins
that fail when called (the script must not reach the model without a real key), or
by fakes with a known token usage (the cost cap). Prices are pinned as in
test-plan §6.4 (gpt-5.4 per 1M tokens: input 2.50, cached input 0.25, output 15.00;
estimates 0.03 per turn and 0.07 per analysis). Expected numbers are hand-written
with the arithmetic in a comment.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from conversations import llm
from conversations.llm import AnalysisResult, LLMError, TurnResult
from scripts.eval import golden
from scripts.eval.run_eval import main, result_filename
from tests.fakes import FakeAnalyzeMistakes, FakeGenerateTurn


@pytest.fixture(autouse=True)
def pinned_prices(settings) -> None:
    settings.LLM_MODEL = "gpt-5.4"
    settings.LLM_PRICES_USD_PER_MTOK = {
        "gpt-5.4": {
            "input": Decimal("2.50"),
            "cached_input": Decimal("0.25"),
            "output": Decimal("15.00"),
        }
    }
    settings.LLM_TURN_COST_ESTIMATE_USD = Decimal("0.03")
    settings.LLM_ANALYSIS_COST_ESTIMATE_USD = Decimal("0.07")


@pytest.fixture
def real_looking_key(settings) -> None:
    """Any value but the test one passes the guard; the fakes stop real calls."""
    settings.OPENAI_API_KEY = "sk-eval-runner-test"


def analysis_result(input_tokens: int) -> AnalysisResult:
    return AnalysisResult(
        mistakes=[],
        learner_facts=[],
        scene_notes=[],
        model="gpt-5.4",
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=0,
    )


def turn_result(
    reply: str = "Hallo! Was darf es sein?", end_conversation: bool = False
) -> TurnResult:
    return TurnResult(
        reply=reply,
        end_conversation=end_conversation,
        model="gpt-5.4",
        input_tokens=4000,
        cached_input_tokens=0,
        output_tokens=0,
    )


def fail_if_called(**kwargs: Any) -> Any:
    raise AssertionError("the eval called the model")


def test_run_under_test_settings_stops_before_any_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """settings_test sets OPENAI_API_KEY = "test-key": exit 2, no call, no file."""
    monkeypatch.setattr(llm, "generate_turn", fail_if_called)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"

    assert main(["run", "--out", str(out)]) == 2
    assert not out.exists()


def test_run_without_a_key_stops_before_any_call(
    monkeypatch: pytest.MonkeyPatch, settings, tmp_path: Path
) -> None:
    settings.OPENAI_API_KEY = ""
    monkeypatch.setattr(llm, "generate_turn", fail_if_called)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)

    assert main(["run", "--out", str(tmp_path / "result.json")]) == 2


@pytest.mark.usefixtures("real_looking_key")
def test_cost_cap_stops_the_run_before_it_is_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 10,000 input tokens * 2.50 per 1M = 0.025 USD per analysis.
    analyze = FakeAnalyzeMistakes(lambda: analysis_result(10_000))
    turn = FakeGenerateTurn(turn_result)
    monkeypatch.setattr(llm, "analyze_mistakes", analyze)
    monkeypatch.setattr(llm, "generate_turn", turn)
    out = tmp_path / "result.json"

    code = main(
        [
            "run",
            "--suite",
            "analysis,turn",
            "--repeats",
            "1",
            "--max-usd",
            "0.10",
            "--out",
            str(out),
        ]
    )

    # Before call 1: 0 + 0.07 <= 0.10, spent 0.025; before call 2: 0.025 + 0.07 =
    # 0.095 <= 0.10, spent 0.05; before call 3: 0.05 + 0.07 = 0.12 > 0.10, stop.
    assert code == 2
    assert len(analyze.calls) == 2
    assert turn.calls == []
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["complete"] is False
    assert Decimal(result["spent_usd"]) == Decimal("0.05")
    assert Decimal(result["max_usd"]) == Decimal("0.10")
    assert len(result["calls"]["analysis"]) == 2
    assert "CC BY-SA 4.0" in result["data_licence"]
    assert "sk-eval-runner-test" not in out.read_text(encoding="utf-8")


@pytest.mark.usefixtures("real_looking_key")
def test_complete_run_without_violations_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    turn = FakeGenerateTurn(turn_result)
    monkeypatch.setattr(llm, "generate_turn", turn)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"

    code = main(["run", "--suite", "memory", "--repeats", "1", "--out", str(out)])

    assert code == 0
    assert len(turn.calls) == len(golden.MEMORY_CASES)
    # The memory block carries the case's scene notes; the turn opens the scene.
    first = turn.calls[0]
    assert first["history"] == []
    assert golden.MEMORY_CASES[0].scene_notes[0][0] in first["memory"]
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["complete"] is True
    # "Hallo! Was darf es sein?" asks none of the forbidden questions.
    assert result["aggregate"]["memory"]["run"] == {"no_repeat": 1.0}


@pytest.mark.usefixtures("real_looking_key")
def test_failed_call_is_charged_and_recorded_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    turn = FakeGenerateTurn(turn_result)
    turn.outcomes.append(LLMError("timeout", billed_without_usage=True))
    monkeypatch.setattr(llm, "generate_turn", turn)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"

    code = main(["run", "--suite", "memory", "--repeats", "1", "--out", str(out)])

    assert code == 1
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["complete"] is True
    first_case = golden.MEMORY_CASES[0].id
    assert result["errors"] == [
        {"series": "memory", "case": first_case, "repetition": 1, "error": "timeout"}
    ]
    # The failed call at the turn estimate 0.03, then 4 calls of 4,000 input tokens
    # * 2.50 per 1M = 0.01 each: 0.03 + 4 * 0.01 = 0.07.
    assert Decimal(result["spent_usd"]) == Decimal("0.07")


@pytest.mark.usefixtures("real_looking_key")
def test_existing_result_file_is_not_overwritten_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A rerun on the same day and commit must not replace the committed baseline."""
    monkeypatch.setattr(llm, "generate_turn", fail_if_called)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"
    out.write_text("baseline", encoding="utf-8")

    assert main(["run", "--suite", "memory", "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "baseline"


@pytest.mark.usefixtures("real_looking_key")
def test_interrupted_run_keeps_the_partial_result_and_reraises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ctrl-C or a bug mid-run must not lose the calls already paid for."""
    turn = FakeGenerateTurn(turn_result)
    turn.outcomes.extend([turn_result(), RuntimeError("bug")])
    monkeypatch.setattr(llm, "generate_turn", turn)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"

    with pytest.raises(RuntimeError, match="bug"):
        main(["run", "--suite", "memory", "--repeats", "1", "--out", str(out)])

    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["complete"] is False
    assert len(result["calls"]["memory"]) == 1
    # One call of 4,000 input tokens * 2.50 per 1M = 0.01.
    assert Decimal(result["spent_usd"]) == Decimal("0.01")


@pytest.mark.usefixtures("real_looking_key")
def test_turn_that_ends_the_conversation_is_a_violation_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    turn = FakeGenerateTurn(lambda: turn_result(end_conversation=True))
    monkeypatch.setattr(llm, "generate_turn", turn)
    monkeypatch.setattr(llm, "analyze_mistakes", fail_if_called)
    out = tmp_path / "result.json"

    code = main(["run", "--suite", "memory", "--repeats", "1", "--out", str(out)])

    assert code == 1
    result = json.loads(out.read_text(encoding="utf-8"))
    kinds = {v["kind"] for v in result["aggregate"]["memory"]["violations"]}
    assert kinds == {"T1"}


def test_result_filename_has_date_model_commit_and_dirty() -> None:
    assert (
        result_filename(date(2026, 10, 18), "gpt-5.4", "0d1845f", dirty=True)
        == "2026-10-18-gpt-5.4-0d1845f-dirty.json"
    )
    assert (
        result_filename(date(2026, 10, 18), "gpt-5.4", "0d1845f", dirty=False)
        == "2026-10-18-gpt-5.4-0d1845f.json"
    )


# --- compare --------------------------------------------------------------------


def write_result(
    path: Path, recast: dict[str, float], instructions_hash: str = "aaa"
) -> Path:
    path.write_text(
        json.dumps(
            {
                "model": "gpt-5.4",
                "commit": "0d1845f",
                "prompt_sha256": {
                    "turn_instructions": instructions_hash,
                    "analysis_instructions": "bbb",
                    "memory_block": "ccc",
                },
                "aggregate": {
                    "turn": {
                        "cases": {
                            case_id: {"recast": value}
                            for case_id, value in recast.items()
                        },
                        "run": {},
                        "violations": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_compare_prints_the_paired_difference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_result(tmp_path / "a.json", {"t1": 0.0, "t2": 0.5, "t3": 1.0})
    b = write_result(tmp_path / "b.json", {"t1": 1.0, "t2": 1.0, "t3": 1.0}, "ddd")

    assert main(["compare", str(a), str(b)]) == 0

    out = capsys.readouterr().out
    line = next(row for row in out.splitlines() if "| recast" in row)
    # Deltas 1.0, 0.5, 0.0: mean 0.5; stdev 0.5, SE 0.5 / sqrt(3) = 0.288675;
    # 0.5 -+ 1.96 * 0.288675 = [-0.065803, 1.065803], zero inside.
    assert "+0.500" in line
    assert "[-0.066, +1.066]" in line
    assert "within noise" in line
    assert "turn/recast t1: +1.000" in out
    assert "same model and same prompt hashes" not in out


def test_compare_warns_about_same_version_and_different_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = write_result(tmp_path / "a.json", {"t1": 0.0, "t2": 1.0})
    b = write_result(tmp_path / "b.json", {"t1": 1.0, "t3": 1.0})

    assert main(["compare", str(a), str(b)]) == 0

    out = capsys.readouterr().out
    assert "same model and same prompt hashes" in out
    assert "only in A: t2; only in B: t3" in out


def test_compare_with_a_bad_file_exits_2(tmp_path: Path) -> None:
    good = write_result(tmp_path / "a.json", {"t1": 1.0})
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    foreign = tmp_path / "foreign.json"
    foreign.write_text(json.dumps({"something": "else"}), encoding="utf-8")

    assert main(["compare", str(good), str(broken)]) == 2
    assert main(["compare", str(good), str(foreign)]) == 2
    assert main(["compare", str(good), str(tmp_path / "missing.json")]) == 2
