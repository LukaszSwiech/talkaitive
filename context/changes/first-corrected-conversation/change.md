---
change_id: first-corrected-conversation
title: First corrected conversation
status: impl_reviewed
created: 2026-10-05
updated: 2026-10-06
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- 2026-10-06 — rozszerzenie zakresu fazy 3 (decyzja użytkownika): Enter wysyła wiadomość, Shift+Enter wstawia nową linię, na wszystkich urządzeniach. Na telefonie nie da się więc wpisać nowej linii — świadomie zaakceptowane (krótkie wiadomości w czacie). Opis w `plan.md` (Faza 3, pkt 3), ręczny test: Progress 3.8.
- 2026-10-06 — zmiana decyzji w fazie 4 (decyzja użytkownika): globalny endpoint `https://api.openai.com/v1` zamiast `eu.api.openai.com`. Rezydencja danych w UE wymaga organizacji OpenAI zatwierdzonej przez sprzedaż (abuse-monitoring controls); konto użytkownika jej nie ma, więc oba klucze dostawały 401 na endpoincie UE. Lokalne testy 4.5–4.7 przeszły na endpoincie globalnym. PRD nie wymaga rezydencji w UE (`research.md`, pytanie otwarte 2). `settings.py`: domyślny `OPENAI_BASE_URL` globalny, ceny `gpt-5.4` bez narzutu +10% (2.50 / 0.25 / 15.00). Plan (pkt 2 fazy 1, fazy 4) nadal opisuje wariant UE — ta notatka go zastępuje.
