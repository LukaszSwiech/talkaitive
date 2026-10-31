"""The AI review script: every exit path, with fakes and a throwaway git repo.

No network and no real key: the SDK client is replaced by `FakeOpenAI`, or runs on
the scripted transport of `tests/fake_provider.py`.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openai
import pydantic
import pytest

from scripts.review import run_review
from scripts.review.criteria import CRITERIA, FAIL_FLOOR, Review
from tests.fake_provider import FakeProvider

REPO = Path(__file__).resolve().parents[1]
# CI has no git identity, and a user's global config may sign commits.
GIT_IDENTITY = (
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.test",
    "-c",
    "commit.gpgsign=false",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ci.yml` runs pytest inside Actions, and a git hook sets the `GIT_*` vars."""
    for name in ("GITHUB_OUTPUT", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *GIT_IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def make_merge_repo(path: Path, files: Mapping[str, str]) -> Path:
    """A repo whose HEAD merges a branch adding `files` into `main`."""
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    (path / "base.txt").write_text("base\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "base")
    git(path, "switch", "-q", "-c", "feature")
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "feature")
    git(path, "switch", "-q", "main")
    (path / "main.txt").write_text("main moved on\n")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "main")
    git(path, "merge", "-q", "--no-ff", "-m", "merge", "feature")
    return path


# --- diff ---------------------------------------------------------------------------


def test_diff_leaves_out_lockfiles_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_merge_repo(
        tmp_path / "repo",
        {
            "uv.lock": "locked\n",
            "package-lock.json": "{}\n",
            "context/notes.md": "notes\n",
            "conversations/views.py": "reviewed = True\n",
        },
    )
    monkeypatch.chdir(repo)

    diff = run_review.read_diff()

    assert "conversations/views.py" in diff
    assert "reviewed = True" in diff
    assert "uv.lock" not in diff
    assert "package-lock.json" not in diff
    assert "context/notes.md" not in diff
    # Only the PR's side of the merge, not what `main` did meanwhile.
    assert "main.txt" not in diff


def test_depth_2_clone_of_a_merge_is_shallow_and_gives_the_same_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_merge_repo(tmp_path / "repo", {"app.py": "x = 1\n"})
    clone = tmp_path / "clone"
    # `file://` matters: a plain local path ignores `--depth`.
    subprocess.run(
        ["git", "clone", "-q", "--depth", "2", f"file://{repo}", str(clone)],
        check=True,
        capture_output=True,
    )
    assert git(clone, "rev-parse", "--is-shallow-repository").strip() == "true"
    monkeypatch.chdir(repo)
    expected = run_review.read_diff()

    monkeypatch.chdir(clone)

    assert run_review.read_diff() == expected
    assert "app.py" in expected


