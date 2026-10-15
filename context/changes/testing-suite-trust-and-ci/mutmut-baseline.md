# mutmut — baseline (Faza 1, spike)

Data: 2026-10-14. Gałąź `test-ci-floor`, kod aplikacji bez zmian względem `3f15aa9`.

## Wersja i konfiguracja

- mutmut **3.8.0** (`uv add --dev mutmut`), Python 3.14.6, pytest 9.1.1, pytest-django 4.14.0, Django 6.1.1, macOS (arm64).
- `pyproject.toml`, sekcja `[tool.mutmut]`:
  - `source_paths = ["accounts", "conversations", "talkaitive"]` — wszystkie trzy pakiety muszą być w `mutants/`, żeby importował się `talkaitive.settings_test`;
  - `also_copy = ["manage.py"]` — patrz „Poprawki” niżej;
  - `only_mutate` = `accounts/ownership.py`, `conversations/budget.py`, `conversations/memory.py`, `conversations/services.py` (zawężenie przez `only_mutate` działa; glob w CLI niepotrzebny).
- `[tool.ruff] extend-exclude` dostał `"mutants"`; lokalnie `mutants/` jest w `.gitignore`.
- Komendy: `uv run mutmut run`, potem `uv run mutmut results` (tylko przeżyte) albo `uv run mutmut results --all true` (wszystkie), `uv run mutmut show <nazwa>` (diff mutanta).

## Poprawki potrzebne, żeby ruszyło

1. **Brak `source_paths`** → `FileNotFoundError: Could not figure out where the code to mutate is` (repo nie ma `src/`). Oczekiwane (research §5).
2. **Testy biegły na oryginalnym kodzie, nie na mutantach.** Pierwszy przebieg kończył się: „Stopping early, because we could not find any test case for any mutant”. Przyczyna: pytest-django (domyślne `django_find_project = true`) dopisuje do `sys.path` katalog najbliższego `manage.py`. mutmut nie kopiuje `manage.py` do `mutants/`, więc pytest-django szedł w górę i dopisywał na początek `sys.path` oryginalne repo (`/Users/Luk/10xDevs4`). Błąd „import file mismatch” jest pod mutmut wyciszony (`PY_IGNORE_IMPORTMISMATCH=1`), więc wszystko przechodziło po cichu na oryginale. Poprawka: `also_copy = ["manage.py"]` — pytest-django znajduje wtedy `mutants/manage.py`.
   - `pythonpath = ["."]` z `[tool.pytest.ini_options]` **nie** był przyczyną: pytest startuje w `mutants/` i czyta `mutants/pyproject.toml`, więc `.` wskazuje na kopię.
3. Niepotrzebne: `--max-children` (0 timeoutów przy domyślnej równoległości = liczba rdzeni), obejścia dla #504 (wielokrotne `pytest.main()` z Django nie sprawiło problemu).

## Wynik pierwszego pełnego przebiegu

- Czas: **23,2 s** zegarowo (149,5 s CPU; 35 mutacji/s, 8 procesów równolegle).
- `mutmut run` zakończył się kodem **0** mimo 65 przeżyć — potwierdza, że mutmut sam nie jest bramką.
- `uv run pytest` po przebiegu: 198 passed. `ruff check .` i `ruff format --check .` czyste przy istniejącym `mutants/`.

| Moduł | Mutanty | Zabite | Przeżyte | Timeout |
|---|---:|---:|---:|---:|
| `accounts/ownership.py` | 2 | 2 | 0 | 0 |
| `conversations/budget.py` | 107 | 103 | 4 | 0 |
| `conversations/memory.py` | 133 | 122 | 11 | 0 |
| `conversations/services.py` | 425 | 375 | 50 | 0 |
| **Razem** | **667** | **602** | **65** | **0** |

**Kontrola sensu:** `conversations.budget.x_is_exhausted__mutmut_14` to `>=` → `>` w `is_exhausted` (odpowiednik C2) — **killed**. mutmut widzi testy, przebieg jest ważny.

