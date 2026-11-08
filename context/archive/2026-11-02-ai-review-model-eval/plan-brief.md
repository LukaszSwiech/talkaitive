# AI Review Model Eval — Plan Brief

> Full plan: `context/changes/ai-review-model-eval/plan.md`
> Research: `context/changes/ai-review-model-eval/research.md`

## What & Why

Measure how well four models run the CI AI reviewer — gpt-5.4 (today's model), gpt-6.1-terra, Claude Sonnet 5.5 and Gemini 3.8 Flash — on cases with known answers, so a model choice rests on false-pass/false-fail rates, cost and time instead of guesses. Leave a free CI test that notices when the reviewer's prompt, schema or model changed without a fresh measurement.

## Starting Point

`scripts/review/run_review.py` makes one `responses.parse` call on `LLM_MODEL` (gpt-5.4) and `criteria.py::final_verdict` fails a PR when a blocker scores ≤ 3. Only one seeded true positive exists; no rates, no other model, no prompt hash anywhere.

## Desired End State

One command runs a promptfoo 0.125.1 eval locally under a hard 10 USD cap and writes a compact result file with a per-model matrix and a winner chosen by a rule fixed before the run. The result and promptfoo share links are committed. `tests/test_review_eval.py` goes red in CI when the fingerprint no longer matches the newest result. Production is untouched; switching models is a recommendation for a later change.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Mode | Autonomous: decisions recorded, conservative option | User's brief said no confirmation | Plan |
| Reuse | Import real `_build_input`, `truncate_diff`, `Review`, `final_verdict`; own API call | `run_review` binds `LLM_MODEL` and its price at import | Research |
| Location | `scripts/review/eval/` | Inside the reviewer's `openai_boundary` exemption | Research |
| Case diffs | Generated from git at run time, never committed; fake secret and injection text built from fragments | Keeps this PR's reviewable diff small and no contiguous secret/injection literal in the repo | Plan + review F1 |
| Result file | One entry per (case, model) with per-repeat arrays, ≤ 20 000 chars; reviewable PR diff checked < 100k | The PR's own AI review fails above 120k | Review F1 |
| OpenRouter route | `chat.completions.parse(response_format=Review)`, `developer`→`system`, no SDK retries; smoke-tested | Responses route on OpenRouter untested; retries would bill unseen calls | Research + F3 |
| Data policy | `data_collection: deny` + `require_parameters` + `zdr` + `only` endpoints advertising `structured_outputs` (drop only `zdr` per model if no endpoint) | User requirement; `require_parameters` alone allows hint-only endpoints | Research + F7 |
| Schema failure | Error row, never a verdict; model errors on expected-pass = false fail; infra errors excluded | Mirrors production exit 1 (fail-closed) without counting transport noise | Plan + F4 |
| Disqualify | Any hard expected-fail case with final verdict `pass`; if all are disqualified, keep gpt-5.4 | Brief's rule, at verdict level | Plan + F5 |
| Expected blocker | Asserted (must be in `failed_blockers`); "right verdict, wrong blocker" and warning detection reported | Each case states its blocker | F5 |
| Rank | False-fail rate → mean cost at regular prices → median latency | Brief's rule; Gemini intro price ends 2026-12-31 | Plan |
| Budget | File ledger, persisted per-call worst-case reservations, settle on every path (full reservation if usage unknown), cap = 10 − 0.50, repeat starts only if it fits whole; skipped repeats keep the run complete | Never crosses 10 USD across OpenAI + OpenRouter | Plan + F2/F3 |
| Gate | sha256 of prompt template, strict schema, call constants, verdict rule vs newest (timestamped) result file, plus `run_review.LLM_MODEL` among its measured models | Free, no network, survives mutant copies; re-measuring one model via `--models` | Research + F9 |
| Bridge check | `--fake` end-to-end promptfoo run at zero cost; absolute `PROMPTFOO_PYTHON`, `PYTHONPATH`=repo | promptfoo only adds the script's own directory to `sys.path` | F8 |
| Model IDs | `anthropic/claude-sonnet-5.5` (not `-5-5`); `gpt-6.1-terra` has no snapshot | Verified 2026-11-02 | Research |

## Scope

**In scope:** eval package + tests; 16 cases (7 pass, 4 hard blocker fails, 2 warning cases, 1 prompt injection, 2 soft real bugs); smoke run; full run (up to 3 repeats); result file + share links; CI fingerprint test; test-plan §6.6; final report.

**Out of scope:** any production setting or `LLM_MODEL` change; CLAUDE.md edit (proposal only); promptfoo/Node/paid calls in CI; committed raw outputs or diff fixtures; prompt or schema tuning per model.

## Architecture / Approach

`run.py` (preflight, budget, per-repeat loop) → promptfoo 0.125.1 (`--no-cache --no-share`) → `provider.py` (materialise case diff from git → real `_build_input` → OpenAI `responses.parse` or OpenRouter `chat.completions.parse` → pydantic `Review`, cost, latency; ledger reserve/settle) → `assertion.py` (real `final_verdict` vs expected) → compact result JSON + Markdown matrix. `fingerprint.py` is shared by the runner and the CI test.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Eval core | Registry, cost, ledger, fingerprint, cases + tests | Seeds that do not match exactly once |
| 2. promptfoo wiring | Provider, assertion, config, runner, dry run | promptfoo Python bridge details |
| 3. Smoke run | 4 real calls, routes and data policy confirmed | A model failing the schema on its route |
| 4. Full run + gate | Result file, share links, CI fingerprint test | Budget stop before 3 repeats |
| 5. Docs + report | test-plan §6.6, report, PR | — |

**Prerequisites:** keys in `.env` (OpenRouter checked 2026-11-02: HTTP 200, 10 USD limit, 0 used); promptfoo 0.125.1 global; Node v25.8.0.
**Estimated effort:** one session; ≤ 10 USD.

## Open Risks & Assumptions

- Gemini on Vertex may not enforce integer enums; pydantic catches it as an error row.
- `gpt-6.1-terra` can change under the same name (no snapshot); the result is dated.
- Soft cases may be missed by every model; they do not disqualify.
- OpenRouter routing latency makes time comparisons indicative only.
- This PR's own AI review may still go red if the reviewable diff grows past the cap; fallback is a two-PR split (code, then results + gate).
- Plan review (`reviews/plan-review.md`): REVISE, 10 findings, all accepted and applied 2026-11-02.

## Success Criteria (Summary)

- pytest and ruff green; CI green on the PR.
- The promptfoo run reproduces from one documented command.
- Matrix and recommendation delivered; production unchanged.
