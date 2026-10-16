<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Rollout Phase 3 — granice prywatności i usuwania konta

- **Plan**: context/changes/testing-privacy-and-deletion-boundaries/plan.md
- **Mode**: Deep
- **Date**: 2026-10-15
- **Verdict**: REVISE → SOUND (after fixes)
- **Findings**: 0 critical, 2 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | WARNING |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | PASS |

## Grounding
11/11 paths ✓, 5/5 symbols ✓ (`_get_conversation`, `select_memory` `for_user`, `user_data_models`, `delete_account`, Django 6.1.1 `log_deletions` before `delete_model` / `delete_queryset`), brief↔plan ✓, Progress↔Phase ✓

## Findings

### F1 — Test 404 może przejść „na pusto” dla przyszłej trasy podrzędnej

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Faza 1, zmiany #1–#2; Current State „Dane podrzędne”
- **Detail**: `ID_ROUTES` było tylko „nazwa → metoda”, a test 404 zawsze wstawia `conversation.pk`. Przyszła trasa po pk `Message`, wymuszona do `ID_ROUTES` przez strażnika, dostałaby 404 z powodu „nie ma takiej wiadomości”, nie „to nie twoja” — zielony test mimo IDOR.
- **Fix**: `ID_ROUTES: dict[str, tuple[str, type[Model]]]`; test 404 obsługuje tylko `Conversation`, inny model wywraca test z komunikatem; strażnik wymaga parametrów dokładnie `{"pk"}`.
  - Strength: Zamyka fałszywie zieloną ścieżkę zostawioną strażnikowi.
  - Tradeoff: Odrobinę więcej kodu w teście.
  - Confidence: HIGH — wynika z `reverse(name, kwargs={"pk": conversation.pk})`.
  - Blind spot: None significant.
- **Decision**: FIXED

### F2 — Strażnik tras nie widzi `re_path` ani konwertera w prefiksie `include()`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Faza 1, zmiana #2
- **Detail**: Reguła „wzorzec ma konwerter” przepuszcza `re_path` z nazwaną grupą i parametr w prefiksie `include()`.
- **Fix**: Wykrywać parametry przez `pattern.regex.groupindex` i sumować je wzdłuż ścieżki `include()`.
- **Decision**: FIXED

### F3 — Mutanty M19–M21 pisane dwa razy (faza 2, potem przepinane w fazie 3)

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Lean Execution
- **Location**: Faza 2 #3, Faza 3 #3, Critical Implementation Details
- **Detail**: Faza 3 przenosi kod, w który celują M19–M21, więc ich `original` trzeba by przepisać; testy zabijające istnieją już dziś.
- **Fix**: Przenieść M19–M21 do fazy 3 (plan, Progress 2.3, plan-brief).
- **Decision**: FIXED
