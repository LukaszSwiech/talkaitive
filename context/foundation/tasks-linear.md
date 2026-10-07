# Zadania w Linear (mirror roadmapy)

> `tasks-linear.md` jest lustrzanym odbiciem (mirror) `context/foundation/roadmap.md` dla integracji z Linear — analogicznie do `context/foundation/tasks-github.md` dla GitHub Issues. Jedynym źródłem prawdy (single source of truth) dla treści i statusu zadań pozostaje `roadmap.md`, sekcje `## Foundations` / `## Slices` / `## Open Roadmap Questions`. Ten plik dokumentuje wyłącznie mechanikę integracji z Linear: co zostało utworzone, jak jest zmapowane, i jak dodawać kolejne zadania w przyszłości.
>
> **Ważne:** Linear i GitHub Issues **nie są ze sobą zsynchronizowane** i nie ma między nimi żadnego bezpośredniego połączenia (linku/integracji) — to świadoma decyzja. To dwa niezależne, ręcznie utrzymywane lustra tego samego `roadmap.md`. Aktualizacja jednego (np. zmiana statusu w Linear) nigdy nie propaguje się automatycznie do drugiego — każde trzeba zaktualizować osobno, wprost z `roadmap.md`.

## Docelowa przestrzeń w Linear

- Workspace: `lukaszswiech`
- Team: `LukaszSwiech` (id `d8db3aa0-bc0e-441f-86c1-d25569796b35`)
- Project: `TalkAItive` (`P-LUK-1`, https://linear.app/lukaszswiech/project/talkaitive-f5b2e2af4edd)

## Mapowanie etykiet GitHub → Linear

GitHub issues z roadmapy dostają etykiety `type:*`/`status:*`/`stream:*`/`north-star`/`roadmap-question` (reguła opisana w `context/foundation/lessons.md`, sekcja „Nadawaj etykiety GitHub…”). W Linear ten sam sens jest wyrażony inaczej:

| GitHub label | Linear odpowiednik | Uwaga |
| --- | --- | --- |
| `type:slice` | etykieta `slice` | bez prefiksu `type:` |
| `type:foundation` | etykieta `foundation` | bez prefiksu `type:` |
| `north-star` | etykieta `north-star` | 1:1 |
| `roadmap-question` | etykieta `roadmap-question` | 1:1, tylko dla pytań z `## Open Roadmap Questions` |
| `stream:account` | etykieta `stream:account` (`#006B75`) | 1:1 |
| `stream:conversation-loop` | etykieta `stream:conversation-loop` (`#5319E7`) | 1:1 |
| `status:proposed` | **status issue** = `Backlog` | świadoma decyzja: Linear ma natywne pole statusu, więc `status:*` NIE jest kopiowane jako etykieta — uniknięcie duplikowania tej samej informacji w dwóch miejscach |
| `status:ready` | **status issue** = `Todo` | jw. |
| `status:planning` | **status issue** = `Todo` | Linear nie ma stanu „Planning”; `ready` i `planning` różni tylko etykieta w GitHub |
| `status:in-progress` | **status issue** = `In Progress` | jw. |
| (brak `status:*`, pytania) | **status issue** = `Backlog` | pytania z `## Open Roadmap Questions` zawsze startują jako `Backlog` |

## Zależności (Prerequisites → blockedBy)

Pole `Prerequisites:` z roadmapy jest odwzorowane jako natywna relacja Linear `blockedBy` (ikona blokady na issue, klikalna do zadania blokującego), a nie tylko jako tekst w opisie:

| Linear issue | blocked by |
| --- | --- |
| S-01 (LUK-17) | F-01 (LUK-16) |
| S-02 (LUK-18) | S-01 (LUK-17) |
| S-03 (LUK-19) | S-01 (LUK-17), S-02 (LUK-18) |
| S-04 (LUK-20) | F-01 (LUK-16) |

Pytania Q-01..Q-06 nie mają zależności (pole `Blocks` w roadmapie jest informacyjne, nie blokujące).

## Aktualne mapowanie (stan na 2026-10-06)

| Roadmap ID | Change ID | Linear Issue | Etykiety | Status |
| --- | --- | --- | --- | --- |
| F-01 | auth-and-access-scaffold | [LUK-16](https://linear.app/lukaszswiech/issue/LUK-16/f-01-auth-i-izolacja-danych-miedzy-uzytkownikami) | `foundation`, `stream:conversation-loop` | Done |
| S-01 | first-corrected-conversation | [LUK-17](https://linear.app/lukaszswiech/issue/LUK-17/s-01-pierwsza-rozmowa-po-niemiecku-z-korekta-na-biezaco-gwiazda) | `slice`, `north-star`, `stream:conversation-loop` | Done |
| S-02 | post-conversation-error-list | [LUK-18](https://linear.app/lukaszswiech/issue/LUK-18/s-02-lista-bledow-po-zakonczonej-rozmowie) | `slice`, `stream:conversation-loop` | In Progress |
| S-03 | cross-session-error-memory | [LUK-19](https://linear.app/lukaszswiech/issue/LUK-19/s-03-pamiec-miedzy-rozmowami-i-domykanie-petli-bledow) | `slice`, `stream:conversation-loop` | Backlog |
| S-04 | account-and-data-deletion | [LUK-20](https://linear.app/lukaszswiech/issue/LUK-20/s-04-usuniecie-konta-wraz-z-danymi) | `slice`, `stream:account` | Backlog |
| Q-01 | — | [LUK-21](https://linear.app/lukaszswiech/issue/LUK-21/q-01-jak-praktika-rozwiazuje-pamiec-miedzy-sesjami-kontrole-poziomu) | `roadmap-question` | Backlog |
| Q-02 | — | [LUK-22](https://linear.app/lukaszswiech/issue/LUK-22/q-02-czy-mvp-zdazy-przed-terminem-miekkim-2026-11-04) | `roadmap-question` | Backlog |
| Q-03 | — | [LUK-23](https://linear.app/lukaszswiech/issue/LUK-23/q-03-ile-razy-w-tygodniu-oznacza-regularne-uzywanie-w-primary-success) | `roadmap-question` | Backlog |
| Q-04 | — | [LUK-24](https://linear.app/lukaszswiech/issue/LUK-24/q-04-jak-ma-wygladac-zakladanie-kont-po-mvp) | `roadmap-question` | Backlog |
| Q-05 | — | [LUK-25](https://linear.app/lukaszswiech/issue/LUK-25/q-05-jakie-sa-niefunkcjonalne-non-goals-mvp) | `roadmap-question` | Backlog |
| Q-06 | — | [LUK-26](https://linear.app/lukaszswiech/issue/LUK-26/q-06-jaki-jest-ballpark-target-scaleqps-i-target-scaledata-volume) | `roadmap-question` | Backlog |

Ta sama kolumna „Linear Issue” jest też utrzymywana w `context/foundation/roadmap.md`, w tabelach `## Backlog Handoff` i `## Open Roadmap Questions` — to jest link nawigacyjny w drugą stronę, żeby nie trzeba było otwierać obu plików naraz.

## Jak dodać nowe zadanie w Linear w przyszłości

Gdy w `roadmap.md` pojawi się nowy `F-NN`/`S-NN` (w `## Foundations`/`## Slices`) albo nowe pytanie `Q-NN` (w `## Open Roadmap Questions`):

1. **Upewnij się, że potrzebne etykiety istnieją** — `mcp__linear__list_issue_labels` (`team="LukaszSwiech"`). Jeśli brakuje etykiety dla nowego streamu (`stream:<nazwa>`), utwórz ją `mcp__linear__save_issue_label` z `teamId` zespołu, kolorem i opisem skopiowanym z sekcji `## Streams` w roadmapie.
2. **Utwórz issue**: `mcp__linear__save_issue` z:
   - `team="LukaszSwiech"`, `project="TalkAItive"`
   - `title` = tytuł pozycji z roadmapy (np. „S-05: …”)
   - `description` = treść z sekcji `## Foundations`/`## Slices`/`## Open Roadmap Questions` (Outcome/PRD refs/Prerequisites/Risk albo Question/Owner/Blocks) + stopka „Źródło: `context/foundation/roadmap.md`, roadmap ID `...`, change ID `...`”
   - `labels` wg tabeli mapowania etykiet wyżej
   - `state`: `Backlog` dla `status:proposed`/pytań, `Todo` dla `status:ready`
3. **Ustaw zależności**: jeśli pozycja ma `Prerequisites:`, dodaj `blockedBy: ["<identyfikator Linear zależności>"]` (append-only, nie usuwa istniejących relacji).
4. **Zaktualizuj mapowanie**: dopisz wiersz w tabeli wyżej w tym pliku ORAZ w odpowiedniej tabeli (`## Backlog Handoff` albo `## Open Roadmap Questions`) w `roadmap.md`.
5. **Zweryfikuj**: `mcp__linear__list_issues` z `project="TalkAItive"` i/lub `mcp__linear__get_issue` (`includeRelations: true`) dla nowego issue.

## Synchronizacja statusu (bez integracji, wykonywana przez agenta, niezależna od GitHub)

Jak opisano w `roadmap.md`: żadna integracja nie synchronizuje Linear ani z `roadmap.md`, ani z GitHub (świadoma decyzja). Dlatego agent, który zmienia `Status:` pozycji w `roadmap.md` (na prośbę użytkownika albo w ramach skilla, np. `/10x-plan`, `/10x-implement`, `/10x-archive`), w tej samej turze i bez osobnej prośby przestawia Linear issue według listy niżej (`mcp__linear__save_issue`, pole `state`) — **niezależnie** od GitHub (ten aktualizuje osobno, patrz `tasks-github.md`) — a potem poprawia wiersz w tabeli „Aktualne mapowanie” wyżej i jej datę „stan na”. Rozstrzygnięte pytanie Q-NN → `Done`.

- `proposed` → `Backlog`
- `ready` → `Todo`
- `planning` → `Todo` (Linear nie ma stanu „Planning”)
- `in-progress` → `In Progress`
- `done` → `Done`
- `blocked` → zostaw bazowy status (`Backlog`/`Todo`), Linear nie ma odrębnego stanu „Blocked” — blokadę wyraża relacja `blockedBy`, nie status
