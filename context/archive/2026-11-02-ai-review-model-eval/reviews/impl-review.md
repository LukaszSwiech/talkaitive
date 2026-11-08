<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: AI Review Model Eval Implementation Plan

- **Plan**: context/changes/ai-review-model-eval/plan.md
- **Scope**: Full plan (range `main...HEAD` = `ai-review-model-eval` + `ai-review-model-eval-results`, HEAD 257eedd)
- **Reviewed phases**: 1, 2, 3, 4, 5 (phases 4 and 5 still have open Progress items: 4.5 manual share-link check, 5.3 PR/CI)
- **Date**: 2026-11-02
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 5 observations

## Evidence gathered

- `uv run pytest`: 805 passed; `tests/test_review_eval.py`: 93 passed, 0 skipped locally.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `run --dry-run` (scratch ledger): worst case 4.2593 USD per repeat, 2 of 3 repeats guaranteed up front, exit 0, fingerprint `7e46f68e…763b6c` = the committed result's fingerprint.
- `run --fake --out <scratchpad> --repeats 1` (scratch ledger): real promptfoo 0.125.1, 64 case-model entries, `complete: True`, the ledger file never created (no spend), winner `None` (the canned all-10 review is a false pass on every blocker, so all models are disqualified, as expected).
- I re-derived the matrix from `entries` for all four models with my own script (no repo imports): false fails 2/6/0/0 of 27, hard false passes 0, mean USD 0.012049 / 0.004032 / 0.012993 / 0.003354, regular 0.006709 for Gemini, median ms 8249/4516/4438/4686, stability 0.875/1.0/0.9375/1.0. All of these match `aggregate`. The winner gemini-3.8-flash follows D8→D9 (it ties Claude on a 0 false-fail rate and is cheaper at the regular price). The entries sum to 1.5566 USD, plus 0.0278 smoke = 1.5844, which matches `ledger_spent_usd` 1.58447.
- The reviewable diff is 91,514 chars for PR 1 (`main...ai-review-model-eval`), 22,224 for PR 2 and 113,280 in total. Each PR is under the 120k cap, and the split follows the plan's documented Fix B.
- Budget ledger: every call reserves its worst case under `flock` before the call and settles in a `finally` block, so settling happens on every path (success, model error, `ValidationError`, any `Exception`, `LengthFinishReasonError` with usage). Without usage, the full reservation stays spent. A killed worker leaves an open reservation, which still counts as spent. Two ways past the cap exist, both accepted by D12: a call whose actual cost is above its reservation, and a new `--ledger` path. The cap test with two processes passes.
- Trust boundary: the provider and runner return or print only fixed error kinds, exception type names, numbers, paths and criterion names. No rationale, diff, model text or key appears in the result file or in errors. Raw output goes outside the repo. The fake key is derived (sha512 + base64) and the injection text is assembled from fragments. A test guards both in `cases.py`.
- Reuse with no copies: the provider imports `_build_input`, `truncate_diff`, `MAX_OUTPUT_TOKENS`, `REASONING_EFFORT` and `TIMEOUT_SECONDS` from `run_review`, and `Review` from `criteria`. The assertion and the runner call the real `final_verdict`, `failed_blockers` and `low_warnings`. The model's own `verdict` is never read. The OpenAI call is byte-identical to `run_review._call_model` apart from the model id.
- CI safety: the materialisation tests skip when `git cat-file -e` cannot find a commit (depth-1 CI). The manual-mutant copies exclude `.git`, so they skip there too. The gate tests read only `scripts/review/eval/results/`, which the mutant copies keep, and make no network calls and need no secrets. I could not reproduce a depth-1 clone (permission denied), so this rests on reading the code.
- AI review job: `openai` is imported only under `scripts/review/` and `tests/`, which `openai_boundary` exempts. The `from openai import` match in `cases.py` sits inside a seed string. I found no key-like literal in the diff (`sk-proj-…` with an ellipsis appears only in `context/research.md`, which the reviewer excludes).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Findings

