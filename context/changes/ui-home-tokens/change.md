---
change_id: ui-home-tokens
title: Ui home tokens
status: impl_reviewed
created: 2026-10-20
updated: 2026-10-21
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

UI change driven by `/10x-ui`.

- **View (one):** home / topic selection — `conversations/templates/conversations/home.html`, rendered inside `accounts/templates/base.html`. Chosen because it will grow (20 topics today; level, language, known-words lists later), so the components built here get reused.
- **Contract variant:** no design system yet → this change introduces it. Plain CSS custom properties with shadcn/ui token names (`--background`, `--foreground`, `--primary`, `--muted`, `--destructive`, `--border`, `--ring`, `--radius`, …). No new dependency and no build step (no Tailwind, no Node in the app). Scope: one token block plus the 2–3 shared components home uses (button, card/list item, notice/alert). A later move to Tailwind v4 + Basecoat stays possible because the token names already match shadcn.
- **Token source:** tweakcn export (Tailwind v4, OKLCH), stored verbatim in `theme-source.css` in this folder.
- **Out of scope:** login, conversation detail, account delete — each gets its own change that inherits this contract.