def test_diff_decodes_invalid_utf8_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_merge_repo(tmp_path / "repo", {"app.py": "x = 1\n"})
    (repo / "latin1.py").write_bytes(b"name = 'caf\xe9'\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "latin1")
    monkeypatch.chdir(repo)

    assert "caf�" in run_review.read_diff()


def test_diff_over_the_cap_is_cut_and_names_the_dropped_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_merge_repo(
        tmp_path / "repo",
        {
            "a_small.py": "a = 1\n",
            "b_big.py": "b = 1\n" * 20_000,
            "c_after.py": "c = 1\n",
            "d_after.py": "d = 1\n",
        },
    )
    monkeypatch.chdir(repo)

    kept, dropped = run_review.truncate_diff(run_review.read_diff())

    assert len(kept) == run_review.MAX_DIFF_CHARS
    assert "a_small.py" in kept
    assert "c_after.py" not in kept
    # `a_small.py` is whole; `b_big.py` is the one the cut falls inside.
    assert dropped == ["b_big.py", "c_after.py", "d_after.py"]


def test_diff_within_the_cap_is_untouched() -> None:
    diff = "diff --git a/x.py b/x.py\n+x = 1\n"

    assert run_review.truncate_diff(diff) == (diff, [])


def test_dropped_paths_with_spaces_and_renames_are_named() -> None:
    filler = "+x\n" * run_review.MAX_DIFF_CHARS
    diff = (
        f"diff --git a/first.py b/first.py\n{filler}"
        "diff --git a/with space.py b/with space.py\n+y\n"
        "diff --git a/old.py b/new.py\n+z\n"
    )

    _, dropped = run_review.truncate_diff(diff)

    assert dropped == ["first.py", "with space.py", "new.py"]


# --- comment and sanitising ---------------------------------------------------------


def make_review(
    verdict: str = "pass",
    *,
    summary: str = "Looks fine.",
    rationale: str = "why",
    **scores: int,
) -> Review:
    """A review with every criterion at 9, except the `scores` given."""
    fields: dict[str, Any] = {
        name: {"score": scores.get(name, 9), "rationale": rationale}
        for name in CRITERIA
    }
    return Review(**fields, verdict=verdict, summary=summary)


HOSTILE = "cc @octocat ![x](http://evil) <img src=x> <!-- hidden -->"


def assert_neutralised(text: str) -> None:
    assert "@octocat" not in text
    assert "![" not in text
    assert "<" not in text


def test_sanitize_neutralises_mentions_images_and_html() -> None:
    assert_neutralised(run_review.sanitize(HOSTILE))


def test_comment_neutralises_the_summary_and_the_rationales() -> None:
    comment = run_review.render_comment(
        make_review(summary=HOSTILE, rationale=HOSTILE), []
    )

    assert_neutralised(comment)
    assert "octocat" in comment


def test_comment_neutralises_dropped_paths() -> None:
    comment = run_review.render_comment(make_review(), [HOSTILE])

    assert_neutralised(comment)
    assert "octocat" in comment


def test_comment_has_the_verdict_the_advisory_note_and_every_criterion() -> None:
    comment = run_review.render_comment(make_review(summary="Nice summary."), [])

    assert "AI review: pass" in comment
    assert "advisory" in comment.lower()
    assert "Nice summary." in comment
    for name in CRITERIA:
        assert f"- **{name}**: 9/10" in comment
    assert "floor" not in comment.lower()


def test_comment_shows_the_final_verdict_and_notes_the_floor_override() -> None:
    comment = run_review.render_comment(make_review("pass", tests=FAIL_FLOOR), [])

    assert "AI review: fail" in comment
    assert "AI review: pass" not in comment
    assert "floor" in comment.lower()


def test_model_fail_with_high_scores_is_not_called_a_floor_override() -> None:
    comment = run_review.render_comment(make_review("fail"), [])

    assert "AI review: fail" in comment
    assert "floor" not in comment.lower()


def test_multiline_rationale_cannot_leave_its_bullet() -> None:
    comment = run_review.render_comment(
        make_review(rationale="first\n\n# Fake heading\n| a | b |"), []
    )

    assert "\n# Fake heading" not in comment
    assert "first # Fake heading | a | b |" in comment


def test_scope_note_always_names_the_exclusions() -> None:
    comment = run_review.render_comment(make_review(), [])

    for path in ("uv.lock", "package-lock.json", "context"):
        assert path in comment
    assert "Truncated" not in comment


def test_scope_note_names_the_cap_and_the_first_20_dropped_paths() -> None:
    dropped = [f"file_{number}.py" for number in range(23)]

    comment = run_review.render_comment(make_review(), dropped)

    assert "Truncated" in comment
    assert f"{run_review.MAX_DIFF_CHARS:,}" in comment
    assert "file_19.py" in comment
    assert "file_20.py" not in comment
    assert "and 3 more" in comment


def test_comment_body_is_capped_with_a_visible_note() -> None:
    comment = run_review.render_comment(make_review(summary="s" * 100_000), [])

    assert len(comment) <= run_review.MAX_COMMENT_CHARS
    assert comment.endswith(run_review.COMMENT_CUT_NOTE)


def test_comment_within_the_cap_has_no_cut_note() -> None:
    comment = run_review.render_comment(make_review(), [])

    assert run_review.COMMENT_CUT_NOTE not in comment


def test_nothing_to_review_comment_names_the_exclusions() -> None:
    comment = run_review.render_nothing_to_review()

    assert "AI review: pass" in comment
    assert "nothing" in comment.lower()
    for path in ("uv.lock", "package-lock.json", "context"):
        assert path in comment


# --- main: fakes and fixtures -------------------------------------------------------

DIFF_MARKER = "DIFFMARKER7f3a"
MODEL_MARKER = "MODELMARKER9b2c"
ERROR_MARKER = "ERRORMARKER4d1e"
PATH_MARKER = "PATHMARKER8a6f"
LOG_PREFIXES = ("model: ", "diff: ", "verdict: ", "cost: ", "status: ", "error: ")
USAGE = SimpleNamespace(
    input_tokens=1200,
    input_tokens_details=SimpleNamespace(cached_tokens=1000),
    output_tokens=40,
)
COST_LINE = "cost: 0.001350 USD (model=gpt-5.4 input=1200 cached=1000 output=40)"


class FakeResponses:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_response(
    parsed: Review | None, usage: object = USAGE, status: str = "completed"
) -> SimpleNamespace:
    return SimpleNamespace(output_parsed=parsed, usage=usage, status=status)


def malformed_output() -> pydantic.ValidationError:
    """What the SDK raises on truncated output; the error text quotes the output."""
    with pytest.raises(pydantic.ValidationError) as truncated:
        Review.model_validate_json(f'{{"verdict": "{MODEL_MARKER}"}}')
    assert MODEL_MARKER in str(truncated.value)
    return truncated.value


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the SDK client class; nothing in these tests touches the network."""
    state = SimpleNamespace(
        client_kwargs=[], responses=FakeResponses(make_response(make_review()))
    )

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            state.client_kwargs.append(kwargs)
            self.responses = state.responses

    monkeypatch.setattr(run_review, "OpenAI", FakeOpenAI)
    return state


@pytest.fixture
def real_sdk(
    fake_provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> FakeProvider:
    """The real SDK client on the scripted transport (`tests/fake_provider.py`)."""
    monkeypatch.setattr(run_review, "OpenAI", fake_provider.make_client)
    return fake_provider


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = make_merge_repo(
        tmp_path / "repo", {f"{PATH_MARKER}.py": f"value = '{DIFF_MARKER}'\n"}
    )
    monkeypatch.chdir(path)
    return path


@dataclass
class Outputs:
    comment: Path
    github_output: Path

    def written(self) -> bool:
        return self.comment.exists() or self.github_output.exists()


@pytest.fixture
def outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Outputs:
    github_output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    return Outputs(tmp_path / "comment.md", github_output)


def review_main(outputs: Outputs) -> int:
    return run_review.main(["--comment-file", str(outputs.comment)])


def prompt_parts(call: Mapping[str, Any]) -> tuple[str, str]:
    (developer, user) = call["input"]
    assert developer["role"] == "developer"
    assert user["role"] == "user"
    return developer["content"], user["content"]


# --- main: the call -----------------------------------------------------------------


@pytest.mark.usefixtures("repo")
def test_client_has_a_timeout_and_no_retries(
    fake_openai: SimpleNamespace, outputs: Outputs
) -> None:
    review_main(outputs)

    assert fake_openai.client_kwargs == [
        {"api_key": "test-key", "timeout": 180, "max_retries": 0}
    ]


@pytest.mark.usefixtures("repo")
def test_call_arguments_are_bounded_and_give_the_model_no_tools(
    fake_openai: SimpleNamespace, outputs: Outputs
) -> None:
    review_main(outputs)

    (call,) = fake_openai.responses.calls
    assert call["model"] == "gpt-5.4"
    assert call["max_output_tokens"] == 6000
    assert call["store"] is False
    assert call["reasoning"] == {"effort": "low"}
    assert call["text_format"] is Review
    assert "tools" not in call


@pytest.mark.usefixtures("repo")
def test_random_delimiter_wraps_the_diff_and_does_not_occur_in_it(
    fake_openai: SimpleNamespace, outputs: Outputs
) -> None:
    review_main(outputs)
    review_main(outputs)

    first, second = fake_openai.responses.calls
    delimiters = []
    for call in (first, second):
        developer, user = prompt_parts(call)
        match = re.fullmatch(r"<<<(\S+)\n(.*)\n\1>>>", user, re.DOTALL)
        assert match is not None
        delimiter, diff = match.groups()
        assert DIFF_MARKER in diff
        assert delimiter not in diff
        assert delimiter in developer
        delimiters.append(delimiter)
    assert delimiters[0] != delimiters[1]


@pytest.mark.usefixtures("repo")
def test_prompt_treats_the_diff_as_data_and_protects_secrets(
    fake_openai: SimpleNamespace, outputs: Outputs
) -> None:
    review_main(outputs)

    developer, _ = prompt_parts(fake_openai.responses.calls[0])
    assert "English" in developer
    assert "never instructions" in developer
    assert "never quote" in developer
    assert "secret" in developer
    assert "cut" not in developer


def test_prompt_says_when_the_diff_was_cut(
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(
        make_merge_repo(tmp_path / "repo", {"big.py": "b = 1\n" * 20_000})
    )

    review_main(outputs)

    developer, user = prompt_parts(fake_openai.responses.calls[0])
    assert "cut" in developer
    assert len(user) < run_review.MAX_DIFF_CHARS + 200


# --- main: the real SDK on the fake transport ---------------------------------------


@pytest.mark.usefixtures("repo")
def test_real_sdk_server_error_is_one_request_and_exit_1(
    real_sdk: FakeProvider, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    real_sdk.fail(500)

    assert review_main(outputs) == 1

    assert len(real_sdk.requests) == 1
    assert real_sdk.sleeps == []
    assert "cost: unknown" in capsys.readouterr().out
    assert not outputs.written()


@pytest.mark.usefixtures("repo")
def test_real_sdk_body_not_matching_the_schema_is_a_real_validation_error(
    real_sdk: FakeProvider, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    real_sdk.reply("x")

    assert review_main(outputs) == 1

    assert "cost: unknown" in capsys.readouterr().out
    assert not outputs.written()


@pytest.mark.usefixtures("repo")
def test_real_sdk_sends_the_bounds_and_a_strict_schema_of_six_criteria(
    real_sdk: FakeProvider, outputs: Outputs
) -> None:
    real_sdk.reply("x")

    review_main(outputs)

    (request,) = real_sdk.requests
    body = json.loads(request.content)
    assert body["store"] is False
    assert body["max_output_tokens"] == 6000
    assert not body.get("tools")
    text_format = body["text"]["format"]
    assert text_format["strict"] is True
    assert set(CRITERIA) <= set(text_format["schema"]["required"])


@pytest.mark.usefixtures("repo")
def test_real_sdk_valid_answer_gets_reviewed_and_priced(
    real_sdk: FakeProvider, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    real_sdk._answer(make_review().model_dump(), None)

    assert review_main(outputs) == 0

    assert COST_LINE in capsys.readouterr().out.splitlines()
    assert outputs.github_output.read_text() == "verdict=pass\n"


# --- main: exit paths ---------------------------------------------------------------


@pytest.mark.usefixtures("repo")
def test_pass_exits_0_with_comment_and_verdict(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    assert review_main(outputs) == 0

    assert "AI review: pass" in outputs.comment.read_text()
    assert outputs.github_output.read_text() == "verdict=pass\n"
    out = capsys.readouterr().out.splitlines()
    assert "model: gpt-5.4" in out
    assert "verdict: pass" in out
    assert COST_LINE in out
    assert any(
        line.startswith("diff: ") and line.endswith("truncated: no") for line in out
    )


@pytest.mark.usefixtures("repo")
def test_model_pass_with_a_score_at_the_floor_exits_0_with_verdict_fail(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_openai.responses.outcome = make_response(make_review(tests=FAIL_FLOOR))

    assert review_main(outputs) == 0

    assert "AI review: fail" in outputs.comment.read_text()
    assert outputs.github_output.read_text() == "verdict=fail\n"
    assert "verdict: fail" in capsys.readouterr().out.splitlines()


@pytest.mark.usefixtures("repo")
def test_verdict_is_appended_to_github_output(
    fake_openai: SimpleNamespace, outputs: Outputs
) -> None:
    outputs.github_output.write_text("earlier=1\n")

    review_main(outputs)

    assert outputs.github_output.read_text() == "earlier=1\nverdict=pass\n"


@pytest.mark.usefixtures("repo")
def test_local_run_without_github_output_still_writes_the_comment(
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT")

    assert review_main(outputs) == 0

    assert outputs.comment.exists()
    assert not outputs.github_output.exists()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_key_exits_2_before_git_and_before_any_client(
    key: str | None,
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if key is None:
        monkeypatch.delenv("OPENAI_API_KEY")
    else:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    # Not a git repo: a git call before the key check would exit 1, not 2.
    monkeypatch.chdir(tmp_path)

    assert review_main(outputs) == 2

    assert fake_openai.client_kwargs == []
    assert not outputs.written()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "OPENAI_API_KEY" in captured.err


@pytest.mark.usefixtures("repo")
def test_refusal_exits_1_with_cost_and_status_completed(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_openai.responses.outcome = make_response(None)

    assert review_main(outputs) == 1

    out = capsys.readouterr().out.splitlines()
    assert COST_LINE in out
    assert "status: completed" in out
    assert not outputs.written()


@pytest.mark.usefixtures("repo")
def test_incomplete_answer_exits_1_with_cost_and_status_incomplete(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_openai.responses.outcome = make_response(None, status="incomplete")

    assert review_main(outputs) == 1

    out = capsys.readouterr().out.splitlines()
    assert COST_LINE in out
    assert "status: incomplete" in out
    assert not outputs.written()


@pytest.mark.usefixtures("repo")
def test_no_parsed_output_and_no_usage_logs_cost_unknown(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_openai.responses.outcome = make_response(None, usage=None)

    assert review_main(outputs) == 1

    assert "cost: unknown" in capsys.readouterr().out


@pytest.mark.usefixtures("repo")
def test_review_without_usage_is_still_posted_with_cost_unknown(
    fake_openai: SimpleNamespace, outputs: Outputs, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_openai.responses.outcome = make_response(make_review(), usage=None)

    assert review_main(outputs) == 0

    assert "cost: unknown" in capsys.readouterr().out
    assert outputs.github_output.read_text() == "verdict=pass\n"


def test_empty_diff_after_exclusions_exits_0_with_no_client(
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(make_merge_repo(tmp_path / "repo", {"context/a.md": "a\n"}))

    assert review_main(outputs) == 0

    assert fake_openai.client_kwargs == []
    assert "nothing" in outputs.comment.read_text().lower()
    assert outputs.github_output.read_text() == "verdict=pass\n"
    assert "cost: 0.000000 USD (no model call)" in capsys.readouterr().out.splitlines()


def test_git_error_exits_1_and_writes_nothing(
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    monkeypatch.chdir(not_a_repo)

    assert review_main(outputs) == 1

    assert fake_openai.client_kwargs == []
    assert not outputs.written()


@pytest.mark.usefixtures("repo")
def test_unwritable_comment_file_exits_1_and_sets_no_verdict(
    fake_openai: SimpleNamespace, outputs: Outputs, tmp_path: Path
) -> None:
    """The comment is written first, so a set verdict always means it exists."""
    outputs.comment = tmp_path / "missing_dir" / "comment.md"

    assert review_main(outputs) == 1

    assert not outputs.github_output.exists()


def test_missing_comment_file_argument_exits_2() -> None:
    assert run_review.main([]) == 2


# --- main: end to end on hostile paths ----------------------------------------------


def test_hostile_paths_are_neutralised_in_the_comment_and_absent_from_the_logs(
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `!!big.txt` sorts first, so the cut drops every hostile name after it.
    monkeypatch.chdir(
        make_merge_repo(
            tmp_path / "repo",
            {
                "!!big.txt": "b = 1\n" * 20_000,
                "![x](evil).txt": "x\n",
                "<img src=x>.txt": "x\n",
                "@octocat.txt": "x\n",
            },
        )
    )

    assert review_main(outputs) == 0

    comment = outputs.comment.read_text()
    assert_neutralised(comment)
    assert "octocat" in comment
    assert "evil" in comment
    assert "img src=x" in comment
    assert "Truncated" in comment
    captured = capsys.readouterr()
    assert "octocat" not in captured.out + captured.err
    assert any(line.endswith("truncated: yes") for line in captured.out.splitlines())


# --- main: log purity ---------------------------------------------------------------


LOG_PURITY_OUTCOMES: dict[str, Callable[[], object]] = {
    "success": lambda: make_response(
        make_review(summary=MODEL_MARKER, rationale=MODEL_MARKER)
    ),
    "floor_fail": lambda: make_response(
        make_review(summary=MODEL_MARKER, rationale=MODEL_MARKER, tests=1)
    ),
    "validation_error": malformed_output,
    "api_error": lambda: openai.APIConnectionError(
        message=ERROR_MARKER, request=SimpleNamespace()
    ),
    "other_exception": lambda: RuntimeError(ERROR_MARKER),
    "refusal": lambda: make_response(None),
    "incomplete": lambda: make_response(None, status="incomplete"),
    "no_usage": lambda: make_response(None, usage=None),
}


@pytest.mark.usefixtures("repo")
@pytest.mark.parametrize("outcome", LOG_PURITY_OUTCOMES)
def test_logs_never_hold_the_diff_model_text_or_paths(
    outcome: str,
    fake_openai: SimpleNamespace,
    outputs: Outputs,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_openai.responses.outcome = LOG_PURITY_OUTCOMES[outcome]()

    review_main(outputs)

    assert DIFF_MARKER in prompt_parts(fake_openai.responses.calls[0])[1]
    captured = capsys.readouterr()
    logged = captured.out + captured.err
    for marker in (DIFF_MARKER, MODEL_MARKER, ERROR_MARKER, PATH_MARKER):
        assert marker not in logged
    for line in logged.splitlines():
        assert line.startswith(LOG_PREFIXES), line


def test_git_error_logs_only_the_type_name(
    outputs: Outputs,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_with_marker() -> str:
        raise subprocess.CalledProcessError(128, ["git", ERROR_MARKER])

    monkeypatch.setattr(run_review, "read_diff", raise_with_marker)

    assert review_main(outputs) == 1

    captured = capsys.readouterr()
    assert captured.err.strip() == "error: CalledProcessError"
    assert ERROR_MARKER not in captured.out


# --- standalone -----------------------------------------------------------------------


def test_script_imports_in_a_clean_interpreter_with_settings_but_no_django_setup() -> (
    None
):
    code = (
        "import sys\n"
        "import scripts.review.run_review\n"
        "from django.apps import apps\n"
        "assert not apps.ready\n"
        "assert 'talkaitive.settings' in sys.modules\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
