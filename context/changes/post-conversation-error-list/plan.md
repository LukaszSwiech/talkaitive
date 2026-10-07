# Lista błędów po zakończeniu rozmowy (S-02) — Implementation Plan

## Overview

Po zakończeniu rozmowy (przycisk „End”, pożegnanie agenta albo dzienny limit) użytkownik widzi pod transkryptem listę swoich błędów z tej rozmowy: kategoria (Grammar / Vocabulary / Word order), fragment błędny → poprawny, oryginalne zdanie i jedno zdanie wyjaśnienia po angielsku. Błędy wykrywa jedno osobne wywołanie modelu nad całym transkryptem (kierunek ustalony w S-01), uruchamiane jako osobny krok po zakończeniu rozmowy. Wynik zapisujemy w nowym modelu `Mistake` (dane per użytkownik), żeby S-03 mogło z nich korzystać.

Realizuje FR-008 i część „po zakończeniu użytkownik widzi listę błędów” z US-01.

## Current State Analysis

- S-01 nie wykrywa ani nie zapisuje błędów. Tura agenta zwraca tylko `AgentTurn{reply, end_conversation}` (`conversations/llm.py:57-59`). Prompt rozmowy już nazywa te same 3 kategorie i pomija literówki/interpunkcję (`conversations/llm.py:35-40`).
- Kierunek z S-01: po zakończeniu jedno osobne wywołanie analizuje cały transkrypt i zwraca błędy w JSON (`context/archive/2026-10-05-first-corrected-conversation/plan.md:42`, `plan-brief.md:28-29`).
- Modele: `Conversation(UserOwned)` z `status`, `end_reason` (user / agent_goodbye / daily_limit), `ended_at`, znacznikiem `agent_turn_started_at` (`conversations/models.py:8-54`); `Message` bez własnego `user`, z `cost_usd` na turach agenta (`conversations/models.py:57-79`). Ostatnia migracja to `0002`.
- Wszystkie trzy drogi zakończenia przechodzą przez `services.end_conversation` (`conversations/services.py:198-205`), ale dwie (pożegnanie, limit) działają wewnątrz transakcji z blokadą wiersza (`conversations/services.py:166-171`, `:192-195`), a w tym module model nigdy nie jest wołany w transakcji (`conversations/services.py:3-8`).
- Po każdym zakończeniu użytkownik ląduje na `conversation_detail` (`conversations/views.py:80-104`); stan „ended” pokazuje tylko komunikat i link (`conversations/templates/conversations/detail.html:57-63`).
- Budżet sumuje wyłącznie `Message.cost_usd` (`conversations/budget.py:58-63`); `is_exhausted` i `is_final_turn` opierają się na `spent_today` (`conversations/budget.py:66-106`).
- Brak zadań w tle; gunicorn `--timeout 120`, 2 workery × 4 wątki (`context/deployment/web-settings.json:7`). Obecny klient: 30 s × 2 próby (`talkaitive/settings.py:62-63`).
- Wzorzec spinnera i blokady przycisków: `data-waits-for-agent` + skrypt w `accounts/templates/base.html:41-76`; strona w toku odświeża się co 5 s przez `<meta http-equiv="refresh">` (`detail.html:5-8`).
- Testy: SDK podmieniany w `tests/test_llm.py:16-54` (`FakeResponses.parse`, `make_response`), `generate_turn` podmieniany w serwisie w `tests/test_conversation_views.py:36-62` (działa, bo `services.py:19` importuje funkcję po nazwie).

## Desired End State

- Po zakończeniu rozmowy dowolną z trzech dróg strona rozmowy pokazuje pod transkryptem spinner „Preparing your list of mistakes…”, sama wysyła POST na `conversations/<pk>/analysis/` (bez JS — przycisk „Show my mistakes”), a po chwili pokazuje listę.
- Lista jest chronologiczna (wg pierwszego wystąpienia). Każda pozycja: etykieta kategorii, `wrong → correct`, „×N” gdy N > 1, oryginalne zdanie, jedno zdanie wyjaśnienia. Brak błędów → „No mistakes found in this conversation.”
- Analiza odbywa się raz na rozmowę; odświeżenie, podwójne kliknięcie ani równoległa karta nie uruchamiają drugiego płatnego wywołania.
- Gdy analiza się nie powiedzie, strona pokazuje komunikat i „Try again” (bez automatycznego ponawiania).
- Koszt analizy wlicza się do dziennego wydatku użytkownika, ale analiza rusza zawsze — także po rozmowie zakończonej limitem.
- Błędy należą do użytkownika (`UserOwned`), inny użytkownik dostaje 404, nic nie trafia do admina, a usunięcie użytkownika lub rozmowy usuwa jej błędy.

