# Usunięcie konta wraz z danymi (S-04) — Implementation Plan

## Overview

Zalogowany użytkownik może usunąć swoje konto wraz ze wszystkimi danymi (rozmowy, błędy, pamięć — FR-013) i może się wylogować (FR-002, dotąd Parked, dołączone przy okazji, bo usuwanie i tak potrzebuje `logout()`). Usunięcie jest natychmiastowe i twarde: po podaniu obecnego hasła w jednej transakcji znikają sesje użytkownika, wpisy logu admina o nim i sam użytkownik z kaskadą ORM. Dokumenty zapisują jawne wyjątki od „trwale w 24 h” (NFR „Usuwanie danych”): logi nadużyć OpenAI (do 30 dni) i przyszłe kopie zapasowe (do 7 dni).

## Current State Analysis

- `request.user.delete()` usuwa wszystkie dane z PRD: `Conversation` i `Mistake` dziedziczą po `UserOwned` z `on_delete=CASCADE` (`accounts/ownership.py:22-25`), `Message` i `Mistake` mają `CASCADE` do `Conversation` (`conversations/models.py:84-85,115-116`). Pamięć to pola `Conversation` + wiersze `Mistake`, bez osobnej tabeli. Kaskadę wykonuje ORM, nie baza (research §1).
- Poza kaskadą zostają: wiersze `django_session` użytkownika (inne urządzenia, do 14 dni, wygasłe — do `clearsessions`, którego nikt nie uruchamia) oraz wpisy `django_admin_log` o nim z e-mailem w `object_repr` (`accounts/models.py:80-81`) — research §2.
- `accounts/views.py` nie ma widoków (sam docstring), `accounts/urls.py:5` ma tylko `login/`. Wylogowania nie ma nigdzie (F-01, świadomie). `LOGOUT_REDIRECT_URL` nieustawione.
- `LoginRequiredMiddleware` chroni każdy nowy widok domyślnie (`talkaitive/settings.py:131`); `LOGIN_URL = "login"` (`:137`).
- Strona główna pokazuje tylko „Signed in as {{ user.email }}” (`conversations/templates/conversations/home.html:5`) — brak nawigacji. Szablon logowania dziedziczy po `base.html`, więc pokazuje komunikaty flash (`accounts/templates/base.html:45-47`).
- Testy kaskady istnieją tylko na modelu testowym `OwnedNote` (`tests/test_ownership.py:37-44`); brak testu na prawdziwych modelach i brak strażnika, który złapie przyszły model z FK do `User` (ryzyko z `roadmap.md:135`).

## Desired End State

- Na stronie głównej przy „Signed in as …” są: przycisk „Log out” (POST) i link „Delete account”.
- `POST /logout/` wylogowuje i przekierowuje na `/login/`. `GET /logout/` zwraca 405.
- `GET /account/delete/` pokazuje, co zniknie (rozmowy, błędy, pamięć), że to nieodwracalne, jedno zdanie o kopiach u dostawcy modelu (OpenAI, do 30 dni) i pole na obecne hasło. Dla superusera zamiast formularza — informacja, że konto właściciela usuwa się przez `/admin/` lub `manage.py`.
- `POST /account/delete/` z poprawnym hasłem (nie-superuser): w jednej transakcji usuwa wszystkie wiersze `django_session` tego użytkownika, wpisy `LogEntry` o nim i samego użytkownika (kaskada); potem wylogowuje bieżące żądanie i przekierowuje na `/login/` z komunikatem „Your account has been deleted.”. Złe hasło lub superuser: konto zostaje, komunikat błędu, przekierowanie z powrotem na `/account/delete/`.
- Test strażnika wylicza wszystkie modele z relacją do `User` i porównuje je z jawną listą (każda z `CASCADE`) — nowy model danych użytkownika wywróci test, dopóki autor świadomie go nie dopisze.
- PRD, roadmapa i `deploy-plan.md` opisują wyjątki od 24 h i to, że wylogowanie jest już zrobione.

### Key Discoveries:

- Wzorzec widoku POST: `@require_POST`, cienki widok, logika w `services`, wyjątek z komunikatem → `messages.error` + redirect (`conversations/views.py:60-68,138-142`; `ConversationError` w `conversations/services.py:52-53`). Typ `AuthenticatedHttpRequest` (`conversations/views.py:24-27`).
- `LogoutView` w Django 6.1 wylogowuje tylko przez POST; bez `next_page`/`LOGOUT_REDIRECT_URL` renderuje `registration/logged_out.html`, którego repo nie ma (dokumentacja Django 6.1, Context7, 2026-10-09).
- `Session.get_decoded()` zwraca słownik sesji; `_auth_user_id` jest w nim tekstem (`str(pk)`), więc porównujemy z `str(user.pk)`.
- `LogEntry.object_id` to tekst, nie FK; wpisy *o* użytkowniku filtrujemy po `content_type` = `ContentType` modelu `User` i `object_id=str(pk)`. Wpisy, których użytkownik jest *autorem*, usuwa już kaskada (FK `LogEntry.user`).
- Wzorce testów: fixture per plik (`tests/test_login.py:9-11`), `client.force_login`, „niezalogowany → 302 do `/login/?next=`” (`tests/test_conversation_views.py:580-598`), wylogowanie sprawdzane przez `"_auth_user_id" not in client.session` (`tests/test_login.py:58`).
- `settings_test` dodaje `tests.ownership_testapp` z `OwnedNote` (`talkaitive/settings_test.py:13`) — strażnik musi go uwzględnić na liście.

## What We're NOT Doing

- **Okno na rozmyślenie / soft delete.** Usunięcie jest natychmiastowe i nieodwracalne; brak `is_active=False` z opóźnionym kasowaniem i brak crona.
- **Obsługa wyścigu z trwającą turą agenta lub analizą.** Jeśli w drugiej karcie trwa płatne wywołanie modelu, po jego powrocie `_lock` (`conversations/services.py:60-66`) rzuci `Conversation.DoesNotExist` → błąd 500 w tej karcie i zapłacone wywołanie bez efektu. Zaakceptowane: dane i tak znikają w całości, osieroconych wierszy nie ma. Brak blokady w widoku i brak zmian w `conversations/services.py`.
- **Samousunięcie superusera z aplikacji.** Zablokowane; konto właściciela usuwa się przez `/admin/` lub `manage.py`.
- **Blokada dla `is_staff` bez `is_superuser`.** Takie konto dziś nie istnieje.
- **Wniosek o ZDR w OpenAI** i jakakolwiek próba usuwania danych po stronie OpenAI.
- **Budowa `pg_dump`.** Zapisujemy tylko regułę retencji w istniejącym TODO.
- **Limit prób hasła na stronie usuwania.** Atakujący musi już mieć zalogowaną sesję; poza zakresem MVP.
- **Nawigacja / strona konta w `base.html`.** Link i przycisk są tylko na stronie głównej.
- **Aktualizacja opisów issue #5 / LUK-20.** Lustra synchronizują tylko status (reguły w `context/foundation/lessons.md`).

## Implementation Approach

Najpierw wylogowanie (najmniejsza, samodzielna zmiana na gotowym widoku Django), potem usuwanie konta według wzorca `conversations`: serwis `accounts/services.py` z jedną funkcją w transakcji i wyjątkiem z komunikatem, cienki widok GET/POST, jeden szablon, link na stronie głównej. Testy obejmują kaskadę na prawdziwych modelach, strażnika relacji do `User`, sesje i log admina. Na końcu dokumenty: wyjątki od 24 h w PRD i `deploy-plan.md`, FR-002 zdjęte z Parked i Non-Goals.

## Critical Implementation Details

- **State sequencing:** porządek w widoku to: serwis usuwa (sesje → `LogEntry` → `user.delete()`, wszystko w `transaction.atomic`), potem `logout(request)`, potem `messages.success`, potem redirect. Serwis usuwa także wiersz *bieżącej* sesji, ale `logout()` nadal trzeba wywołać — dopiero `flush()` w nim podmienia klucz sesji w ciasteczku przeglądarki. `pk` użytkownika zapamiętaj przed `user.delete()` (Django ustawia potem `pk=None`). Komunikat dodany po `logout()` trafia do ciasteczka (domyślne `FallbackStorage`), więc przeżyje przekierowanie.
- **Sesje:** przeglądaj wszystkie wiersze `Session` (także wygasłe — też trzymają id), przez `.iterator()`; uszkodzone dane sesji `get_decoded()` zwraca jako pusty słownik, więc nie wymagają osobnej obsługi.