## Powiązanie z ręczną listą (research §1)

| Ręczny | Mutant mutmut | Status |
|---|---|---|
| C2 | `budget.x_is_exhausted__mutmut_14` | killed |
| M4 | `budget.x_is_final_turn__mutmut_8` (bez `conversation__in=`) | survived |
| M6 | `services.x__mark_analysis_failed__mutmut_9` (bez `pk=`) | survived |
| M7 | `services.x_analyze_conversation__mutmut_51` (`analysis_started_at = None`) | survived |
| M8 | `services.x_agent_turn_in_progress__mutmut_5` (`<` → `<=`) | survived |
| M11 | `memory.x_select_memory__mutmut_9` (bez `status=ENDED`) | survived |
| M12 | `memory.x_select_memory__mutmut_4` (bez `-ended_at`) | survived |

mutmut **nie generuje**: M1–M3 (widoki poza zakresem), M5 (`ended_at__gte` → `__gt` — nazw argumentów / lookupów Django nie zmienia), M9 i M10 (stałe i literały w ustawieniach / stałe modułowe), M13 (`llm.py` poza zakresem). To potwierdza, że ręczna lista z fazy 3 jest potrzebna obok mutmut.

Przewidywania z research §2: potwierdzone `services.py:256` (`_clear_analysis_marker` bez `pk=`), `:279` (`sum(1 …)` → `sum(2 …)`), `:380` (`<=` → `<`), timeout tury `+30` → `+31`. Nie potwierdzone: `budget.py:107` bez `role=ASSISTANT` — zabity.

## Przeżyte mutanty (65) — wstępne grupy

Grupy są tylko opisem, nie decyzją. Klasyfikacja (test / `równoważny` / `brak wymagania` / `przekazany do test-plan Phase N`) to zadanie fazy 6.

**A. Treść komunikatów błędów (26)** — zmieniony tekst (`"XX…XX"`, małe/wielkie litery albo `None`) w wyjątkach `ConversationError` / `AnalysisNotNeeded` / `ImproperlyConfigured`:
- `services.x_start_conversation__mutmut_5`, `_12`, `_13`, `_14`, `_15`, `_39`, `_40`, `_41`, `_42`
- `services.x_send_message__mutmut_4`, `_13`, `_16`, `_17`, `_18`, `_19`
- `services.x_run_agent_turn__mutmut_4`, `_5`, `_6`, `_7`, `_13`
- `services.x_analyze_conversation__mutmut_5`, `_10`, `_11`, `_18`, `_19`
- `budget.x_turn_cost__mutmut_2`

**B. Timeouty i znaczniki „w toku” (12)** — obszar ryzyka #1:
- `services.x__agent_turn_timeout__mutmut_2`, `_3`, `_5`, `_6`, `_7` (liczba prób ±1, `+30` → `-30`/`+31`, `*` → `/`)
- `services.x__analysis_timeout__mutmut_6` (`*` → `/`)
- `services.x_agent_turn_in_progress__mutmut_5` (M8)
- `services.x__mark_turn_started__mutmut_2` (`update_fields=None`)
- `services.x_start_conversation__mutmut_31`, `_38` (znacznik tury przy starcie `None` / pominięty)
- `services.x_run_agent_turn__mutmut_17` (`_mark_turn_started(locked, None)`)
- `services.x_analyze_conversation__mutmut_51` (M7)

**C. Filtry `pk=` / zakres zapytań (6)** — zapytanie dotyka więcej niż jednej rozmowy:
- `services.x__clear_turn_marker__mutmut_3` (bez `pk=`), `_4` (bez `agent_turn_started_at=`)
- `services.x_end_conversation__mutmut_9` (bez `pk=`)
- `services.x__clear_analysis_marker__mutmut_3` (bez `pk=`)
- `services.x__mark_analysis_failed__mutmut_9` (M6)
- `budget.x_is_final_turn__mutmut_8` (M4)

