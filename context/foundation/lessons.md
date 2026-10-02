# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Ręcznie aktualizuj status w GitHub i Linear po zmianie w roadmapie

- **Context**: Zarządzanie `context/foundation/roadmap.md` oraz odpowiadającymi mu ticketami w GitHub Issues i Linear (mapowanie w tabeli `## Backlog Handoff`).
- **Problem**: Status pozycji w roadmapie zmienia się (np. na `done`), ale GitHub Issue i Linear issue zostają w starym stanie, bo żadna integracja nie synchronizuje tego automatycznie — łatwo o tym zapomnieć i mieć rozjazd między źródłami.
- **Rule**: Gdy `Status:` pozycji w roadmap.md się zmienia, zaktualizuj też odpowiedni GitHub Issue i Linear issue z tabeli Backlog Handoff — osobno, dla każdego z nich. GitHub i Linear nie są ze sobą zsynchronizowane (świadoma decyzja — brak cross-linków/integracji między nimi); oba są niezależnymi lustrami tego samego roadmap.md, więc aktualizacja jednego nigdy nie propaguje się do drugiego automatycznie.
- **Applies to**: all

## Nadawaj etykiety GitHub type:*/status:*/stream:* każdemu nowemu F-NN/S-NN issue

- **Context**: GitHub Issues odpowiadające pozycjom `## Foundations`/`## Slices` w roadmap.md (mapowanie w `## Backlog Handoff`).
- **Problem**: Bez etykiet w GitHub nie widać na liście issues, co jest gotowe do wzięcia (`Status: ready`), co czeka (`proposed`), co zablokowane (`blocked`), ani do którego strumienia (`## Streams`) dana pozycja należy — trzeba by za każdym razem zaglądać do roadmap.md.
- **Rule**: Każdy issue dla F-NN/S-NN dostaje trzy etykiety: `type:foundation` lub `type:slice` (typ pozycji), `status:ready` / `status:proposed` / `status:blocked` (kopia pola `Status:` z roadmapu), oraz `stream:<nazwa>` (kopia przynależności z tabeli `## Streams`; dla tego projektu: `stream:conversation-loop` = Stream A, `stream:account` = Stream B). Gdy `Status:` w roadmapie się zmienia, zaktualizuj też etykietę `status:*` na issue (`gh issue edit <n> --remove-label ... --add-label ...`), analogicznie do reguły wyżej. Pytania z `## Open Roadmap Questions` dostają osobną etykietę `roadmap-question` (bez `type:`/`status:`/`stream:`, bo nie są pozycjami roadmapy).
- **Applies to**: all

## Pozycja oznaczona jako "north star" dostaje dodatkową, czwartą etykietę north-star

- **Context**: Etykietowanie GitHub Issues / Linear issues dla F-NN/S-NN (patrz reguła "Nadawaj etykiety GitHub..." wyżej).
- **Problem**: Reguła wyżej mówi o dokładnie trzech etykietach (`type:*`/`status:*`/`stream:*`). W praktyce pozycja wskazana w roadmap.md jako aktualna `## North star` dostaje w GitHub i Linear dodatkową, czwartą etykietę `north-star` — bez tego dopisku łatwo ją pominąć przy nowym issue albo nie wiedzieć, co z nią zrobić, gdy north star zmieni się w kolejnym milestone.
- **Rule**: Pozycja wskazana w roadmap.md jako aktualna `## North star` dostaje dodatkową, czwartą etykietę `north-star` — zarówno w GitHub, jak i w Linear (tam też jako etykieta, nie jako status). Gdy w kolejnym milestone north star się zmienia, przenieś etykietę `north-star` ze starej pozycji na nową (usuń ze starej, dodaj do nowej) — nie zostawiaj jej na obu naraz.
- **Applies to**: all

## Synchronizacja statusu obejmuje też tabelę Open Roadmap Questions, nie tylko Backlog Handoff