### F1 — Runner orchestration (repeat budget gate, exit codes, refusals) has no test

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: scripts/review/eval/run.py:281-424 (no test calls `run.run` or `run.main`)
- **Detail**: Tests cover the helpers (`check_node`, `promptfoo_command`, `missing_keys`, `worst_case_per_repeat`, `row_record`, `aggregate`, `pick_winner`, `write_result`), but no test covers the logic that enforces the D12/D22 budget rule and the trial guards. That logic: skip a repeat when `total > ledger.remaining()` and record `repeats_skipped_budget` with exit 0; stop with `complete: false` and exit 2 when a row has `error == "budget"`; refuse a dirty tree without `--out`; refuse `--out` inside the repo; require `--out` for `--fake`/`--smoke`; share only when the run is complete. A regression in that loop could start a repeat that does not fit, or commit a partial result as complete. The paid run did not exercise these branches either: all 3 repeats fit.
- **Fix**: Add 3–4 tests that call `run.run([...])` with `_out` monkeypatched (git status, node, promptfoo version), `subprocess.run` faked to write a canned promptfoo JSON to the `-o` path, and a `tmp_path` ledger pre-filled with spend. Cover: (a) remaining < total → exit 0, `repeats_skipped_budget` > 0; (b) a canned row with `error_kind: "budget"` → exit 2, `complete: false`; (c) a dirty tree without `--out` → `ConfigError`; (d) `--out` under `REPO` → `ConfigError`.
  - Strength: protects the one guarantee the brief calls hard (never cross 10 USD) at the orchestration level, not only in the ledger.
  - Tradeoff: about 60–100 test lines. PR 1's reviewable diff is already 91.5k, so the tests belong in PR 2 or a follow-up.
  - Confidence: HIGH — every branch is reachable with the existing fakes (`FakeClient` pattern, `grouped` helpers).
  - Blind spot: promptfoo's real JSON shape for budget rows is only verified through `row_record`'s existing test.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): fix in PR 2 — runner orchestration tests (repeat skip, mid-repeat budget stop exit 2, dirty tree, --out inside repo, share only after a full run).

### F2 — D5 "any row served outside `only` is flagged" is not implemented

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: scripts/review/eval/run.py:122 (stores `served` only); scripts/review/eval/provider.py:90
- **Detail**: D5 says that any row served outside `only` is flagged. The runner stores OpenRouter's display name (`"Google"`) and never compares it with `EvalModel.openrouter_only`. `smoke.md` and test-plan §6.6 admit this ("runner does not compare `served` with `only` — you read it in the result"), so the check was moved to a human without a plan addendum. In this run all 96 OpenRouter rows say `Google`, which the report reads as google-vertex. That is correct today, but a future re-run that routes elsewhere would not be flagged.
- **Fix A ⭐ Recommended**: In `models.py`, add a display-name→slug map (`{"Google": "google-vertex", "Azure": "azure"}`). Then count `off_policy` rows per model in `aggregate` (a served name that is missing from the map, or maps outside `openrouter_only`), and show the counter in the matrix.
  - Strength: restores the plan contract mechanically; a few lines plus one test.
  - Tradeoff: adds a matrix column; `aggregate` changes, but the fingerprint does not, so the committed result stays valid.
  - Confidence: MED — display names are OpenRouter's convention and may change; an unknown name should count as off-policy (fail-closed).
  - Blind spot: whether OpenRouter ever returns the slug instead of the name.
- **Fix B**: Add a plan addendum under D5 saying the check is manual (read `served` in the result), as smoke.md already does.
  - Strength: no code change; documents the reality.
  - Tradeoff: leaves the data-policy check to a person on each re-run.
  - Confidence: HIGH — matches what was actually done.
  - Blind spot: none significant.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix A — display-name→slug map in models.py and an off_policy count in the aggregate; an unknown name counts as off policy.

