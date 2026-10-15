---
change_id: testing-suite-trust-and-ci
title: Suite trust and CI floor — mutation-proven tests and a CI gate before main
status: archived
created: 2026-10-14
updated: 2026-10-15
archived_at: 2026-10-15T11:47:23Z
---

## Notes

Open a change folder for rollout Phase 1 of context/foundation/test-plan.md: "Suite trust and CI floor".
Risks covered: #2 (regression reaches production unnoticed: no CI before auto-deploy from main, and AI-written tests verified by the same model may pass on broken code). Test types planned: mutation testing + CI gate (pytest, ruff).
Risk response intent: #2 — prove that deliberately breaking critical deterministic logic (per-user data isolation, daily budget accounting, analysis state, memory selection) makes the test suite fail, and that the suite runs automatically on every PR before merge to main; expected values must come from requirements (PRD, test plan, interview), never copied from the implementation.
After creating the folder, follow the downstream continuation rule.

User decisions D1–D8 from Phase 6 (2026-10-15) — including the unplanned PRD line "Odmowa akcji" (D2) and the turn timeouts left to test-plan Phase 2 (D7) — are recorded in `mutmut-baseline.md`, section "Klasyfikacja 51 pozostałych przeżyć".
