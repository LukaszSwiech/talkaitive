# Rollout Phase 3 — granice prywatności i usuwania konta — Plan Brief

> Full plan: `context/changes/testing-privacy-and-deletion-boundaries/plan.md`
> Research: `context/changes/testing-privacy-and-deletion-boundaries/research.md`

## What & Why

Faza 3 planu testów (ryzyka #3 i #6): udowodnić, że żaden widok ani blok pamięci nie ujawnia cudzych danych, a usunięcie konta usuwa wszystko. Dzisiejsze testy są poprawne, ale stoją na ręcznych listach — nowa trasa z id albo nowy model danych przejdzie bez sygnału. Plan testów wymaga, by „nowy model danych bez świadomej decyzji wywracał test”.

## Starting Point

5 tras z id, wszystkie przez jeden helper `_get_conversation` z `for_user`, mają test 404 z ręczną listą parametrów. Test izolacji pamięci nie odróżnia „dane B odfiltrowane” od „pamięć pusta”. Strażnik relacji widzi tylko klucze obce. Usunięcie użytkownika przez `/admin/` omija `delete_account` i zostawia sesje oraz `LogEntry` z e-mailem.

## Desired End State

Nowa trasa z id albo nowy model aplikacji (także bez klucza obcego) bez wpisu decyzji wywraca test. Każdy model kasowany z kontem dostaje automatycznie sprawdzenie „żaden wiersz Anny nie został, dane Łukasza całe”. Blok pamięci Anny jest niepusty i identyczny z danymi Łukasza i bez nich. Usunięcie przez admina sprząta jak usunięcie przez stronę. Każdy nowy test pada po swoim ręcznym mutancie.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Strażnik tras z id | Router URL vs ręczny słownik `ID_ROUTES`, który zasila też test 404 | Porównanie z rejestrem Django, nie listy z samą sobą; nowa trasa od razu dostaje test 404 | Research |
| Test pamięci | Metamorficzny: Anna z własnymi danymi, wynik z danymi Łukasza i bez nich równy i niepusty | Odróżnia odfiltrowanie od pustej pamięci; wzorzec §6.1 | Research |
| Mutant `memory.py:120` | Zaakceptowany jako `równoważny` | Lista id zawiera tylko rozmowy użytkownika, a `Mistake.user` = użytkownik rozmowy | Research |
| Ścieżka `/admin/` | W zakresie: czerwony test, potem sygnał `pre_delete` na `User` | Każda droga usunięcia (strona, admin, shell) sprząta tak samo — FR-013 | Plan |
| Referencje bez FK | Rejestr decyzji dla każdego modelu spoza `django.*` | Każdy nowy model wywraca test bez względu na typ pól | Plan |
| Test „brak wierszy” | Słownik model → fabryka, porównany z domknięciem kaskady | Nowy model kasowany z kontem nie może ominąć sprawdzenia wierszy | Plan |
| Mutacja `accounts/services.py` | Tylko ręczne mutanty, bez mutmut | Celuje w ryzyko #6 bez szumu tekstów komunikatów | Plan |
| Gałęzie | Jedna gałąź `testing-privacy-and-deletion-boundaries`, jeden PR | Gałąź istnieje; zmiana produkcyjna mała i z czerwonym testem przed poprawką | Plan |

## Scope

**In scope:**
- Strażnik tras z id + test 404 sterowany słownikiem
- Metamorficzny test izolacji pamięci
- Rejestr decyzji modeli, słownik fabryk, behawioralny test usunięcia
- Test i poprawka usuwania przez `/admin/` (sygnał `pre_delete`)
- Ręczne mutanty `M16`–`M24`, rejestr przeżyć, `test-plan.md` §3/§6.2/§6.6, nowy wpis w `lessons.md`

**Out of scope:**
- Drugi test 404 per widok; IDOR dla widoków bez id
- Heurystyka nazw pól (nowe pole tekstowe w istniejącym modelu nie wywróci testu)
- `accounts/services.py` w mutmut; dane poza bazą; E2E; zmiana uprawnień admina

## Architecture / Approach

Każdy strażnik porównuje ręcznie wpisaną decyzję (`ID_ROUTES`, `MODEL_DECISIONS`, `FACTORIES`) z rejestrem Django (`get_resolver()`, `apps.get_models()`, domknięcie kaskady od `User`). Sprzątanie danych spoza kaskady (sesje, `LogEntry` o użytkowniku) przenosi się z `delete_account` do jednej funkcji w `accounts/services.py`, podłączonej jako odbiornik `pre_delete` dla `User`. Admin w Django 6.1.1 zapisuje `LogEntry` o usunięciu przed usunięciem, więc odbiornik usuwa też ten wpis.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Izolacja tras i pamięci (#3) | Strażnik tras, metamorficzny test pamięci, `M16`–`M18` | Dane Łukasza niepasujące do filtrów pamięci — `M16` przeżyje ze złego powodu |
| 2. Rejestr modeli i „brak wierszy” (#6) | `MODEL_DECISIONS`, `FACTORIES`, test behawioralny, `M22`–`M23` | Strażnik porównujący słowniki ze sobą zamiast z rejestrem Django |
| 3. Usuwanie przez `/admin/` (#6) | Czerwony test admina, odbiornik `pre_delete`, `M19`–`M21`, `M24` | Zmiana zachowania produkcyjnego usuwania |
| 4. Domknięcie | Pełna mutacja, rejestr, `test-plan.md`, `lessons.md` | Nowe przeżycia mutmut w `memory.py` po zmianie testów |

**Prerequisites:** gałąź `testing-privacy-and-deletion-boundaries` (jest); zielony `uv run pytest` na starcie.
**Estimated effort:** ~2–3 sesje na 4 fazy.

## Open Risks & Assumptions

- Przewidywania „mutant X zostanie zabity” pochodzą z kodu, nie z pomiaru — każda faza potwierdza je `manual_mutants.py`.
- Usunięcie przez admina usuwa też wpis „Recent actions” o tym usunięciu (zgodne z FR-013, ale właściciel traci ślad audytu).
- Rejestr modeli nie wykryje nowego pola tekstowego z id/e-mailem w istniejącym modelu (świadomie przyjęte).

## Success Criteria (Summary)

- Dodanie trasy z id albo modelu danych bez decyzji daje czerwony test z komunikatem, co zrobić.
- Usunięcie konta — przez stronę albo przez admina — nie zostawia żadnego wiersza, sesji ani wpisu logu o użytkowniku.
- `manual_mutants.py` kończy się kodem 0, mutmut bez niewyjaśnionych przeżyć.
