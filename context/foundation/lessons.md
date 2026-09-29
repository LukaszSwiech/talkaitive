# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Ręcznie aktualizuj status w GitHub i Linear po zmianie w roadmapie

- **Context**: Zarządzanie `context/foundation/roadmap.md` oraz odpowiadającymi mu ticketami w GitHub Issues i Linear (mapowanie w tabeli `## Backlog Handoff`).
- **Problem**: Status pozycji w roadmapie zmienia się (np. na `done`), ale GitHub Issue i Linear issue zostają w starym stanie, bo żadna integracja nie synchronizuje tego automatycznie — łatwo o tym zapomnieć i mieć rozjazd między źródłami.
- **Rule**: Gdy `Status:` pozycji w roadmap.md się zmienia, zaktualizuj też odpowiedni GitHub Issue i Linear issue z tabeli Backlog Handoff — nie zakładaj, że integracja Linear↔GitHub zrobi to sama (synchronizuje tylko nową aktywność od momentu połączenia, nie retroaktywnie i nie w drugą stronę dla ręcznie utworzonych issues).
- **Applies to**: all
