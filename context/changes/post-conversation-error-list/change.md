---
change_id: post-conversation-error-list
title: Post conversation error list
status: impl_reviewed
created: 2026-10-06
updated: 2026-10-07
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- 2026-10-07, faza 4 (4.7): odstępstwo od planu. Analiza 20-turowej rozmowy (41 wiadomości) z effort `high` przekraczała 90 s. Pomiar bez limitu: `high` 164,8 s / $0,21 / 19 pozycji (w tym literówki, wbrew regule), `medium` 52,2 s / $0,067 / 12 pozycji (bez literówek, fragmenty bywają dłuższe niż „najkrótszy”). Decyzja użytkownika: domyślny `LLM_ANALYSIS_REASONING_EFFORT = medium`, `LLM_ANALYSIS_TIMEOUT_SECONDS = 150` (znacznik wygasa po 180 s). Wynik 4.7 po zmianie: ta sama rozmowa w aplikacji ok. 60–80 s (pomiar ręczny), 18 pozycji, $0,08.
- Znana luka (poza zakresem): próba ucięta timeoutem nie zwraca `usage`, więc zapisujemy koszt 0, a OpenAI może ją policzyć — dzienny budżet nie widzi kosztu nieudanych analiz.
