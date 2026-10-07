# Pamięć między rozmowami i domykanie pętli błędów (S-03) — Implementation Plan

## Overview

Kolejna rozmowa ma „pamiętać” poprzednie rozmowy tego samego użytkownika (w tym samym języku ćwiczeń). Agent zna fakty o uczniu (np. imię psa, praca), pamięta wątki i pytania z wcześniejszych rozmów w tej samej scenie (FR-009) i naturalnie stwarza okazję do użycia jednej konstrukcji, w której uczeń wcześniej się mylił — bez mówienia, że to poprawka (FR-010). Źródłem pamięci są dane z analizy po rozmowie (S-02), rozszerzonej o krótkie notatki; przy starcie rozmowy kod wybiera pamięć i zapisuje ją jako stały blok promptu.

## Current State Analysis

- Prompt rozmowy to tylko stałe instrukcje + język + scena oraz historia bieżącej rozmowy (`conversations/llm.py:149-168`). Nie ma żadnej pamięci między rozmowami.
- Zapisane są surowe wiadomości (`Message`) i błędy z analizy S-02 (`Mistake`, `conversations/models.py:91-121`). Brak notatek o wątkach, faktach o uczniu i pytaniach agenta.
- `Mistake` scala tylko identyczne pary `(wrong, correct)` w obrębie jednej rozmowy (`conversations/services.py:334-365`); `occurrences` liczy powtórzenia w tej jednej rozmowie.
- Analiza (`analyze_mistakes`, `conversations/llm.py:244-292`) dostaje cały transkrypt i zwraca `MistakeReport` (`llm.py:105-115`); jej koszt trafia do `Conversation.analysis_cost_usd` i do `spent_today` (`conversations/budget.py:62-74`).
- Start rozmowy: `start_conversation` (`services.py:80-108`) tworzy `Conversation` z kopią tematu i języka, potem `_generate_and_save` (`services.py:153-184`) woła `generate_turn` dla każdej tury i dla „Try again”.
- Rozmowy zakończone bez otwarcia ekranu błędów mają `analyzed_at IS NULL` (S-02 zostawiło to dla S-03, `context/archive/2026-10-06-post-conversation-error-list/plan.md:44`).

## Desired End State

- Analiza po rozmowie zapisuje na `Conversation` dwie listy krótkich notatek: `learner_facts` (trwałe fakty, które uczeń powiedział o sobie) i `scene_notes` (o czym rozmawiano, jakie pytania zadał partner, co partner mówił o sobie). Lista błędów działa jak dotąd.
- Przy starcie rozmowy `conversations/memory.py` wybiera pamięć dla `(user, topic, language)`:
  - do 10 błędów z 20 ostatnich przeanalizowanych rozmów w tym języku; „ten sam błąd” = ta sama para `wrong→correct` po normalizacji spacji i `casefold`; kolejność: liczba różnych rozmów z tą parą (malejąco), potem świeżość (`ended_at` najnowszej rozmowy z tą parą);
  - fakty o uczniu z 10 ostatnich przeanalizowanych rozmów dowolnego tematu, bez powtórzeń, nowsze pierwsze;
  - notatki sceny z 5 ostatnich przeanalizowanych rozmów o tym samym kluczu tematu.
- Blok pamięci jest zapisany na rozmowie (`memory_prompt`) i dołączany po `Scene:` do instrukcji każdej tury i „Try again”; nie zmienia się w trakcie rozmowy.
- Agent wybiera najwyżej jedną konstrukcję z listy (najwyżej położoną spośród pasujących do sceny), stwarza okazję do jej użycia i nigdy nie mówi, że to poprawka; fakty i wątki wykorzystuje tylko, gdy pasują do sceny.
- Weryfikacja: testy jednostkowe wyboru pamięci i budowy promptu; ręczna próba z prawdziwym modelem (sekcja Manual Testing Steps).

### Key Discoveries:

- Snapshot przy starcie to przyjęty wzorzec (`topic_title`, `topic_scenario`, `language` — `conversations/models.py:22-27`); ten sam wzorzec daje stały prompt pod cache prefiksu (`llm.py:13-16`).
- Każde nowe wywołanie LLM wymagałoby własnej kolumny kosztu w `spent_today` (`budget.py:62-74`). Plan nie dodaje nowych wywołań — notatki powstają w istniejącej analizie, więc ich koszt mieści się w `analysis_cost_usd`.
- Dane per użytkownik czytamy tylko przez `for_user` (`accounts/ownership.py:15-30`, `context/foundation/lessons.md:54-66`). Nowe pola leżą na `Conversation`, więc usuwanie konta (CASCADE) i strażnik admina (`tests/test_ownership.py:47-52`) obejmują je bez zmian.
- Produkt ma dwa języki ćwiczeń (`accounts/models.py:48-62`); pamięć filtrujemy po `Conversation.language`.
- Wzorce testów: `FakeAnalyzeMistakes` (`tests/test_analysis.py:53-79`, `tests/test_conversation_views.py:65-95`), `FakeGenerateTurn` (`tests/test_conversation_views.py:36-62`), fałszywy klient SDK (`tests/test_llm.py:25-63`), test stałego prefiksu (`tests/test_llm.py:125`, `:366`).

## What We're NOT Doing

- **Observational Memory (Observer/Reflector) dla faktów o uczniu.** Teraz fakty bierzemy z 10 ostatnich rozmów; docelowo zastąpi je profil ucznia kompresowany w stylu OM (osobne wywołanie LLM, nowa tabela, koszt w budżecie, obsługa błędów). Odłożone po MVP jako osobny issue — patrz Migration Notes.
- Grupowanie błędów po regule/konstrukcji (etykieta z analizy albo osobny krok konsolidacji) — wybrano dokładną parę `wrong→correct`.
- Filtr tematu dla błędów w kodzie — kod wybiera listę bez tematu, a dopasowanie do sceny ocenia agent.
- Analiza zaległych rozmów (`analyzed_at IS NULL`) przy starcie lub ze strony głównej — takie rozmowy nie zasilają pamięci (znane ograniczenie). Rozmowy porzucone jako `active` też nie.
- Uzupełnianie notatek wstecz dla rozmów przeanalizowanych przed S-03 (ich błędy działają od razu; notatek po prostu nie mają).
- Oznaczanie zagadnień jako opanowanych (FR-011), widok pamięci dla użytkownika, edycja pamięci (PRD Non-Goals).
- Zmiany w budżecie, nowe wywołania LLM, przeniesienie analizy poza żądanie HTTP (Q-07).

## Implementation Approach

Trzy fazy od danych do zachowania agenta. Faza 1 zaczyna zbierać notatki w istniejącej analizie, więc zanim pamięć trafi do rozmowy, w bazie są już prawdziwe dane do ręcznego sprawdzenia. Faza 2 to czysty kod nad bazą (bez LLM) — cała logika wyboru i rankingu jest deterministyczna i testowalna. Faza 3 zamienia wybraną pamięć na tekst promptu, zapisuje go jako snapshot przy starcie i przekazuje do każdej tury.

## Critical Implementation Details

- **Kierunek importów:** `services` będzie importować `memory`, więc `memory.py` nie może importować `services` (cykl). Normalizację spacji z `services._normalize` (`services.py:334-336`) trzeba powtórzyć w `memory.py` (jedna linia + `casefold`) albo przenieść do neutralnego miejsca; `llm.py` może importować typ `Memory` z `memory.py`, bo `memory.py` importuje tylko modele.
- **Snapshot jest stały:** `memory_prompt` liczymy raz w `start_conversation` (po `is_exhausted`, przed `create`) i nigdy go nie przeliczamy — także przy „Try again” i gdy w trakcie rozmowy skończy się analiza innej rozmowy. Inaczej zmieniałby się prefiks promptu i spadałby cache.
- **Notatki tylko w udanym zapisie analizy:** zapisujemy je w tym samym zablokowanym bloku co błędy (`services.py:287-310`); spóźniony wynik równoległej analizy jest odrzucany razem z notatkami.

## Phase 1: Notatki w analizie po rozmowie

### Overview

Analiza po rozmowie zwraca i zapisuje dwie listy notatek obok listy błędów. Nic jeszcze nie trafia do rozmowy.

### Changes Required:

#### 1. Pola notatek na rozmowie

**File**: `conversations/models.py`

**Intent**: Dodać miejsce na notatki z analizy, z komentarzem, czym się różnią i skąd pochodzą.