### F3 — Fingerprint does not cover the prompt wrapper or the verdict-rule code

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: scripts/review/eval/fingerprint.py:19-31
- **Detail**: The brief says the CI test "goes red when the review prompt, schema or model changed". The hash covers `_INSTRUCTIONS`, `_TRUNCATED_INSTRUCTION`, the schema, the constants, `FAIL_FLOOR` and `BLOCKERS`, as D18 lists. It does not cover the code that builds the prompt and the verdict: `_build_input` (roles, the `<<<delimiter … delimiter>>>` wrapping of the diff, where the truncation note goes) and the bodies of `final_verdict` / `failed_blockers` (e.g. how `truncated` forces a fail). Any of these can change what the model sees, or the verdict, while CI stays green. The gap comes from the plan (D18), not from the implementation.
- **Fix A ⭐ Recommended**: Record it as a known limit in test-plan §6.6 "Kiedy uruchamiać" and in D18. Widen the hash in the next change that needs a new result anyway (e.g. the reviewer-model switch).
  - Strength: no extra paid run now; the limit is explicit.
  - Tradeoff: the gap stays open until that next run.
  - Confidence: HIGH — documentation only.
  - Blind spot: none significant.
- **Fix B**: Add `inspect.getsource(run_review._build_input)`, `inspect.getsource(criteria.final_verdict)` and `inspect.getsource(criteria.failed_blockers)` to `fingerprint_inputs()`, then re-run the eval (~1.6 USD) for a new result file.
  - Strength: closes the gap the brief describes.
  - Tradeoff: a source hash also turns red on a comment- or formatting-only edit (ruff format runs on every edit), and it costs a paid re-run now.
  - Confidence: MED — the source text is stable under the pinned Python, but brittle.
  - Blind spot: whether ruff's formatter would reformat these functions later.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix B — fingerprint also hashes the source of _build_input, final_verdict, failed_blockers and the floor helper; a new full paid run produces a result with the new fingerprint (budget allows: ~1.6 USD more); the first result file stays as history.

### F4 — Progress and report disagree on the share-link check; Progress edit uncommitted; change not stamped

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/ai-review-model-eval/report.md:10; plan.md:424 (4.5 `[ ]`); working tree `M plan.md`
- **Detail**: report.md says the share links were "checked, redirects to login", but Progress 4.5 is still unchecked. The sha annotations for 5.1/5.2/5.4 in plan.md sit uncommitted in the working tree. 5.3 (PR opened, CI green, `review` result recorded) is pending, and report.md "PR checks" is a placeholder. `change.md` is still `status: implementing`: this reviewer was told not to edit it, so the skill's `impl_reviewed` stamp was not applied.
- **Fix**: Tick 4.5 with a one-line evidence note (or drop the claim from report.md), commit the plan.md Progress edit on `ai-review-model-eval-results`, set `change.md` to `status: impl_reviewed`, and fill "PR checks" once both PRs have run CI and the AI review.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): fix report wording (logged-out check done, logged-in view left to the user), commit Progress, stamp change.md.

### F5 — test-plan: the existing §6.6 was renumbered, against the "new subsection only" contract

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: context/foundation/test-plan.md:243 (new §6.6), :285 (old notes now §6.7), :217 (cross-ref changed §6.6→§6.7)
- **Detail**: The plan says "new subsection only; no other section rewritten", but the change moved "Per-rollout-phase notes" from 6.6 to 6.7 and edited a reference in §6.5. The 10x-test-plan schema (`.claude/skills/10x-test-plan/references/test-plan-schema.md:289`) and the ship skill's message (`ship_state.py:326`, "carry-over notes in §6.6") name §6.6 as the per-rollout notes. Nothing parses the number today, so the effect is cosmetic. The plan caused it by asking for "§6.6".
- **Fix**: Accept the renumbering and note it in the plan (simplest), or make the new section §6.7 and restore "6.6 Per-rollout-phase notes" plus the §6.5 cross-ref.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): restore the original §6.6 numbering; the new eval section becomes §6.7 after it, and references in plan, report and docs are updated.

