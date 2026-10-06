# Pierwsza rozmowa z korektą na bieżąco (S-01) — Implementation Plan

## Overview

Budujemy gwiazdę przewodnią TalkAItive: zalogowany użytkownik wybiera jeden z 20 tematów, prowadzi tekstową rozmowę z agentem (OpenAI GPT-5.4), dostaje korektę wplecioną w odpowiedź (recast, max 1–2 najważniejsze błędy na odpowiedź) i kończy rozmowę przyciskiem „End”, potwierdzonym pożegnaniem albo przez wyczerpany dzienny budżet ($1 na osobę, reset o północy Europe/Berlin). Język rozmowy jest ustawieniem użytkownika (`en` do testów autora, `de` docelowo). Pełny transkrypt trafia do bazy jako wejście dla analizy błędów w S-02.

Realizuje FR-003, FR-004, FR-005, FR-006, FR-007, FR-012 i US-01 (bez części o pamięci i liście błędów — to S-02/S-03). Rozstrzyga otwarte pytanie #2 z PRD (limit: budżet $1/dzień, nowy dzień od północy Europe/Berlin).

## Current State Analysis

- Repo ma jedną aplikację `accounts` z własnym `User` (logowanie e-mailem). Brak kodu LLM i pakietu do API modelu (`pyproject.toml:5-11`).
- `accounts/views.py:5-7` — tymczasowa strona `home` z komentarzem „S-01 replaces it with the conversation screen”; szablon `accounts/templates/accounts/home.html`. Nazwa URL `home` jest celem `LOGIN_REDIRECT_URL` (`talkaitive/settings.py:86`).
- `tests/test_login.py:46-48` sprawdza, że `/` po zalogowaniu zwraca 200 i zawiera e-mail użytkownika — nowa strona główna musi zachować „Signed in as <email>”.
- Wzorzec danych per użytkownik: `accounts/ownership.py:15-30` (`UserOwned`, `for_user`). `lessons.md`: modele podrzędne filtrujemy przez właściciela rodzica, pojedynczy obiekt przez `get_object_or_404(Model.objects.for_user(request.user), pk=pk)`, każdy widok z `pk` ma test „B dostaje 404 na obiekt A”, nic z danych użytkownika nie trafia do admina (`tests/test_ownership.py:47-52`).
- Sekrety z env vars, fail-fast poza DEBUG (`talkaitive/settings.py:38-45`). `TIME_ZONE = "UTC"`, `USE_TZ = True` (`talkaitive/settings.py:145-149`).
- `LoginRequiredMiddleware` jest włączony (`talkaitive/settings.py:79`) — nowe widoki są domyślnie chronione.
- gunicorn na Railway: 2 workery gthread × 4 wątki, `--timeout 120` (`context/deployment/deploy-plan.md:161`). Synchroniczne wywołanie modelu się mieści, jeśli timeout SDK × próby < 120 s.
- `.env` jest już w lokalnym `.gitignore` (linia 17). Klucz LLM nie jest jeszcze ustawiony na Railway (`context/deployment/deploy-plan.md:122`).
- Admin `User` buduje formularz z `fieldsets` (`accounts/admin.py:16-31`), więc nowe pole wystarczy dodać do `fieldsets`.

## Desired End State

- Zalogowany użytkownik bez aktywnej rozmowy widzi na `/` listę 20 tematów; wybór tematu tworzy rozmowę, agent otwiera scenkę pierwszą wypowiedzią w języku z `practice_language`.
- Na ekranie rozmowy użytkownik pisze wiadomości; po wysłaniu przycisk się blokuje, widać animowany spinner i „Agent is typing…”, potem strona pokazuje odpowiedź. Agent wplata poprawną formę max 1–2 najważniejszych błędów, bez wykładu.
- „End” kończy rozmowę. Pożegnanie użytkownika → agent pyta, czy zakończyć; po potwierdzeniu rozmowa się kończy.
- Każda tura zapisuje zużycie tokenów i koszt. Gdy po kolejnej turze budżet $1 na dzień (Europe/Berlin) zostałby przekroczony, agent w tej turze naturalnie się żegna i wspomina o limicie, a rozmowa się kończy. Strona pokazuje, od kiedy można rozmawiać ponownie. Przy wyczerpanym budżecie nie da się zacząć nowej rozmowy.
- Naraz istnieje max 1 aktywna rozmowa na osobę; po zamknięciu karty `/` proponuje „Continue conversation”.
- Awaria API: wiadomość użytkownika zostaje zapisana, strona pokazuje komunikat i „Try again”.
- Produkcja: `OPENAI_API_KEY` ustawiony na Railway, autor ma `practice_language = en`, żona `de`.

### Key Discoveries:

- `accounts/ownership.py:22-30` — baza dla `Conversation`; `Message` to model podrzędny bez własnego `user`.
- `tests/test_ownership.py:8,47-52` — rejestr admina dopuszcza tylko `User` i `Group`; nowych modeli nie rejestrujemy.
- OpenAI SDK (Context7, `/openai/openai-python`): `client.responses.parse(..., text_format=<Pydantic>)` → `response.output_parsed`; `response.usage.input_tokens`, `usage.input_tokens_details.cached_tokens`, `usage.output_tokens` (zawiera tokeny rozumowania). Responses API domyślnie zapisuje odpowiedzi po stronie OpenAI (`store: true`) — wyłączamy. Wyjątki: `APITimeoutError`, `APIConnectionError`, `RateLimitError`, `APIStatusError`; `timeout` i `max_retries` na kliencie.
- SDK czyta klucz ze zmiennej `OPENAI_API_KEY`.
- Cennik GPT-5.4 (openai.com/api/pricing, 2026-10): input $2.50, cached input $0.25, output $15.00 za 1M tokenów; rezydencja danych +10%.
- `research.md` (ten folder): OpenAI to jedyna kompletna opcja „tekst teraz + głos po MVP” (Realtime GA, WebRTC z tokenem efemerycznym, rezydencja UE przez `eu.api.openai.com` dla projektu z regionem EU); do czatu zwykłe Responses API, nie Realtime; logika rozmowy zostaje w Django za cienką warstwą nad dostawcą.