**Contract**: `Conversation.learner_facts` i `Conversation.scene_notes` — `JSONField(default=list, blank=True)`, lista krótkich zdań po angielsku. Puste dla rozmów sprzed S-03, rozmów bez wypowiedzi ucznia i rozmów nieprzeanalizowanych.

#### 2. Migracja

**File**: `conversations/migrations/0004_*.py` (generowana przez `makemigrations`)

**Intent**: Dodać dwa pola z domyślną pustą listą; istniejące wiersze dostają `[]`.

**Contract**: tylko `AddField` × 2, bez migracji danych.

#### 3. Schemat i instrukcje analizy

**File**: `conversations/llm.py`

**Intent**: Poprosić model w tej samej analizie o notatki do kolejnych rozmów, nie zmieniając zasad wykrywania błędów.

**Contract**:
- `MistakeReport` dostaje pola `learner_facts: list[str]` i `scene_notes: list[str]`; `AnalysisResult` przenosi je dalej.
- `_ANALYSIS_INSTRUCTIONS` dostaje nową sekcję (stały tekst, przed `Practice language`, więc prefiks dalej nie zależy od języka): `learner_facts` — najwyżej 5 trwałych faktów, które uczeń powiedział o sobie (np. imię i rasa psa, praca, rodzina, gdzie mieszka), tylko to, co faktycznie powiedział; `scene_notes` — najwyżej 8 notatek: o czym rozmawiano, jakie pytania zadał partner, co partner powiedział o swojej postaci (np. jak fryzjer ściął włosy). Krótkie zdania po angielsku; nigdy nie opisują błędów ani poziomu języka; puste listy są dozwolone.
- Docstring modułu opisuje, że analiza zwraca też notatki.

#### 4. Zapis notatek w serwisie analizy

**File**: `conversations/services.py`

**Intent**: Zapisać notatki razem z listą błędów, w tym samym zablokowanym bloku, żeby spóźniony wynik nie nadpisał niczego.

**Contract**: w `analyze_conversation` (`services.py:287-310`) zapis `learner_facts` i `scene_notes` po `strip()` i odrzuceniu pustych wpisów; dodane do `update_fields`. Ścieżka bez wypowiedzi ucznia (`services.py:262-277`) zostawia puste listy. Docstring modułu wspomina o notatkach.

#### 5. Testy

**Files**: `tests/test_llm.py`, `tests/test_analysis.py`, `tests/test_conversation_views.py`

**Intent**: Pokryć nowe pola i zaktualizować fałszywe analizy, które budują `AnalysisResult`.

**Contract**:
- `test_llm`: notatki z odpowiedzi trafiają do `AnalysisResult`; instrukcje analizy dalej mają wspólny prefiks dla obu języków.
- `test_analysis`: notatki są zapisane po udanej analizie (z obciętymi spacjami, bez pustych wpisów); spóźniony wynik nie zapisuje notatek; rozmowa bez wypowiedzi ucznia ma puste listy; nieudana analiza nie zapisuje notatek.
- `FakeAnalyzeMistakes` w obu modułach zwraca wyniki z nowymi polami.

### Success Criteria:

#### Automated Verification:

- Migracje są kompletne: `uv run python manage.py makemigrations --check --dry-run`
- Migracje przechodzą: `uv run python manage.py migrate`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Prawdziwa rozmowa (lokalnie, `uv run --env-file .env python manage.py runserver`), zakończona, z otwartą listą błędów: lista błędów wygląda jak przed zmianą, a w `uv run python manage.py shell` rozmowa ma sensowne `learner_facts` i `scene_notes` bez opisów błędów
- Czas przygotowania listy błędów nie rośnie zauważalnie (punkt odniesienia z S-02: ok. 52 s dla 20 tur)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Wybór pamięci

### Overview

Nowy moduł `conversations/memory.py` wybiera z bazy pamięć dla nowej rozmowy: ranking dawnych błędów, fakty o uczniu i notatki sceny. Bez LLM i bez zmian w rozmowie.

### Changes Required:

#### 1. Moduł wyboru pamięci

**File**: `conversations/memory.py` (nowy)

**Intent**: Jedno miejsce z regułami wyboru pamięci. Docstring opisuje reguły i zaznacza, że fakty z 10 ostatnich rozmów to rozwiązanie tymczasowe, które po MVP zastąpi profil ucznia w stylu Observational Memory (kompresja, która według autorów OM zachowuje większość informacji).

