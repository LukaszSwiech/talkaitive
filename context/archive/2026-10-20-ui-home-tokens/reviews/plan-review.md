<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Tokeny i komponenty UI na widoku home (ui-home-tokens)

- **Plan**: context/changes/ui-home-tokens/plan.md
- **Mode**: Deep (weryfikacja w kodzie bez sub-agenta)
- **Date**: 2026-10-20
- **Verdict**: REVISE (po triage: SOUND — wszystkie ustalenia poprawione w planie)
- **Findings**: 0 critical, 2 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding

11/11 paths ✓, 10/10 symbols ✓, brief↔plan ✓, Progress↔Phase ✓. Potwierdzone: E2E webServer działa z `DEBUG=True` (`playwright.config.ts:53`), więc `/ui/` jest dostępne dla zrzutów; regex strażnika kolorów trafia dziś tylko w `base.html` i `home.html` (brak fałszywych trafień); aplikacja wysyła tylko komunikaty `error` i `success`; przypięty HTML i numery linii testów zgodne z planem.

## Findings

### F1 — Alert success i granica pola bez tokenów i bez pary kontrastu

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Phase 2 §1, §2, §3; Phase 3 §1
- **Detail**: Faza 3 obiecuje `.alert[data-variant="success"]`, ale faza 2 dodawała tylko `--success` (kolor tekstu) — bez tła alertu i bez pary w `CONTRAST_PAIRS`. Pola `input`/`textarea` miały mieć „widoczną granicę” bez wskazania tokenu i bez pomiaru; w tweakcn jasne `--input` (L=0.970) jest jaśniejsze od tła (L=0.938), a `--border` na tle daje ok. 1.2:1 (WCAG 1.4.11 wymaga 3:1).
- **Fix A ⭐ Recommended**: `--success-muted` + para `foreground/success-muted` 4.5; granica pola = `--input` poprawione w obu motywach + pary `input/background`, `input/card` 3.0.
  - Strength: Domyka obietnicę „AA w obu motywach”; ten sam wzorzec co `--destructive-muted`.
  - Tradeoff: Ciemniejsze obramowania pól niż w tweakcn.
  - Confidence: HIGH — wartości sprawdzone w `theme-source.css:30-31`.
  - Blind spot: Nowa wartość `--input` dobierana w implementacji.
- **Fix B**: Tylko `--success-muted`; granica pola sprawdzana ręcznie.
  - Strength: Zostaje charakter tweakcn.
  - Tradeoff: Plan twierdzi „AA”, a test tego nie pilnuje.
  - Confidence: MED.
  - Blind spot: Pola na stronie logowania mogą być słabo widoczne.
- **Decision**: FIXED (Fix A) — Phase 2 §1 (`--input` w obu motywach, `--success-muted`), §2 (obramowanie `--input`), §3 (3 nowe pary), Phase 3 §1 (kolory wariantów alertu); `plan-brief.md` wiersz „Kontrast”.

### F2 — Zrzuty home zależą od stanu e2e.sqlite3, którego nic nie pilnuje

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 4 §4 (Zrzuty Playwright)
- **Detail**: Spec zakładał użytkownika E2E bez aktywnej rozmowy, ale nic tego nie wymuszało. `e2e.sqlite3` przeżywa między uruchomieniami, `ensure_e2e_user.py` ustawia tylko hasło, a kliknięcie tematu przy pustym kluczu zostawia rozmowę ACTIVE (`conversations/views.py:63-69`). Wtedy zrzut „home default” i test loading padają przy każdym uruchomieniu, wyglądając jak regresja wizualna.
- **Fix**: `ensure_e2e_user.py` przy starcie serwera usuwa `Conversation` i `LLMCharge` użytkownika E2E; spec przed zrzutami home sprawdza `getByRole('heading', { name: 'Choose a topic' })` (przy `reuseExistingServer` skrypt nie biegnie ponownie).
  - Strength: Bramka wizualna mierzy wygląd, nie stan bazy.
  - Tradeoff: Jeden plik więcej w zmianie.
  - Confidence: HIGH — zachowanie start→LLMError widać w kodzie widoku.
  - Blind spot: Przyszłe spec-e, które celowo startują rozmowę, będą się ścigać z tym spec przy `fullyParallel`.
- **Decision**: FIXED — Phase 4 §4 (File + Contract).

### F3 — MESSAGE_TAGS zmienia też komunikaty błędów w adminie

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 §3 (Komunikaty flash)
- **Detail**: `MESSAGE_TAGS` jest globalne; admin jest włączony (`talkaitive/urls.py:31`) i barwi komunikaty po klasie (`ul.messagelist li.error`). Mapowanie `ERROR` → `destructive` zamieniłoby błędy w adminie w wygląd info.
- **Fix**: Zamiast `MESSAGE_TAGS` alias selektora `.alert[data-variant="error"]` = destructive w `components.css`.
- **Decision**: FIXED — Implementation Approach (Alert), Phase 3 §1 (Contract), §3 (bez `settings.py`), §4 i Testing Strategy (test `data-variant="error"` + selektor aliasu); `plan-brief.md` wiersz „Warianty”.

### F4 — Lista tematów w /ui/ może wystartować prawdziwą (płatną) rozmowę

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 4 §2 (Strona kitchen sink)
- **Detail**: „`.choice-list` z trzema tematami” jako kopie formularzy z home sprawiłyby, że Enter przy ręcznym teście fokusu startuje rozmowę z kluczem z `.env`.
- **Fix**: Elementy listy w kitchen sink jako `<button type="button">` bez `<form>`.
- **Decision**: FIXED — Phase 4 §2 (Intent).

### F5 — kitchen_sink.html w folderze zarezerwowanym na komponenty

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 4 §2; Phase 5 §1
- **Detail**: Reguła z fazy 5 rezerwuje `accounts/templates/ui/<nazwa>.html` na szablony komponentów; strona kitchen sink w tym folderze mieszała role. Istniejące strony leżą w `accounts/templates/accounts/`.
- **Fix**: `accounts/templates/accounts/ui_kitchen_sink.html`.
- **Decision**: FIXED — Phase 4 §2 (File).

### F6 — Los starych selektorów .button, .topics, .flash, .flash.error

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §2, Phase 3 §1 i §3
- **Detail**: Po fazie 3 `.flash.error`, `.button` i `.topics` są martwe, a `.flash` i `.alert` mają tę samą specyficzność — wygląd komunikatu zależałby od kolejności reguł. Plan tego nie rozstrzygał.
- **Fix**: W fazie 3 §1 usunąć `.button`, `.topics`, `.flash.error`; `.flash` bez reguł wyglądu (znacznik dla testów).
- **Decision**: FIXED — Phase 3 §1 (Intent).
