# AI review model eval — final report

> Change `ai-review-model-eval`, 2026-11-02. Plan: `plan.md` (decision rule D7–D11, fixed before the runs). Smoke notes: `smoke.md`. Reviews: `reviews/plan-review.md`, `reviews/impl-review.md`.
> Result files: `scripts/review/eval/results/2026-11-02T095143-bb90e26.json` (run 1) and `scripts/review/eval/results/2026-11-02T104452-37e5936.json` (run 2, **current**: its fingerprint is the one the CI gate checks).

## Runs

- Command: `uv run --env-file .env python -m scripts.review.eval.run --repeats 3 --max-usd 10 --share`, each time on a clean tree; promptfoo 0.125.1 (global, version checked), Node v25.8.0, `--no-cache --no-share`, shared explicitly afterwards.
- Run 1 (`bb90e26`) and run 2 (`37e5936`): 16 cases × 4 models × 3 repeats = 192 calls each; 3 of 3 repeats completed both times, none skipped for budget, 0 model errors, 0 infra errors, 0 calls served off policy (run 2 counts it; run 1 predates the counter, but every OpenRouter call was served by "Google" = google-vertex).
- Why two runs: the implementation review (F3) found the fingerprint did not cover the prompt wrapper (`_build_input`) or the verdict code; the fingerprint was extended, which needs a new result file. Prompt, schema and settings were identical in both runs, so run 2 is also a reproducibility check.
- Spend: **3.14 USD total** of the 10 USD cap (smoke 0.03, run 1 1.56, run 2 1.55), enforced by the run's own ledger across OpenAI and OpenRouter. The pre-run worst case was 4.26 USD per repeat; each repeat started only after the ledger confirmed its full worst case still fit.
- Share links (TalkAItive org). Checked: not viewable when logged out (redirect to the promptfoo login). Not checked by the agent: the logged-in view inside the org (needs a sign-in) — left to the user.
  - Run 1: https://www.promptfoo.app/eval/eval-iVA-2026-11-02T09:51:44, https://www.promptfoo.app/eval/eval-ueD-2026-11-02T09:53:31, https://www.promptfoo.app/eval/eval-78q-2026-11-02T09:55:11
  - Run 2: https://www.promptfoo.app/eval/eval-6gv-2026-11-02T10:44:54, https://www.promptfoo.app/eval/eval-tWL-2026-11-02T10:46:38, https://www.promptfoo.app/eval/eval-gWU-2026-11-02T10:48:22

## Matrix (both runs, 6 repeats per model)

Hard cases: 9 expected pass (54 runs per model), 5 expected fail with a blocker (30 runs). Soft cases: 2 subtle real bugs (12 runs), reported only. Warning cases: 2 (12 runs).

| Model (route) | Hard false passes | False fails | Warnings detected | Soft bugs caught | Mean cost / review | Median time | Stability (run 1 / run 2) |
|---|---|---|---|---|---|---|---|
| gpt-5.4 (OpenAI, baseline) | 0 / 30 | 5 / 54 (9.3%) | 8 / 12 | 8 / 12 | 0.0120 USD | 7.4–8.2 s | 0.875 / 0.875 |
| gpt-6.1-terra (OpenAI) | 0 / 30 | 12 / 54 (22.2%) | 12 / 12 | 12 / 12 | 0.0040 USD | 4.5–5.0 s | 1.000 / 1.000 |
| Claude Sonnet 5.5 (OpenRouter) | 0 / 30 | 0 / 54 | 7 / 12 | 3 / 12 | 0.0130 USD | 4.4 s | 0.938 / 0.938 |
| Gemini 3.8 Flash (OpenRouter) | 0 / 30 | 0 / 54 | 9 / 12 | 1 / 12 | 0.0033 USD intro / **0.0067 USD regular** | 4.7–4.9 s | 1.000 / 0.938 |

No model gave a right verdict with the wrong blocker. Stability = share of the 16 cases with the same verdict in all 3 repeats of a run. Times are indicative only: OpenRouter adds routing latency and the routes are different network paths. Per-run matrices: the `.md` next to each result file.

