# Waiting-path recovery (test-plan Phase 2) — Plan Brief

> Full plan: `context/changes/testing-waiting-path-recovery/plan.md`
> Research: `context/changes/testing-waiting-path-recovery/research.md`

## What & Why

Ryzyko #1 z planu testów: użytkownik czeka bez końca na odpowiedź agenta albo na listę błędów, a „Try again” nie przywraca działania. Chcemy dowodu testami, że zawieszenie, błąd albo pusty wynik dostawcy w skończonym czasie kończy się komunikatem i działającym „Try again”, które naprawdę robi nowe wywołanie. Research znalazł też trzy realne dziury, które naprawiamy przy okazji.

## Starting Point

Ścieżka „błąd → Try again” ma testy, ale atrapy siedzą nad SDK, więc nigdy nie wykonuje się prawdziwa pętla ponowień, timeoutów i `Retry-After`. Znacznik „w toku” tury (90 s) jest krótszy niż najdłuższe czekanie SDK z `Retry-After` (do 180 s), pusta odpowiedź agenta zapisuje się jako pusta bańka, a strona analizy po awarii procesu sama uruchamia nową płatną analizę.

## Desired End State

Testy przechodzą całą drogę od strony do SDK z atrapą na transporcie HTTP i dowodzą sukcesu stanem bazy, liczbą zapytań i treścią strony, nigdy samym kodem HTTP. Znacznik tury żyje 210 s (czekanie SDK 180 s + 30 s), pusta odpowiedź daje „Try again”, a wygasły znacznik analizy daje komunikat i przycisk zamiast auto-wysyłki. Mutanty przekazane do tej fazy są zabite albo opisane.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Wyścig `Retry-After` (P1) | Znacznik tury = timeout × próby + ponowienia × 120 s + 30 s (210 s) | OpenAI potwierdza `Retry-After` przy 429/503, a SDK czeka do 120 s — żywe wywołanie nie może wyglądać na martwe | Research + Plan |
| Pusta odpowiedź (P2) | `reply` pusty lub z samych białych znaków → `LLMError`, nic nie zapisane | Wytyczna ryzyka #1: „pusty wynik → komunikat i Try again” | Plan |
| Górna granica znacznika (P3) | Dokładnie 30 s ponad najdłuższe czekanie SDK, sprawdzane co do sekundy | Daje wyrocznię dla wszystkich mutantów znacznika | Plan |
| Przyczyna incydentu Q2 (P4) | Test niezmiennika ustawień (< 300 s Railway) + pomiar realnego czasu jako zadanie Phase 5 | Atrapa nie zna realnego czasu modelu; test łapie ustawienia sprzeczne z platformą | Research + Plan |
| Warstwa atrapy (P5) | Transport HTTP dla SDK i pełnej ścieżki; obecne atrapy dla wyścigów dwóch żądań | Prawdziwe SDK tam, gdzie ma znaczenie; tanie testy kolejności zdarzeń | Research + Plan |
| Analiza po awarii (P6) | Wygasły znacznik = porażka: komunikat + „Try again”, bez auto-wysyłki | Każde ponowne płatne wywołanie wymaga świadomego kliknięcia | Plan |
| Mutacje dla `llm.py` (P7) | Ręczne mutanty w `manual_mutants.py`, bez dodawania `llm.py` do mutmut | Celuje w nowe zachowanie bez szumu z promptów i logów | Plan |
| Czekanie SDK w teście | Podmiana `time.sleep` na rejestrator | SDK usypia się przez `time.sleep`; test widzi żądany czas bez czekania i bez prywatnego API | Plan (próba w scratchpadzie) |

## Scope

**In scope:**
- Moduł atrapy transportu `tests/fake_provider.py`, fixture w `tests/conftest.py`, nowy plik `tests/test_waiting_path.py`
- Testy granicy SDK w `llm.py`, granic znaczników, niezmiennika ustawień, wyścigu znacznika tury
- Poprawki: pusta odpowiedź (`llm.py`), wzór znacznika + `LLM_MAX_RETRY_AFTER_SECONDS` (`settings.py`, `services.py`), stan `analysis_failed` (`services.py`, `views.py`, `detail.html`)
- Ręczne mutanty, przebieg mutmut, rejestr przeżyć, test-plan §6.3, §6.6 i §3

**Out of scope:**
- Koszt nieudanych i ponawianych wywołań (Phase 4), pomiar realnego czasu modelu (Phase 5)
- Zmiana timeoutów, liczby ponowień, effortu; analiza poza żądaniem HTTP; limit prób „Try again”
- Playwright, testy obciążenia, edycja test-plan §2 / §4

## Architecture / Approach

Fixture podmienia `conversations.llm.OpenAI` na klienta z `httpx2.MockTransport` i przekazuje mu ustawienia z `_get_client` bez zmian. Scenariusz w teście opisuje kolejne odpowiedzi dostawcy (zawieszenie, 503 z `Retry-After`, odpowiedź, pusta odpowiedź), a test sprawdza bazę, liczbę zapytań, zarejestrowane sny i stronę. Czas symulujemy znacznikiem w bazie albo parametrem `now`. Wyrocznie czasu (210 s, 180 s, 120 s, 300 s) są wpisane ręcznie ze źródłem.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Atrapa transportu i testy obecnego zachowania | Narzędzie + przypięte zachowanie SDK + pełna ścieżka „zawieszenie → Try again” | Kształt JSON odpowiedzi Responses API (potwierdzony próbą) |
| 2. Pusta odpowiedź = porażka | Czerwony test → sprawdzenie w `llm.py` → ręczne mutanty | Granica „biały tekst” vs „tekst ze spacjami” |
| 3. Znacznik tury liczy `Retry-After` | Granice co do sekundy, niezmiennik 300 s, wyścig, mutmut | Przepisanie istniejącego testu „2 min = wygasły”; nowe ID mutantów |
| 4. Wygasły znacznik analizy = porażka | Stan `analysis_failed`, strony i pełne ścieżki analizy | Nie zepsuć auto-wysyłki pierwszej analizy |
| 5. Cookbook i domknięcie | §6.3, notatka §6.6, status §3 | — |

**Prerequisites:** Phase 1 test-planu zakończona (CI, mutmut, rejestr przeżyć) — spełnione.
**Estimated effort:** ok. 3–4 sesje (faza 1 i 3 największe).

## Open Risks & Assumptions

- Zakładamy, że limit 120 s dla `Retry-After` w SDK (openai 3.24.0) się nie zmieni; test fazy 1 padnie, jeśli się zmieni, a wtedy trzeba zaktualizować `LLM_MAX_RETRY_AFTER_SECONDS`.
- Po awarii procesu w trakcie tury „Agent is typing…” trwa do 210 s zamiast 90 s — świadomy koszt decyzji P1.
- Limit proxy Railway (300 s bez danych) bywał zmieniany (marzec 2026); niezmiennik ustawień trzeba zaktualizować, jeśli Railway zmieni limit.

## Success Criteria (Summary)

- Przy zawieszeniu, błędzie, `Retry-After` i pustej odpowiedzi użytkownik widzi komunikat i „Try again”, a kliknięcie daje odpowiedź lub listę na stronie — dowiedzione testem całej ścieżki.
- Żywe wywołanie nigdy nie pokazuje „Try again”, a po awarii procesu znacznik wygasa w znanym, przetestowanym czasie.
- `uv run pytest`, ruff i obie bramki mutacyjne zielone, bez niewyjaśnionych przeżyć.