### F6 — `promptfoo share` runs without the telemetry/update opt-outs (D15)

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: scripts/review/eval/run.py:332, :380
- **Detail**: `share_env` is `os.environ` minus `REVIEW_EVAL_FAKE`, so the `promptfoo share` subprocess runs without `PROMPTFOO_DISABLE_TELEMETRY=1` and `PROMPTFOO_DISABLE_UPDATE=1`, which D15 sets for promptfoo.
- **Fix**: Build `share_env` from `env` by dropping only `PROMPTFOO_DISABLE_SHARING` and `REVIEW_EVAL_FAKE` (it carries no ledger risk: `share` makes no provider calls).
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): build share_env from the eval env, removing only PROMPTFOO_DISABLE_SHARING and REVIEW_EVAL_FAKE.

### F7 — Gate matches `LLM_MODEL` against labels only; a budget-stopped repeat leaks into the aggregate

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_review_eval.py:847-850; scripts/review/eval/run.py:370-377, :387
- **Detail**: (a) `model_unmeasured` compares `run_review.LLM_MODEL` with `models[].label`. The reviewer's setting holds an API id. These are equal for the OpenAI models but differ for OpenRouter (`claude-sonnet-5.5` vs `anthropic/claude-sonnet-5.5`), which is the switch the report suggests. (b) When a repeat stops on a `budget` row, its partial records stay in `table` and feed `aggregate` (disqualification, stability). D8 counts only completed repeats. Such a result is `complete: false` and the gate rejects it, so only trial output is affected.
- **Fix**: (a) Match against `{m["label"], m["api_id"]}`. (b) Drop, or tag apart, the records appended in the stopped repeat before `aggregate`.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): (a) fix — gate matches label or api_id; (b) declined — incomplete results are rejected by the gate anyway.

### F8 — AI review outcome on PR 1 still unknown; the seed strings sit in its diff

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: scripts/review/eval/cases.py:106-196 (seeds), plan 5.3
- **Detail**: PR 1's diff (91.5k) holds the deliberate bad-code seeds as strings: the unscoped `Conversation.objects.all()` query, the derived key builder, the injection fragments, the unsafe migration text and a `from openai import OpenAI` module string. The module docstring explains them, and the injection is not a contiguous sentence. Still, the required `review` check could score `data_isolation` / `no_secrets` low on its own PR (a false fail). This has not been observed yet, because no PR is open. Separately, D3's "never contiguous in the repo" is kept in the code, but `research.md:121` holds a near-contiguous injection phrase. That file sits in `context/`, which the reviewer and the mutant copies exclude, so it is harmless.
- **Fix**: When the PRs are opened, record the `review` verdict and scores in report.md "PR checks". A false fail there is itself a data point for the report, and the course of action follows the existing ci-ai-review-gate process, not a code change here.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): record the PR check results in report.md after opening the PRs.

## Plan adherence summary (D1–D24)

MATCH: D1, D2, D3 (code), D4, D6, D7, D8, D8a, D9 (+ a documented first-listed tie-break), D10, D11, D12, D13, D14, D16, D17, D18 (as specified; see F3), D19, D20, D21, D22 (untested, F1), D23, D24.
DRIFT: D5 flagging (F2), D15 for `share` (F6).
EXTRA (benign): `PROMPTFOO_DISABLE_SHARING`, `--no-table --no-progress-bar`, `--filter-providers`, git env scrubbing in `cases.py`, a tie-break rule.
No change to `LLM_MODEL`, settings, `run_review.py`, `criteria.py`, `ai-review.yml` or CLAUDE.md, so the "What We're NOT Doing" list holds.
