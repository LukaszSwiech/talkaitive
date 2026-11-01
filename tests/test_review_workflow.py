"""Guards for the safety properties of `.github/workflows/ai-review.yml`.

Parses the workflow as data, so a later edit cannot quietly remove one of them. This
pins the workflow's shape only; whether the required check really stops a merge is
proven by real runs on the PR.

PyYAML comes in through the dev group and is imported directly: an `importorskip` could
make these guards vanish without anyone noticing. The module skips only when `ci.yml`
is missing too, which means a mutation copy without `.github`. If `ci.yml` exists and
`ai-review.yml` does not, the tests fail, so deleting the workflow cannot pass as a
skip.

YAML 1.1 parses the key `on` as boolean `True`, hence `workflow[True]`.
"""

import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CI_WORKFLOW = WORKFLOWS / "ci.yml"
REVIEW_WORKFLOW = WORKFLOWS / "ai-review.yml"

if not CI_WORKFLOW.exists():
    pytest.skip("mutation copy without .github", allow_module_level=True)

ALLOWED_PERMISSIONS = {"contents": "read", "pull-requests": "write"}
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
CALLS_GH = re.compile(r"\bgh (?:api|pr)\b")
BODY_FLAG = re.compile(r"(?:--body(?!-file)|\s-b\s|\s-F\s)")


@cache
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(REVIEW_WORKFLOW.read_text(encoding="utf-8"))


def job() -> dict[str, Any]:
    jobs = workflow()["jobs"]
    assert len(jobs) == 1
    return next(iter(jobs.values()))


def steps() -> list[dict[str, Any]]:
    return job()["steps"]


def step_index(step_id: str) -> int:
    ids = [step.get("id") for step in steps()]
    assert step_id in ids
    return ids.index(step_id)


def step(step_id: str) -> dict[str, Any]:
    return steps()[step_index(step_id)]


def uses_index(action: str) -> int:
    for index, candidate in enumerate(steps()):
        if candidate.get("uses", "").startswith(f"{action}@"):
            return index
    raise AssertionError(f"no step uses {action}")


def run_blocks() -> list[str]:
    return [candidate["run"] for candidate in steps() if "run" in candidate]


def last_line(run: str) -> str:
    return run.strip().splitlines()[-1].strip()


def pinned_actions(parsed: dict[Any, Any]) -> dict[str, str]:
    return {
        candidate["uses"].split("@")[0]: candidate["uses"].split("@")[1]
        for parsed_job in parsed["jobs"].values()
        for candidate in parsed_job["steps"]
        if "uses" in candidate
    }


def test_every_action_is_pinned_to_the_shas_in_ci() -> None:
    uses = [candidate["uses"] for candidate in steps() if "uses" in candidate]
    assert uses
    assert all(SHA_PIN.match(action) for action in uses)
    ci = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert pinned_actions(workflow()) == pinned_actions(ci)


def test_permissions_are_exactly_the_allowed_set() -> None:
    assert workflow()["permissions"] in (
        ALLOWED_PERMISSIONS,
        {**ALLOWED_PERMISSIONS, "issues": "write"},
    )
    assert "permissions" not in job()