### Key Discoveries:

- `conversations/services.py:41-64` — wzorzec znacznika „w toku” z wygasaniem (`_agent_turn_timeout`, `_mark_turn_started`, `_clear_turn_marker`) do skopiowania dla analizy.
- `conversations/services.py:140-171` — wzorzec „sprawdź pod blokadą → wywołaj model poza transakcją → zapisz pod blokadą, jeśli wynik nadal potrzebny”.
- `conversations/llm.py:126-156` — mapowanie `APIError` / `ValidationError` / `output_parsed is None` / brak `usage` na `LLMError`, bez treści rozmowy w logach.
- `conversations/budget.py:24-39` — `turn_cost` liczy koszt z tokenów i działa też dla analizy (ten sam model).
- `tests/test_ownership.py:47-52` — rejestr admina dopuszcza tylko `User` i `Group`.
- Nazwa `ConversationError` jest zajęta przez wyjątek w `conversations/services.py:28`, dlatego model błędu nazywa się `Mistake`.

## What We're NOT Doing

- Wykrywania błędów w trakcie rozmowy (per tura) — tura zostaje `{reply, end_conversation}`.
- Pamięci między rozmowami, wyboru błędów do kolejnej rozmowy ani normalizacji błędów do „zagadnień” — to S-03.
- Historii rozmów, linków do starych list z `/` ani edycji błędów (PRD Non-Goals).
- Analizy rozmów, których strona po zakończeniu nie została otwarta (np. karta zamknięta w trakcie ostatniej tury agenta) — takie rozmowy mogą na zawsze zostać z `analyzed_at IS NULL`, więc S-03 musi to obsłużyć. Poza zakresem MVP: w przyszłości planowana jest osobna strona do analizy, na której użytkownik będzie miał wgląd we wszystkie swoje rozmowy.
- Rezerwowania budżetu pod analizę — `is_final_turn` i `is_exhausted` zostają bez zmian (poza tym, że `spent_today` widzi koszt analiz).
- Literówek, wielkości liter i interpunkcji jako błędów (chyba że zmieniają sens) — ta sama reguła co w rozmowie.
- Scalania „prawie identycznych” błędów albo błędów z tą samą regułą — scalamy tylko identyczne pary.
- Osobnego (tańszego) modelu do analizy, zadań w tle, htmx i streamingu.
- Zmian w ustawieniach usługi `web` na Railway (`context/deployment/web-settings.json` bez zmian).

## Implementation Approach

Analiza to osobny krok, nie część zakończenia. `end_conversation` zostaje szybkie i niezmienione; strona zakończonej rozmowy sama inicjuje POST `conversation_analyze`. Serwis `analyze_conversation` powtarza wzorzec tur z S-01: pod blokadą sprawdza, że rozmowa jest zakończona, nieprzeanalizowana i nieanalizowana właśnie teraz, ustawia znacznik; poza transakcją woła `llm.analyze_mistakes`; pod blokadą zapisuje `Mistake` (po scaleniu i posortowaniu w kodzie), koszt i `analyzed_at`. Porażka ustawia `analysis_failed_at`, co wyłącza auto-wysyłkę (inaczej strona ponawiałaby płatne wywołanie w pętli) i pokazuje „Try again”.

Model zwraca dla każdego błędu numer wiadomości ucznia, więc kolejność chronologiczną i scalanie „×N” wylicza deterministycznie kod, a nie model. Analiza używa tego samego `LLM_MODEL` z osobnym reasoning effort (domyślnie `high`) i osobnym, krótkim limitem czasu (świadomy wybór UX, nie wymóg serwera — patrz „Timing & lifecycle”).

## Critical Implementation Details

