<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Siatka kart tematów na home

- **Plan**: context/changes/ui-home-topic-grid/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4, 5
- **Date**: 2026-10-24
- **Verdict**: NEEDS ATTENTION (was APPROVED before F7 was found during triage)
- **Findings**: 0 critical, 3 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS (2 observations) |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING (manual 4.4 approved baselines that show F7) |

Automated checks run during this review (all green): `uv run pytest` (564 passed), `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check`, `grep -rn "choice-list" accounts conversations tests` (empty), `uv run python scripts/mutation/manual_mutants.py M1 M2` (2/2 match), `npx playwright test tests/e2e/ui-home.spec.ts` (29 passed), `grep -n "topic-card\|ui/icons" CLAUDE.md` (lines 55, 57), `git diff main...HEAD -- CLAUDE.md` (10x-cli block untouched). Manual items 1.5–5.4 are all ticked; the deliberate-break items (1.6, 4.2) leave no trace in the diff by design.

Small unplanned additions (all within the planned components, no finding): `.btn .icon` sizing, `.topic-grid form { height: 100% }`, `z-index: 1` and link hover on `.category-nav`, optional `disabled` parameter on `ui/topic-card.html` (documented in CLAUDE.md), `make_conversation(topic=…)` test helper parameter, `toHaveURL(/#small-talk$/)` in the jump E2E test.

## Findings

### F1 — Plan table still names `swing` for the playground icon

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: context/changes/ui-home-topic-grid/plan.md:102
- **Detail**: Tabler v3.49.0 has no `swing`, so `playground` uses `horse-toy` (`conversations/topics.py:150`, `accounts/templates/ui/icons/horse-toy.svg`). The icons README records the swap (`README.md:30`, `:42-43`), but plan.md:67 requires it in the plan table too, and plan.md:102 still says `swing`. Progress item 1.5 ("README … zgodną z tabelą w tym planie") is ticked although the two disagree on this row.
- **Fix**: Change the icon cell in plan.md:102 to `horse-toy` and add a one-line note under the table that `swing` does not exist in Tabler v3.49.0.
- **Decision**: FIXED (plan.md:102 now `horse-toy`; substitution note added under the table)

### F2 — Draw test hard-codes the topic count

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/test_conversations.py:228
- **Detail**: `assert len(candidates) == 19` breaks as soon as a topic is added, although the next line already checks the exact list (`candidates == [key for key in ALL_KEYS if key != "bakery"]`). The CLAUDE.md how-to for adding a topic does not mention this test, so the next "add a topic" change fails here for no real reason.
- **Fix**: Replace `19` with `len(ALL_KEYS) - 1` (or drop the line; the list comparison covers it).
- **Decision**: FIXED (`len(ALL_KEYS) - 1`; 5 surprise tests pass)

### F3 — `scroll-padding-top: 4rem` has little margin with classic scrollbars

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/static/ui/css/components.css:65
- **Detail**: The nav is about 2.9rem tall (1rem nav padding + 0.875rem × line-height + 0.5rem link padding + 2px border). When the pills overflow sideways on a system with non-overlay scrollbars (Windows, ~17px), the horizontal scrollbar adds ~1rem, which uses up the whole 4rem padding; a jumped-to heading or focused card would then touch the nav edge. The E2E jump test runs only on macOS Chromium (overlay scrollbars), so it cannot catch this.
- **Fix**: Raise `scroll-padding-top` to `4.5rem` and re-run `npx playwright test tests/e2e/ui-home.spec.ts` (the `ui-focus` kitchen-sink baselines may shift and need a reviewed `--update-snapshots`).
- **Decision**: FIXED (`4.5rem`; jump test green; 6 baselines shift by a uniform 0.5rem — `ui-hover` ×4, `home-loading` phone ×2 — refresh deferred until F7 is decided, since F7 touches the same screenshots)

### F4 — `icon_template` gives `ui/icons/.svg` for a Topic without an icon

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/topics.py:25-28
- **Detail**: The card fields default to `""` (needed by `services.py:249`, which rebuilds a `Topic` from the conversation copy). Such a `Topic` passed to `ui/topic-card.html` would raise `TemplateDoesNotExist` (a 500). Not reachable today: cards are rendered only from `TOPICS` via `topics_by_category()`, and `tests/test_topics.py` guards every `TOPICS` entry.
- **Fix**: Add a docstring line on `icon_template` that cards are rendered only from `TOPICS` (a rebuilt `Topic` has no icon).
- **Decision**: FIXED (docstring on `Topic.icon_template`)

