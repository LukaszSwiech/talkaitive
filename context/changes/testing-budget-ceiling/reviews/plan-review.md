<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Rollout Phase 4 — sufit dziennego budżetu

- **Plan**: context/changes/testing-budget-ceiling/plan.md
- **Mode**: Deep
- **Date**: 2026-10-16
- **Verdict**: REVISE (po triage: SOUND)
- **Findings**: 0 critical, 2 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding
8/8 paths ✓, 7/7 symbols ✓, brief↔plan ✓, Progress↔Phase ✓ (13/13 punktów). Weryfikacja w kodzie inline (bez sub-agenta): scenariusze kwotowe zgodne z `LLM_MAX_RETRIES = 1` / `LLM_ANALYSIS_MAX_RETRIES = 0`, chwile UTC dla 2026-10-25 poprawne, kolejność `except` dla `APITimeoutError` trafnie opisana.

## Findings

### F1 — Ręczna weryfikacja fazy 2 jest nieosiągalna

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Faza 2 — Manual Verification (2.4), Manual Testing Steps
- **Detail**: Przy `DAILY_BUDGET_USD=0.02` start rozmowy jest odmawiany od razu (`is_exhausted`: 0 + 0,03 >= 0,02, `budget.py:94-97`). Przy wyższym limicie rozmowę zwykle kończy płatna tura pożegnalna (`is_final_turn`) zanim suma dojdzie do limitu, więc ręczny test sprawdzałby stare zachowanie, nie nowy dach.
- **Fix**: W trakcie aktywnej rozmowy dopisać w `manage.py shell` wpis `LLMCharge` na dziś z kwotą równą `DAILY_BUDGET_USD`, wysłać wiadomość, sprawdzić odmowę i logi, potem usunąć wpis.
- **Decision**: FIXED

### F2 — Dwie płatne ścieżki dalej zapisują 0 USD

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Faza 1 — #3 (`LLMError`) i #5 (zapis kosztu)
- **Detail**: Desired End State obiecuje, że każde wywołanie, które najpewniej kosztowało, liczy się do sumy dnia. Bez przypisanej kwoty zostały: (a) poprawna odpowiedź bez `usage` (`llm.py:283-285`, `:352-354`), (b) nieudany zapis tury po udanym wywołaniu (`services.py:203-207`) — `save_failed` był tylko dla analizy.
- **Fix A ⭐ Recommended**: (a) `usage is None` po poprawnej odpowiedzi → `billed_without_usage=True` + test w `test_llm.py`; (b) jawnie w „What We're NOT Doing” z uzasadnieniem.
  - Strength: (a) to jedno zdanie kontraktu i jeden test; (b) błąd bazy w krótkiej transakcji jest bardzo rzadki.
  - Tradeoff: Obietnica End State dostaje jawny wyjątek.
  - Confidence: HIGH — ścieżki widać wprost w kodzie.
  - Blind spot: None significant.
- **Fix B**: Zaksięgować oba, (b) jako `save_failed` dla tury wzorcem analizy.
  - Strength: Obietnica End State bez wyjątków.
  - Tradeoff: Drugi `try`/`except` w `_generate_and_save`, test i mutant dla rzadkiego przypadku.
  - Confidence: MEDIUM — zachowanie znacznika tury po wycofaniu transakcji niesprawdzone.
  - Blind spot: Znacznik tury zostaje do wygaśnięcia, bo jego zwolnienie cofa się z transakcją.
- **Decision**: FIXED (Fix A)

### F3 — Fragmenty mutantów M31–M33 nie będą unikalne

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Faza 2 — #2 i #5
- **Detail**: Gałąź dachu w `send_message` i `run_agent_turn` to ten sam tekst, a `end_conversation(..., Conversation.EndReason.DAILY_LIMIT, now)` jest już w `_save_agent_turn` (`services.py:230`); `manual_mutants.py` wymaga, by `original` występował w pliku dokładnie raz.
- **Fix**: W Critical Implementation Details: `original` mutantów `M31`–`M33` obejmuje sąsiednią linię właściwą danej funkcji.
- **Decision**: FIXED

### F4 — Scenariusz „przez północ 25 października” nie sprawdza doby 25 h

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Faza 2 — #4, „ponowienie analizy przez północ”
- **Detail**: Chwila zasianego wydatku 1,00 nie jest ustalona; w środku dnia test przejdzie także przy złej granicy doby („24 h wstecz” albo stałe UTC+1). Granicę pokrywają już testy unit z fazy 1 #8.
- **Fix**: Chwila wydatku 2026-10-24 22:00 UTC (= 00:00 CEST 25.10).
- **Decision**: SKIPPED — wystarczą testy unit z fazy 1 #8.

### F5 — Atrapy z test_conversation_views.py nie wystarczą nowemu plikowi

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Faza 1 — #10
- **Detail**: `FakeGenerateTurn` i `FakeAnalyzeMistakes` są w `tests/test_conversation_views.py:46`, `:75`, nie we wspólnym module; `FakeAnalyzeMistakes` nie przyjmuje funkcji, a test „analiza spóźniona” potrzebuje funkcji ustawiającej `analyzed_at` w trakcie wywołania.
- **Fix**: Przenieść obie atrapy do `tests/fakes.py` (fixture'y do `tests/conftest.py`) i dodać wynik-funkcję w `FakeAnalyzeMistakes`.
- **Decision**: FIXED
