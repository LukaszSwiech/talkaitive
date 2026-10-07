# Zadania w GitHub Issues (mirror roadmapy)

> `tasks-github.md` jest lustrzanym odbiciem (mirror) `context/foundation/roadmap.md` dla integracji z GitHub Issues — analogicznie do `context/foundation/tasks-linear.md` dla Linear. Jedynym źródłem prawdy (single source of truth) dla treści i statusu zadań pozostaje `roadmap.md`, sekcje `## Foundations` / `## Slices` / `## Open Roadmap Questions`. Ten plik dokumentuje wyłącznie mechanikę integracji z GitHub: co zostało utworzone, jak jest zmapowane, i jak dodawać kolejne zadania w przyszłości.
>
> **Ważne:** GitHub Issues i Linear **nie są ze sobą zsynchronizowane** i nie ma między nimi żadnego bezpośredniego połączenia (linku/integracji) — to świadoma decyzja. To dwa niezależne, ręcznie utrzymywane lustra tego samego `roadmap.md`. Aktualizacja jednego (np. zamknięcie GitHub Issue) nigdy nie propaguje się automatycznie do drugiego — każde trzeba zaktualizować osobno, wprost z `roadmap.md`.

## Docelowe repo

- Repo: `LukaszSwiech/talkaitive` (GitHub)

## Etykiety GitHub

Etykiety utworzone dla pozycji z roadmapy (reguła też opisana w `context/foundation/lessons.md`, sekcja „Nadawaj etykiety GitHub…”):

| Etykieta | Kolor | Opis |
| --- | --- | --- |
| `type:foundation` | `#1D76DB` | Bounded enabler task z roadmapy |
| `type:slice` | `#0E8A16` | Pionowy, widoczny dla usera slice z roadmapy |
| `status:ready` | `#0E8A16` | Gotowe do rozpoczęcia (`/10x-plan`) |
| `status:proposed` | `#FBCA04` | Zaproponowane, czeka na inne zadania lub doprecyzowanie |
| `status:planning` | `#5319E7` | Zaplanowane (/10x-plan), implementacja jeszcze nie ruszyła |
| `status:in-progress` | `#0052CC` | W trakcie realizacji |
| `north-star` | `#FBCA04` | Pierwszy kompletny fragment produktu (north star) |
| `roadmap-question` | `#C5DEF5` | Otwarte pytanie z roadmapy do rozstrzygnięcia |
| `stream:conversation-loop` | `#5319E7` | Stream A: pętla rozmowy i pamięć (F-01 → S-01 → S-02 → S-03) |
| `stream:account` | `#006B75` | Stream B: zarządzanie kontem (S-04) |

W przeciwieństwie do Linear, GitHub **zachowuje prefiksy** `type:`/`status:`/`stream:` w nazwach etykiet (w Linear te same koncepcje są bez prefiksu `type:`/`status:`, patrz `tasks-linear.md`).

## Zależności (Prerequisites)