**State sequencing** — szablon zakończonej rozmowy rozstrzyga stany w tej kolejności: przeanalizowana (lista) → analiza w toku (spinner + odświeżanie) → nieudana (błąd + „Try again”) → nierozpoczęta (auto-wysyłka). „W toku” musi być przed „nieudana”, bo „Try again” po porażce znowu ustawia znacznik; auto-wysyłka nigdy nie może się pojawić przy ustawionym `analysis_failed_at`.

**Timing & lifecycle** — znacznik analizy wygasa po `LLM_ANALYSIS_TIMEOUT_SECONDS × (LLM_ANALYSIS_MAX_RETRIES + 1) + 30` s (jak `_agent_turn_timeout`). 90 s przy 0 ponowień to świadomy wybór UX (krótkie czekanie, tania porażka naprawiana przez „Try again”), a nie limit serwera: przy `--threads 4` gunicorn działa jako gthread i `--timeout 120` nie ogranicza pojedynczego żądania; realnym sufitem jest proxy Railway — 5 min bez przesyłu danych (`context/foundation/infrastructure.md:72`). Wynik, który przyszedł, gdy rozmowa jest już przeanalizowana (równoległe żądanie po wygaśnięciu znacznika), jest odrzucany i niezliczany — tak jak spóźniona tura w S-01.

## Phase 1: Model danych i budżet

### Overview

Nowy model `Mistake`, pola stanu analizy w `Conversation`, migracja `0003` i wliczanie kosztu analiz do `spent_today`.

### Changes Required:

#### 1. Model `Mistake` i pola analizy

**File**: `conversations/models.py`

**Intent**: Dodać trwały zapis błędów jednej rozmowy jako dane użytkownika (gotowe dla S-03 i S-04) oraz stan analizy na rozmowie, potrzebny do jednorazowości, spinnera i „Try again”.

**Contract**:
- `Conversation`: `analysis_started_at` (DateTime, null) — znacznik „w toku”; `analysis_failed_at` (DateTime, null) — ostatnia porażka; `analyzed_at` (DateTime, null) — analiza zakończona (też przy 0 błędów); `analysis_cost_usd` (Decimal(10,6), default 0). Komentarze w stylu istniejących pól.
- `Mistake(UserOwned)`: `conversation` (FK → `Conversation`, CASCADE, `related_name="mistakes"`), `position` (PositiveInteger, kolejność na liście od 1), `category` (TextChoices `Category`: `grammar`/„Grammar”, `vocabulary`/„Vocabulary”, `word_order`/„Word order”), `wrong`, `correct`, `sentence`, `explanation` (TextField), `occurrences` (PositiveInteger, default 1), `created_at`. `Meta.ordering = ["position", "id"]`. `user` zawsze równy `conversation.user` (ustawia serwis).
- Nie rejestrujemy `Mistake` w adminie.

#### 2. Migracja

**File**: `conversations/migrations/0003_*.py`

**Intent**: Wygenerowana przez `makemigrations`; same pola nullable/z domyślną wartością i nowa tabela, więc bezpieczna dla istniejących rozmów w produkcji.

**Contract**: jedna migracja zależna od `0002_conversation_agent_turn_started_at`.

#### 3. Koszt analiz w budżecie

**File**: `conversations/budget.py`

**Intent**: Żeby koszt analizy liczył się do dziennego limitu, `spent_today` dodaje sumę `analysis_cost_usd` rozmów użytkownika z `analyzed_at >= day_start(now)`. Docstring modułu i `turn_cost` wspominają, że to także koszt analizy.

**Contract**: sygnatura `spent_today(user, now) -> Decimal` bez zmian; filtr przez `Conversation.objects.for_user(user)`.

#### 4. Testy

**File**: `tests/test_conversations.py`, `tests/test_budget.py`

**Intent**: Pokryć cascade i izolację `Mistake` oraz nowe liczenie budżetu.

**Contract**:
- Usunięcie użytkownika i usunięcie rozmowy usuwa jej `Mistake`; `Mistake.objects.for_user(B)` nie zwraca błędów A; anonim dostaje pusty wynik.
- `spent_today` = tury + analizy z dziś; analiza z `analyzed_at` przed północą Europe/Berlin się nie liczy; analiza innego użytkownika się nie liczy; `is_exhausted` staje się prawdą, gdy dopiero koszt analizy przekracza próg.

### Success Criteria:

#### Automated Verification:

- Migracja jest kompletna: `uv run python manage.py makemigrations --check --dry-run`
- Migracja się aplikuje: `uv run python manage.py migrate`
- Testy przechodzą: `uv run pytest`
- Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- `/admin/` nie pokazuje `Mistake` ani pól analizy jako nowego modelu (strona admina bez nowych pozycji).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Wywołanie modelu do analizy

### Overview

Nowa funkcja `llm.analyze_mistakes` ze strukturalną odpowiedzią, osobnym promptem i ustawieniami (effort, limit czasu).

### Changes Required:

#### 1. Ustawienia analizy

**File**: `talkaitive/settings.py`

**Intent**: Osobne ustawienia dla analizy, bo potrzebuje więcej „myślenia” i więcej czasu niż tura rozmowy, ale użytkownik nie powinien czekać dłużej niż ok. 1,5 min.

**Contract**:
- `LLM_ANALYSIS_REASONING_EFFORT = os.environ.get("LLM_ANALYSIS_REASONING_EFFORT", "high")` (wzorzec jak `LLM_REASONING_EFFORT`, komentarz: trafność listy jest kryterium sukcesu PRD).
- `LLM_ANALYSIS_TIMEOUT_SECONDS = 90`, `LLM_ANALYSIS_MAX_RETRIES = 0` (komentarz: świadomy wybór UX — krótkie czekanie i tania porażka, którą naprawia „Try again”; to nie limit serwera — gunicorn gthread nie ucina długich żądań, sufitem jest 5 min bez danych na proxy Railway).

#### 2. `analyze_mistakes`

**File**: `conversations/llm.py`

**Intent**: Jedno wywołanie Responses API, które dostaje cały transkrypt z ponumerowanymi wiadomościami ucznia i zwraca listę błędów tylko z wiadomości ucznia. Ta sama obsługa błędów i zasada „bez treści rozmowy w logach” co `generate_turn`. Docstring modułu wspomina drugą funkcję.

**Contract**:
- Schemat Pydantic: `FoundMistake{message_number: int, category: Literal["grammar", "vocabulary", "word_order"], wrong: str, correct: str, sentence: str, explanation: str}`, `MistakeReport{mistakes: list[FoundMistake]}`.
- `analyze_mistakes(*, language: str, history: Sequence[tuple[str, str]]) -> AnalysisResult`; `AnalysisResult` (frozen dataclass): `mistakes: list[FoundMistake]`, `model`, `input_tokens`, `cached_input_tokens`, `output_tokens`.
- `client.responses.parse(model=settings.LLM_MODEL, instructions=<stała instrukcja + "Practice language: …">, input=<transkrypt>, text_format=MistakeReport, reasoning={"effort": settings.LLM_ANALYSIS_REASONING_EFFORT}, store=False)`; klient z `LLM_ANALYSIS_TIMEOUT_SECONDS` / `LLM_ANALYSIS_MAX_RETRIES` (`_get_client` przyjmuje timeout i liczbę prób).
- Transkrypt w `input` to jeden tekst: wiadomości ucznia oznaczone `[n] Learner:` (n od 1, tylko wiadomości ucznia), wiadomości agenta jako `Partner:` bez numeru (kontekst).
- Instrukcja (po angielsku, stała część pierwsza — prompt caching): analizuj tylko wiadomości ucznia; kategorie grammar / vocabulary / word order; pomijaj literówki, wielkość liter i interpunkcję, chyba że zmieniają sens; `wrong` i `correct` to najkrótszy fragment, który pokazuje błąd (np. „habe … gegangen” → „bin … gegangen”), `sentence` to całe oryginalne zdanie ucznia, `explanation` to jedno krótkie zdanie po angielsku; każde wystąpienie błędu osobno z numerem wiadomości; brak błędów → pusta lista.
- Błędy: `APIError`, `ValidationError`, `output_parsed is None`, brak `usage` → `LLMError`, logowany tylko typ/status.

#### 3. Dokumentacja zmiennych środowiskowych

**File**: `CLAUDE.md` (sekcja „TalkAItive — project notes”, poza blokiem `10x-cli`)

**Intent**: Dopisać opcjonalne `LLM_ANALYSIS_REASONING_EFFORT` (domyślnie `high`) do listy opcjonalnych zmiennych obok `LLM_MODEL`.

**Contract**: jedna fraza w istniejącym punkcie o opcjonalnych env vars.

#### 4. Testy