def test_the_only_trigger_is_pull_request_with_exactly_three_types() -> None:
    triggers = workflow()[True]
    assert set(triggers) == {"pull_request"}
    assert "pull_request_target" not in REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert set(triggers["pull_request"]) == {"branches", "types"}
    assert triggers["pull_request"]["branches"] == ["main"]
    assert set(triggers["pull_request"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
    }


def test_no_expression_reaches_a_run_block() -> None:
    blocks = run_blocks()
    assert blocks
    assert not [block for block in blocks if "${{" in block]


def test_the_model_key_is_only_in_the_review_step() -> None:
    assert "OPENAI_API_KEY" not in workflow().get("env", {})
    assert "OPENAI_API_KEY" not in job().get("env", {})
    holders = [
        candidate.get("id")
        for candidate in steps()
        if "OPENAI_API_KEY" in candidate.get("env", {})
    ]
    assert holders == ["review"]
    assert step("review")["env"]["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    # Catches the secret reaching a `with:` or a job-level expression as well.
    text = REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert text.count("secrets.") == 1


def test_the_github_token_is_only_in_steps_that_call_gh() -> None:
    assert "GH_TOKEN" not in workflow().get("env", {})
    assert "GH_TOKEN" not in job().get("env", {})
    assert "GH_TOKEN" not in step("review")["env"]
    for candidate in steps():
        calls_gh = bool(CALLS_GH.search(candidate.get("run", "")))
        assert calls_gh == ("GH_TOKEN" in candidate.get("env", {})), candidate


def test_checkout_keeps_no_credentials_and_fetches_both_parents() -> None:
    checkout = steps()[uses_index("actions/checkout")]["with"]
    assert checkout["persist-credentials"] is False
    assert checkout["fetch-depth"] == 2
    # With no ref, a pull_request checks out the event's merge commit.
    assert "ref" not in checkout


def test_a_body_is_passed_only_through_a_file() -> None:
    assert "gh pr edit" not in REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert not [block for block in run_blocks() if BODY_FLAG.search(block)]
    assert "gh pr comment" in step("post")["run"]
    assert "--body-file" in step("post")["run"]


def test_the_job_has_no_if_because_a_skipped_job_passes_a_required_check() -> None:
    assert "if" not in job()


def test_the_required_check_keeps_its_name() -> None:
    """The check's name is the job's: a rename would leave the check waiting forever."""
    assert list(workflow()["jobs"]) == ["review"]
    assert "name" not in job()


def test_no_other_workflow_has_a_job_that_reports_as_review() -> None:
    others = [
        path
        for pattern in ("*.yml", "*.yaml")
        for path in WORKFLOWS.glob(pattern)
        if path != REVIEW_WORKFLOW
    ]
    assert CI_WORKFLOW in others
    for path in others:
        for job_id, other_job in yaml.safe_load(path.read_text("utf-8"))[
            "jobs"
        ].items():
            assert job_id != "review", path
            assert other_job.get("name") != "review", path


def test_a_new_run_cancels_the_old_one_for_the_same_pr() -> None:
    concurrency = workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    assert (
        concurrency["group"] == "ai-review-pr-${{ github.event.pull_request.number }}"
    )


def test_the_pr_number_comes_only_from_the_event() -> None:
    assert job()["env"]["PR_NUMBER"] == "${{ github.event.pull_request.number }}"
    assert job()["env"]["GH_REPO"] == "${{ github.repository }}"


def test_the_guard_comes_first_and_ends_red_for_a_fork() -> None:
    guard = step("guard")
    assert step_index("guard") == 0
    assert step_index("guard") < uses_index("actions/checkout")
    assert "uses" not in guard
    assert guard["if"] == (
        "github.event.pull_request.head.repo.full_name != github.repository"
    )
    assert "GH_TOKEN" not in guard.get("env", {})
    assert last_line(guard["run"]) == "exit 1"


def test_steps_run_in_the_safe_order() -> None:
    order = [
        step_index("guard"),
        step_index("ensure-labels"),
        uses_index("actions/checkout"),
        uses_index("astral-sh/setup-uv"),
        step_index("review"),
        step_index("post"),
        step_index("failure-cleanup"),
        step_index("stop"),
    ]
    assert order == sorted(order)
    assert step_index("stop") == len(steps()) - 1


def test_the_stop_step_ends_the_job_red_on_anything_but_a_pass() -> None:
    """Red by default: a review step exiting 0 with no verdict must not end green."""
    stop = step("stop")
    assert stop["name"] == "Stop on a failed review"
    assert stop["if"] == "steps.review.outputs.verdict != 'pass'"
    assert last_line(stop["run"]) == "exit 1"
    assert "env" not in stop


def test_the_review_step_runs_exactly_the_script_without_a_sync() -> None:
    assert step("review")["run"] == (
        "uv run --no-sync python -m scripts.review.run_review "
        '--comment-file "$RUNNER_TEMP/ai-review-comment.md"'
    )
    assert step("review")["timeout-minutes"] == 5
    assert "uv sync --locked --no-dev" in run_blocks()


def test_the_post_step_runs_on_any_verdict_and_validates_it_through_env() -> None:
    post = step("post")
    assert post["if"] == "steps.review.outputs.verdict != ''"
    assert post["env"]["VERDICT"] == "${{ steps.review.outputs.verdict }}"
    run = post["run"]
    assert 'case "$VERDICT" in' in run
    assert re.search(
        r'^\s*pass\)\n\s*result="ai-cr:passed"\n\s*opposite="ai-cr:failed"\n\s*;;$',
        run,
        re.MULTILINE,
    )
    assert re.search(
        r'^\s*fail\)\n\s*result="ai-cr:failed"\n\s*opposite="ai-cr:passed"\n\s*;;$',
        run,
        re.MULTILINE,
    )
    assert re.search(r"^\s*\*\)\n.*\n\s*exit 1$", run, re.MULTILINE)
    assert re.search(r'^\s*delete_label "\$opposite"$', run, re.MULTILINE)
    assert '-f "labels[]=$result"' in run


def test_cleanup_touches_no_label_after_a_failed_guard() -> None:
    assert step("failure-cleanup")["if"] == (
        "failure() && steps.guard.outcome != 'failure'"
    )


def test_only_the_cleanup_runs_after_a_failure() -> None:
    """Any other step on failure() or always() could undo the fail-closed order."""
    holders = [
        candidate.get("id")
        for candidate in steps()
        if "failure()" in str(candidate.get("if", ""))
        or "always()" in str(candidate.get("if", ""))
    ]
    assert holders == ["failure-cleanup"]


def test_the_cleanup_removes_both_result_labels() -> None:
    failure_run = step("failure-cleanup")["run"]
    assert 'delete_label "ai-cr:passed"' in failure_run
    assert 'delete_label "ai-cr:failed"' in failure_run


def test_the_removed_retry_path_is_gone() -> None:
    text = REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert "retry-cleanup" not in text
    assert "ai-cr:review" not in text


def test_only_a_404_is_tolerated() -> None:
    assert not [block for block in run_blocks() if "|| true" in block]
    assert not [candidate for candidate in steps() if "continue-on-error" in candidate]
    assert "continue-on-error" not in job()
    for step_id in ("ensure-labels", "post", "failure-cleanup"):
        run = step(step_id)["run"]
        assert '*"HTTP 404"*)' in run
        # Only stderr is inspected, and anything else stops the step.
        assert "2>&1 >/dev/null" in run
        assert "return 1" in run
