# Waiting-path recovery (test-plan Phase 2, ryzyko #1) — plan implementacji

## Overview

Udowodnić testami, że gdy dostawca modelu wisi, zwraca błąd albo pusty wynik, użytkownik w skończonym czasie widzi komunikat i „Try again”, a ponowienie naprawdę uruchamia nowe wywołanie. Testy idą przez prawdziwe SDK OpenAI z atrapą na transporcie HTTP (granica SDK), a nie przez podmianę naszych funkcji. Przy okazji wchodzą trzy poprawki kodu, o których zdecydowano podczas planowania: znacznik tury uwzględnia `Retry-After`, pusta odpowiedź agenta jest porażką, a wygasły znacznik analizy daje „Try again” zamiast automatycznej, płatnej ponownej analizy.

## Current State Analysis

Pełne ugruntowanie: `context/changes/testing-waiting-path-recovery/research.md`. Najważniejsze:

- Ścieżka „błąd → komunikat → Try again → nowe wywołanie” jest pokryta testami, ale atrapy siedzą **nad** SDK: `FakeOpenAI` podmienia cały klient (`tests/test_llm.py:54-65`), `FakeGenerateTurn` / `FakeAnalyzeMistakes` podmieniają nasze funkcje (`tests/test_conversation_views.py:37-98`). Żaden test nie wykonuje pętli ponowień, timeoutów ani obsługi `Retry-After` w SDK.
- Znacznik tury żyje `LLM_TIMEOUT_SECONDS × (LLM_MAX_RETRIES + 1) + 30` = 90 s (`conversations/services.py:69-73`), a SDK przy 429/503 z `Retry-After` czeka do 120 s przed drugą próbą. OpenAI potwierdza, że wysyła `Retry-After` przy 429 i 503 (developers.openai.com/api/docs/guides/rate-limits, przykład 56 s; odczyt 2026-10-15). Dla 30 + 56 + 30 = 116 s znacznik wygasa w trakcie żywego wywołania, strona pokazuje „Try again”, a kliknięcie robi drugie płatne wywołanie.
- `AgentTurn.reply: str` przyjmuje `""` (`conversations/llm.py:104-106`). Pusta tura zapisuje się jako pusta bańka, bez komunikatu i bez „Try again” (`services.py:207-224`).
- Strona analizy po awarii procesu (znacznik ustawiony, `analysis_failed_at` puste) po wygaśnięciu znacznika spada do formularza z `data-auto-submit` (`conversations/templates/conversations/detail.html:61-82`), więc bez kliknięcia uruchamia nowe płatne wywołanie.
- Sześć przeżywających mutantów przekazanych do tej fazy (`scripts/mutation/accepted_survivors.md`: `_agent_turn_timeout` `_2/_3/_5/_6/_7`, `_clear_turn_marker` `_4`). Obecny test znacznika tury sprawdza tylko 0 s i 2 min (`tests/test_conversation_views.py:550-581`).
- Przyczyna incydentu Q2 (limit 90 s przy analizie trwającej ok. 165 s) nie jest wykrywalna atrapą; naprawiono ją ustawieniami w `dfe3e7d`.

## Desired End State

- Wspólna atrapa transportu (`tests/fake_provider.py` + fixture w `tests/conftest.py`) pozwala w kilku linijkach zagrać scenariusz dostawcy: zawieszenie, status z `Retry-After`, poprawna odpowiedź, pusta odpowiedź. Rejestruje zapytania i czasy, które SDK chciało przespać, a niczego nie czeka naprawdę.
- Testy całej ścieżki (widok → serwis → `llm.py` → SDK → atrapa transportu) w `tests/test_waiting_path.py` dowodzą sukcesu ponowienia stanem bazy, liczbą zapytań na transporcie i treścią strony, nigdy samym kodem HTTP.
- Znacznik tury żyje 210 s (najdłuższe czekanie SDK 180 s + 30 s zapasu), znacznik analizy 180 s; obie granice sprawdzone co do sekundy z oczekiwaną wartością wpisaną ręcznie i opisanym źródłem.
- Pusta albo biała odpowiedź agenta kończy się komunikatem i „Try again”, bez zapisu wiadomości.
- Wygasły znacznik analizy daje komunikat i „Try again” (bez auto-wysyłki i bez odświeżania); świeża strona bez znacznika dalej wysyła się sama.
- Wszystkie mutanty przekazane do Phase 2 są zabite albo mają aktualny wiersz w `accepted_survivors.md`; nowe ręczne mutanty dla pustej odpowiedzi są `killed`.
- `context/foundation/test-plan.md` §6.3 opisuje wzorzec, §6.6 ma notatkę fazy, §3 ma status fazy.