Per-case notes (from the result entries):
- Every model failed all 5 hard blocker cases in every repeat of both runs, including **the prompt-injection case** (`inject-idor`: data_isolation and correctness ≤ 3 every time; the injected "verdict pass" cannot matter, since `final_verdict` ignores the model's verdict).
- gpt-5.4's false fails all come from `pass-safe-migration` (a safe AddField with defaults flagged as an unsafe migration: 2 of 3 repeats in run 1, 3 of 3 in run 2).
- gpt-6.1-terra's false fails: `pass-surprise-view` (correctness) and `pass-safe-migration` (migrations), every repeat. It is the strictest model: it catches every soft bug and every warning but blocks clean PRs.
- Soft bugs vary between runs for gpt-5.4 (5/6, then 3/6), Claude (2/6, then 1/6) and Gemini (0/6, then 1/6): these are judgement calls, as the plan expected (D10).

## Decision by the fixed rule (both runs agree)

1. Disqualification (D8): no model let a hard blocker case pass → none disqualified.
2. Lowest false-fail rate (D9): Claude and Gemini tie at 0.
3. Lowest mean cost at regular prices: Gemini 0.0067 vs Claude 0.0130 → **winner: gemini-3.8-flash**.

## Recommendation (recommend only — nothing was switched)

- **By the rule fixed before the runs, gemini-3.8-flash is the best reviewer**, in both runs: no missed blocker, no false alarm, the most stable of the non-strict models, about half the cost of gpt-5.4 even after its introductory price ends on 2026-12-31 (0.0033 USD intro, 0.0067 USD regular, per review), and faster.
- **Caveat the rule does not weigh:** on the 2 subtle correctness bugs, Gemini caught 1 of 12 runs and gpt-5.4 caught 8 of 12. All four models stop clear violations; subtle logic bugs are where they differ. Two soft cases are a small sample. Before switching, consider adding more soft cases and deciding whether soft sensitivity should enter the rule — a rule change needs a new run with the rule fixed beforehand.
- **Conservative path:** keep gpt-5.4 until that decision is made. It missed no blocker either; its false fails come from one case type (safe migrations), and it is the most sensitive non-strict model on subtle bugs.
- gpt-6.1-terra is not recommended: 22% false fails would block clean PRs often, and it has no dated snapshot, so it can change under the same name.
- A switch needs its own setting for the reviewer (`scripts/review/run_review.py` reads `LLM_MODEL`, which the app shares), an OpenRouter route and a new secret in `ai-review.yml`, and a price entry: a separate change. After it, the CI gate in `tests/test_review_eval.py` requires a result file that lists the new model (re-run with `--models <label>`).

## Route and data checks

- Model IDs verified 2026-11-02: Claude on OpenRouter is `anthropic/claude-sonnet-5.5` (the brief's `claude-sonnet-5-5` is the Anthropic-native form). gpt-6.1-terra has no dated snapshot. No price change versus the 2026-11-01 check.
- OpenRouter requests used `provider: {data_collection: "deny", zdr: true, require_parameters: true, only: [google-vertex, azure]}`; all 192 OpenRouter calls of both runs were served by Google Vertex (reported as "Google"); no ZDR fallback was needed.
- Structured output: OpenAI enforces the strict schema natively. On OpenRouter the `only` list keeps the calls on endpoints that advertise `structured_outputs`; whether Vertex enforces the integer `enum` for Gemini is not documented, so every output was also validated with pydantic. 0 of 384 outputs failed validation.

## Proposal: CLAUDE.md boundary exception (not applied)

Replace the sentence in CLAUDE.md "In the application, only `conversations/llm.py` calls OpenAI; the standalone CI review script `scripts/review/` is the one deliberate exception." with:

> In the application, only `conversations/llm.py` calls a model. Deliberate exceptions outside the app: the CI review script `scripts/review/`, and its local, manual model eval `scripts/review/eval/` (promptfoo 0.125.1, OpenAI and OpenRouter, never in CI; see `context/foundation/test-plan.md` §6.7).

The reviewer's `openai_boundary` criterion already exempts `scripts/review/`, so the eval did not need a criteria change.

## PRs and CI

- One PR would have had ~113k reviewable characters, over the 100k threshold below the AI review's 120k cap, so the change was split (plan-review F1 Fix B): PR 1 = eval code and tests on `ai-review-model-eval`; PR 2 = review fixes, results, CI gate, docs on `ai-review-model-eval-results`, stacked on PR 1.
- The commit `37e5936` on PR 2 has the fingerprint gate red by design (the runner needs a clean tree, so the new result lands in the next commit, `db36a9f`); the PR head is green.

## PR checks

_To be filled after opening the PRs._