## Phase 1: Wylogowanie (FR-002)

### Overview

Użytkownik może się wylogować przyciskiem na stronie głównej.

### Changes Required:

#### 1. Trasa wylogowania

**File**: `accounts/urls.py`

**Intent**: Dodać wbudowany `LogoutView` z przekierowaniem na logowanie, żeby nie był potrzebny szablon `logged_out.html`.

**Contract**: `path("logout/", LogoutView.as_view(next_page="login"), name="logout")`. Tylko POST (GET → 405, zachowanie Django).

#### 2. Przycisk na stronie głównej

**File**: `conversations/templates/conversations/home.html`

**Intent**: Przy „Signed in as …” dodać formularz POST z `{% csrf_token %}` i przyciskiem „Log out”, w stylu istniejących formularzy (`<form method="post">`, klasa `actions` z `base.html:28` do ułożenia w wierszu). Faza 2 dopisze obok link „Delete account”.

**Contract**: `<form method="post" action="{% url 'logout' %}">`. Interfejs po angielsku.

#### 3. Docstring aplikacji

**File**: `accounts/views.py`

**Intent**: Docstring mówi „no own views yet”; po fazie 1 nadal nie ma własnych widoków, ale wspomina tylko login. Dopisać, że logout to wbudowany `LogoutView` (faza 2 i tak go przepisze).

**Contract**: tylko tekst docstringu.

#### 4. Testy

**File**: `tests/test_login.py`

**Intent**: Pokryć wylogowanie obok testów logowania.

**Contract**: testy: `POST /logout/` zalogowanego → 302 na `/login/` i `"_auth_user_id" not in client.session`, potem `GET /` → 302 na `/login/?next=/`; `GET /logout/` → 405; strona główna zalogowanego zawiera formularz z akcją `/logout/`.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Lokalnie (`uv run python manage.py runserver`): po kliknięciu „Log out” na stronie głównej ląduję na `/login/`, a wejście na `/` przekierowuje z powrotem do logowania

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Usuwanie konta (FR-013)

### Overview

Użytkownik usuwa konto po podaniu hasła; znikają wszystkie jego dane w bazie aplikacji, łącznie z sesjami i wpisami logu admina o nim.

### Changes Required:

#### 1. Serwis usuwania konta

**File**: `accounts/services.py` (nowy)

**Intent**: Jedno miejsce z regułami usuwania, żeby widok był cienki (wzorzec `conversations/services.py`). Sprawdza superusera i hasło, potem w jednej transakcji usuwa sesje użytkownika, wpisy `LogEntry` o nim i samego użytkownika (kaskada ORM — nigdy surowym SQL).

**Contract**:
- `class AccountDeletionError(Exception)` — odmowa; komunikat (po angielsku) jest pokazywany użytkownikowi tak, jak jest (jak `ConversationError`).
- `def delete_account(user: User, password: str) -> None` — rzuca `AccountDeletionError`, gdy `user.is_superuser` (komunikat: konto właściciela usuwa się przez `/admin/` lub `manage.py`) albo gdy `not user.check_password(password)` (komunikat: „Incorrect password.”). Inaczej, w `transaction.atomic()`: usuwa każdy `Session`, którego `get_decoded().get("_auth_user_id") == str(user.pk)`; usuwa `LogEntry` z `content_type=ContentType.objects.get_for_model(User)` i `object_id=str(user.pk)`; wywołuje `user.delete()`.
- Docstring modułu: co jest usuwane, dlaczego sesje i log admina osobno (nie obejmuje ich kaskada) i że kopie u OpenAI oraz w kopiach zapasowych są poza aplikacją (odesłanie do PRD NFR „Usuwanie danych”).

#### 2. Widok

**File**: `accounts/views.py`

**Intent**: Pierwszy własny widok aplikacji `accounts`: GET pokazuje stronę potwierdzenia, POST woła serwis. Styl jak `conversations/views.py` (funkcja, dekoratory metod, `AuthenticatedHttpRequest`, POST zawsze przekierowuje). Docstring modułu przepisać.

