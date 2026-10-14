---
change_id: testing-suite-trust-and-ci
title: Suite trust and CI floor — mutation-proven tests and a CI gate before main
status: planned
created: 2026-10-14
updated: 2026-10-14
archived_at: null
---

## Notes

Open a change folder for rollout Phase 1 of context/foundation/test-plan.md: "Suite trust and CI floor".
Risks covered: #2 (regression reaches production unnoticed: no CI before auto-deploy from main, and AI-written tests verified by the same model may pass on broken code). Test types planned: mutation testing + CI gate (pytest, ruff).
Risk response intent: #2 — prove that deliberately breaking critical deterministic logic (per-user data isolation, daily budget accounting, analysis state, memory selection) makes the test suite fail, and that the suite runs automatically on every PR before merge to main; expected values must come from requirements (PRD, test plan, interview), never copied from the implementation.
After creating the folder, follow the downstream continuation rule.