**Contract**:
- Stałe: `MISTAKE_WINDOW_CONVERSATIONS = 20`, `MAX_MISTAKES = 10`, `FACT_WINDOW_CONVERSATIONS = 10`, `SCENE_NOTE_CONVERSATIONS = 5`.
- `PastMistake` (dataclass): `wrong`, `correct`, `explanation` (z najnowszego wystąpienia, w oryginalnej pisowni), `conversations: int` (liczba różnych rozmów z tą parą).
- `Memory` (dataclass): `learner_facts: list[str]`, `scene_notes: list[list[str]]` (jedna lista na wcześniejszą rozmowę, najnowsza pierwsza, puste pominięte), `mistakes: list[PastMistake]`; właściwość `is_empty`.
- `select_memory(user: User, topic_key: str, language: str) -> Memory`.
- Źródło: tylko `Conversation.objects.for_user(user)` ze `status=ended`, `analyzed_at` ustawionym i `language=language`, posortowane po `-ended_at, -id`; błędy przez `Mistake.objects.for_user(user)` zawężone do wybranych rozmów.
- Błędy: z 20 pierwszych rozmów; klucz grupy = para po normalizacji spacji (jak `services._normalize`) i `casefold`; sortowanie: liczba różnych rozmów malejąco, potem `ended_at` najnowszej rozmowy z tą parą malejąco, potem `position` w tej rozmowie rosnąco (deterministyczny remis); pierwsze 10.
- Fakty: z 10 pierwszych rozmów dowolnego tematu, kolejno od najnowszej; duplikaty po normalizacji spacji i `casefold` pominięte (zostaje najnowszy).
- Notatki sceny: z 5 pierwszych rozmów o `topic == topic_key`.
- Stała liczba zapytań, niezależna od liczby rozmów.

#### 2. Testy wyboru pamięci

**File**: `tests/test_memory.py` (nowy)

**Intent**: Pokryć każdą regułę jednym testem z najmniejszym rozstrzygającym przypadkiem.

**Contract** — testy:
- para A w 1 rozmowie z `occurrences=4` i para B w 2 rozmowach po 1 → B przed A;
- remis liczby rozmów → wyżej para z rozmowy o nowszym `ended_at`;
- `"habe  gegangen"→"bin gegangen"` i `"Habe gegangen"→"Bin gegangen"` z dwóch rozmów → jedna pozycja z `conversations=2` i pisownią z nowszej rozmowy;
- para obecna tylko w 21. najnowszej rozmowie → pominięta; więcej niż 10 par → dokładnie 10;
- rozmowy w innym języku, aktywne i nieprzeanalizowane → pominięte;
- dane innego użytkownika nigdy nie trafiają do wyniku;
- notatki sceny tylko z tego samego klucza tematu i najwyżej z 5 rozmów, najnowsza pierwsza;
- fakty z dowolnego tematu, najwyżej z 10 rozmów, duplikat zostaje raz (najnowszy);
- brak danych → `is_empty`.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- `select_memory` wywołane w `uv run python manage.py shell` na lokalnych danych z fazy 1 zwraca oczekiwane fakty, notatki i błędy

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Pamięć w rozmowie

### Overview

Wybrana pamięć staje się stałym blokiem promptu: liczona i zapisywana przy starcie rozmowy, dołączana po scenie do każdej tury.

### Changes Required:

#### 1. Pole snapshotu

**File**: `conversations/models.py`, `conversations/migrations/0005_*.py`

**Intent**: Zapisać tekst bloku pamięci na rozmowie, tak jak kopię tematu.

**Contract**: `Conversation.memory_prompt` — `TextField(blank=True)`; pusty dla rozmów sprzed S-03 i dla użytkownika bez pamięci. Migracja: jedno `AddField`.

#### 2. Tekst bloku pamięci i instrukcje

**File**: `conversations/llm.py`

**Intent**: Zamienić `Memory` na tekst dla modelu i dołączyć go do instrukcji tury. Cały tekst promptu zostaje w `llm.py`.