### F5 — Category nav + section loop markup duplicated in two templates

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: conversations/templates/conversations/home.html:31-51, accounts/templates/accounts/ui_kitchen_sink.html:44-56
- **Detail**: CLAUDE.md says a multi-element component used in 2+ places becomes `ui/<name>.html`. The `category-nav` + `topic-section` loop (incl. the "Topic categories" aria-label) is copied in both pages. The plan chose this on purpose (kitchen sink needs `ks-` ids and one sample per category), so it is not drift.
- **Fix**: Accept for now; extract `ui/category-nav.html` with an `id_prefix` parameter if a third use appears.
- **Decision**: ACCEPTED (deliberate plan choice; extract `ui/category-nav.html` on a third use)

### F6 — Kitchen sink still passes `topics = TOPICS[:3]` for one title

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: conversations/views.py:208
- **Detail**: With the choice list gone, `topics` is used only as `{{ topics.0.title }}` (`ui_kitchen_sink.html:71`). The plan kept the key on purpose (plan.md:278), so this is a leftover, not drift.
- **Fix**: Pass a single `sample_topic = TOPICS[0]` and use `{{ sample_topic.title }}`.
- **Decision**: FIXED (`sample_topic` in `ui_kitchen_sink` view and template; screenshots unchanged)

### F7 — "Agent is typing…" overlaps the next card row and stretches the clicked card (found during triage)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: accounts/templates/base.html:37, accounts/static/ui/css/components.css:69
- **Detail**: The plan's end state says loading on a card "works as before". `base.html` does `form.after(typing)`, so on home the indicator lands inside the card's `<li>`. `.topic-grid form { height: 100% }` makes the form fill the whole `<li>`, so the indicator overflows into the next row (phone: over "Stairwell"; desktop: over "Playground"), and the whole row stretches; the stretched `.topic-card` (a 2-row grid with `align-items: center`) splits name and subtitle to top and bottom. The committed `home-loading-*` baselines show this, and manual item 4.4 ("układ … wyglądają jak zamierzono") approved them. Both sub-agents missed it; it was spotted while checking the F3 screenshot diff.
- **Fix A ⭐ Recommended**: CSS only — `.topic-grid li { display: flex; flex-direction: column; }`, `.topic-grid form { flex: 1; }` instead of `height: 100%`, and `align-content: center` on `.topic-card`; then refresh the `home-loading-*` baselines.
  - Strength: The indicator stays right under the clicked card with no overlap; no JS change; cards keep equal heights in a row and their text stays together when stretched.
  - Tradeoff: While loading, the clicked card's row grows by the indicator's height (~2.5rem), so its siblings stretch too.
  - Confidence: MED — layout reasoning, not yet rendered; the E2E screenshots will confirm.
  - Blind spot: The kitchen-sink loading state is not on a topic card, so only `home-loading-*` show the result.
- **Fix B**: JS — in `base.html` place the indicator after the whole grid for topic cards (e.g. `(form.closest(".topic-grid") || form).after(typing)`), plus `align-content: center` on `.topic-card`.
  - Strength: The grid never changes height; no card stretches.
  - Tradeoff: The indicator appears below the whole category, which on a phone can be several cards below the tap (6 cards in "Shops & errands"), possibly off-screen; touches shared JS used by every waiting form.
  - Confidence: MED — simple change, but the UX is worse on phones.
  - Blind spot: Other `data-waits-for-agent` forms (conversation page) must keep the current behaviour.
- **Decision**: FIXED via Fix A (`.topic-grid li` flex column, `form { flex: 1 }`, `align-content: center` on `.topic-card`). `home-default` and `ui-kitchen-sink` screenshots unchanged; 8 baselines refreshed (`home-loading` ×4 for F7, `ui-hover` ×4 for F3); Playwright 29/29 and `tests/test_ui.py` green.

## Triage summary (2026-10-24)

- **Fixed**: F1, F2, F3, F4, F6, F7 (Fix A)
- **Accepted**: F5
- **Skipped**: none

Final check after all fixes: `uv run pytest` 564 passed, `uv run ruff check .` and `uv run ruff format --check .` clean, `npx playwright test tests/e2e/ui-home.spec.ts` 29 passed (8 baselines refreshed: `home-loading` ×4 for F7, `ui-hover` ×4 for F3). Fixes are not committed yet.