**Contract**:
- `def account_delete(request: AuthenticatedHttpRequest) -> HttpResponse` z `@require_http_methods(["GET", "POST"])`. Typ `AuthenticatedHttpRequest` importować z `conversations.views` albo przenieść w jedno wspólne miejsce — decyzja implementującego, bez duplikowania klasy.
- GET → render `accounts/account_delete.html` z kontekstem `can_delete = not request.user.is_superuser`.
- POST → `delete_account(request.user, request.POST.get("password", ""))`; przy `AccountDeletionError`: `messages.error` + `redirect("account_delete")`; przy sukcesie: `logout(request)`, `messages.success(request, "Your account has been deleted.")`, `redirect("login")` (kolejność — patrz Critical Implementation Details).

#### 3. Trasa

**File**: `accounts/urls.py`

**Intent**: Podpiąć widok.

**Contract**: `path("account/delete/", views.account_delete, name="account_delete")`. Chroniony przez `LoginRequiredMiddleware` bez dekoratora.

#### 4. Szablon strony potwierdzenia

**File**: `accounts/templates/accounts/account_delete.html` (nowy)

**Intent**: Strona, która uczciwie mówi, co się stanie, i wymaga hasła. Po angielsku, dziedziczy po `base.html`, bez nowego CSS poza istniejącymi klasami (`notice`, `error`).

**Contract**:
- Tytuł bloku `title`: „Delete account - TalkAItive” (styl `registration/login.html:3`).
- Treść: konto i wszystkie rozmowy, listy błędów i pamięć zostaną usunięte natychmiast; tego nie da się cofnąć; jedno zdanie, że dostawca modelu (OpenAI) może przechowywać kopie tekstu rozmów do 30 dni do monitoringu nadużyć i aplikacja nie może ich usunąć.
- Gdy `can_delete`: `<form method="post">` z `{% csrf_token %}`, `<label>` + `<input type="password" name="password" autocomplete="current-password" required>`, przycisk „Delete my account permanently”, link „Cancel” do `home`.
- Gdy nie `can_delete`: `notice` z informacją o koncie właściciela, bez formularza, link do `home`.

#### 5. Link na stronie głównej

**File**: `conversations/templates/conversations/home.html`

**Intent**: Obok przycisku „Log out” z fazy 1 dodać link „Delete account” do `account_delete`.

**Contract**: `<a href="{% url 'account_delete' %}">Delete account</a>`.

#### 6. Testy

**File**: `tests/test_account_deletion.py` (nowy)

**Intent**: Udowodnić, że usuwanie obejmuje wszystko i nikogo więcej, oraz zabezpieczyć przyszłe slice'y. Fixture per plik (dwóch użytkowników: Anna, Łukasz; superuser), `force_login` lub `client.login`.

**Contract** — testy:
- **Kaskada na prawdziwych modelach:** Anna i Łukasz mają po zakończonej, przeanalizowanej rozmowie z wiadomościami, błędami i polami pamięci (`memory_prompt`, `learner_facts`, `scene_notes`); po `POST /account/delete/` Anny z poprawnym hasłem: brak jej `User`, `Conversation`, `Message`, `Mistake`; dane Łukasza nietknięte.
- **Strażnik relacji do `User`:** przejście po `apps.get_models()` i ich polach konkretnych (`concrete`), które są relacją (`many_to_one`, `one_to_one` lub `many_to_many`) z `related_model` = `User`; zbiór `(model, nazwa pola)` równy jawnej liście `{Conversation.user, Mistake.user, LogEntry.user, OwnedNote.user}`, a każde FK ma `remote_field.on_delete is models.CASCADE`. Komunikat błędu mówi, co zrobić z nowym modelem (dopisać do listy po sprawdzeniu, że znika z kontem).
- **Sesje:** Anna zalogowana w dwóch klientach, Łukasz w trzecim; usunięcie z pierwszego klienta → w `Session` nie ma wierszy z `_auth_user_id` Anny, drugi klient na `GET /` dostaje 302 do logowania, sesja Łukasza zostaje.
- **Log admina:** wpisy `LogEntry` (tworzone wprost przez `LogEntry.objects.create`, autor: superuser) o Annie i o Łukaszu; po usunięciu Anny zostaje tylko wpis o Łukaszu.
- **Sukces:** odpowiedź 302 na `/login/`, `"_auth_user_id" not in client.session`, strona logowania po przekierowaniu pokazuje „Your account has been deleted.”.
- **Złe hasło:** konto i dane zostają, 302 na `/account/delete/`, komunikat „Incorrect password.”, użytkownik nadal zalogowany.
- **Superuser:** `GET` pokazuje informację bez pola hasła; `POST` z poprawnym hasłem — konto zostaje, komunikat błędu.
- **GET zwykłego użytkownika:** 200, zawiera pole `password` i zdanie o OpenAI.
- **Niezalogowany:** `GET /account/delete/` → 302 na `/login/?next=/account/delete/`.
- **Strona główna:** zawiera link do `/account/delete/`.

