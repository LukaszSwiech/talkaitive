---
change_id: ui-home-topic-grid
title: Home topic card grid with categories, jump links, Surprise me and icons
status: implemented
created: 2026-10-22
updated: 2026-10-24
archived_at: null
---

## Notes

Turn the home topic list into a card grid grouped into 4 categories with jump links (variants A+B), plus a "Surprise me" button that starts a random topic (variant C). Every topic card has an icon (required): a vendored subset of Tabler outline SVGs (MIT, no npm dependency), drawn with currentColor so tokens and dark mode apply, aria-hidden. Topic gains short name, subtitle, category and icon fields; title stays. Must leave a how-to for adding an icon when TOPICS changes (in the CLAUDE.md UI section) and a pytest guard that every topic points to an existing icon file.