Weryfikacja: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run python scripts/mutation/manual_mutants.py` (kod 0), `uv run mutmut run` + `uv run mutmut results` bez niewyjaśnionych przeżyć.

### Key Discoveries:

- SDK usypia się między próbami przez `time.sleep(timeout)` (`.venv/lib/python3.14/site-packages/openai/_base_client.py:1239`). Podmiana `time.sleep` na rejestrator uruchamia prawdziwą pętlę ponowień bez czekania i pokazuje, ile SDK chciało czekać.
- Próba w scratchpadzie (2026-10-15, openai 3.24.0, httpx2 2.13.1) potwierdziła: `OpenAI(http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))` działa z `responses.parse(text_format=...)`; 503 + `retry-after: 56` → jeden sen 56,0 s i 2 zapytania; `httpx2.ReadTimeout` z transportu → 2 zapytania, sen ok. 0,4 s, `APITimeoutError`; `retry-after: 121` → **brak ponowienia**, od razu `RateLimitError`; `request.extensions["timeout"]` = `{'connect': 30, 'read': 30, 'write': 30, 'pool': 30}`.
- Minimalne ciało odpowiedzi Responses API, które SDK parsuje: `id`, `object: "response"`, `created_at`, `model`, `status: "completed"`, `output: [{type: "message", role: "assistant", status: "completed", id, content: [{type: "output_text", annotations: [], text: <JSON AgentTurn / MistakeReport>}]}]`, `parallel_tool_calls`, `tool_choice`, `tools`, `usage` z `input_tokens_details.cached_tokens` i `output_tokens_details.reasoning_tokens`.
- `settings_test.py` ustawia sztuczny `OPENAI_API_KEY` i nie nadpisuje timeoutów, więc `_get_client` (`conversations/llm.py:149-157`) działa w testach bez zmian; atrapę wstrzykujemy, podmieniając `conversations.llm.OpenAI` na wywołanie, które przekazuje dalej argumenty z `_get_client` i dokłada `http_client`.
- Testy serwisu tury żyją w `tests/test_conversation_views.py` (tam `FakeGenerateTurn`); wzorzec testu „porażka nie nadpisuje nowszej próby” jest w `tests/test_analysis.py:408-449`.
- Istniejący test `tests/test_conversation_views.py:557-581` zakłada wygaśnięcie znacznika tury po 2 min — po zmianie na 210 s musi zostać przepisany na nowe granice (faza 3).

## What We're NOT Doing

- Nie liczymy kosztu nieudanych, pustych ani spóźnionych wywołań — to ryzyko #4, test-plan Phase 4.
- Nie mierzymy realnego czasu odpowiedzi modelu (przyczyna incydentu Q2) — pomiar trafia jako zadanie do test-plan Phase 5 (eval z prawdziwym modelem); tutaj tylko niezmiennik ustawień względem limitu proxy Railway.
- Nie zmieniamy `LLM_MAX_RETRIES`, timeoutów ani effortu modelu.
- Nie przenosimy analizy poza żądanie HTTP i nie limitujemy liczby „Try again” (roadmap Q-07, zaakceptowane ryzyko MVP).
- Bez Playwright i bez testów obciążenia (test-plan §7). Spinner JS w trakcie POST zostaje poza zasięgiem testów.
- Nie dodajemy `conversations/llm.py` do `[tool.mutmut]`; nowe zachowanie w `llm.py` potwierdzamy ręcznymi mutantami.
- Nie zmieniamy test-plan §2 / §4 (strategia) — kandydaci do backportu trafiają do notatki fazy dla `/10x-test-plan --refresh`.
- Pusta lista błędów z analizy (`mistakes: []`) nie jest porażką — prompt wprost na nią pozwala.

## Implementation Approach

Najpierw infrastruktura i testy obecnego zachowania (faza 1, bez zmian kodu), bo każda kolejna faza używa atrapy transportu. Potem trzy poprawki, każda test-first: najpierw czerwony test z wyrocznią spoza kodu, potem minimalna zmiana, potem mutanty. Dwie warstwy (decyzja P5): atrapa transportu tam, gdzie liczy się zachowanie SDK (ponowienia, `Retry-After`, timeout, parsowanie) i cała droga do strony; hermetyczne testy serwisu z istniejącymi atrapami tam, gdzie liczy się tylko kolejność zdarzeń dwóch żądań (wyścig znacznika). Upływ czasu symulujemy znacznikiem w bazie albo parametrem `now` serwisów, jak dotąd.

## Critical Implementation Details

- **Podmiana `time.sleep`.** Patchuj `time.sleep` z biblioteki standardowej przez `monkeypatch` (moduł `time`, atrybut `sleep`), a nie prywatne `openai._base_client`. To globalne na czas testu, więc rejestrator zapisuje tylko liczby i nic nie usypia; asercje dotyczą tylko snów z pętli SDK.
- **„Zawieszenie” na transporcie.** Prawdziwe zawieszenie kończy się tym, że httpx po upływie limitu odczytu rzuca `ReadTimeout`. Atrapa rzuca go od razu, a test dodatkowo sprawdza, że każde zapytanie niosło `extensions["timeout"]["read"] == 30`. Dowodzi to, że prawdziwe zawieszenie zostałoby ucięte. Wymiar czasu (co widzą inne żądania w trakcie) sprawdzają testy granic znacznika, nie ten test.
- **Wyrocznie czasu wpisane ręcznie.** 210 s i 180 s stoją w testach jako liczby z docstringiem źródła (SDK: 2 próby × 30 s + 1 × 120 s `Retry-After`, odczytane z SDK i przypięte testem fazy 1; zapas 30 s — decyzja P3 z 2026-10-15), nigdy liczone wzorem z `services.py`.

## Faza 1: Atrapa transportu i testy obecnego zachowania

### Overview

Wspólne narzędzie do grania scenariuszy dostawcy na transporcie HTTP SDK oraz testy, które przypinają zachowanie SDK, na którym opiera się znacznik (ponowienia, `Retry-After`, limit 30 s), i jedną pełną ścieżkę „zawieszenie → Try again → odpowiedź”. Bez zmian kodu produkcyjnego — testy mają być zielone od razu (`/10x-implement`).

### Changes Required:

#### 1. Moduł atrapy transportu

**File**: `tests/fake_provider.py` (nowy)

**Intent**: Jedno miejsce, które buduje klienta SDK z `httpx2.MockTransport`, odtwarza z kolejki zaplanowane odpowiedzi dla kolejnych zapytań i rejestruje, co się wydarzyło. Dzięki temu każdy test opisuje scenariusz dostawcy, a nie szczegóły HTTP.

**Contract**: Obiekt-scenariusz z metodami dodającymi do kolejki kolejne odpowiedzi: zawieszenie (`ReadTimeout`), status z opcjonalnym `retry-after` (np. 429, 503), poprawna tura (`reply`, `end_conversation`), poprawna analiza (pola `MistakeReport`). Zapisuje listę zapytań (z `extensions["timeout"]`) i listę czasów snu. Pusta kolejka przy kolejnym zapytaniu = błąd testu, a nie cicha odpowiedź. Ciało odpowiedzi zgodne z kształtem z „Key Discoveries”. Usage stały i jawny (np. 1200 / 1000 cached / 40), żeby testy innych faz mogły na nim polegać.

#### 2. Fixture

**File**: `tests/conftest.py` (nowy)

**Intent**: Fixture `fake_provider`, która podmienia `conversations.llm.OpenAI` na wywołanie przekazujące dalej argumenty z `_get_client` (klucz, `base_url`, `timeout`, `max_retries` z ustawień) i dokładające `http_client` z atrapą, oraz podmienia `time.sleep` na rejestrator.

**Contract**: `fake_provider` zwraca obiekt-scenariusz z pkt 1. Ustawienia timeoutu i ponowień płyną z Django settings bez zmian — fixture ich nie nadpisuje.

#### 3. Testy granicy SDK w `llm.py`

**File**: `tests/test_llm.py`

**Intent**: Przypiąć zachowanie, na którym opiera się długość znacznika i komunikat dla użytkownika. Oczekiwane wartości z dokumentacji SDK / OpenAI, nie z naszego kodu.

**Contract**: Testy (nazwy orientacyjne):
- tura: dwa zawieszenia → `LLMError`, dokładnie 2 zapytania, każde z limitem odczytu 30 s;
- tura: 503 z `retry-after: 56`, potem poprawna odpowiedź → wynik z tekstem odpowiedzi, 2 zapytania, jeden sen 56 s;
- tura: 429 z `retry-after: 120`, potem odpowiedź → jeden sen 120 s (górna granica respektowana); 429 z `retry-after: 121` → `LLMError` po 1 zapytaniu, bez snu (SDK nie ponawia ponad limit — ta liczba 120 jest podstawą wzoru znacznika w fazie 3; jeśli przyszła wersja SDK ją zmieni, ten test padnie);
- analiza: zawieszenie → `LLMError` po 1 zapytaniu z limitem odczytu 150 s (brak ponowień analizy).

#### 4. Pełna ścieżka tury przez widok

**File**: `tests/test_waiting_path.py` (nowy)

**Intent**: Jeden test całej drogi dla ryzyka #1 bez atrapy nad SDK: wiadomość użytkownika, dostawca wisi przy obu próbach, strona pokazuje komunikat i „Try again”, kliknięcie robi nowe zapytanie, a odpowiedź pojawia się na stronie.

**Contract**: Asercje sukcesu: nowa wiadomość agenta z tekstem z atrapy w bazie, `awaiting_agent_reply` fałszywe, `agent_turn_started_at` puste, liczba zapytań na transporcie wzrosła z 2 do 3, tekst odpowiedzi na stronie, brak „Try again” na stronie. Asercje porażki (przed kliknięciem): wiadomość użytkownika zapisana, brak wiadomości agenta, komunikat „could not reply” i formularz „Try again”. Żadnej asercji opartej wyłącznie na kodzie HTTP. Fixture'y użytkownika / rozmowy wzorowane na `tests/test_conversation_views.py`.

### Success Criteria:

#### Automated Verification:

- Nowe testy z `tests/test_llm.py` i `tests/test_waiting_path.py` przechodzą: `uv run pytest tests/test_llm.py tests/test_waiting_path.py`
- Cały zestaw przechodzi bez sieci i bez klucza: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Test `retry-after: 121` pada, gdy w atrapie zmieni się nagłówek na `120` (ręczne sprawdzenie wrażliwości testu, cofnięte przed commitem)

#### Manual Verification:

- Przegląd `tests/fake_provider.py`: scenariusz czyta się jak opis zachowania dostawcy, bez szczegółów HTTP w testach

**Implementation Note**: Po zielonej weryfikacji automatycznej zatrzymaj się na ręczne potwierdzenie przed fazą 2.

---

## Faza 2: Pusta odpowiedź agenta = porażka

### Overview

Odpowiedź agenta pusta albo złożona z samych białych znaków jest traktowana jak każda inna nieużyteczna odpowiedź: `LLMError`, nic się nie zapisuje, strona pokazuje komunikat i „Try again” (decyzja P2). Test-first (`/10x-tdd`). Pierwszy czerwony test: „gdy dostawca zwraca `reply` z samych spacji, strona pokazuje komunikat i „Try again”, a w rozmowie nie ma wiadomości agenta”.

### Changes Required:

#### 1. Testy

**File**: `tests/test_llm.py`, `tests/test_waiting_path.py`

**Intent**: Wyrocznia: wytyczna ryzyka #1 w `context/foundation/test-plan.md` §2 („pusty wynik → komunikat i Try again”) + decyzja P2.

**Contract**:
- `llm.py`, sparametryzowany jednym testem: `reply` równe `""`, `" "`, `"\n\t "` → `LLMError`; niepusty tekst z otaczającymi spacjami (np. `" Hallo "`) dalej przechodzi (granica: biały tekst vs tekst z białymi znakami);
- ścieżka przez widok: pusta odpowiedź przy wiadomości → brak wiadomości agenta w bazie, `awaiting_agent_reply` prawdziwe, znacznik pusty, komunikat i „Try again” na stronie; kliknięcie z niepustą odpowiedzią w kolejce → odpowiedź zapisana i widoczna, 2 zapytania;
- pusta odpowiedź przy starcie rozmowy → rozmowa czeka na ponowienie (jak `LLMError` dziś).

#### 2. Sprawdzenie w granicy LLM

**File**: `conversations/llm.py`

**Intent**: Po sparsowaniu tury odrzucić odpowiedź bez treści tak samo jak brak `output_parsed`: zalogować sam fakt (bez treści rozmowy) i rzucić `LLMError`.

**Contract**: `generate_turn` rzuca `LLMError`, gdy `parsed.reply.strip() == ""`. `AgentTurn` i `TurnResult` bez zmian. Tekst odpowiedzi zapisywany dalej bez przycinania (zmienia się tylko decyzja „pusty / niepusty”).

#### 3. Ręczne mutanty

**File**: `scripts/mutation/manual_mutants.py`

**Intent**: Dowód, że nowe testy łapią zepsucie (decyzja P7; `llm.py` jest poza mutmut).

**Contract**: Dwa nowe mutanty z `expected="killed"`: (a) usunięte sprawdzenie pustej odpowiedzi, (b) sprawdzenie bez `.strip()` (przepuszcza same spacje). Wzorzec dodawania: test-plan §6.1 pkt 4.

### Success Criteria:

#### Automated Verification:

- Najpierw czerwone: nowe testy padają na kodzie sprzed zmiany w `llm.py`: `uv run pytest tests/test_llm.py tests/test_waiting_path.py`
- Po zmianie wszystkie testy przechodzą: `uv run pytest`
- Nowe ręczne mutanty są `killed`, a lista zgodna z oczekiwaniami: `uv run python scripts/mutation/manual_mutants.py` (kod 0)
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

**Implementation Note**: Po zielonej weryfikacji zatrzymaj się na potwierdzenie przed fazą 3.

---

## Faza 3: Znacznik tury uwzględnia `Retry-After`

### Overview

Znacznik „w toku” ma żyć dokładnie 30 s dłużej niż najdłuższe możliwe czekanie SDK, łącznie z `Retry-After` (decyzje P1, P3): tura 30 × 2 + 1 × 120 + 30 = 210 s, analiza 150 × 1 + 0 × 120 + 30 = 180 s (bez zmiany). Do tego niezmiennik ustawień względem proxy Railway (P4) i test wyścigu znacznika. Test-first (`/10x-tdd`). Pierwszy czerwony test: „znacznik tury ustawiony 209 s temu dalej blokuje „Try again” i pokazuje „Agent is typing…””.

### Changes Required:

#### 1. Testy granic i niezmiennika

**File**: `tests/test_conversation_views.py`, `tests/test_analysis.py`, `tests/test_waiting_path.py`

**Intent**: Zabić mutanty `_agent_turn_timeout` `_2/_3/_5/_6/_7` wyrocznią spoza kodu i chronić ustawienia przed ponowieniem incydentu klasy Q2 względem platformy.

**Contract**:
- serwis (`agent_turn_in_progress` z parametrem `now`): znacznik w wieku `210 s − 1 µs` → w toku; dokładnie 210 s → nie w toku. Analogicznie `analysis_in_progress`: `180 s − 1 µs` / 180 s przy domyślnych ustawieniach (nie przy nadpisaniu z `tests/test_analysis.py:95-96`). Docstring podaje źródło liczb (patrz „Critical Implementation Details”);
- przepisanie `tests/test_conversation_views.py:557-581`: zamiast „2 min = wygasły” — strona przy znaczniku sprzed ok. 200 s pokazuje „Agent is typing…” i odświeżanie, a „Try again” jest odrzucane bez wywołania; przy znaczniku sprzed ok. 220 s pokazuje „Try again”, a kliknięcie robi nowe wywołanie;
- niezmiennik ustawień (`tests/test_waiting_path.py`): najdłuższe czekanie zapytania POST policzone z bieżących ustawień i wpisanego ręcznie limitu SDK 120 s (tura: timeout × próby + ponowienia × 120; analiza: tak samo) jest < 300 s (proxy Railway: docs.railway.com, specs-and-limits, odczyt 2026-10-15) — test pada, gdy ktoś podniesie timeout lub liczbę ponowień ponad limit platformy;
- pełna ścieżka przez transport: 503 z `retry-after: 56`, potem odpowiedź → odpowiedź zapisana i widoczna, sen 56 s, znacznik pusty, brak „Try again”.

#### 2. Test wyścigu znacznika (hermetyczny)

**File**: `tests/test_conversation_views.py`

**Intent**: Zabić `_clear_turn_marker__mutmut_4` i przypiąć „pierwsza odpowiedź wygrywa, spóźniona nie zapisuje się drugi raz” dla tury. Wzorzec: `tests/test_analysis.py:408-449`.

**Contract**: Żądanie A startuje turę w chwili T; w trakcie jego wywołania (hook w `FakeGenerateTurn`) w bazie pojawia się nowszy znacznik T + 211 s (żądanie B przejęło wygasły znacznik i jeszcze czeka). Przypadek porażki A: po `LLMError` znacznik B zostaje nietknięty, a strona dalej pokazuje „Agent is typing…”. Przypadek sukcesu A: odpowiedź A zapisana raz, znacznik B nietknięty; gdy potem kończy się wywołanie B, nie powstaje druga wiadomość agenta.

#### 3. Wzór znacznika i ustawienie

**File**: `talkaitive/settings.py`, `conversations/services.py`

**Intent**: Znacznik dłuższy od najdłuższego czekania SDK łącznie z `Retry-After`, żeby żywe wywołanie nigdy nie wyglądało na martwe.

**Contract**: Nowe ustawienie `LLM_MAX_RETRY_AFTER_SECONDS = 120` obok timeoutów (`settings.py:62-75`), stała, nie zmienna środowiskowa. Komentarz wskazuje `MAX_RETRY_AFTER_DELAY` w SDK i test fazy 1, który ją przypina. `_agent_turn_timeout` i `_analysis_timeout`: `timeout × (ponowienia + 1) + ponowienia × LLM_MAX_RETRY_AFTER_SECONDS + 30`. Komentarze przy obu funkcjach i przy ustawieniach (`settings.py:68-73`) zaktualizowane. Analiza przy 0 ponowień zostaje na 180 s.

#### 4. Mutacje i rejestr przeżyć

**File**: `scripts/mutation/accepted_survivors.md`

**Intent**: Domknąć mutanty przekazane do Phase 2.

**Contract**: Po usunięciu `mutants/`: `uv run mutmut run` i `uv run mutmut results`. Wiersze `przekazany do test-plan Phase 2` usunięte dla zabitych mutantów. Nowe przeżycia w `_agent_turn_timeout` / `_analysis_timeout` / `_clear_turn_marker` sklasyfikowane: człony mnożone przez `LLM_ANALYSIS_MAX_RETRIES = 0` w analizie jako `równoważny` z warunkiem powrotu (jak dzisiejszy wiersz `_analysis_timeout__mutmut_6`, zaktualizowany do nowych identyfikatorów). Identyfikatory mutantów zmienią się po zmianie funkcji — klasyfikuj według diffu (`uv run mutmut show <nazwa>`), nie według starych numerów.

### Success Criteria:

#### Automated Verification:

- Najpierw czerwone: test granicy 209 s / 210 s i test strony przy ok. 200 s padają na kodzie sprzed zmiany: `uv run pytest tests/test_conversation_views.py`
- Po zmianie wszystkie testy przechodzą: `uv run pytest`
- mutmut bez niewyjaśnionych przeżyć w `_agent_turn_timeout`, `_analysis_timeout`, `_clear_turn_marker`: `uv run mutmut run` + `uv run mutmut results`
- Ręczne mutanty zgodne z oczekiwaniami: `uv run python scripts/mutation/manual_mutants.py` (kod 0)
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

**Implementation Note**: Po zielonej weryfikacji zatrzymaj się na potwierdzenie przed fazą 4.

---

## Faza 4: Wygasły znacznik analizy = porażka

### Overview

Gdy proces padł w trakcie analizy (znacznik ustawiony, brak wyniku i brak `analysis_failed_at`), po wygaśnięciu znacznika strona pokazuje komunikat i „Try again” zamiast sama wysyłać nową, płatną analizę (decyzja P6). Strona bez żadnej próby dalej wysyła się sama. Test-first (`/10x-tdd`). Pierwszy czerwony test: „strona zakończonej rozmowy ze znacznikiem analizy sprzed 181 s pokazuje komunikat i „Try again” i nie ma formularza z `data-auto-submit`”.

### Changes Required:

#### 1. Testy stanów strony i ponowienia

**File**: `tests/test_conversation_views.py`, `tests/test_waiting_path.py`

**Intent**: Przypiąć decyzję P6 i zamknąć luki z researchu (strona po wygaśnięciu znacznika analizy; ponowienie analizy przez widok kończące się listą).

**Contract**:
- znacznik analizy sprzed ok. 190 s, brak wyniku i porażki → komunikat „could not prepare your list of mistakes” i „Try again”; brak `data-auto-submit`; brak `meta refresh`;
- znacznik sprzed ok. 170 s → spinner i `meta refresh` (bez zmian);
- brak znacznika i porażki → formularz z `data-auto-submit` (bez zmian; nowa analiza po zakończeniu rozmowy dalej rusza sama);
- pełna ścieżka przez transport: wygasły znacznik → kliknięcie „Try again” → 1 nowe zapytanie, `analyzed_at` ustawione, `analysis_failed_at` puste, pozycje listy z atrapy widoczne na stronie, brak „Try again”;
- pełna ścieżka: zawieszenie analizy → komunikat i „Try again” → kliknięcie z poprawną odpowiedzią w kolejce → lista na stronie (2 zapytania łącznie).

#### 2. Stan „analiza nieudana”

**File**: `conversations/services.py`, `conversations/views.py`, `conversations/templates/conversations/detail.html`

**Intent**: Jedno źródło prawdy dla „analiza się nie udała”: zapisana porażka albo znacznik, który wygasł bez wyniku. Strona wybiera stan na jego podstawie, bez zapisu do bazy przy GET.

**Contract**: Nowa funkcja serwisu `analysis_failed(conversation, now) -> bool`: prawda, gdy rozmowa nie ma wyniku, znacznik nie jest ważny i (`analysis_failed_at` ustawione albo `analysis_started_at` ustawione). Widok `conversation_detail` przekazuje ją do szablonu, a gałąź porażki w `detail.html` używa jej zamiast samego `conversation.analysis_failed_at`. Kolejność gałęzi w szablonie bez zmian („gotowe” → „w toku” → „porażka” → auto-wysyłka). `analyze_conversation` bez zmian: wygasły znacznik już dziś pozwala ruszyć (`tests/test_analysis.py:254-269`).

### Success Criteria:

#### Automated Verification:

- Najpierw czerwone: test strony z wygasłym znacznikiem pada na kodzie sprzed zmiany: `uv run pytest tests/test_conversation_views.py`
- Po zmianie wszystkie testy przechodzą: `uv run pytest`
- mutmut bez niewyjaśnionych przeżyć w `analysis_failed`: `uv run mutmut run` + `uv run mutmut results`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Lokalnie (`uv run python manage.py runserver`): zakończona rozmowa z ręcznie ustawionym w shellu Django znacznikiem analizy sprzed 4 min pokazuje komunikat i „Try again”, strona sama się nie wysyła i nie odświeża

**Implementation Note**: Po zielonej weryfikacji zatrzymaj się na potwierdzenie przed fazą 5.

---

## Faza 5: Cookbook i domknięcie fazy w test-plan

### Overview

Zapisać wzorzec tak, żeby następny test dla granicy LLM powstał bez czytania tego planu (`/10x-implement`).

### Changes Required:

#### 1. Cookbook §6.3

**File**: `context/foundation/test-plan.md`

**Intent**: Zastąpić „TBD — see §3 Phase 2” wzorcem.

**Contract**: §6.3: lokalizacja (`tests/fake_provider.py`, fixture `fake_provider`, `tests/test_waiting_path.py`), kiedy atrapa transportu (zachowanie SDK, cała ścieżka do strony), a kiedy `FakeGenerateTurn` / `FakeAnalyzeMistakes` (kolejność zdarzeń dwóch żądań), jak symulować czas (znacznik w bazie, parametr `now`), zasada „sukces = stan bazy + liczba zapytań + treść strony, nigdy sam kod HTTP”, testy referencyjne z nazwami.

#### 2. Notatka fazy, status i kandydaci do backportu

**File**: `context/foundation/test-plan.md`

**Intent**: Zapis tego, czego faza nauczyła, i rzeczy dla `/10x-test-plan --refresh`.

**Contract**: §6.6: 2–3 linie (np. `Retry-After` z OpenAI do 120 s skracał ważność znacznika; pusta odpowiedź zapisywała się jako sukces; pomiar realnego czasu analizy względem limitu → zadanie dla Phase 5). §3: status Phase 2 zgodnie z konwencją kolumny Status. Kandydaci do backportu w §2 / §4 (z `research.md`, sekcja „Kandydaci do backportu”) wymienieni w notatce §6.6 jako do przeniesienia przez `/10x-test-plan --refresh`, bez edycji §2 / §4.

### Success Criteria:

#### Automated Verification:

- W §6.3 nie ma już „TBD”: `grep -n "TBD — see §3 Phase 2" context/foundation/test-plan.md` nic nie zwraca
- Pełna bramka lokalna zielona: `uv run pytest && uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- §6.3 czyta się jako samodzielna instrukcja: nowy test dla dostawcy da się napisać, czytając tylko §6.3 i testy referencyjne

