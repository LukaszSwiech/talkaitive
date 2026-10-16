# Rollout Phase 3 — granice prywatności i usuwania konta: plan implementacji

## Overview

Faza 3 z `context/foundation/test-plan.md` §3 (ryzyka #3 i #6). Dzisiejsze testy izolacji i usuwania konta są poprawne, ale opierają się na ręcznie pisanych listach: nowa trasa z id albo nowy model danych przejdzie bez sygnału. Plan zamienia te listy na strażniki porównujące ręczną decyzję z rejestrem Django (router URL, rejestr modeli), wzmacnia test izolacji pamięci wzorcem metamorficznym, zamyka znalezioną w researchu ścieżkę usuwania przez `/admin/` (sygnał `pre_delete` na `User`) i potwierdza każdy nowy test ręcznym mutantem.

## Current State Analysis

Źródło: `context/changes/testing-privacy-and-deletion-boundaries/research.md` (zweryfikowane w kodzie na `df25bc5`).

- **Trasy z id (#3):** dokładnie 5 tras z `<int:pk>` (`conversations/urls.py:8-30`), wszystkie przez `_get_conversation` → `get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)` (`conversations/views.py:24-25`). `test_other_user_gets_404_on_every_conversation_url` (`tests/test_conversation_views.py:846-881`) sprawdza 404, brak zmiany stanu i brak wywołań modelu na wszystkich 5, ale lista parametrów (`("get", "")`, `("post", "messages/")`, …) jest pisana ręcznie i nic jej nie porównuje z routerem. Mutant `C1` pilnuje helpera.
- **Dane podrzędne (#3):** brak tras do `Message`/`Mistake` po id; `Message` czytany tylko przez zawężoną rozmowę, `Mistake` przez `for_user` + `conversation=` (`views.py:90`, `:95-97`). Nowy test zbędny — przyszłe trasy podrzędne obejmie strażnik tras.
- **Pamięć (#3):** `select_memory` filtruje rozmowy przez `for_user(user)` (`conversations/memory.py:80`) i błędy przez `for_user(user)` + `conversation_id__in` (`memory.py:120`). Test `test_memory_never_contains_another_users_data` (`tests/test_conversation_views.py:1309-1323`) daje Annie zero własnych danych i sprawdza `memory_prompt == ""` — nie odróżnia „dane B odfiltrowane” od „pamięć A zepsuta/pusta”. Brak ręcznego mutanta usuwającego `for_user` z `memory.py`; mutmut takich nie generuje.
- **Strażnik relacji (#6):** `test_every_relation_to_user_data_is_known_and_cascades` (`tests/test_account_deletion.py:132-166`) porównuje relacje z rejestru Django z literałem 6 par — nie porównuje listy z samą sobą. Widzi tylko FK/O2O/M2M; nie widzi id/e-maila zapisanego jako tekst ani `GenericForeignKey`.
- **Test behawioralny usuwania (#6):** `test_deleting_account_removes_all_data_of_that_user_only` (`tests/test_account_deletion.py:85-107`) liczy wiersze 3 nazwanych modeli. Nowy model dopisany do `expected` w strażniku nie dostaje sprawdzenia wierszy automatycznie.
- **Ścieżka `/admin/` (#6, nowe ustalenie):** `User` jest w adminie (`accounts/admin.py:8-9`), a ręczne sprzątanie sesji i `LogEntry` o użytkowniku (`accounts/services.py:46-53`) działa tylko w `delete_account`, wołanym z widoku `account_delete`. Usunięcie przez admina idzie zwykłym `delete()` — zostają sesje i `LogEntry` z `object_repr` = e-mail.
- **Mutacja `accounts/`:** `accounts/services.py` nie jest w `[tool.mutmut]` i nie ma żadnego ręcznego mutanta (`scripts/mutation/manual_mutants.py`, ostatni id `M15`).

## Desired End State

- Nowa trasa z konwerterem id w adresie (poza `admin:`) bez wpisu w ręcznym słowniku tras wywraca test; każda trasa ze słownika automatycznie dostaje test „inny użytkownik → 404, bez zmiany stanu, bez wywołań modelu”.
- Blok pamięci Anny jest niepusty i identyczny z danymi Łukasza i bez nich; usunięcie `for_user` z zapytania o rozmowy w `select_memory` wywraca test.
- Każdy model spoza aplikacji `django.*` ma w teście świadomą decyzję („kasowany z użytkownikiem” / „to nie są dane użytkownika, bo…”); nowy model — także bez żadnego klucza obcego — wywraca test.
- Każdy model z domknięcia kaskady od `User` ma fabrykę danych; test usuwa Annę przez stronę i sprawdza, że żaden wiersz Anny nie został, a wiersze Łukasza są całe. Nowy model z domknięcia bez fabryki wywraca test.
- Usunięcie użytkownika przez `/admin/` (pojedyncze i akcja zbiorcza) usuwa jego sesje i wszystkie wpisy `LogEntry` o nim, tak jak usunięcie przez stronę.
- `uv run python scripts/mutation/manual_mutants.py` kończy się kodem 0 z nowymi mutantami `M16`–`M24`; każde zaakceptowane przeżycie ma wiersz w `scripts/mutation/accepted_survivors.md`.

### Key Discoveries:

- `_get_conversation` jest jedyną granicą izolacji widoków; serwisy używają `for_user(conversation.user)` i ufają widokowi (`conversations/services.py:60-66`, `:92-96`).
- `memory.py:120` bez `for_user` jest równoważny: `conversation_id__in` zawiera tylko id rozmów użytkownika, a `Mistake.user` jest zawsze użytkownikiem rozmowy (`conversations/services.py:421-434`).
- Django 6.1.1 admin zapisuje `LogEntry` o usunięciu **przed** usunięciem obiektu, w obu ścieżkach: `log_deletions` → `delete_model` (`django/contrib/admin/options.py:2544-2545`) i `log_deletions` → `delete_queryset` (`django/contrib/admin/actions.py:49-50`). Sygnał `pre_delete` zdąży więc usunąć także ten wpis.
- Modele aplikacji dziś: `accounts.User`, `conversations.Conversation`, `conversations.Message`, `conversations.Mistake`; w testach dodatkowo `tests.ownership_testapp.OwnedNote` (`talkaitive/settings_test.py:12-13`).
- `manual_mutants.py` wymaga, by fragment `original` występował w pliku dokładnie raz, i odrzuca mutanta, który się nie kompiluje.

## What We're NOT Doing

- Drugi test 404 per widok — istniejący test sparametryzowany zostaje, zmienia się tylko źródło parametrów.
- Test IDOR dla `account_delete`, `home`, `conversation_start` — nie mają id w adresie; izolację `home`/`start` już pilnują `M1`/`M2`.
- Heurystyka nazw pól (`*user*`, `*email*`) w strażniku — wybrany rejestr modeli; świadome ograniczenie: nowe pole tekstowe dodane do **istniejącego** modelu nie wywróci testu.
- `accounts/services.py` w `[tool.mutmut]` — tylko ręczne mutanty (decyzja: bez szumu mutantów tekstów komunikatów).
- Dane poza bazą (pliki, cache, OpenAI, kopie zapasowe) — dziś ich nie ma albo są poza produktem (PRD NFR „Usuwanie danych”).
- Testy E2E w przeglądarce — żadna z tych awarii nie zależy od JS (`test-plan.md` §7).
- Zmiana uprawnień admina (np. zakaz usuwania użytkowników) — ścieżka zostaje, tylko sprząta jak strona.

## Implementation Approach

Każdy strażnik porównuje **ręcznie wpisaną decyzję** z **rejestrem Django** (router URL, `apps.get_models()`, domknięcie kaskady), nigdy listę wyliczoną z tego samego źródła co parametry testu. Oczekiwane wartości pochodzą z PRD (Guardrails, FR-013, NFR „Prywatność” / „Usuwanie danych”) i `test-plan.md` §2, z podanym źródłem w docstringu testu (§6.1 krok 1). Każdy nowy test potwierdzamy ręcznym mutantem w tej samej fazie (§6.1 kroki 3–5). Jedyna zmiana kodu aplikacji (faza 3) idzie test-first: najpierw czerwony test usunięcia przez admina, potem poprawka.

## Branches and PRs

Jedna gałąź `testing-privacy-and-deletion-boundaries` (już istnieje) i jeden PR dla wszystkich faz.

## Critical Implementation Details

- **Kolejność mutantów i refaktoru:** `M19`–`M21` (sprzątanie sesji i `LogEntry`) powstają dopiero w fazie 3, na kodzie po przeniesieniu do odbiornika sygnału — pisane raz. Gdyby powstały w fazie 2, ich fragmenty `original` przestałyby istnieć po refaktorze i `manual_mutants.py` kończyłby się kodem 2 („fragment found 0 times”). Testy, które je zabijają, istnieją już dziś (`tests/test_account_deletion.py`).
- **Sygnał a `pk`:** w `pre_delete` `instance.pk` jest jeszcze ustawione (po `delete()` jest `None`), więc id do porównania z sesjami i `LogEntry.object_id` bierzemy z `instance` w odbiorniku. `QuerySet.delete()` wysyła `pre_delete` dla każdego obiektu, gdy istnieje odbiornik — akcja zbiorcza admina jest więc objęta bez osobnego kodu.
- **Mutant „nowy model bez FK” (`M23`):** model dopisany mutantem nie ma migracji. To celowe — zabić go ma wyłącznie test rejestru modeli (czyta metadane, nie tabelę); żaden test nie powinien paść przez brak tabeli, bo bez FK kaskada go nie dotyka.

## Faza 1: Izolacja tras i pamięci (#3)

### Overview

Strażnik tras z id oparty o router URL, słownik tras jako jedno źródło parametrów testu 404, metamorficzny test izolacji pamięci i trzy ręczne mutanty.

### Changes Required:

#### 1. Słownik tras z id i test 404 sterowany słownikiem

**File**: `tests/test_conversation_views.py`

**Intent**: Zastąpić ręczną listę sufiksów w `test_other_user_gets_404_on_every_conversation_url` ręcznie wpisanym słownikiem „nazwa trasy → metoda HTTP”; URL budować przez `reverse(name, kwargs={"pk": conversation.pk})`. Asercje testu bez zmian.

**Contract**: stała modułowa `ID_ROUTES: dict[str, tuple[str, type[Model]]]` — nazwa trasy → (metoda HTTP, model, którego pk jest w adresie); 5 wpisów (`conversation_detail: ("get", Conversation)`, `conversation_send`, `conversation_retry`, `conversation_end`, `conversation_analyze`: `("post", Conversation)`). Parametryzacja testu 404 iteruje po `ID_ROUTES.items()`. Test 404 umie zbudować obiekt innego użytkownika tylko dla `Conversation`; wpis z innym modelem wywraca test komunikatem „dodaj budowanie obiektu tego modelu dla innego użytkownika”, żeby przyszła trasa podrzędna (np. po pk `Message`) nie dostała 404 „na pusto” z powodu id rozmowy w miejscu id wiadomości.

#### 2. Strażnik: każda trasa z id ma decyzję

**File**: `tests/test_conversation_views.py`

**Intent**: Nowy test bez bazy przechodzi rekurencyjnie po `django.urls.get_resolver()` i zbiera nazwy tras, które mają parametr w adresie (np. `<int:pk>`). Parametry wykrywa przez nazwane grupy `pattern.regex.groupindex` (działa dla `path` i `re_path`) i sumuje je wzdłuż całej ścieżki `include()`, bo parametr może siedzieć w prefiksie rodzica. Pomija przy tym przestrzeń nazw `admin` (dane per użytkownik nie są w adminie — pilnuje `tests/test_ownership.py:47-52`). Zbiór porównuje z `set(ID_ROUTES)`. Komunikat błędu mówi: dodaj trasę do `ID_ROUTES` (dostanie test 404), a widok pobiera obiekt przez `for_user` (lessons.md).

**Contract**: test `test_every_url_with_an_id_is_covered_by_the_404_test`; porównuje router z literałem `ID_ROUTES` — nigdy z parametrami wyliczonymi z routera. Trasa bez nazwy z konwerterem też musi wywrócić test (nie da się jej dodać do słownika bez nazwy). Każda trasa z `ID_ROUTES` ma dokładnie parametry `{"pk"}`; inny zestaw wywraca test (test 404 buduje URL przez `reverse(..., kwargs={"pk": ...})`).

#### 3. Metamorficzny test izolacji pamięci

**File**: `tests/test_conversation_views.py`

**Intent**: Wzmocnić `test_memory_never_contains_another_users_data` (ta sama nazwa): Anna ma własną zakończoną, przeanalizowaną rozmowę z faktem, notatką sceny i błędem. Najpierw liczymy jej blok pamięci tą samą drogą co `start_conversation` (`select_memory` + formatowanie, `conversations/services.py:110-112`) bez danych Łukasza. Potem Łukasz dostaje **nowsze** rozmowy w tym samym języku i temacie, z faktami, notatkami i błędami. Start rozmowy Anny przez widok ma dać `memory_prompt` równy wcześniejszemu wynikowi, niepusty i bez danych Łukasza (także w `fake_llm.calls[0]["memory"]`). Docstring: źródło PRD Guardrails + `test-plan.md` §2 #3, wzorzec §6.1 (metamorficzny).

**Contract**: dane Łukasza muszą pasować do każdego filtra `select_memory` poza `for_user` (status `ENDED`, `analyzed_at`, język, temat), inaczej mutant `M16` przeżyje ze złego powodu.

#### 4. Ręczne mutanty #3

**File**: `scripts/mutation/manual_mutants.py`, `scripts/mutation/accepted_survivors.md`

**Intent**: Dopisać trzy mutanty i jeden wiersz rejestru.

**Contract**:
- `M16` — `conversations/memory.py`: `Conversation.objects.for_user(user)` w `select_memory` → `Conversation.objects.all()`; `expected="killed"`.
- `M17` — `conversations/memory.py`: `Mistake.objects.for_user(user).filter(conversation_id__in=…)` → `Mistake.objects.filter(conversation_id__in=…)`; `expected="accepted"`, wiersz `równoważny` w `accepted_survivors.md` (uzasadnienie: lista id zawiera tylko rozmowy użytkownika, a `Mistake.user` = użytkownik rozmowy, `services.py:421-434`).
- `M18` — `conversations/urls.py`: dopisana trasa `conversations/<int:pk>/copy/` (nazwa `conversation_copy`, widok `views.conversation_detail`) na początku `urlpatterns`; `expected="killed"` (strażnik tras).
- Docstring modułu i nagłówek rejestru (lista id) zaktualizowane do `M16`–`M18`.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C1 M16 M17 M18`

#### Manual Verification:

- Przegląd diffu: `ID_ROUTES` jest literałem, a strażnik nie wylicza oczekiwanego zbioru z routera

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie przeglądu przez człowieka przed fazą 2.

---

## Faza 2: Rejestr modeli i test „żaden model nie zostawia wierszy” (#6)

### Overview

Rejestr decyzji dla każdego modelu aplikacji, słownik fabryk dla każdego modelu z domknięcia kaskady, behawioralny test usunięcia przez stronę i ręczne mutanty usuwania konta.

### Changes Required:

#### 1. Rejestr decyzji dla wszystkich modeli aplikacji

**File**: `tests/test_account_deletion.py`

**Intent**: Nowy test zbiera z `apps.get_models()` każdy model, którego aplikacja nie jest z `django.*`, i porównuje ten zbiór z ręcznym słownikiem decyzji. Decyzja `CASCADE` oznacza „dane użytkownika, kasowane z kontem” i wymaga, by model był w `user_data_models()`; decyzja „nie są to dane użytkownika” wymaga tekstu uzasadnienia. Komunikat błędu prowadzi autora: FK z CASCADE do danych użytkownika + fabryka niżej, albo decyzja z uzasadnieniem.

**Contract**: stała `MODEL_DECISIONS: dict[type[Model], str]` z dzisiejszymi wpisami `User`, `Conversation`, `Message`, `Mistake`, `OwnedNote` (wszystkie `CASCADE`; `User` jako korzeń). Test `test_every_app_model_has_a_deletion_decision`: (a) zbiór modeli aplikacji == klucze słownika, (b) modele z decyzją `CASCADE` ⊆ `user_data_models()`.

#### 2. Fabryki i test „żaden wiersz Anny nie został”

**File**: `tests/test_account_deletion.py`

**Intent**: Słownik „model → fabryka”, gdzie fabryka tworzy dla danego użytkownika co najmniej jeden wiersz modelu i zwraca jego instancje. Test sprawdza, że klucze słownika == `user_data_models()` (nowy model z domknięcia bez fabryki wywraca test). Test behawioralny tworzy dane fabrykami dla Anny i Łukasza, usuwa Annę przez `POST /account/delete/` i sprawdza dla każdego modelu: żaden pk Anny nie istnieje, każdy pk Łukasza istnieje. Istniejący `test_deleting_account_removes_all_data_of_that_user_only` zostaje (sprawdza pola pamięci Łukasza).

**Contract**: `FACTORIES: dict[type[Model], Callable[[User], list[Model]]]`; fabryka `LogEntry` tworzy wpis, którego **autorem** jest użytkownik; fabryka `User` zwraca samego użytkownika. Testy `test_every_user_data_model_has_a_factory` i `test_deleting_account_leaves_no_row_of_that_user_in_any_model`.

#### 3. Ręczne mutanty #6 (kaskada i strażnik)

**File**: `scripts/mutation/manual_mutants.py`

**Intent**: Potwierdzić, że nowe testy fazy padają po zepsuciu kaskady i po dodaniu modelu bez decyzji. Mutanty sprzątania sesji i `LogEntry` (`M19`–`M21`) powstają w fazie 3, na kodzie po refaktorze.

**Contract**:
- `M22` — `conversations/models.py`: `Message.conversation` z `on_delete=models.PROTECT` zamiast `CASCADE`; `expected="killed"`.
- `M23` — `conversations/models.py`: dopisany na końcu pliku model bez FK z polem tekstowym na e-mail użytkownika; `expected="killed"` (tylko rejestr modeli).

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py M22 M23`

#### Manual Verification:

- Przegląd diffu: `MODEL_DECISIONS` i `FACTORIES` są literałami porównywanymi z rejestrem Django, nie z sobą nawzajem

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie przeglądu przez człowieka przed fazą 3.

---

## Faza 3: Usuwanie przez `/admin/` (#6)

### Overview

Test-first: czerwony test usunięcia przez admina, potem sprzątanie danych spoza kaskady przeniesione do odbiornika `pre_delete` na `User`, żeby każda droga usunięcia sprzątała tak samo.

### Changes Required:

#### 1. Czerwony test usunięcia przez admina

**File**: `tests/test_account_deletion.py`

**Intent**: Właściciel (superuser) usuwa Annę w adminie — raz przez stronę potwierdzenia usunięcia obiektu, raz przez akcję zbiorczą `delete_selected` z listy użytkowników (parametryzacja). Po usunięciu: brak sesji Anny, brak jakiegokolwiek `LogEntry` o Annie (także nowego wpisu o samym usunięciu), dane Anny z fabryk usunięte; sesje właściciela i Łukasza, dane Łukasza i wpis `LogEntry` o Łukaszu zostają. Docstring: źródło PRD FR-013 + NFR „Usuwanie danych”; ścieżka z researchu §6.3. Test musi być czerwony na obecnym kodzie, zanim powstanie poprawka.

**Contract**: test `test_deleting_user_in_admin_removes_sessions_and_log_entries_about_them`; korzysta z fabryk z fazy 2.

#### 2. Sprzątanie w odbiorniku `pre_delete`

**File**: `accounts/services.py`, `accounts/apps.py`

**Intent**: Wydzielić usuwanie sesji i `LogEntry` o użytkowniku do jednej funkcji w `accounts/services.py`, podłączonej jako odbiornik `pre_delete` dla `User` (podłączenie w `AccountsConfig.ready`). `delete_account` zachowuje sprawdzenie superusera i hasła oraz transakcję, a sprzątanie robi już przez `user.delete()`. Docstring modułu opisuje, że sprzątanie działa na każdej drodze usunięcia (strona, admin, `manage.py shell`).

**Contract**: odbiornik `pre_delete` z `sender=User`; id użytkownika z `instance.pk` (patrz Critical Implementation Details). Zachowanie `delete_account` dla strony bez zmian — istniejące testy usuwania przechodzą bez edycji asercji.

#### 3. Mutanty po refaktorze

**File**: `scripts/mutation/manual_mutants.py`

**Intent**: Dodać mutanty sprzątania (na kodzie po refaktorze) i mutanta odłączonego sygnału.

**Contract**:
- `M19` — `accounts/services.py`: usunięta pętla po sesjach w funkcji sprzątającej; `expected="killed"` (`test_deleting_account_ends_all_sessions_of_that_user_only`).
- `M20` — `accounts/services.py`: usunięte kasowanie `LogEntry` o użytkowniku; `expected="killed"` (`test_deleting_account_removes_admin_log_entries_about_that_user`).
- `M21` — `accounts/services.py`: `LogEntry` bez filtra `object_id=`; `expected="killed"` (zostaje wpis o Łukaszu).
- `M24` — `accounts/apps.py` (albo miejsce podłączenia): odbiornik niepodłączony; `expected="killed"` (test admina i testy usuwania przez stronę).

### Success Criteria:

#### Automated Verification:

- Nowy test admina jest czerwony przed poprawką: `uv run pytest tests/test_account_deletion.py -k admin`
- Testy przechodzą po poprawce: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py M19 M20 M21 M24`

#### Manual Verification:

- Lokalnie (`uv run python manage.py runserver`): właściciel usuwa testowego użytkownika w `/admin/`, a w „Recent actions” nie zostaje wpis z jego e-mailem

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie ręcznego sprawdzenia przed fazą 4.

---

## Faza 4: Domknięcie

### Overview

Pełna mutacja, rejestr przeżyć i aktualizacja planu testów.

### Changes Required:

#### 1. Pełny przebieg mutacji

**File**: `scripts/mutation/accepted_survivors.md`

**Intent**: Uruchomić całą listę ręcznych mutantów i mutmut na świeżo (po samych zmianach testów usunąć `mutants/`). Każde nowe przeżycie mutmut dostaje test albo wiersz w rejestrze z klasyfikacją.

**Contract**: 0 niewyjaśnionych przeżyć (`test-plan.md` §5).

#### 2. Plan testów i lessons

**File**: `context/foundation/test-plan.md`, `context/foundation/lessons.md`

**Intent**: Wypełnić §6.2 wzorcem „widok z danymi per użytkownik” (słownik `ID_ROUTES` + strażnik routera, metamorficzny test pamięci, `MODEL_DECISIONS` + `FACTORIES` dla nowego modelu), dopisać notatkę fazy 3 w §6.6 (w tym ścieżka `/admin/` i kandydaci do `--refresh`), ustawić Status fazy 3 w §3 na `complete`, jak w fazach 1 i 2. Do `lessons.md` **dopisać** (bez edycji istniejących wpisów) regułę: nowy model dostaje decyzję w `MODEL_DECISIONS`, a model kasowany z kontem — fabrykę w `FACTORIES`; nowa trasa z id — wpis w `ID_ROUTES`.

**Contract**: sekcje §3, §6.2, §6.6 w `test-plan.md`; nowy wpis na końcu `lessons.md`.

### Success Criteria:

#### Automated Verification:

- Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py`
- mutmut bez niewyjaśnionych przeżyć: `rm -rf mutants && uv run mutmut run && uv run mutmut results`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Przegląd §6.2 i nowego wpisu w `lessons.md` przez człowieka

---

## Testing Strategy

### Unit Tests:

- Strażnik tras (bez bazy): router vs `ID_ROUTES`.
- Rejestr modeli i fabryk (bez bazy): `apps.get_models()` / `user_data_models()` vs `MODEL_DECISIONS` / `FACTORIES`.

### Integration Tests:

- 404 na każdej trasie z `ID_ROUTES` dla innego użytkownika (istniejący test, nowe źródło parametrów).
- Metamorficzny test pamięci przez `POST /conversations/start/` z `fake_llm`.
- Usunięcie przez stronę: żaden wiersz Anny w żadnym modelu z domknięcia; dane Łukasza całe.
- Usunięcie przez admina (pojedyncze i zbiorcze): sesje i `LogEntry` o Annie usunięte.

### Manual Testing Steps:

1. Przegląd diffów faz 1–2 pod kątem „lista porównana z samą sobą”.
2. Lokalne usunięcie testowego użytkownika w `/admin/` i sprawdzenie „Recent actions”.

## Performance Considerations

Pętla po wszystkich sesjach przy każdym usunięciu użytkownika — bez zmian względem dzisiejszego `delete_account`; przy max 10 użytkownikach pomijalne (`test-plan.md` §7).

## Migration Notes

Brak migracji: sygnał i testy nie zmieniają schematu. Mutanty `M22`/`M23` zmieniają modele tylko w tymczasowej kopii repo.

## References

- Research: `context/changes/testing-privacy-and-deletion-boundaries/research.md`
- Plan testów: `context/foundation/test-plan.md` §2 (#3, #6), §6.1 (wzorzec potwierdzenia mutacją)
- Granica izolacji: `conversations/views.py:24-25`
- Wybór pamięci: `conversations/memory.py:77-120`
- Usuwanie konta: `accounts/services.py:28-54`
- Strażnik relacji: `tests/test_account_deletion.py:110-166`
- Test 404: `tests/test_conversation_views.py:846-881`
- Test pamięci: `tests/test_conversation_views.py:1309-1323`
- Kolejność logu i usunięcia w adminie: `django/contrib/admin/options.py:2544-2545`, `django/contrib/admin/actions.py:49-50` (Django 6.1.1)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Izolacja tras i pamięci (#3)

#### Automated

- [x] 1.1 Testy przechodzą: `uv run pytest` — ae92858
- [x] 1.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — ae92858
- [x] 1.3 Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py C1 M16 M17 M18` — ae92858

#### Manual

- [x] 1.4 Przegląd diffu: `ID_ROUTES` jest literałem, a strażnik nie wylicza oczekiwanego zbioru z routera — ae92858

### Phase 2: Rejestr modeli i test „żaden model nie zostawia wierszy” (#6)

#### Automated

- [x] 2.1 Testy przechodzą: `uv run pytest` — df76370
- [x] 2.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — df76370
- [x] 2.3 Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py M22 M23` — df76370

#### Manual

- [x] 2.4 Przegląd diffu: `MODEL_DECISIONS` i `FACTORIES` są literałami porównywanymi z rejestrem Django, nie z sobą nawzajem — df76370

### Phase 3: Usuwanie przez `/admin/` (#6)

#### Automated

- [x] 3.1 Nowy test admina jest czerwony przed poprawką: `uv run pytest tests/test_account_deletion.py -k admin` — 375e2e4
- [x] 3.2 Testy przechodzą po poprawce: `uv run pytest` — 375e2e4
- [x] 3.3 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 375e2e4
- [x] 3.4 Mutanty fazy zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py M19 M20 M21 M24` — 375e2e4

#### Manual

- [x] 3.5 Lokalnie (`uv run python manage.py runserver`): właściciel usuwa testowego użytkownika w `/admin/`, a w „Recent actions” nie zostaje wpis z jego e-mailem — 375e2e4

### Phase 4: Domknięcie

#### Automated

- [x] 4.1 Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py` — 818a553
- [x] 4.2 mutmut bez niewyjaśnionych przeżyć: `rm -rf mutants && uv run mutmut run && uv run mutmut results` — 818a553
- [x] 4.3 Testy przechodzą: `uv run pytest` — 818a553
- [x] 4.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 818a553

#### Manual

- [x] 4.5 Przegląd §6.2 i nowego wpisu w `lessons.md` przez człowieka — 818a553