- **Context**: Reguła "Ręcznie aktualizuj status w GitHub i Linear po zmianie w roadmapie" (na górze tego pliku) opisuje synchronizację dla tabeli `## Backlog Handoff`.
- **Problem**: roadmap.md ma też osobną procedurę synchronizacji dla tabeli `## Open Roadmap Questions` (po uzyskaniu odpowiedzi na pytanie Q-NN) — inny przebieg niż dla F-NN/S-NN (zamknięcie issue + usunięcie/oznaczenie wiersza, a nie zmiana etykiety `status:*`). Reguła na górze tego pliku wspomina wyłącznie Backlog Handoff, więc łatwo o tej drugiej procedurze zapomnieć.
- **Rule**: Ta sama zasada ręcznej, niezależnej synchronizacji GitHub/Linear dotyczy też tabeli `## Open Roadmap Questions` w roadmap.md: gdy pytanie Q-NN zostaje rozstrzygnięte, zamknij odpowiedni GitHub Issue (`gh issue close`), osobno przestaw Linear issue na `Done` (`mcp__linear__save_issue`, pole `state`), i usuń lub oznacz jako rozwiązany odpowiedni wiersz w tabeli w roadmap.md.
- **Applies to**: all

## Status:* w Linear to natywne pole state, nie etykieta — nie kopiuj wzorca etykiet z GitHub

- **Context**: Etykietowanie i synchronizacja statusu dla F-NN/S-NN/Q-NN w GitHub Issues i Linear.
- **Problem**: Reguła "Nadawaj etykiety GitHub type:*/status:*/stream:*..." opisuje etykiety `status:*` wyłącznie dla GitHub. Bez wyraźnego zastrzeżenia można by błędnie założyć, że ten sam wzorzec (etykieta `status:*`) trzeba powtórzyć w Linear.
- **Rule**: W Linear pole `Status:` z roadmapu NIE jest kopiowane jako etykieta — to świadoma decyzja: wyraża je natywne pole `state` issue (`Backlog`/`Todo`/`In Progress`/`Done`), żeby nie duplikować tej samej informacji w dwóch miejscach. Pełna mechanika obu integracji (etykiety, zależności, jak dodać nowe zadanie, mapowanie statusów) jest w `context/foundation/tasks-github.md` (GitHub) i `context/foundation/tasks-linear.md` (Linear) — sprawdź je przed ręczną synchronizacją statusu.
- **Applies to**: all

## Dozwolone wartości Status: pozycji roadmapy i ich odpowiedniki w GitHub/Linear

- **Context**: Wartości pola `Status:` pozycji F-NN/S-NN w roadmap.md i ich odwzorowanie w GitHub/Linear.
- **Problem**: Dozwolone wartości `Status:` nie były nigdzie zebrane w jednym miejscu. `tasks-linear.md` znał wartość `in-progress`, ale `tasks-github.md` nie miał dla niej żadnej etykiety ani reguły synchronizacji — przy realnej zmianie statusu na `in-progress` GitHub Issue zostałby nie zaktualizowany.
- **Rule**: `Status:` pozycji w roadmap.md może przyjąć jedną z wartości: `proposed`, `ready`, `in-progress`, `blocked`, `done`. Przy `in-progress`: w GitHub ustaw etykietę `status:in-progress` (usuwając poprzednią `status:*`), issue zostaje `open`; w Linear ustaw `state` na `In Progress`. Pełne tabele synchronizacji: `context/foundation/tasks-github.md`, `context/foundation/tasks-linear.md`.
- **Applies to**: all

## Status planning: dodany do dozwolonych wartości Status: (uzupełnia regułę wyżej)

- **Context**: `/10x-plan` po zapisaniu `plan.md` przestawia pozycję roadmapy na `planning`, a reguła „Dozwolone wartości Status:…” wyżej nie znała tej wartości ani jej odpowiedników w GitHub/Linear.
- **Problem**: Bez `planning` na liście skill albo łamie listę dozwolonych wartości, albo pomija synchronizację roadmapy po planowaniu; GitHub nie miał też etykiety `status:in-progress`, choć dokumentacja ją opisywała.
- **Rule**: Dozwolone wartości `Status:` to `proposed`, `ready`, `planning`, `in-progress`, `blocked`, `done` (ta lista zastępuje listę z reguły wyżej). Przy `planning`: w GitHub etykieta `status:planning` (usuwając poprzednią `status:*`), issue zostaje `open`; w Linear `state` = `Todo` (Linear nie ma stanu „Planning”). Etykiety `status:planning` i `status:in-progress` istnieją w GitHub od 2026-10-01. Tabele: `context/foundation/tasks-github.md`, `context/foundation/tasks-linear.md`.
- **Applies to**: all