**File**: `tests/test_llm.py`

**Intent**: Te same fałszywe SDK (`FakeResponses`, `make_response`) co dla tur.

**Contract**:
- `text_format is MistakeReport`, `reasoning.effort` = `LLM_ANALYSIS_REASONING_EFFORT`, `store=False`, klient z timeoutem/próbami analizy.
- Transkrypt numeruje tylko wiadomości ucznia (1..N), wiadomości agenta są w tekście bez numeru.
- Stała część instrukcji jest identyczna dla dwóch różnych języków (prefiks do cache).
- `APIError` / `ValidationError` / `output_parsed=None` / brak `usage` → `LLMError`; log nie zawiera tekstu rozmowy.
- Poprawna odpowiedź → `AnalysisResult` z błędami i tokenami.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Jednorazowe wywołanie `analyze_mistakes` z prawdziwym kluczem (`uv run --env-file .env python manage.py shell`) na krótkim transkrypcie z 2 znanymi błędami zwraca oba błędy z poprawną kategorią, a `gpt-5.4` przyjmuje effort `high` (brak błędu 400).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Serwis analizy

### Overview

`services.analyze_conversation`: jednorazowa, odporna na równoległe żądania analiza zakończonej rozmowy, ze scalaniem, sortowaniem i zapisem kosztu.

### Changes Required:

#### 1. `analyze_conversation`

**File**: `conversations/services.py`

**Intent**: Uruchomić analizę dokładnie raz dla zakończonej rozmowy, niezależnie od drogi zakończenia i stanu budżetu; zapisać listę i koszt albo stan porażki. Docstring modułu opisuje też analizę.

**Contract**:
- `analyze_conversation(conversation: Conversation, now: datetime) -> None`; podnosi `ConversationError` (rozmowa aktywna: „This conversation has not ended yet.”; już przeanalizowana: „The list of mistakes is already ready.”; w toku: „The list of mistakes is still being prepared. Please wait.”) i przepuszcza `LLMError`. Dwie ostatnie odmowy (już przeanalizowana, w toku) to `AnalysisNotNeeded(ConversationError)` — podklasa w `services.py`, żeby widok mógł je pominąć bez komunikatu.
- Pod `_lock`: sprawdzenia jak wyżej, potem `analysis_started_at = now`.
- Rozmowa bez wiadomości ucznia: bez wywołania modelu — `analyzed_at = now`, koszt 0, znacznik wyczyszczony.
- Poza transakcją: `analyze_mistakes(language=conversation.language, history=...)` (import po nazwie, jak `generate_turn`, żeby testy mogły go podmienić). Wyjątek → czyści własny znacznik, ustawia `analysis_failed_at = now`, przepuszcza wyjątek.
- Pod `_lock`: jeśli nadal nieprzeanalizowana — zapis `Mistake` (`user=conversation.user`), `analyzed_at = now`, `analysis_cost_usd = turn_cost(...)`, `analysis_failed_at = None`; zawsze czyści własny znacznik (tylko gdy równy `now`, jak `_clear_turn_marker`).
- `analysis_in_progress(conversation, now) -> bool` — publiczna, dla widoku (jak `agent_turn_in_progress`), z wygasaniem po `LLM_ANALYSIS_TIMEOUT_SECONDS × (LLM_ANALYSIS_MAX_RETRIES + 1) + 30` s.

#### 2. Scalanie i kolejność

**File**: `conversations/services.py`

**Intent**: Deterministycznie zamienić surową listę modelu na pozycje listy: chronologicznie, identyczne pary scalone.

**Contract**:
- Normalizacja do porównań: `strip()` i zwinięcie białych znaków; wielkość liter ma znaczenie.
- Odrzucamy wpisy z pustym `wrong` lub `correct` albo z `wrong == correct` po normalizacji.
- Sortowanie stabilne po `message_number`; numery spoza `1..N` trafiają na koniec (w kolejności modelu).
- Identyczna para (`wrong`, `correct`) po normalizacji → jedna pozycja w miejscu pierwszego wystąpienia, z jej `category`, `sentence`, `explanation` i `occurrences` = liczba wystąpień.
- `position` = 1..K po scaleniu.

#### 3. Testy