---

## Testing Strategy

### Unit Tests:

- Granice `agent_turn_in_progress` / `analysis_in_progress` / `analysis_failed` z parametrem `now` (co do mikrosekundy na brzegu).
- Niezmiennik ustawień względem 300 s proxy Railway.

### Integration Tests:

- Klient testowy Django + prawdziwa baza (SQLite) + prawdziwe SDK + atrapa transportu: zawieszenie → Try again → odpowiedź; 503 + `Retry-After` → odpowiedź; pusta odpowiedź → Try again → odpowiedź; zawieszenie analizy → Try again → lista; wygasły znacznik analizy → Try again → lista.
- Hermetyczne testy serwisu z `FakeGenerateTurn` dla wyścigu dwóch żądań.

### Manual Testing Steps:

1. Faza 4: wygasły znacznik analizy w lokalnej bazie → strona z „Try again”, bez auto-wysyłki.
2. Opcjonalnie (wbudowana przeglądarka): przy wiadomości z niedziałającym kluczem strona kończy się komunikatem i „Try again”, a nie wiecznym spinnerem.

## Performance Considerations

Najdłuższe czekanie POST tury rośnie formalnie do 180 s (tylko przy `Retry-After` 120 s od dostawcy), dalej poniżej 300 s Railway; wątek gunicorna jest zajęty tak długo jak dziś przy tym samym zachowaniu dostawcy. Po awarii procesu w trakcie tury „Agent is typing…” trwa do 210 s zamiast 90 s — świadomy koszt decyzji P1.