### Success Criteria:

#### Automated Verification:

- Migracje są kompletne (brak nowych): `uv run python manage.py makemigrations --check --dry-run`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Lokalnie: konto testowe założone w `uv run python manage.py shell` (`User.objects.create_user`) z jedną zakończoną rozmową; strona `/account/delete/` czytelnie mówi, co zniknie, i zawiera zdanie o OpenAI
- Lokalnie: złe hasło pokazuje błąd i nic nie usuwa; poprawne hasło kończy się na `/login/` z komunikatem „Your account has been deleted.”, a w `shell` brak użytkownika, jego rozmów, wiadomości i błędów
- Lokalnie: zalogowany superuser widzi na `/account/delete/` informację bez formularza

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Dokumenty — wyjątki od 24 h i FR-002

### Overview

Dokumenty mówią prawdę o tym, co produkt usuwa i czego nie może, oraz że wylogowanie jest zrobione.

### Changes Required:

#### 1. PRD

**File**: `context/foundation/prd.md`

**Intent**: Zapisać wyjątki od „trwale w 24 h” tam, gdzie jest wymóg, i usunąć non-goal, który przestał być prawdą.

**Contract**:
- NFR „Usuwanie danych” (`prd.md:95`): dopisać, że 24 h dotyczy danych w bazie aplikacji (usuwane natychmiast); poza kontrolą produktu są kopie u dostawcy modelu (OpenAI, logi monitoringu nadużyć do 30 dni, brak ZDR) i kopie zapasowe bazy (do 7 dni, gdy powstaną — reguła w `context/deployment/deploy-plan.md`).
- Non-Goals → Funkcjonalne: usunąć punkt „Wylogowanie poza zakresem wiążącym MVP” (`prd.md:130`). FR-002 zostaje bez zmiany priorytetu.

#### 2. Roadmapa

**File**: `context/foundation/roadmap.md`

**Intent**: Zdjąć FR-002 z Parked i dopisać je do S-04, bo jest dostarczane w tej zmianie.

**Contract**: usunąć punkt „Wylogowanie (FR-002)” z `## Parked`; w S-04 (`### S-04` → `PRD refs`) i w wierszu S-04 tabeli `## At a glance` (kolumna PRD refs) dopisać `FR-002`; w `Outcome` S-04 dopisać, że użytkownik może też się wylogować. Pola `Status` nie ruszać (osobna synchronizacja skilli).

#### 3. Plan wdrożenia

**File**: `context/deployment/deploy-plan.md`

**Intent**: Reguła retencji ma istnieć, zanim powstanie backup.

**Contract**: w TODO „Daily off-platform `pg_dump`” (`deploy-plan.md:200`) dopisać podpunkt: zrzuty starsze niż 7 dni są usuwane; dane usuniętych kont mogą przetrwać w zrzutach do 7 dni (wyjątek zapisany w PRD, NFR „Usuwanie danych”).

### Success Criteria:

#### Automated Verification:

- PRD nie zawiera już non-goal o wylogowaniu: `! grep -n "Wylogowanie poza zakresem" context/foundation/prd.md`
- Roadmapa nie ma FR-002 w Parked: `! grep -n "Wylogowanie (FR-002)" context/foundation/roadmap.md`
- `deploy-plan.md` zawiera regułę 7 dni: `grep -n "7 dni\|7 days" context/deployment/deploy-plan.md`

#### Manual Verification:

- Treść wyjątku w PRD jest zgodna ze zdaniem na stronie `/account/delete/` (OpenAI, 30 dni) i z regułą w `deploy-plan.md` (7 dni)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `delete_account`: superuser odrzucony, złe hasło odrzucone, sukces usuwa sesje, `LogEntry` o użytkowniku i użytkownika z kaskadą (pokryte przez testy widoku w `tests/test_account_deletion.py`).
- Strażnik relacji do `User` z `CASCADE`.

### Integration Tests:

- Pełny przepływ przez klienta testowego: logowanie → `GET /account/delete/` → `POST` → `/login/` z komunikatem; drugi klient tej samej osoby traci sesję; dane drugiej osoby zostają.
- Wylogowanie przez `POST /logout/`.

### Manual Testing Steps:

1. `uv run python manage.py runserver`, zaloguj się na konto testowe, kliknij „Log out” → `/login/`.
2. Zaloguj się ponownie, odbądź krótką rozmowę (z `.env` i prawdziwym modelem albo pomiń) i zakończ ją.
3. „Delete account” → wpisz złe hasło → błąd, konto zostaje.
4. Wpisz poprawne hasło → `/login/` z komunikatem; próba logowania tym kontem się nie udaje; w `shell` brak danych.
5. Zaloguj się jako superuser → `/account/delete/` pokazuje informację bez formularza.

## Performance Considerations

Przegląd wszystkich wierszy `django_session` rośnie liniowo z liczbą sesji; przy kilku użytkownikach (PRD `target_scale.users: small`) to ułamek sekundy. Przy dużej skali trzeba by przejść na backend sesji z indeksem po użytkowniku — poza MVP.

## Migration Notes

Brak zmian schematu i migracji. Wdrożenie przez auto-deploy z `main`. Na produkcji nie testujemy usuwania na prawdziwych kontach; ewentualna próba tylko na koncie testowym założonym w `/admin/` (jego wpis „Added” w logu admina też zniknie).

## References

- Related research: `context/changes/account-and-data-deletion/research.md`
- Wzorzec widoku POST: `conversations/views.py:60-68,138-142`
- Wzorzec wyjątku z komunikatem: `conversations/services.py:52-57`
- Test kaskady na modelu testowym i strażnik admina: `tests/test_ownership.py:37-52`
- Decyzja o braku wylogowania w F-01: `context/archive/2026-10-01-auth-and-access-scaffold/plan-brief.md:42`
- Reguły `UserOwned` / `for_user`: `context/foundation/lessons.md:54-66`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Wylogowanie (FR-002)

#### Automated

- [x] 1.1 Testy przechodzą: `uv run pytest` — 9d90a73
- [x] 1.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 9d90a73

#### Manual

- [x] 1.3 Lokalnie (`uv run python manage.py runserver`): po kliknięciu „Log out” na stronie głównej ląduję na `/login/`, a wejście na `/` przekierowuje z powrotem do logowania — 9d90a73

### Phase 2: Usuwanie konta (FR-013)

#### Automated

- [x] 2.1 Migracje są kompletne (brak nowych): `uv run python manage.py makemigrations --check --dry-run` — a58a433
- [x] 2.2 Testy przechodzą: `uv run pytest` — a58a433
- [x] 2.3 Lint i format: `uv run ruff check . && uv run ruff format --check .` — a58a433

#### Manual

- [x] 2.4 Lokalnie: konto testowe założone w `uv run python manage.py shell` (`User.objects.create_user`) z jedną zakończoną rozmową; strona `/account/delete/` czytelnie mówi, co zniknie, i zawiera zdanie o OpenAI — a58a433
- [x] 2.5 Lokalnie: złe hasło pokazuje błąd i nic nie usuwa; poprawne hasło kończy się na `/login/` z komunikatem „Your account has been deleted.”, a w `shell` brak użytkownika, jego rozmów, wiadomości i błędów — a58a433
- [x] 2.6 Lokalnie: zalogowany superuser widzi na `/account/delete/` informację bez formularza — a58a433

### Phase 3: Dokumenty — wyjątki od 24 h i FR-002

#### Automated

- [x] 3.1 PRD nie zawiera już non-goal o wylogowaniu: `! grep -n "Wylogowanie poza zakresem" context/foundation/prd.md` — 807a050
- [x] 3.2 Roadmapa nie ma FR-002 w Parked: `! grep -n "Wylogowanie (FR-002)" context/foundation/roadmap.md` — 807a050
- [x] 3.3 `deploy-plan.md` zawiera regułę 7 dni: `grep -n "7 dni\|7 days" context/deployment/deploy-plan.md` — 807a050

#### Manual

- [x] 3.4 Treść wyjątku w PRD jest zgodna ze zdaniem na stronie `/account/delete/` (OpenAI, 30 dni) i z regułą w `deploy-plan.md` (7 dni) — 807a050
