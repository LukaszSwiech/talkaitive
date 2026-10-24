<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Siatka kart tematów na home

- **Plan**: context/changes/ui-home-topic-grid/plan.md
- **Mode**: Deep
- **Date**: 2026-10-23
- **Verdict**: REVISE → SOUND po triage (wszystkie wnioski naniesione na plan)
- **Findings**: 0 critical, 2 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

13/13 paths ✓, 6/6 symbols ✓, brief↔plan ✓, Progress↔Phase ✓

## Findings

### F1 — Test skoku do „Social life” nie może się wywrócić

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 4 — Spec Playwright, kryterium 4.2
- **Detail**: „Social life” to ostatnia sekcja. Pod nią są tylko 4 karty i stopka, czyli mniej niż wysokość ekranu w obu rozmiarach testu (1280×720 i 390×844, `tests/e2e/ui-home.spec.ts:17-20`). Przeglądarka zatrzymuje się na dole strony, a nagłówek zostaje daleko pod paskiem. Bez przesunięcia test i tak byłby zielony, więc kryterium 4.2 było niewykonalne.
- **Fix**: Test sprawdza link „Neighbours & small talk” (druga kategoria) i dodatkowo asercję `window.scrollY > 0`.
- **Decision**: FIXED — Faza 4, punkt „Nowy test „jump link…”” przepisany.

### F2 — Pasek sticky może zasłonić kartę z fokusem

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 — components.css (`.category-nav`, `.topic-section`); kryterium 3.7
- **Detail**: `scroll-margin-top` na sekcjach działa tylko przy skoku do kotwicy. Przy Shift+Tab przeglądarka przewija kartę z fokusem do górnej krawędzi, czyli pod pasek (WCAG 2.2, 2.4.11 „Focus Not Obscured”). Kryterium 3.7 sprawdzało tylko Tab w dół.
- **Fix A ⭐ Recommended**: `scroll-padding-top` na `html:has(.category-nav)` zamiast `scroll-margin-top` na sekcjach.
  - Strength: Jedna reguła obejmuje kotwice i przewijanie do fokusu. Działa tylko na stronach z paskiem.
  - Tradeoff: Kryterium 4.2 psuje teraz `scroll-padding-top`.
  - Confidence: MED — Chrome i Firefox biorą scroll-padding pod uwagę przy fokusie.
  - Blind spot: Safari niesprawdzone; kryterium 3.7 sprawdza teraz Shift+Tab.
- **Fix B**: `scroll-margin-top` także na `.topic-card`.
  - Strength: Minimalna zmiana, kryterium 4.2 bez zmian.
  - Tradeoff: Ta sama wartość w dwóch miejscach.
  - Confidence: MED — nie każda przeglądarka bierze scroll-margin pod uwagę przy fokusie.
  - Blind spot: Działanie przy fokusie nie jest sprawdzone.
- **Decision**: FIXED — Fixed via Fix A. Zmienione: Critical Implementation Details, kontrakt CSS w Fazie 3, kryteria 3.7 i 4.2 (w fazach i w Progress), wiersz „Linki-skoki” w `plan-brief.md`.

### F3 — Wspólna funkcja w Fazie 2 może zepsuć mutanty M1/M2

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Widok i trasa
- **Detail**: `scripts/mutation/manual_mutants.py:93-106` szuka w `views.py` tekstu `active = (` + `Conversation.objects.for_user(request.user)` z wcięciem 4 spacji (M1) i 8 spacji (M2). Każdy wariant musi wystąpić dokładnie raz (`:555-566`). Funkcja pomocnicza może zmienić wcięcie albo powielić kod. Skrypt mutacji wtedy się wywróci, a pytest tego nie zauważy.
- **Fix**: Kryterium `uv run python scripts/mutation/manual_mutants.py M1 M2` (exit 0) w Fazie 2. Gdy tekst się zmieni, w tym samym kroku poprawić `original` mutanta.
- **Decision**: FIXED — zdanie w kontrakcie widoku, nowe kryterium i krok 2.4 w Progress.

### F4 — Kitchen sink: pasek z 4 linkami, ale karty tylko z 2 kategorii

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 — Kitchen sink
- **Detail**: `TOPICS[:3]` to dog-walk, supermarket i bakery, czyli tylko kategorie small-talk i errands. Linki do appointments i social nie miały celu. Ukryte zależności: `ui_kitchen_sink.html:59` używa `{{ topics.0.title }}`, a test fokusu (`ui-home.spec.ts:84-87`) zakłada, że pierwszy fokus trafia w „Primary”.
- **Fix**: Po jednej przykładowej karcie z każdej kategorii w mini-sekcjach `ks-<key>`. Klucz `topics` zostaje, a sekcja stoi w miejscu dawnej „Choice list”.
- **Decision**: FIXED — punkt 5 Fazy 3 przepisany.

### F5 — Kontrakt korzenia <svg> nie chroni grubości linii

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Wklejone ikony Tabler
- **Detail**: Ikony Tabler outline mają w korzeniu `stroke-width="2"`, `stroke-linecap="round"` i `stroke-linejoin="round"`. Kontrakt ich nie wymieniał, więc przy ujednolicaniu łatwo je zgubić: linia miałaby grubość 1 i kanciaste końce.
- **Fix**: Trzy atrybuty obowiązkowe w kontrakcie. Strażnik w `tests/test_topics.py` sprawdza też `stroke-width="2"`.
- **Decision**: FIXED — kontrakt ikon i lista testów w Fazie 1.
