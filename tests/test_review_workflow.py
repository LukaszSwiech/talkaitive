"""Guards for the safety properties of `.github/workflows/ai-review.yml`.

Parses the workflow as data, so a later edit cannot quietly remove one of them. This
pins the workflow's shape only; whether the labels really behave is proven by a real
run on the PR.

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


def test_triggers_are_only_pull_request_and_dispatch() -> None:
    triggers = workflow()[True]
    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    assert "pull_request_target" not in REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert triggers["pull_request"]["branches"] == ["main"]
    assert set(triggers["pull_request"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "labeled",
    }
    pr_number = triggers["workflow_dispatch"]["inputs"]["pr_number"]
    assert pr_number["required"] is True
    assert pr_number["type"] == "number"


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
    assert "refs/pull/{0}/merge" in checkout["ref"]
    assert "inputs.pr_number" in checkout["ref"]


def test_a_body_is_passed_only_through_a_file() -> None:
    assert "gh pr edit" not in REVIEW_WORKFLOW.read_text(encoding="utf-8")
    assert not [block for block in run_blocks() if BODY_FLAG.search(block)]
    assert "gh pr comment" in step("post")["run"]
    assert "--body-file" in step("post")["run"]


def test_the_job_runs_only_for_open_same_repo_prs_and_the_retry_label() -> None:
    condition = job()["if"]
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository"
        in condition
    )
    assert "github.event.pull_request.state == 'open'" in condition
    assert "github.event.label.name == 'ai-cr:review'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition


def test_a_new_run_cancels_the_old_one_except_for_unrelated_labels() -> None:
    concurrency = workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is True
    assert "github.run_id" in concurrency["group"]
    assert "github.event.pull_request.number" in concurrency["group"]
    assert "inputs.pr_number" in concurrency["group"]


def test_the_pr_number_reaches_the_shell_for_both_events() -> None:
    pr_number = job()["env"]["PR_NUMBER"]
    assert "github.event.pull_request.number" in pr_number
    assert "inputs.pr_number" in pr_number
    assert job()["env"]["GH_REPO"] == "${{ github.repository }}"


def test_the_guard_comes_first_and_checks_every_refusal() -> None:
    assert step_index("guard") == 0
    assert "uses" not in steps()[0]
    assert "workflow_dispatch" in step("guard")["if"]
    for field in ("isCrossRepository", "baseRefName", "state"):
        assert field in step("guard")["run"]


def test_steps_run_in_the_safe_order() -> None:
    order = [
        step_index("guard"),
        step_index("ensure-labels"),
        uses_index("actions/checkout"),
        uses_index("astral-sh/setup-uv"),
        step_index("review"),
        step_index("post"),
        step_index("failure-cleanup"),
        step_index("retry-cleanup"),
    ]
    assert order == sorted(order)


def test_the_review_step_runs_the_script_without_a_sync() -> None:
    run = step("review")["run"]
    assert run.startswith("uv run --no-sync python -m scripts.review.run_review ")
    assert '--comment-file "$RUNNER_TEMP/ai-review-comment.md"' in run
    assert step("review")["timeout-minutes"] == 5
    assert "uv sync --locked --no-dev" in run_blocks()


def test_the_post_step_validates_the_verdict_it_gets_through_env() -> None:
    post = step("post")
    assert "steps.review.outputs.verdict" in post["if"]
    assert post["env"]["VERDICT"] == "${{ steps.review.outputs.verdict }}"
    run = post["run"]
    assert 'case "$VERDICT" in' in run
    assert re.search(r"^\s*pass\)$", run, re.MULTILINE)
    assert re.search(r"^\s*fail\)$", run, re.MULTILINE)
    assert re.search(r"^\s*\*\)\n.*\n\s*exit 1$", run, re.MULTILINE)


def test_cleanups_touch_no_label_after_a_failed_guard() -> None:
    failure_condition = step("failure-cleanup")["if"]
    assert "failure()" in failure_condition
    assert "steps.guard.outcome != 'failure'" in failure_condition
    retry_condition = step("retry-cleanup")["if"]
    assert "!cancelled()" in retry_condition
    assert "steps.guard.outcome != 'failure'" in retry_condition


def test_each_cleanup_removes_its_labels() -> None:
    failure_run = step("failure-cleanup")["run"]
    assert 'delete_label "ai-cr:passed"' in failure_run
    assert 'delete_label "ai-cr:failed"' in failure_run
    assert 'delete_label "ai-cr:review"' in step("retry-cleanup")["run"]


def test_only_a_404_is_tolerated() -> None:
    assert not [block for block in run_blocks() if "|| true" in block]
    assert not [candidate for candidate in steps() if "continue-on-error" in candidate]
    for step_id in ("ensure-labels", "post", "failure-cleanup", "retry-cleanup"):
        run = step(step_id)["run"]
        assert '*"HTTP 404"*)' in run
        # Only stderr is inspected, and anything else stops the step.
        assert "2>&1 >/dev/null" in run
        assert "return 1" in run
