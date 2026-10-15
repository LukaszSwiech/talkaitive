---
change_id: testing-waiting-path-recovery
title: Test-plan Phase 2 — provider hang or error ends in a message and a working "Try again"
status: implemented
created: 2026-10-15
updated: 2026-10-15
archived_at: null
---

## Notes

Open a change folder for rollout Phase 2 of context/foundation/test-plan.md: "Waiting-path recovery".
Risks covered: #1 (użytkownik czeka bez końca na odpowiedź agenta albo listę błędów; „Try again” nie przywraca działania, gdy API dostawcy odpowiada wolno lub z błędem). Test types planned: integration.
Risk response intent: #1 — gdy dostawca wisi, zwraca błąd albo pusty wynik, użytkownik w skończonym czasie widzi komunikat i „Try again”, a ponowienie naprawdę uruchamia nowe wywołanie; znacznik „w toku” wygasa i nie blokuje strony na zawsze. Must challenge: „atrapa, która od razu rzuca wyjątek, odpowiada prawdziwemu zawieszeniu”, „status 200 po ponowieniu = sukces”, „incydent z wywiadu Q2 jest już pokryty testami”. Anti-pattern to avoid: tylko happy path; asercja na samym kodzie HTTP; atrapa podmieniająca wewnętrzną logikę zamiast granicy SDK.
After creating the folder, follow the downstream continuation rule.
