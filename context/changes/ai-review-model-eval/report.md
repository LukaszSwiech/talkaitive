# AI review model eval — final report

> Change `ai-review-model-eval`, 2026-11-02. Plan: `plan.md` (decision rule D7–D11, fixed before the run). Result file: `scripts/review/eval/results/2026-11-02T095143-bb90e26.json` (+ `.md` matrix). Smoke notes: `smoke.md`.

## Run

- Command: `uv run --env-file .env python -m scripts.review.eval.run --repeats 3 --max-usd 10 --share` on a clean tree at `bb90e26`; promptfoo 0.125.1 (global, version checked), Node v25.8.0, `--no-cache --no-share`, shared explicitly afterwards.
- 16 cases × 4 models × 3 repeats = 192 calls; 3 of 3 repeats completed, none skipped for budget, `complete: true`, 0 model errors, 0 infra errors.
- Spend: **1.58 USD total** (smoke 0.03 + full run 1.56) of the 10 USD cap, enforced by the run's own ledger across OpenAI and OpenRouter. The pre-run worst case was 4.26 USD per repeat, so only 2 of 3 repeats were guaranteed up front; each further repeat started only after the ledger confirmed its full worst case still fit.
- Share links (TalkAItive org; not viewable when logged out — checked, redirects to login):
  - https://www.promptfoo.app/eval/eval-iVA-2026-11-02T09:51:44
  - https://www.promptfoo.app/eval/eval-ueD-2026-11-02T09:53:31
  - https://www.promptfoo.app/eval/eval-78q-2026-11-02T09:55:11

## Matrix

Hard cases: 9 expected pass (27 runs per model), 5 expected fail with a blocker (15 runs). Soft cases: 2 subtle real bugs (6 runs), reported only.

| Model (route) | Hard false passes | False fails | Wrong blocker | Warnings detected | Soft bugs caught | Mean cost / review | Median time | Stability |
|---|---|---|---|---|---|---|---|---|
| gpt-5.4 (OpenAI, baseline) | 0 / 15 | 2 / 27 (7.4%) | 0 | 4 / 6 | 5 / 6 | 0.0120 USD | 8.2 s | 0.875 |
| gpt-6.1-terra (OpenAI) | 0 / 15 | 6 / 27 (22.2%) | 0 | 6 / 6 | 6 / 6 | 0.0040 USD | 4.5 s | 1.000 |
| Claude Sonnet 5.5 (OpenRouter) | 0 / 15 | 0 / 27 | 0 | 3 / 6 | 2 / 6 | 0.0130 USD | 4.4 s | 0.938 |
| Gemini 3.8 Flash (OpenRouter) | 0 / 15 | 0 / 27 | 0 | 5 / 6 | 0 / 6 | 0.0034 USD intro / **0.0067 USD regular** | 4.7 s | 1.000 |

Stability = share of the 16 cases with the same verdict in all 3 repeats. Times are indicative only: OpenRouter adds routing latency, and the OpenAI and OpenRouter routes are not the same network path.

Per-case notes (from the result entries):
- Every model failed all 5 hard blocker cases in every repeat, including **the prompt-injection case** (`inject-idor`: data_isolation + correctness ≤ 3 every time; the injected "verdict pass" never mattered, since `final_verdict` ignores the model's verdict).
- gpt-5.4's 2 false fails: `pass-safe-migration` (a safe AddField with defaults) flagged as an unsafe migration in 2 of 3 repeats — also its only unstable cases.
- gpt-6.1-terra's 6 false fails: `pass-surprise-view` (correctness, 3/3) and `pass-safe-migration` (migrations, 3/3). It is the strictest model: it catches every soft bug and every warning but blocks clean PRs.
- Claude missed the `tests` warning on `warn-no-tests` 3/3 and caught `soft-paid-resubmit` in 2 of 3 repeats only.
- Gemini caught neither soft bug in any repeat.

## Decision by the fixed rule

1. Disqualification (D8): no model let a hard blocker case pass → none disqualified.
2. Lowest false-fail rate (D9): Claude and Gemini tie at 0.
3. Lowest mean cost at regular prices: Gemini 0.0067 vs Claude 0.0130 → **winner: gemini-3.8-flash**.

## Recommendation (recommend only — nothing was switched)

- **By the rule fixed before the run, gemini-3.8-flash is the best reviewer**: no missed blocker, no false alarm, perfectly stable, about half the cost of gpt-5.4 even after its introductory price ends on 2026-12-31 (0.0034 USD intro, 0.0067 USD regular, per review), and about 1.8× faster.
- **Caveat that the rule does not weigh:** Gemini caught 0 of 6 subtle correctness bugs, while gpt-5.4 caught 5 of 6. The CI gate's blockers stop clear violations with every model; subtle logic bugs are where they differ. With only 2 soft cases this is a small sample. Before switching, consider adding more soft cases and deciding whether soft sensitivity should enter the rule — that is a change to the decision rule, so it needs a new run with the rule fixed beforehand.
- **Conservative path:** keep gpt-5.4 until that decision is made. It has no missed blocker either, its false-fail rate is low (one migration case), and it is the most sensitive model on subtle bugs except the over-strict gpt-6.1-terra.
- gpt-6.1-terra is not recommended: 22% false fails would block clean PRs often. It also has no dated snapshot, so it can change under the same name.
- A switch needs its own setting for the reviewer: `scripts/review/run_review.py` reads `LLM_MODEL`, which the app shares, and an OpenRouter route, a new secret in `ai-review.yml`, and a price entry. That is a separate change; after it, the CI gate in `tests/test_review_eval.py` requires a result file that lists the new model (re-run with `--models <label>`).

## Route and data checks

- Model IDs verified 2026-11-02: Claude on OpenRouter is `anthropic/claude-sonnet-5.5` (the brief's `claude-sonnet-5-5` is the Anthropic-native form). gpt-6.1-terra has no dated snapshot. No price change versus the 2026-11-01 check.
- OpenRouter requests used `provider: {data_collection: "deny", zdr: true, require_parameters: true, only: [google-vertex, azure]}`; every one of the 96 OpenRouter calls was served by Google Vertex (reported as "Google"), so no ZDR fallback was needed.
- Structured output: OpenAI enforces the strict schema natively. On OpenRouter the `only` list keeps the calls on endpoints that advertise `structured_outputs`; whether Vertex enforces the integer `enum` for Gemini is not documented, so every output was also validated with pydantic. 0 of 192 outputs failed validation.

## Proposal: CLAUDE.md boundary exception (not applied)

Replace the sentence in CLAUDE.md "In the application, only `conversations/llm.py` calls OpenAI; the standalone CI review script `scripts/review/` is the one deliberate exception." with:

> In the application, only `conversations/llm.py` calls a model. Deliberate exceptions outside the app: the CI review script `scripts/review/`, and its local, manual model eval `scripts/review/eval/` (promptfoo 0.125.1, OpenAI and OpenRouter, never in CI; see `context/foundation/test-plan.md` §6.6).

The reviewer's `openai_boundary` criterion already exempts `scripts/review/`, so the eval did not need a criteria change.

## PRs and CI

- The reviewable diff would have been ~113k characters in one PR, over the 100k threshold below the AI review's 120k cap, so the change was split (plan-review F1 Fix B): PR 1 = eval code and tests (91.5k reviewable chars), PR 2 = result, CI gate, docs (22.2k), stacked on PR 1.
- CI and AI review results: see "PR checks" below (filled after the PRs were opened).

## PR checks

_To be filled after opening the PRs._
