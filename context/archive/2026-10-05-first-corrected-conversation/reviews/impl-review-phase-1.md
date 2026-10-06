<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Pierwsza rozmowa z korektą na bieżąco (S-01)

- **Plan**: context/changes/first-corrected-conversation/plan.md
- **Scope**: Phase 1 of 4
- **Reviewed phases**: 1
- **Date**: 2026-10-06
- **Verdict**: APPROVED
- **Findings**: 0 critical 2 warnings 3 observations

Zakres przeglądu: commit `8d8d845` (16 plików). Kryteria automatyczne 1.1–1.5 uruchomione ponownie na zacommitowanym kodzie — wszystkie przechodzą (31 testów). Krok ręczny 1.6 potwierdzony przez użytkownika w tej sesji.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Zmiana LLM_MODEL bez wpisu w cenniku wyjdzie dopiero po płatnym wywołaniu

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings.py:58-70
- **Detail**: `LLM_MODEL` można nadpisać zmienną env, ale `LLM_PRICES_USD_PER_MTOK` ma tylko wpis `gpt-5.4`. Test `test_llm_model_has_a_price_entry` sprawdza tylko model domyślny. Plan (faza 2) każe `turn_cost` rzucać `ImproperlyConfigured` dla nieznanego modelu — ale to nastąpi PO wywołaniu API (koszt poniesiony, odpowiedź niezapisana, budżet nieliczony).
- **Fix**: Zwalidować przy starcie aplikacji (w `settings.py` po definicji cennika): jeśli `LLM_MODEL` nie jest w `LLM_PRICES_USD_PER_MTOK`, rzucić `ImproperlyConfigured` z czytelnym komunikatem.
  - Strength: Błąd konfiguracji wychodzi przy starcie (fail-fast, jak `SECRET_KEY`), zanim padnie jakiekolwiek płatne wywołanie.
  - Tradeoff: Zmiana modelu na Railway wymaga jednoczesnego dopisania ceny w kodzie (to i tak potrzebne, żeby budżet działał).
  - Confidence: HIGH — ten sam wzorzec fail-fast jest już w `settings.py` dla `SECRET_KEY` i `OPENAI_API_KEY`.
  - Blind spot: None significant.
- **Decision**: FIXED — sprawdzenie `LLM_MODEL` przy starcie w `settings.py` + test `test_unpriced_llm_model_fails_at_startup` (break-check: czerwony po wyłączeniu warunku)

### F2 — Message nie ma własnego for_user (ryzyko IDOR w późniejszych fazach)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: conversations/models.py:54-76
- **Detail**: `Message` jest zwykłym `models.Model` bez `user` i bez `for_user`. Każde przyszłe `Message.objects.get(pk=pk)` w widoku byłoby IDOR (lessons.md: „Widoki szczegółów pobierają obiekt przez for_user”). Reguła wymaga filtrowania przez właściciela rodzica, ale nic tego nie wymusza mechanicznie. Plan fazy 3 nie pobiera `Message` po `pk` (widoki czytają `conversation.messages`), więc dziś nie ma luki.
- **Fix A ⭐ Recommended**: Nic nie zmieniać teraz; w fazie 3 pobierać wiadomości wyłącznie przez `conversation.messages` (rozmowa z `for_user`) i pilnować tego w review fazy 3
  - Strength: Zgodne z planem; brak nowego kodu bez użytkownika.
  - Tradeoff: Ochrona opiera się na dyscyplinie, nie na mechanizmie.
  - Confidence: HIGH — plan fazy 3 nie przewiduje widoku z `Message` po `pk`.
  - Blind spot: Przyszły slice (S-02) może dodać taki widok.
- **Fix B**: Dodać `MessageQuerySet.for_user(user)` (`filter(conversation__user=user)`, pusty wynik dla anonimowego) jako manager `Message.objects` + test
  - Strength: Mechaniczna ochrona zgodna z regułą z lessons.md.
  - Tradeoff: Dodatkowy kod i test poza planem fazy 1.
  - Confidence: MED — wymaga decyzji o kształcie API zgodnym z `UserOwned`.
  - Blind spot: Nie sprawdzono, jak `UserOwned.for_user` obsługuje anonimowego, żeby zachować spójność.
- **Decision**: FIXED via Fix A — bez zmian w kodzie; w fazie 3 wiadomości tylko przez `conversation.messages` (rozmowa z `for_user`), pilnowane w review fazy 3 (follow-up zapisany w follow-ups/review-fixes.md)

### F3 — settings_test nie ustawia atrapy OPENAI_API_KEY

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings_test.py
- **Detail**: Przy uruchomieniu `uv run --env-file .env pytest` prawdziwy klucz trafiłby do ustawień testowych; jedynie atrapa `generate_turn` chroni przed płatnym wywołaniem. Gdy testy uruchomi się z `DEBUG=False`, brak zmiennej wywali cały zestaw (`KeyError`).
- **Fix**: Dodać do `settings_test.py` `OPENAI_API_KEY = "test-key"`, żeby przypadkowe prawdziwe wywołanie kończyło się 401, a nie płatnym requestem.
- **Decision**: FIXED — `OPENAI_API_KEY = "test-key"` w `settings_test.py` (zweryfikowane: nadpisuje klucz z env). Uwaga: `KeyError` przy `DEBUG=False` bez zmiennej pada w `from .settings import *`, więc to zostaje świadomym fail-fast jak dla `SECRET_KEY`.

### F4 — LLM_REASONING_EFFORT="none" niezweryfikowane na prawdziwym API

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings.py:60
- **Detail**: Context7 wymienia `none` jako najniższą wartość, ale nie potwierdza, że `gpt-5.4` ją przyjmuje. Testy z atrapą klienta tego nie wykryją; błąd wyjdzie przy pierwszym prawdziwym wywołaniu.
- **Fix**: Nic w kodzie; sprawdzić w ręcznym teście fazy 3. Jeśli API odrzuci, zmienić domyślną wartość na `minimal` lub `low` (zmienna env, bez zmiany kodu).
- **Decision**: FIXED as follow-up — bez zmian w kodzie; do sprawdzenia przy pierwszym prawdziwym wywołaniu API w ręcznym teście fazy 3 (follow-ups/review-fixes.md)

### F5 — OPENAI_API_KEY nie jest jeszcze ustawiony na Railway

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings.py:50-53, context/deployment/deploy-plan.md:154
- **Detail**: Poza DEBUG brak `OPENAI_API_KEY` celowo wywala start. Push tego commita na `main` przed ustawieniem zmiennej na Railway zablokuje deploy (pre-deploy/healthcheck padnie; stara wersja działa dalej). Plan już o tym mówi (faza 4, krok 3).
- **Fix**: Brak akcji teraz; nie wypychać na `main`, dopóki zmienna nie jest ustawiona na serwisie `web`.
- **Decision**: SKIPPED — plan już to pokrywa (faza 4, krok 3: zmienna przed pushem)
