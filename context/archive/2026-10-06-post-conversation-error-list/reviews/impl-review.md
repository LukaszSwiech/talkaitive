<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Lista błędów po zakończeniu rozmowy (S-02)

- **Plan**: context/changes/post-conversation-error-list/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-10-07
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 4 observations

Reviewed range: `adc1081..7c2ac87` plus the uncommitted working tree at review time (`conversations/services.py`, `tests/test_analysis.py`, edited by a parallel session). Gates on that tree: `uv run pytest` 153 passed; `ruff check` + `ruff format --check` clean; `makemigrations --check --dry-run` no changes.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Poprawka „failed tylko bez nowszego znacznika” nie jest w HEAD

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: conversations/services.py:286-289, tests/test_analysis.py
- **Detail**: W drzewie roboczym jest niezatwierdzona zmiana z równoległej sesji: aktualizacja `analysis_failed_at` filtruje też `analysis_started_at__isnull=True`, więc porażka starego żądania nie nadpisuje stanu, gdy nowsze żądanie przejęło wygasły znacznik; plus 2 testy. Zmiana jest poprawna (zgodna z regułą „spóźniony wynik” z Critical Implementation Details), ale nie ma jej w żadnym commicie ani w `change.md`.
- **Fix**: Niech sesja, która ją zrobiła, zacommituje ją jako osobny commit `fix(post-conversation-error-list): …` i dopisze jedną linię do Notes w `change.md`.
- **Decision**: FIXED — w równoległej sesji: commit `7f8d62c`, notatka w `change.md` (`7419586`).

### F2 — Udokumentowane odstępstwa: effort/limit analizy i normalizacja zapisanych wartości

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: talkaitive/settings.py:64-75, conversations/services.py:361
- **Detail**: Plan: effort `high`, limit 90 s. Teraz: `medium`, 150 s (pomiar i decyzja w Notes `change.md`); tytuł kroku 4.7 w Progress nadal mówi o `high` / 90 s. Dodatkowo `_merge_mistakes` zapisuje `wrong`/`correct` po zwinięciu białych znaków, a `sentence`/`explanation` po `strip()` — plan mówił o normalizacji tylko do porównań; nieszkodliwe.
- **Fix**: Bez zmian w kodzie; odstępstwo jest opisane w `change.md`.
- **Decision**: FIXED (differently) — na wyraźną, jednorazową prośbę użytkownika tekst `plan.md` poprawiony bezpośrednio (effort `medium`, 150 s, normalizacja przy zapisie, krok 4.7 w bloku fazy i w Progress), żeby agent czytający sam plan nie widział rozjazdu. Krok 2.3 bez zmian (historyczny test effort `high`).

### F3 — Błąd zapisu po udanym wywołaniu modelu nie ustawia stanu porażki

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:293-306
- **Detail**: Wyjątek w drugim `transaction.atomic()` (np. błąd DB przy `bulk_create`) cofa też `_clear_analysis_marker`, a `analysis_failed_at` nie jest ustawiane. Strona przez ~180 s pokazuje spinner, potem wpada w auto-wysyłkę i robi jedno kolejne płatne wywołanie; koszt pierwszego nie jest zapisany. To samo zachowanie co przy turze agenta (`_generate_and_save`, :179-183), więc spójne; nie tworzy pętli.
- **Fix**: Opcjonalnie owinąć zapis w try/except, który czyści znacznik i ustawia `analysis_failed_at`, tak jak ścieżka wywołania modelu.
- **Decision**: FIXED — `_mark_analysis_failed` wywoływane też po błędzie zapisu; test `test_save_error_after_model_call_marks_failure`.

### F4 — Koszt analizy liczony do dnia startu żądania

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:296, conversations/budget.py:68-72
- **Detail**: `analyzed_at = now` to czas startu żądania, a tury liczą się po `Message.created_at` (czas zapisu). Analiza zaczęta przed północą Europe/Berlin i skończona po niej trafia do poprzedniego, już zresetowanego dnia. Skutek: najwyżej koszt jednej analizy.
- **Fix**: Zaakceptować albo ustawiać `analyzed_at = timezone.now()` w chwili zapisu.
- **Decision**: ACCEPTED — świadome zachowanie: koszt analizy liczy się do dnia startu żądania (`analyzed_at = now`); skutek pomijalny.

### F5 — Analiza zajmuje wątek gunicorna do 150 s

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings.py:71-75, context/deployment/web-settings.json:7
- **Detail**: 2 workery × 4 wątki = 8 slotów; każda analiza trzyma jeden slot do ~150 s (gthread nie ucina żądania — komentarz w settings jest poprawny). Przy skali MVP wystarcza, ale to sufit równoległych analiz.
- **Fix**: Zaakceptować na MVP; wrócić do tematu przy zadaniach w tle.
- **Decision**: ACCEPTED — na MVP wystarcza (zob. Q-07 w roadmapie).

Known, already documented (not a finding): an analysis cut off by the timeout records cost 0, while OpenAI may bill it (`change.md` Notes).
