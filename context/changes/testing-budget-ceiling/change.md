---
change_id: testing-budget-ceiling
title: Test rollout phase 4 — prove the daily budget ceiling holds
status: implementing
created: 2026-10-16
updated: 2026-10-16
archived_at: null
---

## Notes

Open a change folder for rollout Phase 4 of context/foundation/test-plan.md: "Budget ceiling". Risks covered: #4 — the daily $1 limit does not hold: a single message or analysis costs many times more than usual, and failed or retried paid calls are not counted in the day's spend. Test types planned: unit + integration. Risk response intent: #4 — prove that the day's total cost (turns, analyses, failed and retried attempts) never exceeds the limit; once the limit is reached no new paid call can start; the reset happens at midnight Europe/Berlin, including across DST changes. Challenge "an attempt cut off by a timeout costs nothing" and "a per-call message/response length cap exists"; avoid computing the expected cost with the same formula as the code, and avoid fixed dates without a time zone. Note: E2E (Playwright) is now a mandatory layer (test-plan §7, 2026-10-16); research should judge by cost × signal whether a browser-level check of the "limit reached" state adds signal beyond integration tests. After creating the folder, follow the downstream continuation rule.