## Migration Notes

Brak migracji bazy: nowe ustawienie jest stałą, a stan „analiza nieudana” jest wyliczany z istniejących pól. Znaczniki ustawione przed wdrożeniem po prostu zaczną żyć według nowego wzoru.

## References

- Research: `context/changes/testing-waiting-path-recovery/research.md`
- Plan testów: `context/foundation/test-plan.md` (§2 ryzyko #1, §3 Phase 2, §6.1 wzorzec mutacji)
- Rejestr przeżyć: `scripts/mutation/accepted_survivors.md`
- Wzorzec wyścigu: `tests/test_analysis.py:408-449`
- Pętla ponowień SDK: `.venv/lib/python3.14/site-packages/openai/_base_client.py:1140-1239`
- OpenAI Rate limits (`Retry-After` przy 429 / 503): https://developers.openai.com/api/docs/guides/rate-limits (odczyt 2026-10-15)
- Railway limity HTTP: docs.railway.com/networking/public-networking/specs-and-limits (odczyt 2026-10-15, za researchem)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Atrapa transportu i testy obecnego zachowania

#### Automated

- [x] 1.1 Nowe testy z `tests/test_llm.py` i `tests/test_waiting_path.py` przechodzą: `uv run pytest tests/test_llm.py tests/test_waiting_path.py` — 72ffd3e
- [x] 1.2 Cały zestaw przechodzi bez sieci i bez klucza: `uv run pytest` — 72ffd3e
- [x] 1.3 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 72ffd3e
- [x] 1.4 Test `retry-after: 121` pada, gdy w atrapie zmieni się nagłówek na `120` (ręczne sprawdzenie wrażliwości testu, cofnięte przed commitem) — 72ffd3e

#### Manual

- [x] 1.5 Przegląd `tests/fake_provider.py`: scenariusz czyta się jak opis zachowania dostawcy, bez szczegółów HTTP w testach — 72ffd3e

### Phase 2: Pusta odpowiedź agenta = porażka

#### Automated

- [x] 2.1 Najpierw czerwone: nowe testy padają na kodzie sprzed zmiany w `llm.py`: `uv run pytest tests/test_llm.py tests/test_waiting_path.py`
- [x] 2.2 Po zmianie wszystkie testy przechodzą: `uv run pytest`
- [x] 2.3 Nowe ręczne mutanty są `killed`, a lista zgodna z oczekiwaniami: `uv run python scripts/mutation/manual_mutants.py` (kod 0)
- [x] 2.4 Lint i format: `uv run ruff check . && uv run ruff format --check .`

### Phase 3: Znacznik tury uwzględnia `Retry-After`

#### Automated

- [ ] 3.1 Najpierw czerwone: test granicy 209 s / 210 s i test strony przy ok. 200 s padają na kodzie sprzed zmiany: `uv run pytest tests/test_conversation_views.py`
- [ ] 3.2 Po zmianie wszystkie testy przechodzą: `uv run pytest`
- [ ] 3.3 mutmut bez niewyjaśnionych przeżyć w `_agent_turn_timeout`, `_analysis_timeout`, `_clear_turn_marker`: `uv run mutmut run` + `uv run mutmut results`
- [ ] 3.4 Ręczne mutanty zgodne z oczekiwaniami: `uv run python scripts/mutation/manual_mutants.py` (kod 0)
- [ ] 3.5 Lint i format: `uv run ruff check . && uv run ruff format --check .`

### Phase 4: Wygasły znacznik analizy = porażka

#### Automated

- [ ] 4.1 Najpierw czerwone: test strony z wygasłym znacznikiem pada na kodzie sprzed zmiany: `uv run pytest tests/test_conversation_views.py`
- [ ] 4.2 Po zmianie wszystkie testy przechodzą: `uv run pytest`
- [ ] 4.3 mutmut bez niewyjaśnionych przeżyć w `analysis_failed`: `uv run mutmut run` + `uv run mutmut results`
- [ ] 4.4 Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [ ] 4.5 Lokalnie (`uv run python manage.py runserver`): zakończona rozmowa z ręcznie ustawionym w shellu Django znacznikiem analizy sprzed 4 min pokazuje komunikat i „Try again”, strona sama się nie wysyła i nie odświeża

### Phase 5: Cookbook i domknięcie fazy w test-plan

#### Automated

- [ ] 5.1 W §6.3 nie ma już „TBD”: `grep -n "TBD — see §3 Phase 2" context/foundation/test-plan.md` nic nie zwraca
- [ ] 5.2 Pełna bramka lokalna zielona: `uv run pytest && uv run ruff check . && uv run ruff format --check .`

#### Manual

- [ ] 5.3 §6.3 czyta się jako samodzielna instrukcja: nowy test dla dostawcy da się napisać, czytając tylko §6.3 i testy referencyjne
