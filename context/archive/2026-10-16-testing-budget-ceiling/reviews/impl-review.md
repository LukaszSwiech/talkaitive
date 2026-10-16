<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Rollout Phase 4 — sufit dziennego budżetu

- **Plan**: context/changes/testing-budget-ceiling/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-16
- **Verdict**: APPROVED
- **Findings**: 0 critical, 0 warnings, 5 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING (tylko obserwacje: F1, F2) |
| Architecture | PASS |
| Pattern Consistency | WARNING (tylko obserwacja: F3) |
| Success Criteria | WARNING (tylko obserwacje: F4, F5) |

## Evidence

Diff `main...HEAD` (d37e240, 51e5d3a, 834e476, e28c640), 24 pliki; review inline (bez sub-agentów), kod czytany z gita.

- `uv run python manage.py makemigrations --check --dry-run` → `No changes detected`
- `uv run pytest -q` → `305 passed`
- `uv run ruff check . && uv run ruff format --check .` → `All checks passed!`, `121 files already formatted`
- `uv run python scripts/mutation/manual_mutants.py` → `36 mutants, 36 match, 0 mismatch`, kod 0 (M25–M34 KILLED)
- `uv run mutmut results` (wyniki z istniejącego `mutants/`, **bez** świeżego `rm -rf mutants && mutmut run` — kasowanie katalogu zostało w tej sesji odrzucone; kod aplikacji nie zmienił się od 834e476) → 57 przeżyć, każde ma wiersz w `scripts/mutation/accepted_survivors.md`.

Punkty sprawdzone wprost (bez znalezisk):