**D. Zapis pól i liczenie przy analizie (7)**:
- `services.x_analyze_conversation__mutmut_33` (`sum(1 …)` → `sum(2 …)`), `_42`, `_90` (lista `update_fields` usunięta), `_52` (`update_fields=None`)
- `services.x__merge_mistakes__mutmut_3` (`<=` → `<`), `_5`, `_6` (klucz sortowania `(1, 0)` → `(2, 0)` / `(1, 1)`)

**E. Granica długości wiadomości (1)**:
- `services.x_send_message__mutmut_7` (`len(text) > MAX` → `>=`)

**F. Kolejność i wybór w pamięci i budżecie (13)**:
- `memory.x_select_memory__mutmut_4` (M12), `_5` (bez `-id`), `_9` (M11), `_18` (`window = None`)
- `memory.x__key__mutmut_2` (`" ".join` → `"XX XX".join`)
- `memory.x__mistakes__mutmut_39` (`position=None`), `_47` (`explanation` → `None`), `_48`, `_53` (`conversations=0` → `None` / `1`), `_57` (`conversation_ids.add(None)`), `_58` (`<` → `<=` przy wyborze najnowszego wariantu)
- `budget.x_is_final_turn__mutmut_4` (bez `-created_at`), `_5` (bez `-id`)

## Decyzja go/no-go

**Rekomendacja: GO.** mutmut działa z pytest-django po jednej poprawce konfiguracji (`also_copy = ["manage.py"]`), przebieg trwa ~23 s, kontrola sensu przechodzi, a wynik pokrywa się z ręcznym pomiarem z researchu (M4, M6, M7, M8, M11, M12 przeżywają też w mutmut). Plan awaryjny niepotrzebny. Faza 6 zaczyna od tej listy 65 nazw.

## Wynik końcowy (Faza 6)

Data: 2026-10-15. Gałąź `test-mutation-trust`, kod aplikacji bez zmian (`git diff -- accounts conversations talkaitive` pusty).

**Uwaga o pamięci podręcznej mutmut.** `uv run mutmut run` na istniejącym `mutants/` po samych zmianach w testach nie liczy mutantów od nowa: przebieg trwał 3,7 s („0.00 mutations/second”) i pokazał stare 65 przeżyć. mutmut 3 przelicza tylko funkcje, których kod się zmienił. Po dopisaniu testów trzeba usunąć (albo przenieść) katalog `mutants/` i dopiero wtedy uruchomić `mutmut run`.

| Moduł | Mutanty | Przeżyte — Faza 1 | Przeżyte — start Fazy 6 (po fazach 4–5) | Przeżyte — koniec Fazy 6 | Zabite — koniec |
|---|---:|---:|---:|---:|---:|
| `accounts/ownership.py` | 2 | 0 | 0 | 0 | 2 |
| `conversations/budget.py` | 107 | 4 | 3 | 3 | 104 |
| `conversations/memory.py` | 133 | 11 | 10 | 8 | 125 |
| `conversations/services.py` | 425 | 50 | 48 | 40 | 385 |
| **Razem** | **667** | **65** | **61** | **51** | **616** |

- Czas: start Fazy 6 — **23,7 s** zegarowo; pełny przebieg po pierwszych czterech testach (świeży `mutants/`) — **25,4 s** (55 przeżyć); końcowy pełny przebieg po teście komunikatów odmowy (decyzja D2) — **24,5 s** zegarowo (151,9 s CPU, 35 mutacji/s), 0 timeoutów.
- Fazy 4–5 zabiły w mutmut dokładnie cztery mutanty z ręcznej listy: M4 (`budget.x_is_final_turn__mutmut_8`), M6 (`services.x__mark_analysis_failed__mutmut_9`), M7 (`services.x_analyze_conversation__mutmut_51`), M12 (`memory.x_select_memory__mutmut_4`). M8 i M11 przeżywają zgodnie z rejestrem.
- Kontrola sensu: `conversations.budget.x_is_exhausted__mutmut_14` dalej **killed**.

### Nowe testy (Faza 6) i mutanty, które zabijają