**Contract**:
- `format_memory(memory: Memory) -> str` — `""` dla pustej pamięci; sekcje tylko dla niepustych list:
  - fakty o uczniu (nowsze pierwsze; przy sprzeczności ufaj nowszemu; używaj tylko, gdy naturalnie pasują do sceny);
  - wcześniejsze rozmowy w tej samej scenie (najnowsza pierwsza; jesteś tą samą osobą; nawiązuj, gdy to naturalne; nie zadawaj ponownie pytań, które już padły);
  - konstrukcje, w których uczeń się mylił (najważniejsze pierwsze, `wrong → correct` + wyjaśnienie): wybierz najwyżej jedną — najwyżej na liście spośród tych, które naturalnie pasują do sceny — i stwórz naturalną okazję do jej użycia; nigdy nie mów, że to ćwiczenie ani że uczeń wcześniej popełnił ten błąd; jeśli żadna nie pasuje, zignoruj listę.
- `_build_instructions(topic, language, memory)` dokleja `memory` po `Scene:` (pusta linia odstępu), tylko gdy niepusty; bez pamięci instrukcje są identyczne jak dziś.
- `generate_turn(..., memory: str)` — nowy wymagany argument kluczowy, przekazywany do `_build_instructions`.
- Docstring modułu: kolejność promptu to stałe instrukcje → język → scena → pamięć (stała w obrębie rozmowy).

#### 3. Snapshot przy starcie i przekazanie do tur

**File**: `conversations/services.py`

**Intent**: Policzyć pamięć raz przy starcie i używać tej samej kopii w każdej turze.

**Contract**:
- `start_conversation`: po `is_exhausted` liczy `format_memory(select_memory(user, topic.key, user.practice_language))` i zapisuje w `memory_prompt` przy `Conversation.objects.create`.
- `_generate_and_save`: przekazuje `memory=conversation.memory_prompt` do `generate_turn`.
- Docstring modułu: pamięć to snapshot ze startu.

#### 4. Testy

**Files**: `tests/test_llm.py`, `tests/test_conversations.py` lub `tests/test_conversation_views.py`

**Intent**: Pilnować kolejności promptu, stałości snapshotu i izolacji.

**Contract**:
- `test_llm`: pamięć stoi po `Scene:`; pusta pamięć → instrukcje identyczne jak bez niej; stały prefiks `_INSTRUCTIONS` bez zmian; `format_memory` pomija puste sekcje, zwraca `""` dla pustej pamięci i zawiera regułę „najwyżej jedna konstrukcja”.
- serwis/widoki: start zapisuje `memory_prompt` z danych użytkownika; każda tura i „Try again” dostają ten sam `memory` (`FakeGenerateTurn` zapisuje kwargs), także gdy po starcie zakończy się analiza innej rozmowy; `memory_prompt` użytkownika A nie zawiera danych użytkownika B; rozmowa w drugim języku nie dostaje pamięci z pierwszego.

### Success Criteria:

#### Automated Verification:

- Migracje są kompletne: `uv run python manage.py makemigrations --check --dry-run`
- Migracje przechodzą: `uv run python manage.py migrate`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Kolejna rozmowa w tej samej scenie nawiązuje do poprzedniej i nie powtarza wcześniejszych pytań
- Rozmowa w innej scenie korzysta z faktu o uczniu, gdy pasuje (np. sąsiad zna imię psa podane w parku), i nie wciąga wątków z innej sceny
- Agent stwarza okazję do najwyżej jednej dawnej konstrukcji, naturalnie i bez mówienia, że to poprawka
- Od drugiej tury `cached_input_tokens` w `Message` jest większe od zera (cache działa z blokiem pamięci)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Reguły wyboru w `select_memory` (ranking, remis, `casefold`, okna 20/10/5, limit 10, język, izolacja, pominięte rozmowy).
- Budowa promptu: kolejność, pusta pamięć, stały prefiks, treść sekcji `format_memory`.
- Zapis notatek w analizie, w tym spóźniony i nieudany wynik.

### Integration Tests:

- Start → tura → „Try again” z fałszywym `generate_turn`: ten sam `memory` w każdym wywołaniu.
- Izolacja: snapshot użytkownika A bez danych użytkownika B.

### Manual Testing Steps:

