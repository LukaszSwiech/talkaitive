---
change_id: ci-ai-code-review
title: AI code review agent in GitHub Actions
status: impl_reviewed
created: 2026-10-31
updated: 2026-10-31
archived_at: null
---

## Notes

Python script (OpenAI, structured output) reviews every same-repo PR diff in GitHub Actions and posts a comment plus an ai-cr:passed / ai-cr:failed label. Purpose: 10xChampion evidence (M5L2 + M5L3). Full brief, rules and start instructions: `requirements.md` in this folder. Read it first.
