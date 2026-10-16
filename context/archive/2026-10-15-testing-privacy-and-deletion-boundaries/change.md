---
change_id: testing-privacy-and-deletion-boundaries
title: Test rollout Phase 3 — privacy isolation and account-deletion boundaries
status: archived
created: 2026-10-15
updated: 2026-10-16
archived_at: 2026-10-16T08:03:07Z
---

## Notes

Open a change folder for rollout Phase 3 of context/foundation/test-plan.md: "Privacy and deletion boundaries".
Risks covered: #3 (user B sees user A's conversations, mistakes or memory — via a swapped id in the URL, child data, or memory built from someone else's conversations), #6 (data left behind after account deletion, e.g. from a model added in a later slice). Test types planned: integration (+ mutation of the relation guard).
Risk response intent: #3 — every view with an id in the URL and every path to child data returns 404 for another user's object, and user A's memory block contains no data of user B; must challenge "logged in = allowed to see the object" and "the lessons.md pattern is applied everywhere"; avoid an isolation test for only one view, asserting 403 instead of 404, or testing a dummy model instead of the real ones. #6 — after account deletion no model related to the user keeps rows, and a new data model without a deliberate decision breaks the test; must challenge "the existing relation guard surely catches a new model"; avoid a cascade test on a dummy model only, or a guard that compares a list with itself.
Work happens on branch testing-privacy-and-deletion-boundaries (already created and checked out; §3 already set to "change opened").
After creating the folder, follow the downstream continuation rule.
