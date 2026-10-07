<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Pamięć między rozmowami i domykanie pętli błędów (S-03)

- **Plan**: context/changes/cross-session-error-memory/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-07
- **Verdict**: APPROVED
- **Findings**: 0 critical, 2 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

Automated: `makemigrations --check --dry-run` (no changes), `migrate` (nothing to apply), `pytest` (180 passed), `ruff check` + `ruff format --check` (clean). No DRIFT/MISSING; extra tests only (benign). All per-user reads go through `for_user`; `select_memory` runs a constant 3 queries.

## Findings

### F1 — Limity notatek tylko w instrukcji, kod ich nie pilnuje

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:352
- **Detail**: „Najwyżej 5 faktów / 8 notatek, jedno krótkie zdanie” jest tylko w promptcie analizy (llm.py:91-100). `MistakeReport` ma `list[str]` bez granic, a `_clean_notes` tylko robi `strip()`. Jeśli model zwróci 30 notatek albo akapit na 2000 znaków, wszystko trafi do bazy, a potem do instrukcji każdej tury przyszłych rozmów (fakty z 10 rozmów, notatki z 5). Koszt inputu nie ma górnej granicy.
- **Fix**: W `_clean_notes` przyciąć listę (limit 5 dla faktów, 8 dla notatek) i pominąć notatki dłuższe niż np. 200 znaków; test z fałszywą analizą zwracającą za dużo.
  - Strength: Plan zakłada górną granicę ~1–1,5 tys. tokenów (Performance Considerations) — to ją realnie gwarantuje.
  - Tradeoff: Trzeba wybrać próg długości; za niski utnie dobre notatki.
  - Confidence: HIGH — jedna funkcja, jedno miejsce zapisu.
  - Blind spot: Nie mierzyliśmy, jak długie notatki model daje w praktyce.
- **Decision**: ACCEPTED — ufamy modelowi w trzymaniu limitów; koszt ograniczają cache bloku pamięci, dzienny budżet (`DAILY_BUDGET_USD`) i okna 10/5 rozmów; ręczny test 1.5 dał sensowne notatki. Wrócić, gdy zmieni się `LLM_MODEL`.

### F2 — Ręczny krok 3.8 (cache od drugiej tury) niesprawdzony

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/cross-session-error-memory/plan.md:339
- **Detail**: 3.8 to jedyny niezaznaczony punkt Progress. Kod wygląda poprawnie (`memory_prompt` liczony raz w `services.py:106-118`, czytany w każdej turze `services.py:192`), ale cache nie został potwierdzony na prawdziwym modelu.
- **Fix**: W shellu sprawdzić `cached_input_tokens` w `Message` rozmowy z pamięcią (od 2. tury > 0) i zaznaczyć 3.8.
- **Decision**: FIXED — lokalne rozmowy były za krótkie, więc zrobiona symulacja 32 tur z prawdziwym `generate_turn` (bez zapisu do bazy, koszt 0,117 USD): instrukcje z pamięcią ~1,5 tys. tokenów; `cached_input_tokens` 0 w turach 0–5 i 11, potem 1792 → 2816 → 3840. Prefiks jest stabilny; brak trafień na starcie wynika z best-effort cache OpenAI. 3.8 zaznaczone w planie z notką.

### F3 — Blok pamięci bez ograniczników; nowe linie w notatkach zostają

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/llm.py:167, conversations/services.py:352
- **Detail**: Tekst ucznia (przez notatki i `Mistake.wrong`) trafia do instrukcji systemowych. Notatka z `\n` w środku może wyglądać jak nowa linia instrukcji. Skutek ograniczony: dotyczy tylko własnej pamięci ucznia (`for_user`), ale utrwala się między rozmowami.
- **Fix**: W `_clean_notes` użyć `" ".join(note.split())` zamiast `strip()` (razem z F1).
- **Decision**: ACCEPTED — ryzyko dotyczy tylko własnej pamięci ucznia (`for_user`); model analizy parafrazuje, a model rozmowy odróżnia notatkę od polecenia. Wrócić, gdyby pamięć kiedyś była współdzielona między użytkownikami.

### F4 — Okno 5 rozmów sceny liczy też rozmowy bez notatek

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/memory.py:88
- **Detail**: Najpierw `[:5]`, potem odrzucenie pustych list. Rozmowy sprzed S-03 zajmują miejsca w oknie, więc przez pewien czas wraca mniej niż 5 list notatek. Zgodne z literą planu (i przypięte testem `tests/test_memory.py:170`), ale plan nie mówi, że to zamierzone. Efekt przejściowy — znika po 5 nowych rozmowach w scenie.
- **Fix**: Zostawić kod i dopisać do planu zdanie, że to znane, przejściowe ograniczenie.
- **Decision**: SKIPPED — efekt przejściowy, nie warto czasu.