**File**: `tests/test_analysis.py` (nowy; helpery i fixture'y jak w `tests/test_conversation_views.py:21-91`, `FakeAnalyzeMistakes` w stylu `FakeGenerateTurn`)

**Intent**: Pokryć wszystkie reguły serwisu bez sieci.

**Contract**:
- Analiza działa po każdej z trzech dróg zakończenia (`user`, `agent_goodbye`, `daily_limit`), także gdy `is_exhausted` jest prawdą.
- Aktywna rozmowa → `ConversationError`, brak wywołania modelu.
- Druga analiza tej samej rozmowy → `ConversationError`, model wywołany raz.
- Znacznik w toku → odmowa; wygasły znacznik → analiza rusza.
- Spóźniony wynik przy już przeanalizowanej rozmowie → odrzucony, bez drugiego zapisu i kosztu.
- Rozmowa bez wiadomości ucznia → `analyzed_at` ustawione, 0 błędów, koszt 0, model niewywołany.
- `LLMError` → `analysis_failed_at` ustawione, znacznik wyczyszczony, brak `Mistake`; ponowienie po porażce działa i czyści `analysis_failed_at`.
- Scalanie: „habe gegangen → bin gegangen” w wiadomości 1 i 4 → jedna pozycja z `occurrences=2` na pozycji wiadomości 1; „habe gefahren → bin gefahren” zostaje osobno; różnica tylko w białych znakach scala się, różnica w wielkości liter nie.
- Kolejność: wpisy zwrócone przez model w kolejności 3, 1, 2 zapisują się jako 1, 2, 3; numer spoza zakresu ląduje na końcu; pusty / identyczny `wrong`/`correct` odrzucony.
- Koszt analizy trafia do `analysis_cost_usd` i do `spent_today`.
- Zapisane `Mistake.user` = właściciel rozmowy.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Przegląd testów scalania i kolejności w `tests/test_analysis.py` potwierdza, że opisują regułę zgodną z decyzjami (chronologicznie, identyczne pary z „×N”).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Widok i ekran listy

### Overview

Adres `conversations/<pk>/analysis/`, stany zakończonej rozmowy w szablonie, auto-wysyłka w `base.html` i ręczny test na prawdziwym modelu.

### Changes Required:

#### 1. Widok i URL

**File**: `conversations/views.py`, `conversations/urls.py`

**Intent**: Cienki widok POST, który woła serwis i zawsze przekierowuje na stronę rozmowy (POST → redirect → GET); `conversation_detail` dostaje dane do stanów analizy.

**Contract**:
- `path("conversations/<int:pk>/analysis/", views.conversation_analyze, name="conversation_analyze")`; `@require_POST`, pobranie przez `_get_conversation`; `AnalysisNotNeeded` (już gotowe / w toku — zwykle nieaktualna strona z auto-wysyłką) → samo przekierowanie, bez komunikatu; pozostały `ConversationError` → `messages.error`; `LLMError` → nic (strona pokazuje stan porażki).
- `conversation_detail` dodaje do kontekstu: `mistakes` (`Mistake.objects.for_user(request.user).filter(conversation=conversation)`), `analysis_in_progress` (z serwisu).

#### 2. Szablon zakończonej rozmowy

**File**: `conversations/templates/conversations/detail.html` (opcjonalnie fragment `_mistakes.html`)

**Intent**: Pod transkryptem i komunikatem o zakończeniu pokazać jeden z czterech stanów (kolejność z „Critical Implementation Details”).

**Contract**:
- Przeanalizowana: nagłówek „Your mistakes”; lista `<ol>` w kolejności `position`; każda pozycja: etykieta `get_category_display`, `wrong → correct`, „×N” gdy `occurrences > 1`, `sentence`, `explanation`. 0 błędów → „No mistakes found in this conversation.”
- W toku: spinner + „Preparing your list of mistakes…” i `<meta http-equiv="refresh" content="5">` w `{% block head %}`.
- Nieudana: „We could not prepare your list of mistakes. Please try again.” + formularz POST z „Try again” (`data-waits-for-agent`).
- Nierozpoczęta: formularz POST z przyciskiem „Show my mistakes”, oznaczony `data-auto-submit` i `data-waits-for-agent`.
- Link „Back to the home page” zostaje na dole.

#### 3. Auto-wysyłka i tekst spinnera

**File**: `accounts/templates/base.html`

**Intent**: Formularz z `data-auto-submit` wysyła się sam po załadowaniu strony (przez `requestSubmit()`, czyli tą samą ścieżką co klik — blokada przycisków i spinner). Spinner pokazuje tekst z formularza, a nie zawsze „Agent is typing…”. Style listy w istniejącym bloku `<style>`.

**Contract**:
- Formularz może mieć `data-waiting-text`; brak → „Agent is typing…”. `pageshow` (bfcache) przywraca domyślny tekst.
- Auto-wysyłka uruchamia się tylko przy zwykłym załadowaniu skryptu (nie przy przywróceniu z bfcache).
- Bez JS formularz działa jak zwykły przycisk.

#### 4. Testy widoków

**File**: `tests/test_conversation_views.py`

**Intent**: Pokryć adres, izolację i każdy stan strony.

**Contract**:
- `conversation_analyze` dla cudzej rozmowy → 404 (dopisać do sparametryzowanego testu 404); anonim → przekierowanie do logowania (dopisać do istniejącego testu).
- GET na `conversation_analyze` → 405.
- Strona zakończonej rozmowy: nierozpoczęta → formularz z `data-auto-submit`; w toku → meta refresh i „Preparing your list of mistakes…”; nieudana → „Try again” i brak `data-auto-submit`; przeanalizowana → pozycje w kolejności, „×2” przy scalonej, etykieta „Word order”; 0 błędów → „No mistakes found…”.
- Aktywna rozmowa nie pokazuje żadnego z tych elementów.
- Lista jest w HTML po transkrypcie.
- POST na aktywną rozmowę → komunikat błędu i redirect.
- POST na już przeanalizowaną rozmowę i na rozmowę w toku → redirect bez komunikatu błędu, model niewywołany.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`
- Brak brakujących migracji: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Lokalnie z prawdziwym kluczem (`uv run --env-file .env python manage.py runserver`): rozmowa (`de`) z celowymi błędami z każdej kategorii, zakończona „End” → spinner, potem lista chronologiczna pod transkryptem; błędy i kategorie są trafne (kryterium sukcesu PRD).
- Ten sam błąd powtórzony dwa razy pokazuje się raz z „×2”; literówka nie pojawia się na liście.
- Rozmowa zakończona pożegnaniem agenta i rozmowa zakończona dziennym limitem (np. tymczasowo niski `DAILY_BUDGET_USD` w `.env`) też dostają listę.
- Czas analizy ok. 20-turowej rozmowy z effort `high` mieści się wyraźnie poniżej 90 s; wynik zapisany w Progress.
- Odświeżenie strony w trakcie analizy nie uruchamia drugiego wywołania (w `manage.py shell`: jeden zestaw `Mistake`, jeden koszt).
- Z wyłączonym JS przycisk „Show my mistakes” działa.
- Strona na szerokości telefonu jest czytelna (lista bez poziomego przewijania).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `tests/test_llm.py` — schemat, prompt, numeracja transkryptu, mapowanie błędów SDK, brak treści w logach.
- `tests/test_analysis.py` — jednorazowość, znacznik, porażka i ponowienie, scalanie, kolejność, koszt, wszystkie drogi zakończenia.
- `tests/test_budget.py` — `spent_today` z kosztem analiz i granicą północy Europe/Berlin.
- `tests/test_conversations.py` — cascade i `for_user` dla `Mistake`.

### Integration Tests:

- `tests/test_conversation_views.py` — pełny przepływ: zakończenie → strona z auto-wysyłką → POST analizy (fałszywy model) → strona z listą; 404 dla innego użytkownika; anonim → logowanie.

### Manual Testing Steps:

1. Rozmowa po niemiecku z błędami: „Ich habe gestern in die Stadt gegangen”, „Ich weiß, dass er kommt morgen”, złe słowo (np. „Ich mache ein Foto von dem Brot” w złym znaczeniu), jeden błąd powtórzony, jedna literówka.
2. „End” → spinner → lista: chronologicznie, 3 kategorie, „×2” przy powtórzeniu, bez literówki, wyjaśnienia po angielsku.
3. Pożegnanie z agentem i potwierdzenie → lista.
4. Niski `DAILY_BUDGET_USD` → koniec przez limit → lista mimo wyczerpanego budżetu.
5. Zmierzenie czasu analizy długiej rozmowy.

## Performance Considerations

Jedno wywołanie na rozmowę; transkrypt ok. 20 tur to kilka tysięcy tokenów wejścia, więc koszt analizy to głównie tokeny rozumowania przy effort `high` (szacunkowo kilka centów). Żądanie analizy zajmuje jeden wątek gunicorna na czas wywołania (do 90 s); przy 2 workerach × 4 wątkach i 2 użytkownikach to wystarczy.

## Migration Notes

Migracja `0003` dodaje tylko pola nullable / z wartością domyślną i nową tabelę, więc istniejące rozmowy na produkcji zostają bez zmian. Rozmowa zakończona przed wdrożeniem dostanie listę dopiero, gdy ktoś otworzy jej stronę (wtedy ruszy auto-wysyłka); `/` nie linkuje do starych rozmów, więc nie wymuszamy analizy wstecz.

## References

- Roadmap: `context/foundation/roadmap.md:102-112` (S-02)
- PRD: `context/foundation/prd.md:77` (FR-008), `:42` (trafność listy), `:114` (budżet)
- Decyzja o analizie po rozmowie: `context/archive/2026-10-05-first-corrected-conversation/plan.md:42`
- Wzorzec tury i znacznika: `conversations/services.py:41-171`
- Wywołanie modelu: `conversations/llm.py:116-166`
- Budżet: `conversations/budget.py:58-106`
- Lessons: `context/foundation/lessons.md:54-66`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Model danych i budżet

#### Automated

- [x] 1.1 Migracja jest kompletna: `uv run python manage.py makemigrations --check --dry-run`
- [x] 1.2 Migracja się aplikuje: `uv run python manage.py migrate`
- [x] 1.3 Testy przechodzą: `uv run pytest`
- [x] 1.4 Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [x] 1.5 `/admin/` nie pokazuje `Mistake` ani pól analizy jako nowego modelu (strona admina bez nowych pozycji).

### Phase 2: Wywołanie modelu do analizy

#### Automated

- [ ] 2.1 Testy przechodzą: `uv run pytest`
- [ ] 2.2 Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [ ] 2.3 Jednorazowe wywołanie `analyze_mistakes` z prawdziwym kluczem (`uv run --env-file .env python manage.py shell`) na krótkim transkrypcie z 2 znanymi błędami zwraca oba błędy z poprawną kategorią, a `gpt-5.4` przyjmuje effort `high` (brak błędu 400).

### Phase 3: Serwis analizy

#### Automated

- [ ] 3.1 Testy przechodzą: `uv run pytest`
- [ ] 3.2 Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [ ] 3.3 Przegląd testów scalania i kolejności w `tests/test_analysis.py` potwierdza, że opisują regułę zgodną z decyzjami (chronologicznie, identyczne pary z „×N”).

### Phase 4: Widok i ekran listy

#### Automated

- [ ] 4.1 Testy przechodzą: `uv run pytest`
- [ ] 4.2 Lint i format bez zmian: `uv run ruff check . && uv run ruff format --check .`
- [ ] 4.3 Brak brakujących migracji: `uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [ ] 4.4 Lokalnie z prawdziwym kluczem (`uv run --env-file .env python manage.py runserver`): rozmowa (`de`) z celowymi błędami z każdej kategorii, zakończona „End” → spinner, potem lista chronologiczna pod transkryptem; błędy i kategorie są trafne (kryterium sukcesu PRD).
- [ ] 4.5 Ten sam błąd powtórzony dwa razy pokazuje się raz z „×2”; literówka nie pojawia się na liście.
- [ ] 4.6 Rozmowa zakończona pożegnaniem agenta i rozmowa zakończona dziennym limitem (np. tymczasowo niski `DAILY_BUDGET_USD` w `.env`) też dostają listę.
- [ ] 4.7 Czas analizy ok. 20-turowej rozmowy z effort `high` mieści się wyraźnie poniżej 90 s; wynik zapisany w Progress.
- [ ] 4.8 Odświeżenie strony w trakcie analizy nie uruchamia drugiego wywołania (w `manage.py shell`: jeden zestaw `Mistake`, jeden koszt).
- [ ] 4.9 Z wyłączonym JS przycisk „Show my mistakes” działa.
- [ ] 4.10 Strona na szerokości telefonu jest czytelna (lista bez poziomego przewijania).