| Test | Źródło oczekiwanej wartości | Zabite mutanty |
|---|---|---|
| `tests/test_conversation_views.py::test_opening_turn_and_retry_show_typing_and_start_no_second_call` (parametry `opening`, `retry`) | PRD prd.md:96 (informacja zwrotna przez cały czas czekania); test-plan §2 ryzyko #1 (znacznik „w toku”) | `services.x_start_conversation__mutmut_31`, `_38`, `services.x_run_agent_turn__mutmut_17` |
| `tests/test_conversation_views.py::test_ending_an_old_ended_conversation_leaves_the_current_one_active` | PRD FR-006 (przycisk kończy tę rozmowę), FR-004 | `services.x_end_conversation__mutmut_9` |
| `tests/test_memory.py::test_pair_from_three_conversations_ranks_above_fresher_pair_from_two` | PRD Business Logic „Kryterium wyboru błędów” (najpierw częstość w wielu rozmowach, potem świeżość) | `memory.x__mistakes__mutmut_57` |
| `tests/test_memory.py::test_two_pairs_repeated_in_the_same_two_conversations_both_count_twice` | PRD Business Logic „Kryterium wyboru błędów”, FR-010 | `memory.x__mistakes__mutmut_39` |
| `tests/test_conversation_views.py::test_refused_action_shows_a_reason` (parametry: limit, druga rozmowa, czekanie na agenta, nic do ponowienia) | PRD „Odmowa akcji” (prd.md:97, dopisane 2026-10-15 — decyzja D2): powód odmowy widoczny, nigdy pusty ani „None”; brzmienie nie jest wymaganiem | `services.x_start_conversation__mutmut_12`, `_39`, `services.x_send_message__mutmut_16`, `services.x_run_agent_turn__mutmut_4` |

Każdy potwierdzony świeżym pełnym przebiegiem mutmut (status `killed`). `uv run pytest`: 217 passed.

### Klasyfikacja 51 pozostałych przeżyć

Każda nazwa ma wiersz w `scripts/mutation/accepted_survivors.md` (data 2026-10-15). Klasyfikację zaakceptował użytkownik 2026-10-15 (decyzje D1–D8): nowe testy zostają; do PRD dopisano tylko „Odmowa akcji” (D2); dokładne brzmienie komunikatów (D3), limit długości wiadomości (D4), kolejność błędów spoza `1..N` (D5) i wyjaśnienie w pamięci (D6) zostają jako wpisy; timeouty tury zostają w test-plan Phase 2 (D7); remisy co do mikrosekundy — `równoważny` jak M8 (D8).

| Klasyfikacja | Liczba | Co obejmuje |
|---|---:|---|
| `równoważny` | 23 | M8 i M11 (nazwy mutmut), pełny zapis obiektu pod blokadą (`update_fields=None`), tekst `AnalysisNotNeeded` (nigdy nie pokazywany), klucze sortowania bez wpływu, remisy co do mikrosekundy, `_analysis_timeout` przy 0 ponowień |
| `przekazany do test-plan Phase 2` | 6 | długość timeoutu tury (5) i czyszczenie cudzego znacznika tury po wygaśnięciu (1) |
| `przekazany do test-plan Phase 4` | 1 | granica limitu długości wiadomości (`send_message__mutmut_7`) |
| `brak wymagania` | 21 | brzmienie komunikatów (17; 4 warianty `None` zabija `test_refused_action_shows_a_reason`), kolejność błędów przy numerach spoza `1..N` (2), wyjaśnienie w bloku pamięci (1), treść `ImproperlyConfigured` (1) |

Przewidywania z research §2: `services.py:256` (`_clear_analysis_marker` bez `pk=`) — przeżywa, ale sklasyfikowany jako `równoważny` w praktyce (wymaga identycznej mikrosekundy znacznika). `services.py:279` i `:380` — przeżywają jako `brak wymagania` (widoczne tylko przy numerach wiadomości spoza zakresu, reguła z docstringu). `budget.py:107` — zabity już w Fazie 1.
