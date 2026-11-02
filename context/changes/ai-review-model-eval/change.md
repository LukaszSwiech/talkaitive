---
change_id: ai-review-model-eval
title: Compare AI review models with promptfoo and add a regression gate
status: implementing
created: 2026-11-02
updated: 2026-11-02
archived_at: null
---

## Notes

Compare AI review models with promptfoo and leave a regression gate.

The user's full brief (2026-11-02), the source of requirements for every step of this change:

- **Flow:** /10x-research → /10x-plan → /10x-plan-review → /10x-implement → /10x-impl-review without waiting for the user. The plan needs no user confirmation: record decisions and pick the conservative option. Call the user only for a rejected credential, a missing permission, or a quality gate failed 3 times. Chat in Polish, PRs in English. The orchestrator delegates research, test-set building, implementation, verification and review to subagents (one focused task each, never two editing the same files at once).
- **Branch:** `ai-review-model-eval` from an up-to-date `main` (ci-ai-review-gate is merged: PR 28 at f3a9789, PR 31 at 12dccd1). Uses the criteria from change ci-ai-review-gate. Open a new PR.
- **Permissions:** push non-main branches and open a PR. Forbidden: push to main, force-push, merge, reading or printing key values. Do not change `LLM_MODEL` or production settings: only recommend.
- **Credentials:** `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `PROMPTFOO_API_KEY` in `.env` (gitignored, `NAME = value` with spaces, so load with `uv run --env-file .env ...`; check that promptfoo reads the real value; never read or print values). promptfoo CLI 0.125.1 installed globally, Node v25.8.0, `promptfoo auth whoami` → organization TalkAItive. OpenRouter key has a 10 USD limit. One cheap real OpenRouter check at the start.
- **Models:** gpt-5.4 (baseline, direct OpenAI), gpt-6.1-terra (direct OpenAI), claude-sonnet-5-5 and gemini-3.8-flash (via OpenRouter). IDs and prices from a pricing check on 2026-11-01: verify at research time and flag changes. Gemini's price is introductory until 2026-12-31: show both prices. Verify each model really enforces the structured output schema through its route. Ask OpenRouter for providers that do not collect data.
- **Test set (~16 cases):** pass cases from slices of real merged PRs (12–28); fail cases seeded per criterion (at least one for each of the six) plus real bugs fixed in git history; at least one prompt injection inside a diff. Each case states expected verdict and expected blocker. Assert through the real `scripts/review/criteria.py` `final_verdict`; reuse the real prompt and schema without copying them.
- **Run:** local only, 3 repeats if the budget allows. Hard budget 10 USD total across all providers: compute the worst case before the run and stop before crossing it (the OpenRouter key limit does not cover direct OpenAI calls). Pin promptfoo 0.125.1 in the documented command and check Node support. Document as a deliberate exception to "only conversations/llm.py calls a model" — as a proposal in the final report, no CLAUDE.md edit.
- **Decision rule (fixed before the run):** a false pass on a blocker disqualifies a model; then lowest false-fail rate, then cost, then time. Report a matrix of pass/fail, cost and time per model plus repeat-to-repeat stability. Commit the result file and the promptfoo share link. OpenRouter routing adds latency, so timings are not fully comparable.
- **Regression gate:** the eval stays local (like `scripts/eval`). Add a free CI test that goes red when the review prompt, schema or model changed without a new result file (stored hash). No paid calls and no new secrets in CI.
- **Finish:** Polish summary with the recommendation, without waiting for an answer. A model switch needs a separate setting (run_review shares `LLM_MODEL` with the app) and its own change.
- **Done when:** pytest and ruff green, promptfoo run reproducible from one documented command, matrix and recommendation delivered.