1. Lokalnie z kluczem: `uv run --env-file .env python manage.py runserver`.
2. Rozmowa `dog-walk`: podaj imię psa i swoją pracę, popełnij świadomie jeden błąd; zakończ i otwórz listę błędów; sprawdź notatki w shellu.
3. Rozmowa `neighbour-stairwell`: sąsiad może nawiązać do psa; nie wspomina wątków z parku jak z własnej rozmowy.
4. Druga rozmowa `dog-walk`: partner pamięta poprzednie spotkanie i nie powtarza pytań; pojawia się najwyżej jedna naturalna okazja do konstrukcji z błędu.
5. W shellu porównaj `memory_prompt` rozmów z kroków 3–4 z oczekiwaniami; sprawdź `cached_input_tokens` od drugiej tury.

## Performance Considerations

- Wybór pamięci to stała liczba zapytań przy starcie rozmowy (bez LLM), więc start nie zwalnia zauważalnie.
- Blok pamięci zwiększa input każdej tury. Przy górnej granicy (10 błędów, fakty z 10 rozmów, notatki z 5 rozmów) to rząd 1–1,5 tys. tokenów; bez cache ok. 0,03–0,04 USD na rozmowę z 10 turami, z cache od drugiej tury ok. 10× mniej. Notatki zwiększają też output analizy (kilkaset tokenów).

## Migration Notes

- Migracje `0004` i `0005` tylko dodają pola z wartością domyślną; deploy przez pre-deploy `migrate` na Railway.
- Rozmowy sprzed S-03: błędy działają od razu (para jest zapisana), notatek brak, `memory_prompt` pusty — aktywna rozmowa sprzed deployu kończy się bez pamięci.
- Po zapisaniu planu: wpis „Observational Memory dla profilu ucznia” w `## Parked` roadmapy i nowy issue po MVP (GitHub i Linear osobno), z informacją, że zastąpi fakty z 10 ostatnich rozmów.

## References

- Research: `context/changes/cross-session-error-memory/research.md`
- PRD: `context/foundation/prd.md` (FR-009, FR-010, Business Logic)
- Roadmap: `context/foundation/roadmap.md` (S-03)
- S-02 plan: `context/archive/2026-10-06-post-conversation-error-list/plan.md`
- Wzorzec snapshotu: `conversations/models.py:22-27`; zapis analizy: `conversations/services.py:240-315`; prompt: `conversations/llm.py:149-191`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Notatki w analizie po rozmowie

#### Automated

- [x] 1.1 Migracje są kompletne: `uv run python manage.py makemigrations --check --dry-run` — c149bc8
- [x] 1.2 Migracje przechodzą: `uv run python manage.py migrate` — c149bc8
- [x] 1.3 Testy przechodzą: `uv run pytest` — c149bc8
- [x] 1.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — c149bc8

#### Manual

- [x] 1.5 Prawdziwa rozmowa (lokalnie, `uv run --env-file .env python manage.py runserver`), zakończona, z otwartą listą błędów: lista błędów wygląda jak przed zmianą, a w `uv run python manage.py shell` rozmowa ma sensowne `learner_facts` i `scene_notes` bez opisów błędów — c149bc8
- [x] 1.6 Czas przygotowania listy błędów nie rośnie zauważalnie (punkt odniesienia z S-02: ok. 52 s dla 20 tur) — c149bc8

### Phase 2: Wybór pamięci

#### Automated

- [x] 2.1 Testy przechodzą: `uv run pytest`
- [x] 2.2 Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [x] 2.3 `select_memory` wywołane w `uv run python manage.py shell` na lokalnych danych z fazy 1 zwraca oczekiwane fakty, notatki i błędy

### Phase 3: Pamięć w rozmowie

#### Automated

- [ ] 3.1 Migracje są kompletne: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 3.2 Migracje przechodzą: `uv run python manage.py migrate`
- [ ] 3.3 Testy przechodzą: `uv run pytest`
- [ ] 3.4 Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual

- [ ] 3.5 Kolejna rozmowa w tej samej scenie nawiązuje do poprzedniej i nie powtarza wcześniejszych pytań
- [ ] 3.6 Rozmowa w innej scenie korzysta z faktu o uczniu, gdy pasuje (np. sąsiad zna imię psa podane w parku), i nie wciąga wątków z innej sceny
- [ ] 3.7 Agent stwarza okazję do najwyżej jednej dawnej konstrukcji, naturalnie i bez mówienia, że to poprawka
- [ ] 3.8 Od drugiej tury `cached_input_tokens` w `Message` jest większe od zera (cache działa z blokiem pamięci)