GitHub Issues (utworzone przez `gh issue create`) **nie mają** tu ustawionych natywnych relacji „blocked by” (w przeciwieństwie do Linear, gdzie są to prawdziwe relacje — patrz `tasks-linear.md`). Zależność jest wyrażona wyłącznie tekstowo: w polu `## Prerequisites` treści issue oraz przez odwołania do numerów innych issues (np. „F-01 (#1)”).

## Aktualne mapowanie (stan na 2026-10-07)

| Roadmap ID | Change ID | GitHub Issue | Etykiety | Stan |
| --- | --- | --- | --- | --- |
| F-01 | auth-and-access-scaffold | [#1](https://github.com/LukaszSwiech/talkaitive/issues/1) | `type:foundation`, `stream:conversation-loop` | closed |
| S-01 | first-corrected-conversation | [#2](https://github.com/LukaszSwiech/talkaitive/issues/2) | `type:slice`, `north-star`, `stream:conversation-loop` | closed |
| S-02 | post-conversation-error-list | [#3](https://github.com/LukaszSwiech/talkaitive/issues/3) | `type:slice`, `stream:conversation-loop` | closed |
| S-03 | cross-session-error-memory | [#4](https://github.com/LukaszSwiech/talkaitive/issues/4) | `type:slice`, `status:in-progress`, `stream:conversation-loop` | open |
| S-04 | account-and-data-deletion | [#5](https://github.com/LukaszSwiech/talkaitive/issues/5) | `type:slice`, `status:proposed`, `stream:account` | open |
| Q-01 | — | [#6](https://github.com/LukaszSwiech/talkaitive/issues/6) | `roadmap-question` | open |
| Q-02 | — | [#7](https://github.com/LukaszSwiech/talkaitive/issues/7) | `roadmap-question` | open |
| Q-03 | — | [#8](https://github.com/LukaszSwiech/talkaitive/issues/8) | `roadmap-question` | open |
| Q-04 | — | [#9](https://github.com/LukaszSwiech/talkaitive/issues/9) | `roadmap-question` | open |
| Q-05 | — | [#10](https://github.com/LukaszSwiech/talkaitive/issues/10) | `roadmap-question` | open |
| Q-06 | — | [#11](https://github.com/LukaszSwiech/talkaitive/issues/11) | `roadmap-question` | open |
| Q-07 | — | [#14](https://github.com/LukaszSwiech/talkaitive/issues/14) | `roadmap-question` | open |
| Parked: Profil ucznia (OM) | — | [#16](https://github.com/LukaszSwiech/talkaitive/issues/16) | — (bez etykiet, pozycja po MVP) | open |

Ta sama kolumna „GitHub Issue” jest też utrzymywana w `context/foundation/roadmap.md`, w tabelach `## Backlog Handoff` i `## Open Roadmap Questions` — link nawigacyjny w drugą stronę.

## Jak dodać nowe zadanie w GitHub w przyszłości

Gdy w `roadmap.md` pojawi się nowy `F-NN`/`S-NN` (w `## Foundations`/`## Slices`) albo nowe pytanie `Q-NN` (w `## Open Roadmap Questions`):

1. **Upewnij się, że potrzebne etykiety istnieją** — `gh label list --repo LukaszSwiech/talkaitive`. Jeśli brakuje etykiety dla nowego streamu (`stream:<nazwa>`), utwórz ją: `gh label create "stream:<nazwa>" --repo LukaszSwiech/talkaitive --color <hex> --description "<opis ze Streams w roadmapie>"`.
2. **Utwórz issue**: `gh issue create --repo LukaszSwiech/talkaitive --title "<ID>: <tytuł>" --body "<treść skopiowana z sekcji roadmapy>" --label "<etykiety wg tabeli wyżej>"`. Treść (`body`) to Outcome/PRD refs/Prerequisites/Risk (albo Question/Owner/Blocks dla pytań) + stopka „Źródło: `context/foundation/roadmap.md`, roadmap ID `...`, change ID `...`”.
3. **Zaktualizuj mapowanie**: dopisz wiersz w tabeli wyżej w tym pliku ORAZ w odpowiedniej tabeli (`## Backlog Handoff` albo `## Open Roadmap Questions`) w `roadmap.md`.
4. **Zweryfikuj**: `gh issue view <n> --repo LukaszSwiech/talkaitive` lub `gh issue list --repo LukaszSwiech/talkaitive --state all`.

## Synchronizacja statusu (bez integracji, wykonywana przez agenta, niezależna od Linear)

Jak opisano w `roadmap.md`: żadna integracja nie synchronizuje GitHub Issues ani z `roadmap.md`, ani z Linear (świadoma decyzja). Dlatego agent, który zmienia `Status:` pozycji w `roadmap.md` (na prośbę użytkownika albo w ramach skilla, np. `/10x-plan`, `/10x-implement`, `/10x-archive`), w tej samej turze i bez osobnej prośby aktualizuje GitHub Issue według listy niżej — **niezależnie** od Linear (ten aktualizuje osobno, patrz `tasks-linear.md`) — a potem poprawia wiersz w tabeli „Aktualne mapowanie” wyżej i jej datę „stan na”:

- `proposed` → etykieta `status:proposed`, issue pozostaje `open`
- `ready` → etykieta `status:ready`, issue pozostaje `open` (`gh issue edit <n> --remove-label status:proposed --add-label status:ready`)
- `planning` → etykieta `status:planning`, issue pozostaje `open` (`gh issue edit <n> --remove-label status:ready --add-label status:planning`)
- `in-progress` → etykieta `status:in-progress`, issue pozostaje `open` (`gh issue edit <n> --remove-label <poprzednia status:*> --add-label status:in-progress`)
- `done` → zdejmij etykietę `status:*` i zamknij issue jako ukończone: `gh issue edit <n> --remove-label <poprzednia status:*>`, potem `gh issue close <n> --reason completed --comment "<krótkie podsumowanie + ścieżka w context/archive/>"`
- `blocked` → brak dedykowanej etykiety `status:blocked` obecnie utworzonej; jeśli potrzebna, utwórz ją analogicznie do kroku 1 wyżej

Gdy pytanie z `## Open Roadmap Questions` zostaje rozstrzygnięte, agent w tej samej turze: `gh issue close <n>`, usuwa/oznacza jako rozwiązany odpowiedni wiersz w `roadmap.md` i poprawia wiersz w tabeli „Aktualne mapowanie” wyżej.
