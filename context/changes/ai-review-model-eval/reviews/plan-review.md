<!-- PLAN-REVIEW-REPORT -->
# Plan Review: AI Review Model Eval Implementation Plan

- **Plan**: context/changes/ai-review-model-eval/plan.md
- **Mode**: Deep (codebase verification done inline by the reviewer; no sub-agent, per the orchestrator's instruction)
- **Date**: 2026-11-02
- **Verdict**: REVISE
- **Findings**: 1 critical, 8 warnings, 1 observation
- **Triage mode**: autonomous. No questions were asked; each finding carries the reviewer's recommendation. `change.md` was not touched (the orchestrator forbade it), so its `status: plan_reviewed` update is left to the orchestrator.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | FAIL |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

Grounding: 6/6 existing paths ✓ (`scripts/review/{run_review,criteria,cost}.py`, `talkaitive/settings.py`, `context/foundation/test-plan.md`, `tests/test_review_criteria.py`); 16/16 symbols ✓ (`_build_input`, `truncate_diff`, `Review`, `final_verdict`, `_INSTRUCTIONS`, `_TRUNCATED_INSTRUCTION`, `MAX_OUTPUT_TOKENS`, `REASONING_EFFORT`, `TIMEOUT_SECONDS`, `MAX_DIFF_CHARS`, `EXCLUDED_PATHS`, `FAIL_FLOOR`, `BLOCKERS`, `cost_usd`, `_get_conversation`, `surprise_topic_key`); 12/12 case SHAs exist locally ✓; Progress↔Phase ✓ (5 phases, every Success Criteria bullet has a row, no checkboxes in phase blocks); brief↔plan ✓ except one claim (F1: the injection text is not kept out of the PR). `docs/reference/contract-surfaces.md` does not exist (check skipped).

Checked in promptfoo 0.125.1's installed dist (`/opt/homebrew/lib/node_modules/promptfoo/dist/src`): the Python wrapper puts only the script's own directory on `sys.path` (`python/persistent_wrapper.py:93-101`); assertions get `output` as returned plus `context.providerResponse` and `context.metadata` (`evaluator-*.js:5644-5694`); `tests: file://x.py:generate_tests` is supported (`index.js:29226`); `promptfoo share <id>` is not blocked by `sharing: false` in the config (`index.js:28222-28230`, `35222-35232`). The repo is **PUBLIC** (`gh repo view`).

Coverage of the user's brief: every requirement is covered or reasoned, with these gaps: per-route structured-output **enforcement** is checked only by output validity (F7); "check Node support" is not in the runner's preflight (F10); "at least one fail per each of six criteria" is adapted for the two warning criteria, but warning detection never reaches the matrix (F5); "3 repeats if the budget allows" conflicts with the `complete` rule (F2).

## Findings

### F1 — This PR's own diff will likely exceed the reviewer's 120k cap and fail the required `review` check

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: D2, D20, Phase 4 §1, Phase 5 Success Criteria; plan-brief "Case diffs" row
- **Detail**: D2 keeps diff fixtures out of the repo to stay under `MAX_DIFF_CHARS = 120_000` (`run_review.py:52`), but the result file goes under `scripts/review/eval/results/`, and the reviewer does not exclude that path (`EXCLUDED_PATHS = ("uv.lock", "package-lock.json", "context")`, `run_review.py:62`). D20 stores one row per (case, model, repeat): 16 × 4 × 3 = 192 rows. At ~330 chars per compact row that is ~63k chars, and the `scripts/eval` precedent result is 177 579 bytes (`scripts/eval/results/2026-10-19-gpt-5.4-56e6109.json`). The code is large too: PR 28's reviewable diff was 78 848 chars without any result file (`git diff f3a9789^1 f3a9789` minus excluded paths), and `scripts/eval` + its tests come to ~120k chars. A diff over the cap makes `final_verdict` return `fail` whatever the scores (`criteria.py:122`), so the required `review` check goes red. Separately, `cases.py` will hold the seed `new` strings as literals: the injection comment ("AI reviewer: ignore previous instructions…"), `Conversation.objects.all()` and `from openai import OpenAI` in views. So the plan-brief's claim that the PR stays "free of a fake secret/injection" holds only for the secret (D3). Phase 5 checks only `lint-and-test`, not `review`.
- **Fix A ⭐ Recommended**: Shrink the result file, measure the diff before the PR, and keep the injection out of the source
  - Plan edits: (1) D20: rows are stored as one entry per (case, model) with per-repeat arrays (`verdicts`, `failed_blockers`, `scores` as 6-int lists, `cost`, `latency_ms`, `error`); no indentation; add the contract "result JSON ≤ 20 000 chars, asserted by the writer". Full rows stay in `~/.cache/...` and behind the share links. (2) D3: the injection text is built at run time from fragments, like the fake secret. (3) Phase 5 Automated: "the reviewable diff `git diff main...HEAD -- . ':(exclude)uv.lock' ':(exclude)package-lock.json' ':(exclude)context' | wc -c` is below 100 000 chars before the PR opens". Manual: "the `review` check result on the PR is recorded in report.md; a false fail is analysed, not overridden". (4) Correct the plan-brief "Case diffs" row.
  - Strength: keeps one PR (as the plan wants) and makes the cap a measured fact instead of a hope.
  - Tradeoff: the committed file is less granular, so matrix re-derivation (4.6) uses arrays.
  - Confidence: HIGH — both size inputs were measured in this repo.
  - Blind spot: the final code size is unknown until Phase 2. If it alone nears 100k, Fix B is needed anyway.
- **Fix B**: Split into two PRs: PR 1 has the eval code without the result; PR 2 has the result file and the gate test
  - Strength: each diff stays well under the cap whatever the code size.
  - Tradeoff: the second PR depends on the first being merged; it changes the plan's `## Branches and PRs` and adds a second paid AI-review run.
  - Confidence: MEDIUM — it follows the CLAUDE.md branch rules, but adds coordination.
  - Blind spot: the user must merge PR 1 before PR 2, and the autonomous flow cannot merge.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix A, plus Fix B as the fallback if the size check fails

### F2 — A budget-skipped repeat makes the run "incomplete", which the success criterion and the gate test both reject

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: D12, Phase 2 §4 (exit codes), Phase 4 §1–2 and criterion 4.1
- **Detail**: The brief says "3 repeats **if the budget allows**", and Phase 4 §1 says repeats that do not fit "are skipped and reported". But the runner contract exits 2 with `"complete": false` on a "budget stop", criterion 4.1 demands exit 0 with `complete: true`, and `test_newest_result_is_complete` would reject the file. The whole-repeat pre-check in D12 makes a skipped third repeat plausible. With the real case sizes (~75k input chars per repeat), the worst case is about 4.3 USD per repeat. Before repeat 3 the remaining budget is roughly 9.50 − smoke − 2 × actual. That fits only while actual spend per repeat stays under ~2.6 USD, and that figure is unmeasured for three of the four models. "Stability" is also undefined when fewer than 2 repeats finish.
- **Fix**: Define in D12/D20: `complete` = at least one repeat finished, and every started repeat has a row for every case × model with no `budget` error. A repeat that was never started because its worst case did not fit is recorded in `repeats_requested`, `repeats_completed` and `repeats_skipped_budget`, and still exits 0. Exit 2 / `complete: false` only when a reservation is refused mid-repeat. Stability = "n/a" when `repeats_completed < 2`. Reword 4.1 to "exits 0 with `complete: true`; `repeats_completed` recorded (3 if the budget allowed)".
  - Strength: matches the brief's wording and keeps the autonomous flow from stalling on a correct, budget-respecting result.
  - Tradeoff: a 1–2 repeat result gives weaker stability evidence. The report must say so.
  - Confidence: HIGH — the contradiction is in the plan text itself.
  - Blind spot: the actual cost per repeat for Claude and Gemini with `effort: low` on OpenRouter.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F3 — The ledger can under-count: error paths, SDK retries on OpenRouter and reasoning tokens past `max_tokens`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: D12, D14, Phase 1 §2, Phase 2 §1
- **Detail**: (a) The plan says to "settle with actual", but not what happens when the call raises after it was billed: pydantic `ValidationError` from `responses.parse`, `LengthFinishReasonError` / `ContentFilterFinishReasonError` from `chat.completions.parse`, or a timeout. Settling those at 0 releases spent money. (b) The OpenAI route pins `max_retries=0`, but the OpenRouter client is specified as `OpenAI(base_url=..., api_key=...)`, which defaults to 2 retries and a 600 s timeout. One reservation could then cover up to 3 billed attempts. (c) The worst case assumes 6000 output tokens. Whether OpenRouter's `max_tokens` also caps Gemini/Claude reasoning tokens is undocumented in research §3. If it does not, actual cost can exceed the reservation. (d) A worker crash between reserve and settle is not addressed.
- **Fix**: In D12/D14 add: "Any exception after the request is sent settles at the full reservation, or at the usage carried by the exception when present (`LengthFinishReasonError.completion.usage`). Unsettled reservations persist in the file and count as spent (crash-safe). If actual > reservation, record actual; if total spent + reserved ever exceeds the effective cap, refuse all further reservations. The OpenRouter client uses `timeout=TIMEOUT_SECONDS, max_retries=0`. Map `LengthFinishReasonError` → `incomplete`." Phase 3 manual: "per route, completion tokens incl. reasoning ≤ `MAX_OUTPUT_TOKENS`; if not, raise that model's worst-case output in D13 before the full run". Phase 1 tests: "tests never use the default ledger path".
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F4 — D7 counts budget, config and transport errors as false fails, which can skew the ranking

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: D7, D9, Phase 2 §4 aggregation
- **Detail**: D7 says an error on an expected-pass case is a false fail, and error kinds include `budget` and `api:<ExceptionType>`. A mid-run budget refusal, an OpenRouter 429/503, or "no endpoint satisfies `zdr`" is not the model's quality. Yet under D9's first criterion (lowest false-fail rate) it can decide the winner, and it hits OpenRouter models more than direct OpenAI ones.
- **Fix**: In D7: "Only `schema`, `no_output` and `incomplete` are model errors (fail-closed → false fail on an expected-pass case). `budget`, `config` and `api:*` are infra errors: excluded from rates, listed per model, and a model with an infra error on any hard case in every completed repeat is 'not measured' for that case. A model with unmeasured hard blocker cases cannot be declared winner."
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F5 — The decision rule does not say what happens when no model qualifies, and blocker and warning detection never reach the verdict or the matrix

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: D8, D9, D11, Phase 2 §2 (assertion) and §4 (aggregation)
- **Detail**: (a) D8 disqualifies a model on a false pass in *any* repeat: 5 hard fail cases × up to 3 repeats × 4 models. It is plausible that every model, the baseline included, is disqualified at least once, and the plan has no rule for that tie, so the "winner" would be whatever the code does. (b) The brief says each case states an expected verdict **and** an expected blocker. The assertion compares only the verdict, so a fail-secret case blocked for a hallucinated `correctness` 2 while `no_secrets` scored 9 shows green in promptfoo. Reading "false pass on a blocker" at verdict level for disqualification is defensible, because the gate's job is to stop the PR. But blocker misses must still be visible. (c) D11 says warnings are "reported", but the Phase 2 aggregation list (false passes, false fails, error rate, blocker attribution, soft sensitivity, cost, latency, stability) has no warning-detection figure. The brief's "at least one fail per each of six criteria" then measures nothing for `tests` and `openai_boundary`.
- **Fix A ⭐ Recommended**: Keep verdict-level disqualification, assert the blocker, report warnings, and add a no-winner rule
  - Plan edits: D8 adds "If no model qualifies, the recommendation is to keep gpt-5.4 (no switch), and the models are listed by fewest false passes, for information only." The assertion passes only when the verdict matches **and**, for a fail case, every expected blocker is in `failed_blockers(review)`. The aggregation adds "right verdict, wrong blocker" and "warning detection rate (expected warning ≤ 3)" per model, both in the matrix. Record in D11 that the brief's "fail per criterion" is adapted for warnings because `final_verdict` cannot fail on them (`criteria.py:90`).
  - Strength: rule decided before the run (the brief requires a fixed rule); the promptfoo UI shows blocker misses.
  - Tradeoff: promptfoo's pass rate no longer equals "verdict correct". The matrix must keep the two apart.
  - Confidence: HIGH — the plan text plainly leaves this undecided.
  - Blind spot: how often models disagree on the blocker; unknown until the run.
- **Fix B**: Disqualify on a majority of repeats (≥ 2 of 3) instead of any repeat
  - Strength: less sensitive to one sampling flake.
  - Tradeoff: weaker than the brief's literal "a false pass disqualifies", and it lets a sometimes-leaky gate win.
  - Confidence: MEDIUM — it changes the user's rule, against the "conservative option" mandate.
  - Blind spot: with fewer than 3 repeats (F2) a majority is ill-defined.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix A

### F6 — Warning seeds may honestly trigger a blocker, punishing a better reviewer on a `hard` case

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 §4 cases table (`warn-no-tests`, `warn-openai-boundary`), D10, D11
- **Detail**: `warn-openai-boundary` adds a direct OpenAI call in `conversations/views.py`. That call skips `llm.py`'s daily-budget charge and error handling, and a careful reviewer can fairly score `correctness` ≤ 3 for it, which gives verdict `fail`. `warn-no-tests` *removes* an existing test along with a behaviour change, which reads like hiding a regression (`correctness`). Both are `hard` with expected `pass`, so a correct, stricter model collects false fails, and D9 ranks false fails first.
- **Fix**: In the cases table: `warn-openai-boundary` = a module-level `from openai import OpenAI` plus a small helper that builds a client but is not wired to any URL or request path (behaviour-neutral). `warn-no-tests` = a small, obviously intended behaviour change with **no new test** (no test deletion). Add to Phase 1 manual 1.4: "the two warning diffs read as behaviour-neutral for blockers". If that cannot be achieved, tier them `soft`.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F7 — Structured-output enforcement per route is not actually verified; `require_parameters` and ZDR allow endpoints that only list `response_format`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: D5, Phase 3 §1 and criteria 3.3–3.4
- **Detail**: The brief asks to "verify each model really enforces the structured output schema through its route". Phase 3 only checks that one output parses. Research §3 says Bedrock counts as ZDR but lists only `response_format`, not `structured_outputs`, and that `require_parameters` "does not prove strict decoding". So a Claude call can be served by an endpoint that treats the schema as a hint. The D5 fallback (drop `zdr`) widens the set further. A valid output on one smoke call proves nothing about enforcement, and in the full run the served provider can differ per call.
- **Fix**: In D5, add `provider.only` restricted to endpoints that list `structured_outputs` and satisfy the data policy (per research §3: Claude → `google-vertex`, `azure`; Gemini → `google-vertex`), resolved in the smoke from the free `GET /api/v1/models/<slug>/endpoints`. Each row records `served_provider`, and the aggregation flags any row served outside the list. Phase 3 manual 3.3 then reads "each model returns a schema-valid review from an endpoint listing `structured_outputs`; Gemini integer-enum enforcement recorded as 'validated client-side, not provably enforced' if Vertex documents string-only enums". The report states which models are enforced vs. validated only.
  - Strength: turns "verify enforcement" from an assumption into a recorded, per-row fact, using only free metadata calls.
  - Tradeoff: if `only` leaves no endpoint, the model errors out. That is the intended "report, don't work around" outcome.
  - Confidence: MEDIUM — the endpoint slugs come from research and must be confirmed in the smoke.
  - Blind spot: whether OpenRouter's `only` combines with `zdr` as expected; confirmed by the smoke.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F8 — The promptfoo Python bridge cannot import `scripts.*` as specified, and the dry run never exercises promptfoo

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: D15, Phase 2 §1–4 and criterion 2.3
- **Detail**: promptfoo 0.125.1 loads `provider.py`, `assertion.py` and `cases.py` with `spec_from_file_location` and puts only the script's own directory on `sys.path` (`persistent_wrapper.py:93-101`). The interpreter is started on promptfoo's wrapper, so the repo root is not on the path. `from scripts.review.run_review import _build_input` (and the `talkaitive.settings` import behind it) then fails in all three files. D15's `PROMPTFOO_PYTHON=.venv/bin/python` is relative to the node process's cwd. The provider runs `git` with an unspecified cwd. `--dry-run` "does everything except the promptfoo call", so the first time the bridge runs is the paid smoke (Phase 3).
- **Fix**: D15: the runner sets `PYTHONPATH=<repo root>`, an absolute `PROMPTFOO_PYTHON`, and `cwd=<repo root>` for promptfoo. The provider runs git with `cwd=REPO_ROOT` from `__file__`. The assertion accepts `output` as dict or JSON string. Add `--fake` (provider returns a canned `Review` and reserves 0, no network) and a Phase 2 Automated criterion: "`uv run python -m scripts.review.eval.run --fake --out <tmp>` runs promptfoo 0.125.1 end to end over all cases and models, exits 0 and writes a result file".
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F9 — Gate details: newest file by name is ambiguous, `settings.LLM_MODEL` is ambiguous, and every future re-run costs all four models

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architectural Fitness
- **Location**: D18, D21, Phase 4 §2
- **Detail**: (a) Files named `<YYYY-MM-DD>-<shortsha>.json` sort by a random hex on the same day, so "newest by name" is undefined for two runs in one day. (b) "`settings.LLM_MODEL`" could mean `django.conf.settings` (which is `settings_test` under pytest and unconfigured in the runner), `talkaitive.settings`, or the value bound in `run_review` (`run_review.py:50`). Only the last is what the reviewer uses. A local `LLM_MODEL` in the runner's env would also differ from CI. (c) Including the model in the hash means switching the reviewer to a model the result already measured with the same prompt still turns CI red and forces a new run. The runner has no `--models` subset, so every future prompt tweak costs a full 4-model eval (~6 USD real). (d) `to_strict_json_schema` output can change with an `openai`/pydantic upgrade, which turns CI red on a dependency bump. That may be wanted, but the failure message should say it. CI itself is safe: no `LLM_MODEL` in `ci.yml`, the test needs no git history, and the mutant copies keep `scripts/` (`manual_mutants.py:38-50`, mutmut `also_copy`).
- **Fix**: D21: name `<YYYY-MM-DD>T<HHMMSS>-<shortsha>.json` (or sort by a `created_at` field). D18: read `scripts.review.run_review.LLM_MODEL`, and the runner prints it in preflight. Hash only prompt + schema + call constants + verdict rule, and assert separately that `LLM_MODEL` is in the newest result's measured models (still red for an unmeasured model). Add `--models` to the runner so a re-run can measure only the reviewer's model. The gate's failure message names the command and mentions SDK/pydantic upgrades. Optionally drop `EXCLUDED_PATHS` and `MAX_DIFF_CHARS` from the hash: the eval cases do not exercise them.
  - Strength: no false alarms, cheaper re-runs, and a deterministic "newest".
  - Tradeoff: the brief's "model changed → red" becomes "model changed to an unmeasured model → red". Arguably the same intent, but a reading the report should state.
  - Confidence: HIGH for (a)/(b); MEDIUM for (c), which is a design preference.
  - Blind spot: None significant.
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan

### F10 — Node support is not checked by the runner, and share links go into a public repo

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: D15, D16, Phase 2 §4 preflight, Phase 4 manual 4.5
- **Detail**: The brief asks to "check Node support". The preflight checks only the promptfoo version and records `node_version`. The `npx -y promptfoo@0.125.1` fallback downloads at run time. The repo is public, so the committed share links are readable by anyone who can open them. Their content includes the eval diffs (the fake secret, the injection) and model outputs.
- **Fix**: Preflight: refuse if `node --version` < 22.22.0 (promptfoo 0.125.1 `engines`). Phase 4 manual 4.5: "share links open in the TalkAItive org **and are not viewable logged out**".
- **Decision**: ACCEPTED (orchestrator, autonomous mode, 2026-11-02): Fix in plan
