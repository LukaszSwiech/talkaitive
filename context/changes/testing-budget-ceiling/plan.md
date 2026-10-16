# Rollout Phase 4 — sufit dziennego budżetu: plan implementacji

## Overview

Faza 4 z `context/foundation/test-plan.md` §3 (ryzyko #4). Research pokazał, że dziś nie da się udowodnić, że „suma kosztów dnia nie przekracza limitu”, bo to nieprawda: nieudane i spóźnione płatne wywołania zapisują koszt 0, a w trwającej rozmowie wysłanie wiadomości i „Try again” nigdy nie są odmawiane z powodu budżetu. Plan (1) dodaje księgę kosztów wywołań, które nie zostawiają wiadomości ani wyniku analizy, tak żeby każda próba, która najpewniej kosztowała, liczyła się do sumy dnia, (2) dodaje twardy dach: gdy suma dnia osiągnie limit, żadna nowa płatna tura ani ponowienie analizy się nie zaczyna, (3) przypina całość testami unit + integracyjnymi z oczekiwanymi kwotami wpisanymi ręcznie i potwierdza je ręcznymi mutantami.

## Current State Analysis

Źródło: `context/changes/testing-budget-ceiling/research.md` (zweryfikowane w kodzie na `146c106`).

- **Limit jest miękki z prognozą.** Twardo sprawdzany tylko przy starcie rozmowy (`conversations/services.py:108-109` → `is_exhausted`, `conversations/budget.py:77-97`: rozmowa zakończona `DAILY_LIMIT` dziś albo `spent + 0,03 >= budżet`). Wysłanie wiadomości i „Try again” tury tylko wyliczają `is_final_turn` (`budget.py:100-117`: `spent + koszt ostatniej tury agenta tej rozmowy (albo 0,03) >= budżet`) i wykonują płatną turę pożegnalną (`services.py:176-232`).
- **Jedno drogie wywołanie przechodzi przez limit bez końca rozmowy.** Spent 0,90, ostatnia tura 0,05 → tura nie jest ostatnia; jeśli kosztuje 0,40, suma dnia = 1,30, a rozmowa trwa; dopiero następna wiadomość dostaje (płatną) turę pożegnalną.
- **Nieudana próba = 0 USD.** `usage` jest czytane dopiero po wszystkich sprawdzeniach (`conversations/llm.py:274-294`, `:348-364`). Timeout / błąd połączenia / 429 / 5xx (`llm.py:259-267`, `:335-342`), `ValidationError` (`:268-272`, `:343-346`), `output_parsed is None` i pusty `reply` (`:274-282`, `:348-351`), spóźniona tura (`services.py:179-180`, `:205`), spóźniona analiza (`:332-333`) i nieudany zapis analizy po udanym wywołaniu (`:357-360`) nie zostawiają żadnego kosztu. Żaden model nie ma miejsca na taki koszt: tura zapisuje `Message.cost_usd`, analiza `Conversation.analysis_cost_usd`.
- **Analiza jest celowo poza limitem** (S-02, `services.py:18-19`, przypięte `tests/test_analysis.py:148-169`); jej ponowienia też.
- **Granica dnia** `ZoneInfo("Europe/Berlin")` z parametrem `now` (`budget.py:46-59`); testy granic mają literały UTC także w dniach zmiany czasu (`tests/test_budget.py:120-140`), ale brak testu sumy (`spent_today`) po obu stronach północy w te dni. `test_is_exhausted_false_after_midnight_reset` (`tests/test_budget.py:244-251`) liczy oczekiwaną chwilę przez `next_reset` — antywzorzec z test-planu.
- **Atrapa transportu** zwraca zawsze `usage` 1200 / 1000 / 40 (`tests/fake_provider.py:24-26`, `:166-172`), bez parametru per odpowiedź. Atrapa nad SDK w `tests/test_llm.py` (`fake_openai`, `SimpleNamespace(output_parsed=..., usage=...)`, `:52`, `:328`) pozwala ustawić `usage` przy pustej odpowiedzi.
- **UI**: strona rozmowy zakończonej `DAILY_LIMIT` pokazuje godzinę resetu (`conversations/views.py:78-83`, `detail.html:60-63`, `_reset_notice.html`); odmowy (`ConversationError`) idą przez `messages.error` (`views.py:114-115`, `:126-127`, `:147-148`); nieudana analiza pokazuje „Try again” (`detail.html:72-77`).
- **Mutacje**: `conversations/budget.py` i `conversations/services.py` są w `[tool.mutmut]`, `conversations/llm.py` nie; ręczne mutanty kończą się na `M24` (`scripts/mutation/manual_mutants.py`).

## Desired End State

- Każde wywołanie modelu, które najpewniej kosztowało, liczy się do sumy dnia: udana tura i analiza jak dziś, a do tego (w nowej księdze) odpowiedź z `usage` bez użytecznego wyniku, spóźniona tura lub analiza i nieudany zapis analizy — prawdziwym kosztem z `usage`; timeout, błąd schematu i poprawna odpowiedź bez `usage` — szacunkiem (tura: koszt ostatniej udanej tury tej rozmowy albo 0,03 USD; analiza: 0,07 USD). Szybki błąd statusu (429 / 5xx), błąd połączenia i brak klucza dają 0.
- Gdy suma dnia ≥ limit: wysłanie wiadomości i „Try again” tury są odmawiane bez wywołania modelu, wiadomość nie jest zapisywana, rozmowa kończy się `DAILY_LIMIT`, a strona pokazuje godzinę resetu. Ponowienie analizy po błędzie jest odmawiane, a strona zamiast „Try again” pokazuje godzinę resetu. Pierwsza próba analizy zawsze rusza (S-02). Start nowej rozmowy jest odmawiany jak dziś.
- Dopóki suma < limit, zachowanie bez zmian: prognoza tury pożegnalnej, agent żegna się sam.
- Przekroczenie dnia jest ograniczone do wywołań, które zaczęły się poniżej limitu (najdroższe: jedna tura w toku) plus pierwszych prób analiz — test dowodzi tego przez „po dachu do atrapy dostawcy nie trafia żadne żądanie”.
- Testy unit + integracyjne mają oczekiwane kwoty wpisane ręcznie (rachunek w komentarzu), granice dnia jako literały UTC, także w dniach zmiany czasu; każdy nowy test pada na swoim ręcznym mutancie (`M25`–`M34`).

### Key Discoveries:

- `APITimeoutError` dziedziczy po `APIConnectionError` → `APIError` (openai-python), więc gałąź timeoutu musi stać przed `except APIError` (`llm.py:259`, `:335`).
- Koszt z `usage` jest znany w chwili błędu dla `output_parsed is None` i pustego `reply` (`response` istnieje); dla `ValidationError` obiekt odpowiedzi nie jest dostępny w `except` — stąd szacunek.
- `Message.created_at` to zegar rzeczywisty (`auto_now_add`, `conversations/models.py:89`), a `analyzed_at` i nowa księga — `now` z parametru (`services.py:339`). Testy z datami-literałami mogą sterować tylko wierszami zasianymi helperami (`tests/test_budget.py:52-63`).
- `analysis_failed(conversation, now)` (`services.py:260-272`) już rozróżnia „była wcześniejsza próba” (zapisany błąd albo wygasły znacznik) — to jest definicja ponowienia analizy dla dachu.
- `is_exhausted` jest „the only budget exhausted predicate” (`budget.py:78`); nowy predykat dachu musi mieć inną nazwę i docstring wyjaśniający różnicę.

## What We're NOT Doing

- `max_output_tokens` i limit liczby prób „Try again” — zostają zaakceptowanym ryzykiem Q-07 (decyzja w planowaniu); ponowienia zatrzymuje teraz dach dnia.
- Test E2E (Playwright) stanu „limit wyczerpany” — cost × signal: komunikat jest HTML-em z serwera (klient testowy widzi ten sam tekst), serwer E2E działa bez modelu (`OPENAI_API_KEY: ''`), więc ścieżki pieniędzy są dla przeglądarki nieosiągalne, a stan wymagałby osobnego użytkownika, `storageState` i danych wygasających o północy. Uzasadnienie trafia do §6.4 test-planu.
- Jedna księga wszystkich wywołań (także udanych tur i analiz) — `Message.cost_usd` i `analysis_cost_usd` zostają źródłem dla udanych wywołań; księga tylko dla wywołań bez innego zapisu.
- Liczenie każdego żądania HTTP z osobna: timeout po ponowieniu SDK (do 2 żądań na turę) to jeden szacunek; pierwsze żądanie, które padło timeoutem, a drugie 5xx, daje 0 (świadome przybliżenie).
- Księgowanie nieudanego zapisu tury po udanym wywołaniu (`services.py:203-207`) — błąd bazy w krótkiej transakcji pod blokadą jest bardzo rzadki, a obsługa wymagałaby drugiego `try`/`except` w `_generate_and_save`; koszt takiej tury zostaje 0 (świadome przybliżenie; analiza ma `save_failed`, bo jej zapis jest dłuższy i ma osobną ścieżkę błędu).
- Dach na pierwszą próbę analizy (S-02 bez zmian) i zmiana prognozy tury pożegnalnej.
- Pokazywanie użytkownikowi kosztów i wpisów księgi; rejestracja księgi w adminie (zakaz z `lessons.md`).
- Sprawdzenie miesięcznego limitu na projekcie OpenAI — poza repo (Open Risks w briefie).

## Implementation Approach

Najpierw księga (faza 1), bo dach (faza 2) bez niej nie widziałby nieudanych prób. Zasada podziału odpowiedzialności: `llm.py` tylko mówi, co wie o koszcie nieudanego wywołania (tokeny z `usage` albo „prawdopodobnie płatne bez `usage`”), `budget.py` zna ceny, szacunki i sumę dnia, `services.py` decyduje, kiedy zapisać koszt i kiedy odmówić. Oczekiwane wartości w testach pochodzą z decyzji tego planu, PRD (Access Control „Koszty modeli”) i cennika w ustawieniach przypiętego w fixture literałami — nigdy z `turn_cost` ani `next_reset` (`test-plan.md` §6.1 krok 1). Każdy nowy test potwierdzamy ręcznym mutantem w tej samej fazie.

## Branches and PRs

Jedna gałąź `testing-budget-ceiling` (już istnieje) i jeden PR dla wszystkich faz — migracja tylko dodaje tabelę, a faza 2 zależy od fazy 1.

## Critical Implementation Details

- **Odmowa z zakończeniem rozmowy:** `end_conversation` w gałęzi dachu musi się zatwierdzić przed zgłoszeniem `ConversationError` — wyjątek rzucony wewnątrz `transaction.atomic()` cofnąłby zakończenie. Zakończ pod blokadą, wyjdź z bloku, potem zgłoś odmowę.
- **Zapis kosztu nie może ukryć pierwotnego błędu:** w ścieżce „nieudany zapis analizy” baza mogła właśnie zawieść; jeśli zapis wpisu księgi też się nie uda, zaloguj to (bez treści rozmowy) i zgłoś pierwotny wyjątek.
- **Dwa zegary:** turę zapisaną przez kod datuje zegar rzeczywisty, więc scenariusze przechodzące przez `send_message` / `run_agent_turn` używają `now = timezone.now()` (wydatek zasiany na tę samą chwilę); scenariusze z datami-literałami (północ, zmiana czasu) sterują tylko księgą, analizą i wierszami zasianymi helperami.
- **Mutanty fazy 2** (`M31`–`M34`) piszemy dopiero na kodzie fazy 2 — `manual_mutants.py` wymaga, by fragment `original` występował w pliku dokładnie raz. Gałąź dachu w `send_message` i `run_agent_turn` będzie tym samym tekstem, a `end_conversation(..., Conversation.EndReason.DAILY_LIMIT, now)` jest już w `_save_agent_turn` (`services.py:230`), więc `original` mutantów `M31`–`M33` obejmuje też sąsiednią linię właściwą danej funkcji (np. poprzedni komunikat odmowy).
- **Istniejące mutanty budżetu:** `C2` szuka linii `        >= settings.DAILY_BUDGET_USD` (osobna linia po złamaniu przez ruff) dokładnie raz w `budget.py`, `M4` — filtra `conversation__in=…` przenoszonego do `next_turn_estimate`, `M5` — `ended_at__gte=day_start(now)`. Nowe wyrażenia z `DAILY_BUDGET_USD` (`is_final_turn`, `limit_reached`) nie mogą dać drugiej takiej linii; jeśli refaktor zmieni fragment, popraw `original` mutanta tak, by trafiał w to samo zachowanie (`is_exhausted`), nie kod pod mutanta.

## Faza 1: Księga kosztów — każde płatne wywołanie liczy się do sumy dnia (#4)

### Overview

Nowy model-księga, dane o koszcie w `LLMError`, zapis kosztu na każdej ścieżce błędu i spóźnienia, suma dnia z księgą, testy unit / `llm` / integracyjne z kwotami-literałami i ręczne mutanty `M25`–`M30`.

### Changes Required:

#### 1. Model księgi i migracja

**File**: `conversations/models.py`, `conversations/migrations/0006_llmcharge.py` (nowa, `makemigrations`)

**Intent**: Miejsce na koszt wywołania, które nie zostawia `Message` ani wyniku analizy, z własną datą, żeby suma dnia w Berlinie przypisała go do właściwego dnia.

**Contract**: `class LLMCharge(UserOwned)` — `conversation` (FK `Conversation`, `CASCADE`, `related_name="charges"`), `kind` (`TextChoices`: `turn`, `analysis`), `reason` (`TextChoices`: `estimate` — timeout lub zła odpowiedź bez `usage`; `no_usable_answer` — odpowiedź z `usage` bez wyniku; `late_result` — wynik niepotrzebny po przyjściu; `save_failed` — wynik opłacony, zapis się nie udał), `cost_usd` (`DecimalField(max_digits=10, decimal_places=6)`), `charged_at` (`DateTimeField(db_index=True)`, ustawiane jawnie z `now`, nie `auto_now_add`). `user` zawsze = użytkownik rozmowy. Bez rejestracji w adminie.

#### 2. Szacunek kosztu analizy

**File**: `talkaitive/settings.py`

**Intent**: Kwota księgowana za analizę, która padła timeoutem lub złym schematem.

**Contract**: `LLM_ANALYSIS_COST_ESTIMATE_USD = Decimal("0.07")` obok `LLM_TURN_COST_ESTIMATE_USD`, z komentarzem o źródle (pomiar S-02: 20 tur, `medium`, 0,067 USD — `settings.py:69-72`).

#### 3. `LLMError` niesie to, co wiadomo o koszcie

**File**: `conversations/llm.py`

**Intent**: Serwis musi wiedzieć, czy nieudane wywołanie kosztowało i ile tokenów zużyło, bez wiedzy `llm.py` o cenach i budżecie.

**Contract**: `LLMError(message, *, usage: CallUsage | None = None, billed_without_usage: bool = False)`; `CallUsage` (dataclass: `model`, `input_tokens`, `cached_input_tokens`, `output_tokens`). W `generate_turn` i `analyze_mistakes`:
- `APITimeoutError` (osobna gałąź **przed** `except APIError`) → `billed_without_usage=True`;
- `ValidationError` → `billed_without_usage=True`;
- `output_parsed is None` / pusty `reply` → `usage=` z `response.usage`, gdy jest; gdy `response.usage is None` → `billed_without_usage=True`;
- poprawna odpowiedź, ale `response.usage is None` (`llm.py:283-285`, `:352-354`) → `billed_without_usage=True` (odpowiedź przyszła, więc wywołanie kosztowało);
- pozostałe `APIError` (429 / 5xx / błąd połączenia) i brak klucza → bez danych (koszt 0).
Logowanie bez zmian (bez treści rozmowy).

#### 4. Suma dnia z księgą i wspólny szacunek tury

**File**: `conversations/budget.py`

**Intent**: `spent_today` dodaje sumę księgi od północy; szacunek „koszt ostatniej tury agenta tej rozmowy albo 0,03” staje się jedną funkcją używaną przez prognozę i przez księgowanie timeoutu tury.

**Contract**: `spent_today` = tury + analizy + `LLMCharge.objects.for_user(user).filter(charged_at__gte=day_start(now))` (suma `cost_usd`). Nowa `next_turn_estimate(user: User, conversation: Conversation) -> Decimal` (logika wyjęta z `is_final_turn`, bez zmiany zachowania); `is_final_turn` = `spent_today + next_turn_estimate >= DAILY_BUDGET_USD`. Docstring modułu wspomina księgę.

#### 5. Zapis kosztu w serwisach

**File**: `conversations/services.py`

**Intent**: Każda ścieżka, na której wywołanie najpewniej kosztowało, a nic nie zostało zapisane, tworzy wpis w księdze z `charged_at = now`.

**Contract**: prywatny helper zapisu (rozmowa, `kind`, `reason`, koszt, `now`) i helper „koszt z `LLMError`” (`usage` → `turn_cost(...)`, `reason=no_usable_answer`; `billed_without_usage` → szacunek, `reason=estimate`; inaczej brak wpisu). Miejsca:
- `_generate_and_save`, `except` — tylko dla `LLMError`; szacunek tury = `next_turn_estimate` liczony **przed** wywołaniem (tą samą wartością co prognoza); znacznik zwalniany jak dziś;
- `_generate_and_save`, gdy `locked.awaiting_agent_reply` jest fałszem (wynik spóźniony) → `late_result` z prawdziwym kosztem;
- `analyze_conversation`, `except` wokół `analyze_mistakes` — dla `LLMError`; szacunek `LLM_ANALYSIS_COST_ESTIMATE_USD`;
- `analyze_conversation`, `analyzed_at is not None` po wywołaniu → `late_result`;
- `analyze_conversation`, `except` wokół zapisu → `save_failed` z prawdziwym kosztem (poza nieudaną transakcją; patrz Critical Implementation Details).
Docstring modułu: zdanie o księdze („a late result is dropped, but its cost is counted”) zamiast „unpaid” / „not counted” (`services.py:180`, `:332`).

#### 6. Strażniki usuwania konta

**File**: `tests/test_account_deletion.py`

**Intent**: Nowy model jest danymi użytkownika i musi znikać z kontem (wymuszają to strażniki §6.2).

**Contract**: `MODEL_DECISIONS[LLMCharge] = CASCADE`; fabryka w `FACTORIES` tworząca rozmowę z wpisem księgi.

#### 7. Atrapa transportu: `usage` per odpowiedź

**File**: `tests/fake_provider.py`

**Intent**: Scenariusz „jedno drogie wywołanie” na granicy SDK i odpowiedź 200 z pustym `reply` o znanym koszcie.

**Contract**: `reply(..., usage: tuple[int, int, int] | None = None)` i `analysis(..., usage=...)` — (input, cached, output); domyślnie dzisiejsze stałe. `_response_body` przyjmuje te liczby.

#### 8. Testy unit budżetu

**File**: `tests/test_budget.py`

**Intent**: Księga w sumie dnia, granice dnia w dniach zmiany czasu, usunięcie antywzorca.

**Contract**: helper `add_charge(conversation, cost, at)`; testy: wpis dziś liczy się, wpis sprzed północy nie, wpis dokładnie o północy tak, wpis innego użytkownika nie; suma tur + analiz + księgi (literał); w dniach 2026-03-29 i 2026-10-25 koszty 1 s przed i dokładnie o północy Berlina (chwile UTC wpisane ręcznie) — suma o 12:00 liczy tylko drugi; `next_turn_estimate` (brak tury → 0,03, jest tura → jej koszt). `test_is_exhausted_false_after_midnight_reset` używa chwili-literału UTC zamiast `next_reset(NOON)`. Fixture przypina `LLM_ANALYSIS_COST_ESTIMATE_USD`.

#### 9. Testy `LLMError` na granicy SDK

**File**: `tests/test_llm.py`

**Intent**: Przypiąć, co `llm.py` mówi o koszcie każdego rodzaju błędu.

**Contract**: dla tury i analizy: timeout → `billed_without_usage` i brak `usage`; `ValidationError` → `billed_without_usage`; `output_parsed is None` / pusty `reply` z `usage` → `usage` z tymi samymi tokenami; poprawna odpowiedź bez `usage` → `billed_without_usage`; 503 → ani `usage`, ani `billed_without_usage`.

#### 10. Testy integracyjne ścieżek kosztu

**File**: `tests/test_budget_ceiling.py` (nowy)

**Intent**: Od widoku lub serwisu do księgi: każda ścieżka zostawia dokładnie oczekiwaną kwotę w sumie dnia.

**Contract**: fixture przypina ceny gpt-5.4 (2,50 / 0,25 / 15,00), `DAILY_BUDGET_USD = 1.00`, szacunki 0,03 / 0,07. Atrapy `FakeGenerateTurn` i `FakeAnalyzeMistakes` (dziś w `tests/test_conversation_views.py:46`, `:75`) przenieść do wspólnego `tests/fakes.py`, a ich fixture'y do `tests/conftest.py`; `FakeAnalyzeMistakes` dostaje wynik-funkcję wywoływaną z tymi samymi kwargs (jak `FakeGenerateTurn`) — potrzebną w teście analizy spóźnionej, która w trakcie wywołania ustawia `analyzed_at`. Każdy test sprawdza przyrost `spent_today` (literał z rachunkiem w komentarzu, np. domyślne `usage` atrapy: 200 × 2,50 + 1000 × 0,25 + 40 × 15,00 = 1350 / 1M = 0,00135 USD), liczbę wpisów księgi i `len(fake_provider.requests)`:
- tura: `hang(times=2)` bez wcześniejszej tury agenta → 0,03; z wcześniejszą turą 0,02 → 0,02;
- tura: `reply("")` (pusty `reply`) → 0,00135, `reason=no_usable_answer`;
- tura: `fail(503)` × 2 → brak wpisu, suma bez zmian;
- tura spóźniona (użytkownik zakończył rozmowę w trakcie, `FakeGenerateTurn` z funkcją w kolejce) → prawdziwy koszt, `late_result`;
- analiza: `hang` → 0,07; spóźniona → prawdziwy koszt; nieudany zapis (np. `_save_mistakes` podmienione na rzucające) → prawdziwy koszt, `save_failed`.
Docstringi podają źródło: decyzje tego planu (szacunek) i PRD Access Control „Koszty modeli”.

#### 11. Ręczne mutanty fazy 1

**File**: `scripts/mutation/manual_mutants.py`, `scripts/mutation/accepted_survivors.md`

**Intent**: Potwierdzić, że nowe testy łapią zepsucie, którego mutmut nie wygeneruje (`llm.py` poza mutmut, usunięte wywołania i filtry).

**Contract** (wszystkie `expected="killed"`):
- `M25` — `llm.py`, `generate_turn`: bez gałęzi `APITimeoutError` (timeout wpada w ogólne `APIError`, koszt 0);
- `M26` — `llm.py`, `analyze_mistakes`: to samo dla analizy;
- `M27` — `llm.py`, `generate_turn`: pusty `reply` → `LLMError` bez `usage`;
- `M28` — `budget.py`, `spent_today`: bez składnika księgi;
- `M29` — `budget.py`, `spent_today`: księga bez `for_user` (`LLMCharge.objects.filter(...)`);
- `M30` — `services.py`, `_generate_and_save`: spóźniona tura bez wpisu w księdze.
Docstring modułu i nagłówek rejestru: lista id do `M30`.

### Success Criteria:

#### Automated Verification:

- Migracja jest kompletna: `uv run python manage.py makemigrations --check --dry-run`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C2 M4 M5 M25 M26 M27 M28 M29 M30`

#### Manual Verification:

- Przegląd diffu: każda oczekiwana kwota w nowych testach jest literałem z rachunkiem w komentarzu, nie wynikiem `turn_cost` / `next_turn_estimate`

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie przeglądu przez człowieka przed fazą 2.

---

## Faza 2: Twardy dach — po osiągnięciu limitu żadne nowe płatne wywołanie (#4)

### Overview

Predykat „suma dnia ≥ limit”, odmowa z zakończeniem rozmowy przy wysłaniu i „Try again” tury, odmowa ponowienia analizy, godzina resetu zamiast „Try again” analizy, testy scenariuszowe i mutanty `M31`–`M34`.

### Changes Required:

#### 1. Predykat dachu

**File**: `conversations/budget.py`

**Intent**: Jedno miejsce dla „dzisiejsza suma już osiągnęła limit” — w odróżnieniu od `is_exhausted` (blokada startu z zapasem na jedną turę).

**Contract**: `limit_reached(user: User, now: datetime) -> bool` = `spent_today(user, now) >= settings.DAILY_BUDGET_USD`. Docstring `is_exhausted` przestaje mówić „the only predicate” i wskazuje różnicę.

#### 2. Dach w rozmowie i w ponowieniu analizy

**File**: `conversations/services.py`

**Intent**: Po osiągnięciu limitu żadna nowa płatna tura ani ponowienie analizy się nie zaczyna.

**Contract**:
- `send_message`: pod blokadą, po sprawdzeniu statusu i `awaiting_agent_reply`, **przed** zapisem wiadomości użytkownika: gdy `limit_reached` → `end_conversation(..., DAILY_LIMIT, now)`, wyjście z transakcji, potem `ConversationError("You have used today's conversation limit.")`; wiadomość nie jest zapisywana.
- `run_agent_turn`: to samo, po sprawdzeniu `agent_turn_in_progress` (tura w toku dostaje dotychczasową odmowę „still replying”, rozmowa nie jest kończona w trakcie wywołania).
- `analyze_conversation`: pod blokadą, po gałęzi „brak wypowiedzi ucznia” (ta nie płaci): gdy `analysis_failed(locked, now)` i `limit_reached` → `ConversationError` z informacją, że listę można przygotować po resecie (brzmienie nie jest wymaganiem, PRD „Odmowa akcji”); znaczniki bez zmian. Pierwsza próba (bez wcześniejszej) rusza jak dziś.
Docstring modułu: akapit o dachu (analiza: „the first attempt runs whatever is left; a retry waits for the reset once the limit is reached”).

#### 3. Godzina resetu zamiast „Try again” analizy

**File**: `conversations/views.py`, `conversations/templates/conversations/detail.html`

**Intent**: Przy wyczerpanym dniu strona nie oferuje przycisku, który i tak zostanie odmówiony.

**Contract**: `conversation_detail` przekazuje `analysis_retry_reset_at = next_reset(now)` gdy `analysis_failed` i `limit_reached(request.user, now)`, inaczej `None`. W gałęzi `analysis_failed` szablon pokazuje komunikat o błędzie i `_reset_notice.html` (z `reset_at=analysis_retry_reset_at`) zamiast formularza „Try again”.

#### 4. Testy scenariuszowe dachu

**File**: `tests/test_budget_ceiling.py`

**Intent**: Dowód niezmiennika: po dachu do dostawcy nie trafia żadne żądanie; każda odmowa ma widoczny powód.

**Contract** (kwoty i chwile-literały w teście, rachunek w komentarzu):
- **jedno drogie wywołanie**: wydane 0,90, ostatnia tura rozmowy 0,05; `reply(..., usage=(0, 0, 20000))` (20 000 × 15,00 / 1M = 0,30) → suma 1,20, rozmowa nadal aktywna; następne wysłanie przez widok → odmowa, `end_reason=DAILY_LIMIT`, wiadomość niezapisana, brak nowego żądania, strona pokazuje godzinę resetu;
- **ponowienia zatrzymane na limicie**: wydane 0,96, ostatnia tura 0,02; wysłanie + `hang(times=2)` → +0,02; „Try again” (teraz tura pożegnalna) + `hang(times=2)` → +0,02, suma 1,00; kolejne „Try again” → odmowa, rozmowa zakończona `DAILY_LIMIT`, łącznie dokładnie 4 żądania;
- **brzeg**: suma 0,999999 → wysłanie przechodzi do modelu; dokładnie 1,00 → odmowa;
- **ponowienie analizy przez północ ze zmianą czasu**: wydane 1,00 zasiane na 2026-10-25 (dzień 25 h); pierwsza analiza rusza (`hang` → +0,07); ponowienie o 23:59 CET (`2026-10-25 22:59 UTC`) → `ConversationError`, brak żądania; ponowienie o 00:00 CET (`2026-10-25 23:00 UTC`) → żądanie, lista zapisana;
- **strona**: nieudana analiza przy osiągniętym limicie pokazuje godzinę resetu i nie ma przycisku „Try again”; poniżej limitu przycisk jest;
- **bez regresji**: start przy wyczerpanym limicie dalej odmawiany bez wywołania; tura pożegnalna poniżej limitu dalej się wykonuje.

#### 5. Ręczne mutanty fazy 2

**File**: `scripts/mutation/manual_mutants.py`, `scripts/mutation/accepted_survivors.md`

**Intent**: Usunięte sprawdzenia dachu muszą wywracać testy.

**Contract** (wszystkie `expected="killed"`):
- `M31` — `send_message` bez sprawdzenia dachu;
- `M32` — `run_agent_turn` bez sprawdzenia dachu;
- `M33` — gałąź dachu w `send_message` bez `end_conversation` (odmowa, ale rozmowa zostaje aktywna);
- `M34` — `analyze_conversation` bez dachu na ponowienie.
Docstring modułu i nagłówek rejestru: lista id do `M34`.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C2 M31 M32 M33 M34`

#### Manual Verification:

- Lokalnie z prawdziwym modelem (`uv run --env-file .env python manage.py runserver`): po dopisaniu w trakcie aktywnej rozmowy wpisu `LLMCharge` na dziś z kwotą równą `DAILY_BUDGET_USD` (kroki w Manual Testing Steps) kolejna wiadomość kończy rozmowę z komunikatem o limicie i godziną resetu, a w logach serwera nie ma nowego wywołania modelu

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie ręcznego sprawdzenia przez człowieka przed fazą 3.

---

## Faza 3: Domknięcie

### Overview

Wzorzec testu budżetu w cookbooku test-planu, notatka fazy, pełny przebieg mutacji z rejestrem przeżyć i dopisek do Q-07 w roadmapie.

### Changes Required:

#### 1. Test-plan

**File**: `context/foundation/test-plan.md`

**Intent**: Następny autor testu budżetu wie, jak go napisać; status fazy jest aktualny.

**Contract**:
- §3 wiersz 4: Status `complete`.
- §6.4 (zamiast „TBD”): lokalizacja (`tests/test_budget.py` unit, `tests/test_budget_ceiling.py` przepływy); zasada „każda ścieżka wywołania modelu kończy się zapisem kosztu: `Message`, wynik analizy albo `LLMCharge`”; jak symulować dzień (literały UTC, `now` z parametru, dwa zegary); kwoty z rachunkiem w komentarzu; sprawdzanie „brak żądania po dachu” przez `len(fake_provider.requests)`; dlaczego bez E2E (cost × signal); testy wzorcowe z fazy.
- §6.6: notatka „Phase 4 — Budget ceiling (data)” — co research obalił (nieudana próba = 0, brak dachu w rozmowie), co zmieniono, wynik mutacji; punkty do `/10x-test-plan --refresh`: §2 Risk Response Guidance #4 „What would prove protection” przeformułować na niezmiennik dachu (przekroczenie tylko o wywołania rozpoczęte poniżej limitu + pierwsze analizy); Q-07 częściowo zaadresowane.

#### 2. Mutacje — pełny przebieg

**File**: `scripts/mutation/accepted_survivors.md`

**Intent**: Bramka mutacji z §5: 0 niewyjaśnionych przeżyć po zmianach w `budget.py` i `services.py`.

**Contract**: `rm -rf mutants/`, `uv run mutmut run`, `uv run mutmut results`; każde nowe przeżycie zabite testem albo z wierszem w rejestrze (`równoważny` / `brak wymagania`); cała lista ręczna kończy się kodem 0.

#### 3. Roadmapa — dopisek do Q-07

**File**: `context/foundation/roadmap.md`

**Intent**: Q-07 nie jest rozstrzygnięte (praca poza żądaniem HTTP, `max_output_tokens`), ale jego część o koszcie nieudanych prób i ponowieniach już nie jest aktualna.

**Contract**: w wierszu Q-07 jedno zdanie z datą: koszt timeoutu i nieudanych prób jest liczony (szacunek albo `usage`), ponowienia zatrzymuje dach dnia (`testing-budget-ceiling`). Pytanie zostaje otwarte, więc GitHub #14 i Linear LUK-27 bez zmian (reguły synchronizacji w `lessons.md` dotyczą rozstrzygnięcia).

### Success Criteria:

#### Automated Verification:

- Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py`
- Każde przeżycie mutmut ma wiersz w rejestrze: `rm -rf mutants && uv run mutmut run && uv run mutmut results`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Przegląd §6.4 i §6.6 test-planu oraz dopisku Q-07: zgodne z decyzjami tego planu

**Implementation Note**: Po zielonej weryfikacji poczekaj na potwierdzenie przeglądu; PR i push wykonuje użytkownik.

---

## Testing Strategy

### Unit Tests:

- `spent_today` z księgą: dziś / wczoraj / dokładnie północ / inny użytkownik; suma trzech źródeł.
- Dni zmiany czasu (2026-03-29: 23 h, 2026-10-25: 25 h): koszty po obu stronach północy Berlina, chwile UTC wpisane ręcznie.
- `next_turn_estimate`, `limit_reached` na brzegu (0,999999 / 1,00).
- `LLMError`: co niesie przy timeoucie, złym schemacie, pustej odpowiedzi z `usage`, 503.

### Integration Tests:

- Każda ścieżka kosztu (tura i analiza: timeout, pusta odpowiedź, 503, spóźnienie, nieudany zapis) → dokładny przyrost sumy dnia i liczba żądań.
- Scenariusze dachu: jedno drogie wywołanie, ponowienia zatrzymane na limicie, ponowienie analizy przez północ 25 października, strona bez „Try again” przy wyczerpanym dniu, brak regresji startu i tury pożegnalnej.

### Manual Testing Steps:

1. `.env` z kluczem (bez zmiany `DAILY_BUDGET_USD` — przy limicie ≤ 0,03 start rozmowy jest odmawiany przez `is_exhausted`, a przy wyższym rozmowę kończy tura pożegnalna, zanim zadziała dach), `uv run --env-file .env python manage.py runserver`.
2. Zacząć rozmowę i wymienić jedną-dwie wiadomości (poniżej limitu bez zmian).
3. W drugim terminalu `uv run --env-file .env python manage.py shell`: utworzyć `LLMCharge` dla aktywnej rozmowy (`user` = jej użytkownik, `kind=turn`, `reason=estimate`, `cost_usd = settings.DAILY_BUDGET_USD`, `charged_at = timezone.now()`).
4. Wysłać wiadomość: odmowa z komunikatem o limicie, rozmowa zakończona `DAILY_LIMIT`, godzina resetu na stronie; w logach serwera brak wywołania modelu po odmowie.
5. Usunąć wpis w tym samym shellu — inaczej limit zostaje wyczerpany do północy Berlina.

## Performance Considerations

`spent_today` dostaje trzecie zapytanie agregujące (indeks na `charged_at`); wywoływane kilka razy na żądanie, przy max 10 użytkownikach bez znaczenia.

## Migration Notes

Migracja `0006` tylko dodaje tabelę — bezpieczna dla Railway (pre-deploy `migrate`). Istniejące dane bez zmian; historyczne nieudane próby zostają z kosztem 0. Wycofanie: revert commitu i migracji wstecz (`migrate conversations 0005`) — tabela księgi znika razem z wpisami.

## References

- Research: `context/changes/testing-budget-ceiling/research.md`
- Test-plan: `context/foundation/test-plan.md` §2 (ryzyko #4, Risk Response Guidance), §6.1 (wzorzec potwierdzenia mutacją), §6.3 (atrapa dostawcy)
- PRD: `context/foundation/prd.md:115` (Access Control „Koszty modeli”), `:97` („Odmowa akcji”)
- Decyzja S-02 (analiza poza limitem): `context/archive/2026-10-06-post-conversation-error-list/plan.md:45`
- Roadmap Q-07: `context/foundation/roadmap.md:162`
- Wzorzec planu fazy: `context/archive/2026-10-15-testing-privacy-and-deletion-boundaries/plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Księga kosztów — każde płatne wywołanie liczy się do sumy dnia (#4)

#### Automated

- [x] 1.1 Migracja jest kompletna: `uv run python manage.py makemigrations --check --dry-run` — d37e240
- [x] 1.2 Testy przechodzą: `uv run pytest` — d37e240
- [x] 1.3 Lint i format: `uv run ruff check . && uv run ruff format --check .` — d37e240
- [x] 1.4 Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C2 M4 M5 M25 M26 M27 M28 M29 M30` — d37e240

#### Manual

- [x] 1.5 Przegląd diffu: każda oczekiwana kwota w nowych testach jest literałem z rachunkiem w komentarzu, nie wynikiem `turn_cost` / `next_turn_estimate` — d37e240

### Phase 2: Twardy dach — po osiągnięciu limitu żadne nowe płatne wywołanie (#4)

#### Automated

- [x] 2.1 Testy przechodzą: `uv run pytest` — 51e5d3a
- [x] 2.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 51e5d3a
- [x] 2.3 Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C2 M31 M32 M33 M34` — 51e5d3a

#### Manual

- [x] 2.4 Lokalnie z prawdziwym modelem (`uv run --env-file .env python manage.py runserver`): po dopisaniu w trakcie aktywnej rozmowy wpisu `LLMCharge` na dziś z kwotą równą `DAILY_BUDGET_USD` (kroki w Manual Testing Steps) kolejna wiadomość kończy rozmowę z komunikatem o limicie i godziną resetu, a w logach serwera nie ma nowego wywołania modelu — 51e5d3a

### Phase 3: Domknięcie

#### Automated

- [x] 3.1 Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py`
- [x] 3.2 Każde przeżycie mutmut ma wiersz w rejestrze: `rm -rf mutants && uv run mutmut run && uv run mutmut results`
- [x] 3.3 Testy przechodzą: `uv run pytest`
- [x] 3.4 Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [x] 3.5 Przegląd §6.4 i §6.6 test-planu oraz dopisku Q-07: zgodne z decyzjami tego planu