## What We're NOT Doing

- **Analiza błędów i lista błędów po rozmowie** — S-02. Ustalony kierunek (wejście do planu S-02): po zakończeniu rozmowy jedno osobne wywołanie analizuje cały transkrypt i zwraca JSON z błędami (kategoria: gramatyka / słownictwo / szyk zdania, wersja błędna → poprawna); S-02 może przeanalizować też rozmowy zapisane przez S-01.
- Pamięć między rozmowami (S-03), usuwanie konta (S-04).
- Rozmowa głosowa. Wybór OpenAI ma ją ułatwić po MVP (Realtime API), ale nic głosowego tu nie budujemy.
- Streaming odpowiedzi, htmx, WebSockety — zwykły formularz + mały skrypt.
- Przegląd poprzednich rozmów przez użytkownika (PRD: brak historii).
- Wybór języka w UI — język ustawia właściciel w `/admin/`.
- Pokazywanie użytkownikowi pozostałego budżetu (PRD wymaga tylko komunikatu o wyczerpaniu).
- Tematy edytowalne w adminie — lista jest stałą w kodzie.
- Abstrakcja wielu dostawców LLM — jeden moduł `llm.py` z OpenAI; podmiana dostawcy = przepisanie tego modułu.
- Zmiana PRD/roadmapy poza synchronizacją statusu (rozstrzygnięcie pytania #2 jest zapisane w tym planie).

## Implementation Approach

Nowa aplikacja `conversations` trzyma modele, tematy, logikę budżetu, moduł LLM i widoki. Jedynym miejscem, które importuje `openai`, jest `conversations/llm.py` — reszta kodu woła `generate_turn(...)` i dostaje prosty `TurnResult`, a testy podmieniają tę funkcję atrapą (zero ruchu sieciowego w testach). Każda tura modelu zwraca ustrukturyzowany JSON `{reply, end_conversation}`; flaga służy tylko do zakończenia po potwierdzonym pożegnaniu. Koszt tury liczymy z `usage` i cennika w ustawieniach, zapisujemy przy wiadomości agenta, a „wydane dziś” to suma kosztów od ostatniej północy w Europe/Berlin. Widoki to klasyczne POST → redirect → GET; oczekiwanie pokazuje mały skrypt w szablonie.

Kolejność: dane i ustawienia → logika (LLM + budżet) testowana jednostkowo → widoki → wdrożenie z prawdziwym kluczem. Prawdziwe API pojawia się dopiero w fazie 4.

## Critical Implementation Details

- **Strefa czasowa na produkcji.** Obraz Railpack może nie mieć systemowej bazy stref czasowych; `zoneinfo.ZoneInfo("Europe/Berlin")` wtedy rzuca `ZoneInfoNotFoundError`. Dodaj zależność `tzdata` (Python używa jej jako fallbacku).
- **Kolejność wdrożenia.** Poza DEBUG brak `OPENAI_API_KEY` celowo wywala start aplikacji (jak `SECRET_KEY`). Zmienna musi być ustawiona na Railway **przed** pushem tej zmiany na `main`, inaczej pre-deploy/healthcheck padnie.
- **Timeout vs gunicorn.** `timeout` SDK × (`max_retries` + 1) musi być wyraźnie poniżej 120 s timeoutu gunicorna (30 s × 2 = 60 s), inaczej worker zostanie zabity w trakcie czekania na model.
- **Prompt caching.** Stałe instrukcje (rola, poziom, zasady recastu, temat) idą na początek; zmienne elementy (instrukcja „ostatnia tura”) jako osobny komunikat na końcu `input`, żeby nie psuć cache'owanego prefiksu.

## Phase 1: Fundament danych i ustawień

### Overview

Zależności, ustawienia LLM i budżetu, pole języka przy użytkowniku, aplikacja `conversations` z modelami, migracjami i listą tematów. Bez widoków i bez wywołań API.

### Changes Required:

#### 1. Zależności

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Dodać klienta OpenAI i bazę stref czasowych potrzebną na produkcji.

**Contract**: `uv add openai tzdata` (nie `pip install`).

#### 2. Ustawienia

**File**: `talkaitive/settings.py`

**Intent**: Wszystkie parametry LLM i budżetu w jednym miejscu, czytane z env vars tam, gdzie mają się dać zmienić bez deployu kodu; klucz API fail-fast poza DEBUG, zgodnie z wzorcem `SECRET_KEY`. Dodać `conversations` do `INSTALLED_APPS`.

**Contract**:
- `OPENAI_API_KEY` — poza DEBUG `os.environ["OPENAI_API_KEY"]`; w DEBUG `os.environ.get(...)` (może być `None`; wtedy `llm.py` rzuca czytelny błąd konfiguracji przy pierwszym wywołaniu).
- `OPENAI_BASE_URL` — env, domyślnie `"https://eu.api.openai.com/v1"` (rezydencja danych w UE; klucz z projektu OpenAI w regionie EU działa tylko z tym adresem).
- `LLM_MODEL` — env, domyślnie `"gpt-5.4"`.
- `LLM_PRICES_USD_PER_MTOK` — słownik model → `{"input", "cached_input", "output"}` jako `Decimal`; wpis dla `gpt-5.4` z narzutem +10% za rezydencję danych: 2.75 / 0.275 / 16.50 (cennik standardowy 2.50 / 0.25 / 15.00).
- `LLM_REASONING_EFFORT` — env, domyślnie najniższy wysiłek rozumowania wspierany przez GPT-5.4 (sprawdź dozwolone wartości w Context7 `/openai/openai-python` przed wpisaniem; cel: najkrótszy czas odpowiedzi w czacie).
- `LLM_TIMEOUT_SECONDS = 30`, `LLM_MAX_RETRIES = 1`.
- `DAILY_BUDGET_USD` — `Decimal` z env, domyślnie `"1.00"`.
- `BUDGET_TIME_ZONE = "Europe/Berlin"`.
- `LLM_TURN_COST_ESTIMATE_USD` — `Decimal("0.03")`, szacunek kosztu tury, gdy rozmowa nie ma jeszcze żadnej tury agenta.

#### 3. Język ćwiczeń przy użytkowniku

**File**: `accounts/models.py`, nowa migracja `accounts/migrations/0003_*.py`, `accounts/admin.py`

**Intent**: Każdy użytkownik ma swój język rozmów; autor testuje po angielsku, żona ćwiczy niemiecki równolegle. Ustawia go właściciel w `/admin/`.

**Contract**: `PracticeLanguage(models.TextChoices)` z wartościami `en` („English”), `de` („German”), zdefiniowane w `accounts/models.py` (używane też przez `Conversation`). Pole `User.practice_language = CharField(max_length=2, choices=PracticeLanguage, default="de", db_default="de")` — `db_default` zostawia DEFAULT w kolumnie, więc revert kodu bez cofnięcia migracji nie psuje tworzenia użytkowników (NOT NULL). W `UserAdmin`: pole w `fieldsets` (np. sekcja „Practice”) i w `list_display`.

#### 4. Aplikacja `conversations` i modele

**File**: `conversations/__init__.py`, `conversations/apps.py`, `conversations/models.py`, `conversations/migrations/0001_initial.py`

**Intent**: Zapis rozmów i pełnego transkryptu z zużyciem tokenów, z bazodanową gwarancją „max 1 aktywna rozmowa na osobę”. Żadnej rejestracji w adminie.

**Contract**:
- `Conversation(UserOwned)`: `topic` (`CharField(max_length=50)` **bez** `choices` — Django zapisuje `choices` w migracjach, więc każda zmiana listy tematów wymagałaby nowej migracji; poprawność klucza sprawdza serwis przez `get_topic`), `topic_title` i `topic_scenario` (`TextField`, kopia z `Topic` przy starcie — rozmowa pamięta swoją scenkę także po zmianie lub usunięciu tematu w kodzie; potrzebne też S-02), `language` (`PracticeLanguage`, kopiowany z użytkownika przy starcie), `status` (`active` / `ended`), `end_reason` (puste / `user` / `agent_goodbye` / `daily_limit`), `created_at`, `ended_at` (null). `UniqueConstraint(fields=["user"], condition=Q(status="active"), name="conversations_one_active_per_user")`.
- `Message`: `conversation` (FK, `CASCADE`, related_name `messages`), `role` (`user` / `assistant`), `text`, `created_at` (indeks), dla tur agenta: `model`, `input_tokens`, `cached_input_tokens`, `output_tokens` (nullable int), `cost_usd` (`DecimalField(max_digits=10, decimal_places=6, default=0)`). Domyślne sortowanie po `created_at`, `id`.
- Metoda/właściwość na `Conversation` mówiąca, czy rozmowa czeka na odpowiedź agenta: aktywna i (brak wiadomości albo ostatnia wiadomość ma `role=user`).
- Type hints na metodach (pod przyszły `mypy` + `django-stubs`).

#### 5. Tematy

**File**: `conversations/topics.py`

**Intent**: 20 stałych tematów — codzienne sytuacje z życia w Niemczech dla persony z PRD. Tytuł widzi użytkownik (UI po angielsku), opis scenki dostaje model.

**Contract**: niemutowalny typ `Topic(key: str, title: str, scenario: str)`, krotka `TOPICS` (20 pozycji, unikalne `key` w formie slug) i funkcja `get_topic(key) -> Topic | None` (`None` dla nieznanego klucza). Listę można zmieniać bez migracji; stare rozmowy korzystają z własnej kopii tytułu i scenariusza. Lista (key — title):
1. `dog-walk` — Walking the dog: chatting with another dog owner
2. `supermarket` — Supermarket: asking where to find something
3. `bakery` — Bakery: ordering breakfast rolls
4. `neighbour-stairwell` — Neighbour in the stairwell: small talk
5. `neighbour-parcel` — Picking up a parcel from a neighbour
6. `doctor-appointment` — Calling a doctor's office for an appointment
7. `pharmacy` — Pharmacy: asking for something for a cold
8. `colleague-weekend` — Weekend plans with a colleague
9. `playground` — Playground: chatting with another parent
10. `post-office` — Post office: sending a parcel
11. `hairdresser` — Hairdresser: explaining the cut you want
12. `restaurant` — Restaurant: ordering and paying
13. `public-transport` — Public transport: ticket problem and directions
14. `train-delay` — Train delay: talking with a fellow passenger
15. `landlord-heating` — Reporting a broken heater to the landlord
16. `registration-office` — Registering your address at the Bürgeramt
17. `bus-stop-weather` — Weather small talk at the bus stop
18. `birthday-party` — Birthday party: meeting a friend's friends
19. `sports-club` — Joining a local sports club
20. `car-workshop` — Booking a tyre change at a car workshop

### Success Criteria:

#### Automated Verification:

- Migracje bez rozjazdu: `uv run python manage.py makemigrations --check --dry-run`
- Testy przechodzą: `uv run pytest` (w tym nowe: rozmowa użytkownika A niewidoczna przez `for_user` dla B; druga aktywna rozmowa tego samego użytkownika → `IntegrityError` (sprawdzane w `pytest.raises` + `transaction.atomic()`), zakończona + nowa aktywna → OK; usunięcie użytkownika usuwa jego rozmowy i wiadomości; `practice_language` domyślnie `de`; `TOPICS` ma 20 unikalnych kluczy; `get_topic` zwraca temat dla znanego klucza i `None` dla nieznanego; `LLM_MODEL` ma wpis w `LLM_PRICES_USD_PER_MTOK`)
- Test rejestru admina nadal przechodzi: `uv run pytest tests/test_ownership.py`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- `uv run python manage.py check`

#### Manual Verification:

- W `/admin/` przy użytkowniku widać i da się zmienić „Practice language”; modele rozmów nie pojawiają się w adminie

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Moduł LLM i budżet

### Overview

Logika bez widoków: wywołanie modelu z promptem rozmowy i logika budżetu dziennego. Wszystko testowane jednostkowo z atrapą klienta i stałymi datami.

### Changes Required:

#### 1. Budżet dzienny

**File**: `conversations/budget.py`

**Intent**: Jedno miejsce na zasady limitu: koszt tury, wydane dziś, czy budżet wyczerpany, czy następna tura ma być ostatnią i od kiedy wolno rozmawiać ponownie. Funkcje przyjmują `now` jako parametr, żeby testy mogły użyć stałych dat (w tym zmiany czasu letniego).

**Contract**:
- `turn_cost(model, input_tokens, cached_input_tokens, output_tokens) -> Decimal` = `(input − cached) × input + cached × cached_input + output × output`, ceny za 1M z `LLM_PRICES_USD_PER_MTOK`; brak modelu w cenniku → `ImproperlyConfigured`.
- `day_start(now) -> datetime` — ostatnia północ w `BUDGET_TIME_ZONE` (aware). `next_reset(now) -> datetime` — następna północ.
- `spent_today(user, now) -> Decimal` — suma `Message.cost_usd` z rozmów użytkownika (`Conversation.objects.for_user(user)`) dla wiadomości z `created_at >= day_start(now)`.
- `is_exhausted(user, now) -> bool` — `True`, gdy od `day_start(now)` jest rozmowa użytkownika zakończona z `daily_limit` (`ended_at >= day_start(now)`) **lub** `spent_today + LLM_TURN_COST_ESTIMATE_USD >= DAILY_BUDGET_USD`. To jedyny predykat „budżet wyczerpany” — używają go `/`, `start_conversation` i komunikat o resecie. Bez tego po zakończeniu z `daily_limit` przy `spent_today` tuż poniżej budżetu `/` znów pokazałby tematy, a nowa rozmowa żegnałaby się już w turze otwierającej.
- `is_final_turn(user, conversation, now) -> bool` — `spent_today + szacunek >= DAILY_BUDGET_USD`, gdzie szacunek = koszt ostatniej tury agenta w tej rozmowie albo `LLM_TURN_COST_ESTIMATE_USD`, gdy jej brak.

#### 2. Moduł LLM

**File**: `conversations/llm.py`

**Intent**: Jedyne miejsce z importem `openai`. Buduje prompt z tematu, języka i historii, wywołuje Responses API z ustrukturyzowanym wyjściem i zwraca prosty wynik albo jeden typ błędu, który widoki umieją pokazać.

**Contract**:
- `TurnResult` (dataclass): `reply: str`, `end_conversation: bool`, `model: str`, `input_tokens: int`, `cached_input_tokens: int`, `output_tokens: int`.
- `class LLMError(Exception)` — rzucany przy każdym błędzie SDK (`APITimeoutError`, `APIConnectionError`, `RateLimitError`, `APIStatusError`), braku klucza, odmowie modelu albo pustym `output_parsed`; błąd logowany (bez treści rozmowy w logu).
- `generate_turn(*, topic: Topic, language: str, history: Sequence[tuple[str, str]], final_turn: bool) -> TurnResult`.
- Wywołanie: `client.responses.parse(model=LLM_MODEL, instructions=..., input=[...], text_format=AgentTurn, reasoning={"effort": LLM_REASONING_EFFORT}, store=False)`; klient z `api_key=OPENAI_API_KEY`, `base_url=OPENAI_BASE_URL`, `timeout=LLM_TIMEOUT_SECONDS`, `max_retries=LLM_MAX_RETRIES`. `AgentTurn` to model Pydantic `{reply: str, end_conversation: bool}`.
- Pusta historia (start rozmowy) → do `input` trafia krótka niezapisywana wiadomość „otwórz scenkę”; agent zaczyna rozmowę.
- `final_turn=True` → na końcu `input` dodatkowa instrukcja: to ostatnia odpowiedź, odpowiedz krótko, naturalnie się pożegnaj i powiedz, że dzienny limit rozmów się skończył.
- Instrukcje (stałe, na początku, w kolejności stabilnej dla cache): agent jest partnerem do rozmowy w scenariuszu tematu, mówi wyłącznie w języku `language` na poziomie B1–B2 (krótkie, naturalne wypowiedzi, jedno pytanie naraz); gdy wypowiedź użytkownika ma błędy, wplata poprawną formę **max 1–2 najważniejszych** (gramatyka, słownictwo, szyk zdania) naturalnie w odpowiedź, bez tłumaczenia reguł i bez wyliczania błędów; pomija literówki i interpunkcję, jeśli nie zmieniają sensu; gdy użytkownik się żegna, odpowiada w scence i krótko pyta, czy zakończyć rozmowę — `end_conversation=true` wyłącznie po wyraźnym potwierdzeniu; nie przerywa rozmowy wykładem.

### Success Criteria:

#### Automated Verification:

- Testy budżetu przechodzą: `uv run pytest tests/test_budget.py` (koszt tury z cached tokens; `day_start` / `next_reset` dla godzin tuż przed i po północy Europe/Berlin, także w dniu zmiany czasu; wiadomości z wczoraj nie liczą się do dziś; wydatki innego użytkownika się nie liczą; `is_final_turn` z i bez wcześniejszej tury; `is_exhausted` jest `True` po zakończeniu rozmowy z `daily_limit` dziś, nawet gdy `spent_today` < budżetu, i `False` po północy; `is_exhausted` jest `True`, gdy budżetu nie starcza na `LLM_TURN_COST_ESTIMATE_USD`; brak modelu w cenniku → `ImproperlyConfigured`)
- Testy LLM przechodzą z atrapą klienta, bez sieci: `uv run pytest tests/test_llm.py` (klient dostaje `base_url` z `OPENAI_BASE_URL`; przekazuje `store=False`, model, effort i język do wywołania; język `en` vs `de` trafia do instrukcji; `final_turn` dodaje instrukcję pożegnania na końcu `input`; mapuje `usage` na `TurnResult`; wyjątek SDK i pusty wynik → `LLMError`)
- Cały zestaw: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Ekrany i przepływ rozmowy

### Overview

Strona główna, start rozmowy, ekran czatu, wysyłanie, ponawianie, kończenie i komunikat o limicie. Widoki są cienkie: logika tur żyje w jednej funkcji serwisowej.

### Changes Required:

#### 1. Serwis tury rozmowy

**File**: `conversations/services.py`

**Intent**: Jedna ścieżka dla „wygeneruj odpowiedź agenta” używana przez start, wysłanie i ponowienie: sprawdza budżet, woła `llm.generate_turn`, zapisuje wiadomość agenta z kosztem i kończy rozmowę, gdy trzeba.

**Contract**:
- `start_conversation(user, topic_key, now) -> Conversation` — odmawia, gdy `get_topic(topic_key)` zwraca `None`; kopiuje `title` i `scenario` tematu do `topic_title` / `topic_scenario`; odmawia, gdy `is_exhausted`; odmawia, gdy użytkownik ma już aktywną rozmowę (`try: with transaction.atomic(): Conversation.objects.create(...)` / `except IntegrityError` — bez zagnieżdżonego `atomic()` złapany błąd psuje bieżącą transakcję i kolejne zapytania rzucają `TransactionManagementError`); kopiuje `user.practice_language` do `language`; potem `run_agent_turn`.
- `send_message(conversation, text, now)` — tylko dla aktywnej rozmowy, która nie czeka na odpowiedź; zapisuje wiadomość użytkownika, potem `run_agent_turn`.
- `run_agent_turn(conversation, now)` — `final = is_final_turn(...)`; `generate_turn(topic=Topic(conversation.topic, conversation.topic_title, conversation.topic_scenario), ..., final_turn=final)` (temat z kopii w rozmowie, nie z `TOPICS`); zapisuje `Message(role=assistant, …, cost_usd=turn_cost(...))`; jeśli `final` → koniec z `daily_limit`, w przeciwnym razie jeśli `end_conversation` → koniec z `agent_goodbye`. `LLMError` przepuszcza wyżej, nie zapisując niczego poza wiadomością użytkownika.
- `end_conversation(conversation, reason, now)` — ustawia `status=ended`, `end_reason`, `ended_at`; idempotentne.
- Ochrona przed podwójnym wysłaniem po stronie serwera (JS to tylko wygoda): `send_message` sprawdza „czeka na odpowiedź” i zapisuje wiadomość użytkownika w jednym krótkim `transaction.atomic()` z `Conversation.objects.select_for_update()`; `run_agent_turn` woła `generate_turn` **poza** transakcją, a przed zapisem odpowiedzi agenta w nowym `atomic()` + `select_for_update()` ponownie sprawdza, że rozmowa jest aktywna i nadal czeka na odpowiedź — jeśli nie (równoległe retry/wysłanie już odpowiedziało), wynik odrzuca bez zapisu. Koszt odrzuconej tury nie trafia do budżetu (max jedna tura; twardy limit w panelu OpenAI zostaje drugą linią obrony).

#### 2. Widoki i URL-e

**File**: `conversations/views.py`, `conversations/urls.py`, `talkaitive/urls.py`, `accounts/urls.py`, `accounts/views.py`, `accounts/templates/accounts/home.html` (usunięcie)

**Intent**: Strona główna z S-01 zastępuje placeholder z `accounts`. Każdy obiekt rozmowy pobierany przez `for_user` (cudza rozmowa → 404). Wzorzec POST → redirect → GET. Typy na sygnaturach widoków.

**Contract** (nazwa URL `home` zostaje):
- `GET /` (`home`) — „Signed in as <email>”; jeśli aktywna rozmowa → link „Continue conversation”; jeśli budżet wyczerpany → komunikat z godziną `next_reset` w Europe/Berlin; inaczej lista 20 tematów (formularz POST na start).
- `POST /conversations/start/` (`conversation_start`) — `start_conversation`; redirect do rozmowy; `LLMError` → redirect do rozmowy w stanie „czeka na odpowiedź”.
- `GET /conversations/<pk>/` (`conversation_detail`) — transkrypt; aktywna: pole wiadomości + „End”, a jeśli czeka na odpowiedź → komunikat o błędzie + „Try again” zamiast pola; zakończona: informacja o zakończeniu (przy `daily_limit` z godziną, od kiedy można rozmawiać ponownie) + link do strony głównej.
- `POST /conversations/<pk>/messages/` (`conversation_send`) — pusta wiadomość albo rozmowa czekająca/zakończona → bez wywołania modelu, redirect z komunikatem.
- `POST /conversations/<pk>/retry/` (`conversation_retry`) — tylko gdy czeka na odpowiedź → `run_agent_turn`.
- `POST /conversations/<pk>/end/` (`conversation_end`) — koniec z `user`.
- Usunąć `home` z `accounts/views.py` i `accounts/urls.py` oraz szablon `accounts/home.html`; `talkaitive/urls.py` dołącza `conversations.urls`.

#### 3. Szablony i wskaźnik oczekiwania

**File**: `conversations/templates/conversations/home.html`, `conversations/templates/conversations/detail.html`, `accounts/templates/base.html`

**Intent**: Proste, czytelne ekrany w stylu obecnego `base.html`. Podczas czekania na model użytkownik widzi ruch, nie tylko tekst (NFR z PRD).

**Contract**: przy wysłaniu formularza (wiadomość, start tematu, „Try again”) kilka linii JS w szablonie blokuje przycisk i pokazuje element z **animowanym spinnerem w czystym CSS** (`@keyframes`, bez pliku GIF i bez zależności) oraz tekstem „Agent is typing…”; bez JS formularze nadal działają. Wiadomości agenta i użytkownika wizualnie rozróżnione; po załadowaniu strona przewija się do ostatniej wiadomości. Style w `base.html` (jedno miejsce na CSS). `base.html` dostaje blok `{% for message in messages %}` (dziś go nie ma), żeby komunikaty z `django.contrib.messages` po przekierowaniach (pusta wiadomość, rozmowa zakończona, start odrzucony) były widoczne.

**Dodane 2026-10-06 (decyzja użytkownika w trakcie fazy 3)**: w polu wiadomości **Enter wysyła** wiadomość, **Shift+Enter** wstawia nową linię — na wszystkich urządzeniach, także na telefonie (tam nowej linii nie da się wpisać; akceptujemy, wiadomości w czacie są krótkie). Wysyłka przez `form.requestSubmit()` (ta sama ścieżka co przycisk „Send”: spinner, blokada przycisku, walidacja `required`), Enter w trakcie składania znaku (`event.isComposing`) nie wysyła. `<textarea>` dostaje `enterkeyhint="send"`. Bez JS Enter dalej wstawia nową linię, a wysyła przycisk. Brak testu automatycznego (brak narzędzia do testów JS) — sprawdzane ręcznie.

**Dodane 2026-10-06 (po przeglądzie fazy 3, `reviews/impl-review-phase-3.md`)**:
- Dodatki z implementacji: wspólny fragment `conversations/templates/conversations/_reset_notice.html` (godzina resetu na `/` i na ekranie rozmowy); skrypt w `base.html` działa na każdej stronie i przy wysyłce blokuje wszystkie przyciski; po powrocie z back/forward cache strona się odblokowuje.
- F1 — tura w toku: `Conversation.agent_turn_started_at` (migracja `conversations/0002`; rollback `migrate conversations zero` obejmuje ją). Znacznik ustawiany pod blokadą wiersza razem z utworzeniem rozmowy / zapisem wiadomości użytkownika / sprawdzeniem retry, czyszczony po zapisie odpowiedzi lub po dowolnym wyjątku (tylko własny). Ważny `LLM_TIMEOUT_SECONDS × (LLM_MAX_RETRIES + 1) + 30` s. W tym czasie retry jest odrzucany bez wywołania modelu, a ekran rozmowy pokazuje spinner „Agent is typing…” zamiast błędu i odświeża się co 5 s (`<meta http-equiv="refresh">` w nowym `{% block head %}` w `base.html`).
- F2 — wiadomość użytkownika max `services.MAX_MESSAGE_LENGTH = 2000` znaków (po `strip()`), ten sam `maxlength` na `<textarea>`.
- F3 — `pydantic.ValidationError` z `responses.parse` (ucięty/niepoprawny JSON) → `LLMError` w `llm.py`, bez łańcucha wyjątku i bez treści w logu. Błąd nie trafia do historii wysyłanej do modelu; retry wysyła tę samą historię.
- F4 — widoki typowane `AuthenticatedHttpRequest` (`user: User`, w `conversations/views.py`); `budget.py` przyjmuje `User`.

### Success Criteria:

#### Automated Verification:

- Testy widoków przechodzą z atrapą `generate_turn`: `uv run pytest tests/test_conversation_views.py` (start tworzy rozmowę z wiadomością otwierającą, językiem użytkownika i kopią tytułu i scenariusza tematu; nieznany klucz tematu → start odrzucony bez wywołania modelu; wysłanie zapisuje obie wiadomości i koszt; `end_conversation=true` kończy z `agent_goodbye`; tura przy wyczerpywanym budżecie dostaje `final_turn=true` i kończy z `daily_limit`; start przy wyczerpanym budżecie odrzucony i `/` pokazuje godzinę resetu; druga aktywna rozmowa niemożliwa, `/` pokazuje „Continue conversation”; `LLMError` zostawia wiadomość użytkownika i pokazuje „Try again”, a retry kończy turę; wysłanie do zakończonej lub czekającej rozmowy nie woła modelu; pusta wiadomość nie woła modelu, a strona po przekierowaniu pokazuje komunikat; gdy w trakcie `generate_turn` (atrapa z efektem ubocznym) inna ścieżka zapisze już odpowiedź agenta, druga odpowiedź nie jest zapisywana; „End” kończy z `user`; użytkownik B dostaje 404 na GET i każdy POST rozmowy użytkownika A; niezalogowany jest przekierowany do logowania)
- Istniejące testy logowania przechodzą bez zmian asercji: `uv run pytest tests/test_login.py`
- Cały zestaw: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- `uv run python manage.py check`

#### Manual Verification:

- Lokalnie z prawdziwym kluczem z `.env` (najpierw kroki 1–2 z fazy 4: konto OpenAI i `.env`; bez klucza każdy start kończy się od razu na „Try again”): przejście po ekranach (lista tematów, rozmowa, „End”, komunikat o limicie) wygląda czytelnie na telefonie i desktopie
- Spinner się kręci i przycisk jest zablokowany do czasu odpowiedzi
- Enter wysyła wiadomość (ze spinnerem i blokadą jak przycisk „Send”), Shift+Enter wstawia nową linię, pusty Enter nic nie wysyła; na telefonie klawisz Enter ma etykietę „Send”/„Wyślij”

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Wdrożenie z prawdziwym modelem

### Overview

Prawdziwy klucz lokalnie i na produkcji, ręczny test jakości rozmowy po angielsku, deploy i ustawienie języków kont. Kroki z „(you)” wykonuje użytkownik; agent nie robi `git push`. Kroki 1–2 (konto OpenAI, `.env`) wykonuje się już przed ręcznym testem fazy 3 — tam są potrzebne do zobaczenia ekranu rozmowy i spinnera.

### Changes Required:

#### 1. Konto OpenAI (you)

**File**: — (panel platform.openai.com)

**Intent**: Klucz tylko dla tej aplikacji, dane przetwarzane w UE i twardy sufit wydatków niezależny od budżetu w kodzie (ochrona przed błędem w liczeniu kosztów).

**Contract**: projekt „talkaitive” utworzony z regionem danych **EU** (rezydencja EEA+CH, endpoint `eu.api.openai.com`) i z własnym kluczem API; przed dalszymi krokami sprawdzić, że `gpt-5.4` jest dostępny w tym projekcie (jeśli nie — wybrać najbliższy dostępny model, zaktualizować `LLM_MODEL` i cennik); miesięczny limit/alert wydatków projektu (np. $20). Klucz nigdy nie trafia do czatu ani repo.

#### 2. Lokalne uruchomienie (you + agent)

**File**: `.env` (lokalny, poza gitem), `CLAUDE.md` (sekcja „TalkAItive — project notes”)

**Intent**: Lokalnie aplikacja czyta klucz z `.env`; sposób uruchamiania zapisany w notatkach projektu.

**Contract**: `.env` z `OPENAI_API_KEY=...` (tworzy użytkownik); uruchamianie `uv run --env-file .env python manage.py runserver`. W `CLAUDE.md` (poza blokiem `10x-cli`) dopisać do listy env vars `OPENAI_API_KEY` i `LLM_MODEL` / `DAILY_BUDGET_USD` oraz sposób uruchamiania z `--env-file`.

#### 3. Produkcja (you approve, then you push)

**File**: Railway (serwis `web`), `context/deployment/deploy-plan.md`

**Intent**: Zmienna ustawiona przed deployem, potem push, potem ustawienie języków kont; dokumentacja wdrożenia aktualna.

**Contract**: `OPENAI_API_KEY` na serwisie `web` ustawiony przez `--stdin` (klucz nie pojawia się w treści komendy) — **przed** pushem; push na `main` wykonuje użytkownik; w `/admin/` autor `practice_language=en`, żona `de`. W `deploy-plan.md`: zmienna w tabeli „`web` variables” i zamknięcie punktu „LLM API key” w „Out of scope / follow-ups”. `web-settings.json` bez zmian (ustawienia serwisu się nie zmieniają).

### Success Criteria:

#### Automated Verification:

- Pełny zestaw przed pushem: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
- Symulacja produkcji: `DEBUG=False SECRET_KEY=x OPENAI_API_KEY=x ALLOWED_HOSTS=localhost uv run python manage.py check --deploy` (bez nowych ostrzeżeń poza zaakceptowanymi w `deploy-plan.md`)
- Brak klucza poza DEBUG wywala start: `DEBUG=False SECRET_KEY=x uv run python manage.py check` kończy się `KeyError: 'OPENAI_API_KEY'`
- Po deployu: `curl -sI https://web-production-5e685.up.railway.app/healthz/` → 200

#### Manual Verification:

- Lokalnie z prawdziwym kluczem i `practice_language=en`: pełna rozmowa na 2 tematy; recast pojawia się naturalnie, max 1–2 poprawki na odpowiedź, bez wykładu; odpowiedź przychodzi w akceptowalnym czasie
- Pożegnanie w rozmowie → agent pyta o zakończenie; potwierdzenie kończy rozmowę
- Test limitu lokalnie z `DAILY_BUDGET_USD=0.05`: agent żegna się z informacją o limicie, `/` pokazuje godzinę resetu (północ Europe/Berlin)
- `OPENAI_API_KEY` ustawiony na Railway przed pushem; po pushu produkcja działa, rozmowa po angielsku działa na produkcji
- W panelu OpenAI koszt testów zgadza się z grubsza z sumą `cost_usd` w bazie

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `budget.py`: koszt z cached tokens, granice dnia Europe/Berlin (przed/po północy, dzień zmiany czasu), izolacja wydatków między użytkownikami, `is_final_turn`.
- `llm.py`: kształt wywołania (`store=False`, model, effort, instrukcje z językiem i tematem, instrukcja ostatniej tury na końcu `input`), mapowanie `usage`, mapowanie wyjątków na `LLMError` — klient OpenAI zastąpiony atrapą.
- Modele: ograniczenie „1 aktywna”, kaskadowe usuwanie, `for_user`.

### Integration Tests:

- Widoki przez klienta testowego Django z atrapą `generate_turn`: pełny przepływ start → wiadomości → koniec (przyciskiem, pożegnaniem, limitem), błąd API i ponowienie, izolacja użytkowników (404), przekierowanie niezalogowanych.

### Manual Testing Steps:

1. Ustaw sobie `practice_language=en` w `/admin/`, uruchom `uv run --env-file .env python manage.py runserver`.
2. Wybierz temat „Bakery”, odpowiadaj z celowymi błędami (np. „Yesterday I go to the shop”) — sprawdź, że agent naturalnie powtarza poprawną formę.
3. Napisz „Bye, see you!” — agent powinien zapytać, czy kończyć; potwierdź.
4. Zamknij kartę w trakcie rozmowy, wróć na `/` — „Continue conversation”.
5. Ustaw `DAILY_BUDGET_USD=0.05`, prowadź rozmowę do pożegnania z limitem; sprawdź komunikat z godziną resetu.

## Performance Considerations

- Każda tura wysyła całą historię; przy ~20 turach to ok. 65 tys. tokenów wejścia na rozmowę. Automatyczny prompt caching OpenAI obniża koszt powtarzanego prefiksu (cached input $0.25 zamiast $2.50).
- Wywołanie modelu blokuje wątek gunicorna na kilka sekund; przy 2 użytkownikach i 8 wątkach to nie problem.
- `spent_today` to jedna agregacja SQL po zaindeksowanym `created_at`.

## Migration Notes

- Dwie nowe migracje: `accounts.0003` (pole z wartością domyślną `de` — istniejące konta dostają `de`) i `conversations.0001`. Obie bezpieczne dla istniejących danych; stosuje je pre-deploy `migrate` na Railway.
- Rollback, w tej kolejności (dane rozmów przepadają — akceptowalne na tym etapie):
  1. Póki wdrożony kod ma jeszcze pliki migracji: na produkcji `railway ssh --service web -i ~/.ssh/id_ed25519_railway` → `python manage.py migrate conversations zero` i `python manage.py migrate accounts 0002`. Po revercie tych plików już nie ma i migracji nie da się cofnąć (pre-deploy robi tylko `migrate` w przód).
  2. Odwrócenie commitu; push wykonuje użytkownik.
  Pominięcie kroku 1 zostawia osierocone tabele `conversations_*` i kolumnę `practice_language` (z `db_default`, więc nieszkodliwą).

## References

- Research: `context/changes/first-corrected-conversation/research.md` (wybór dostawcy, głos po MVP, rezydencja UE, ryzyko STT dla listy błędów)
- Infrastruktura: `context/foundation/infrastructure.md:153` (workery/timeout gunicorna przy wolnych wywołaniach LLM)
- PRD: `context/foundation/prd.md` (FR-003…FR-007, FR-012, US-01, Open Question #2)
- Roadmapa: `context/foundation/roadmap.md` (S-01)
- Reguły: `context/foundation/lessons.md` („Dane per użytkownik…”, „Widoki szczegółów…”)
- Wzorzec własności danych: `accounts/ownership.py:15-30`, `tests/test_ownership.py`
- Wzorzec sekretów: `talkaitive/settings.py:38-45`
- Wdrożenie: `context/deployment/deploy-plan.md`
- OpenAI Python SDK: Context7 `/openai/openai-python` (Responses API `parse`, błędy, timeouty); cennik: https://openai.com/api/pricing/

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Fundament danych i ustawień

#### Automated

- [x] 1.1 Migracje bez rozjazdu: `uv run python manage.py makemigrations --check --dry-run` — 8d8d845
- [x] 1.2 Testy przechodzą: `uv run pytest` (modele, ograniczenie 1 aktywnej, kaskada, `practice_language`, tematy, cennik) — 8d8d845
- [x] 1.3 Test rejestru admina nadal przechodzi: `uv run pytest tests/test_ownership.py` — 8d8d845
- [x] 1.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 8d8d845
- [x] 1.5 `uv run python manage.py check` — 8d8d845

#### Manual

- [x] 1.6 W `/admin/` widać i da się zmienić „Practice language”; modele rozmów nie pojawiają się w adminie — 8d8d845

### Phase 2: Moduł LLM i budżet

#### Automated

- [x] 2.1 Testy budżetu przechodzą: `uv run pytest tests/test_budget.py` — 897d81c
- [x] 2.2 Testy LLM przechodzą z atrapą klienta, bez sieci: `uv run pytest tests/test_llm.py` — 897d81c
- [x] 2.3 Cały zestaw: `uv run pytest` — 897d81c
- [x] 2.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 897d81c

### Phase 3: Ekrany i przepływ rozmowy

#### Automated

- [x] 3.1 Testy widoków przechodzą z atrapą `generate_turn`: `uv run pytest tests/test_conversation_views.py` — 9594f51
- [x] 3.2 Istniejące testy logowania przechodzą bez zmian asercji: `uv run pytest tests/test_login.py` — 9594f51
- [x] 3.3 Cały zestaw: `uv run pytest` — 9594f51
- [x] 3.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 9594f51
- [x] 3.5 `uv run python manage.py check` — 9594f51

#### Manual

- [x] 3.6 Przejście po ekranach wygląda czytelnie na telefonie i desktopie — 9594f51
- [x] 3.7 Spinner się kręci i przycisk jest zablokowany do czasu odpowiedzi — 9594f51
- [x] 3.8 Enter wysyła wiadomość, Shift+Enter wstawia nową linię (także na telefonie) — 9594f51

### Phase 4: Wdrożenie z prawdziwym modelem

#### Automated

- [x] 4.1 Pełny zestaw przed pushem: `uv run pytest && uv run ruff check . && uv run ruff format --check .` — c602ec2
- [x] 4.2 Symulacja produkcji: `check --deploy` bez nowych ostrzeżeń — c602ec2
- [x] 4.3 Brak klucza poza DEBUG wywala start (`KeyError: 'OPENAI_API_KEY'`) — c602ec2
- [ ] 4.4 Po deployu: `/healthz/` → 200

#### Manual

- [x] 4.5 Lokalnie z prawdziwym kluczem: pełna rozmowa na 2 tematy, naturalny recast max 1–2 poprawki, akceptowalny czas odpowiedzi — c602ec2
- [x] 4.6 Pożegnanie → agent pyta o zakończenie; potwierdzenie kończy rozmowę — c602ec2
- [x] 4.7 Test limitu lokalnie z `DAILY_BUDGET_USD=0.05`: pożegnanie z informacją o limicie i godzina resetu — c602ec2
- [ ] 4.8 `OPENAI_API_KEY` ustawiony na Railway przed pushem; rozmowa działa na produkcji
- [ ] 4.9 Koszt w panelu OpenAI zgadza się z grubsza z sumą `cost_usd` w bazie