- Każda ścieżka wywołania modelu kończy się zapisem kosztu: udana tura → `Message.cost_usd`; udana analiza → `analysis_cost_usd`; timeout / `ValidationError` / brak `usage` → `LLMCharge` `estimate`; pusta odpowiedź z `usage` → `no_usable_answer`; spóźniona tura i analiza → `late_result`; nieudany zapis analizy → `save_failed` (poza nieudaną transakcją, błąd zapisu kosztu logowany bez treści, pierwotny wyjątek zgłoszony). Wyjątek świadomy: nieudany zapis tury po udanym wywołaniu (plan, „What We're NOT Doing”).
- `APITimeoutError` stoi przed `except APIError` w `generate_turn` i `analyze_mistakes`.
- Odmowy na dachu w `send_message` i `run_agent_turn` zatwierdzają `end_conversation` przed `raise ConversationError` (flaga `at_ceiling`, wyjątek po wyjściu z `transaction.atomic()`); test `test_turn_retries_stop_once_the_limit_is_reached` przypina `ended_at == refused_at`.
- Kwoty w nowych testach to literały z rachunkiem w komentarzu; żaden test nie liczy oczekiwanej wartości przez `turn_cost`, `next_turn_estimate`, `day_start` ani `next_reset` (antywzorzec w `test_is_exhausted_false_after_midnight_reset` usunięty).
- Faza 3: `M14.original` po zmianie (`raise _no_usable_answer(response)`) usuwa całą gałąź `if`, kod zostaje poprawny składniowo, więc mutant nadal testuje zachowanie, nie składnię. Przeklasyfikowane i nowe wiersze rejestru (`analyze_conversation__mutmut_61–66`, `_149–156`, przenumerowania `_68`, `_120`, `next_turn_estimate__mutmut_4/5`, `start_conversation__mutmut_37–39`) zgadzają się z bieżącymi przeżyciami; trzy zabite przeżycia (`run_agent_turn__mutmut_23`, `_31`, `analyze_conversation__mutmut_60`) mają asercje w `test_turn_retries_stop_once_the_limit_is_reached` i `test_refused_action_shows_a_reason`.

## Findings

### F1 — Nieudany zapis wpisu księgi zastępuje `LLMError` błędem bazy

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:248-252 (tura), conversations/services.py:439-449 (analiza)
- **Detail**: W `except` wokół `generate_turn` i `analyze_mistakes` `_charge_failed_call` zapisuje `LLMCharge` przed `raise`. Jeśli ten zapis rzuci (baza niedostępna), pierwotny `LLMError` zostaje zastąpiony `DatabaseError`: widok nie złapie go jako `LLMError`, użytkownik dostaje 500 zamiast komunikatu z „Try again”. Plan (Critical Implementation Details) wymagał ochrony tylko w ścieżce `save_failed` i tam jest ona zrobiona; dwie pozostałe ścieżki są niespójne z nią. Bardzo rzadkie (baza pada akurat po błędzie modelu), znacznik tury jest już zwolniony.
- **Fix**: Owinąć `_charge_failed_call` w obu miejscach tym samym `try`/`except Exception` + `logger.error(type(...).__name__)` co w `save_failed` — albo świadomie zostawić i dopisać zdanie do „What We're NOT Doing”.
- **Decision**: SKIPPED

### F2 — Godzina resetu przy nieudanej analizie mówi „You can talk again”

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/templates/conversations/detail.html:74-77, conversations/templates/conversations/_reset_notice.html:1
- **Detail**: Nowa gałąź `analysis_failed and analysis_retry_reset_at` dołącza `_reset_notice.html`, który zawsze brzmi „You can talk again after HH:MM …”. W kontekście listy błędów chodzi o ponowienie analizy, nie o rozmowę; komunikat odmowy z serwisu mówi poprawnie „You can get your list of mistakes after the reset.”. Brzmienie nie jest wymaganiem (PRD „Odmowa akcji”), ale tekst na stronie jest mylący. Test `test_failed_analysis_at_the_limit_shows_the_reset_time_instead_of_try_again` przypina obecne „You can talk again after”.
- **Fix**: Parametr w `_reset_notice.html` (np. `with action="get your list of mistakes"`, domyślnie „talk”) i zmiana asercji testu na godzinę/strefę zamiast czasownika.
- **Decision**: FIXED — `_reset_notice.html` przyjmuje `action` (domyślnie „talk again”), `detail.html` przekazuje „get your list of mistakes”; asercje w `test_failed_analysis_*` sprawdzają `(Europe/Berlin)` zamiast czasownika. 305 testów, ruff czysty (niezacommitowane).

### F3 — Atrapy i helpery księgi nie są wspólne, jak zakładał plan

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/test_conversation_views.py:46-71, tests/test_analysis.py:85, tests/test_budget_ceiling.py:401-410, tests/test_budget.py:75-84
- **Detail**: Plan (faza 1, pkt 10) mówił: atrapy do `tests/fakes.py` **i ich fixture'y do `tests/conftest.py`**. Klasy trafiły do `tests/fakes.py`, ale fixture'y `fake_llm` / `fake_analysis` zostały w `test_conversation_views.py`, a `test_budget_ceiling.py` buduje atrapy ręcznie w każdym teście (to akurat działa, bo te testy potrzebują własnych wyników). Do tego cztery prawie identyczne fabryki wpisu `LLMCharge`: `add_charge` w `test_budget.py`, drugi `add_charge` w `test_budget_ceiling.py` (zdefiniowany w połowie pliku, między testami), `spend_the_whole_day` w `test_conversation_views.py` i `make_llm_charge_rows` w `test_account_deletion.py`. Nieszkodliwe, ale kolejny model w księdze oznacza cztery miejsca do zmiany.
- **Fix**: Jedna fabryka `add_charge(conversation, cost, at, kind=..., reason=...)` w `tests/fakes.py` (albo `conftest.py`) używana przez trzy pliki testów budżetu/widoków; w planie dopisek, że fixture'y zostały przy jedynym użytkowniku.
- **Decision**: FIXED — `add_charge(conversation, cost, at)` w `tests/fakes.py`; usunięte kopie w `test_budget.py`, `test_budget_ceiling.py`, `spend_the_whole_day` w `test_conversation_views.py`; `make_llm_charge_rows` używa `add_charge`. Fixture'y `fake_llm` / `fake_analysis` świadomie zostają w swoich plikach (każdy plik ma inny domyślny wynik); `plan.md` bez zmian (bez ręcznej edycji planu). 305 testów, ruff czysty, M28/M29 KILLED (niezacommitowane).

### F4 — `send_message__mutmut_7` jako `brak wymagania` pomija wyrocznię spójności UI ↔ serwer

- **Severity**: 💡 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Success Criteria
- **Location**: scripts/mutation/accepted_survivors.md (wiersz `x_send_message__mutmut_7`)
- **Detail**: Uzasadnienie mówi „brak wyroczni dla dokładnie 2000 znaków”. Jest jednak wyrocznia wewnętrzna: formularz ma `maxlength="2000"`, więc przeglądarka pozwala wpisać dokładnie 2000 znaków; mutant (`>` → `>=`) sprawia, że serwer odrzuca wiadomość, na którą UI pozwolił. Sprzeczny jest tylko tekst „under 2000 characters”. Klasyfikacja nie jest błędna, ale argument z `maxlength` nie jest w wierszu rozważony.
- **Fix A ⭐ Recommended**: Test „wiadomość o długości `max_message_length` z kontekstu strony jest przyjęta” (jedna wyrocznia: UI i serwer zgodne) i usunięcie wiersza z rejestru.
  - Strength: Zabija mutanta testem opartym na zachowaniu widocznym dla użytkownika, nie na brzmieniu.
  - Tradeoff: Przypina, że 2000 jest dozwolone; tekst „under 2000” trzeba wtedy poprawić na „up to 2000”.
  - Confidence: MED — `maxlength` i `MAX_MESSAGE_LENGTH` pochodzą z tej samej stałej (`max_message_length` w kontekście widoku).
  - Blind spot: Nie sprawdzałem, czy któryś istniejący test już wysyła dokładnie 2000 znaków.
- **Fix B**: Zostawić `brak wymagania`, dopisać w uzasadnieniu, że `maxlength` rozważono i odrzucono jako wyrocznię (bo komunikat mówi „under”).
  - Strength: Zero zmian w kodzie i testach.
  - Tradeoff: Rozjazd UI ↔ serwer pozostaje nieprzypięty.
  - Confidence: HIGH — to tylko doprecyzowanie tekstu.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — nowy `test_message_as_long_as_the_field_allows_is_accepted` (wyrocznia: `maxlength` odczytany ze strony), komunikat „Please keep your message to N characters or fewer.”, wiersz `x_send_message__mutmut_7` usunięty z rejestru; `mutmut run conversations.services.x_send_message__mutmut_7` → killed. 306 testów, ruff czysty (niezacommitowane). Liczba przeżyć w test-plan §6.6 („57”) zmienia się na 56 — do potwierdzenia pełnym przebiegiem mutmut.

### F5 — Ręczne sprawdzenie 2.4 bez śladu w diffie

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/testing-budget-ceiling/plan.md:398
- **Detail**: Punkt 2.4 (lokalnie z prawdziwym modelem: wpis `LLMCharge` = `DAILY_BUDGET_USD`, kolejna wiadomość kończy rozmowę bez wywołania modelu) jest `[x] — 51e5d3a`, ale opis commita 51e5d3a wymienia tylko testy i kod. Z natury ręczne sprawdzenie nie zostawia śladu w repo; to samo zachowanie przypinają testy `test_one_expensive_call_crosses_the_limit_and_the_next_message_is_refused` i `test_message_at_exactly_the_limit_is_refused_without_a_call`. Też: w Manual Testing Steps krok 5 (usunięcie wpisu) — jeśli pominięty, lokalny limit jest wyczerpany do północy Berlina.
- **Fix**: Użytkownik potwierdza, że sprawdzenie zostało wykonane (i wpis usunięty); inaczej odznaczyć 2.4.
- **Decision**: SKIPPED

## Triage

| Decision | Findings |
|----------|----------|
| Fixed | F2, F3, F4 (Fix A) |
| Skipped | F1, F5 |

Weryfikacja po poprawkach (niezacommitowane): `uv run pytest` → 306 passed; `ruff check` + `ruff format --check` czyste; `manual_mutants.py` → 36/36, kod 0; pełny `uv run mutmut run` → 841 mutantów, 56 przeżyć, 0 niesprawdzonych, każde przeżycie ma wiersz w rejestrze. Test-plan §6.6 (notatka fazy 4) zaktualizowany: 57 → 56 przeżyć, z wzmianką o zabitym `x_send_message__mutmut_7`.
