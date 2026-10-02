# Auth i izolacja danych między użytkownikami — Implementation Plan

## Overview

F-01 z roadmapy: zaproszony użytkownik loguje się e-mailem i hasłem, każda strona poza logowaniem (i `/healthz/`) wymaga zalogowania, a przyszłe dane per użytkownik (rozmowy, błędy, pamięć z S-01…S-03) dostają jeden wspólny wzorzec izolacji, sprawdzany testami. Na koniec zmiana trafia na produkcję przez kontrolowany reset bazy, bo zmiana modelu użytkownika po pierwszej migracji wymaga czystej bazy.

## Current State Analysis

- Repo to goły `startproject`: brak własnych aplikacji, modeli, widoków i szablonów (`talkaitive/settings.py:62-69`, `talkaitive/urls.py:28-31`).
- Użytkownik to domyślny `auth.User` (logowanie po `username`). Na produkcji tabela `auth_user` istnieje — 18 migracji i jedno konto admina, brak innych danych i brak backupu (`context/deployment/deploy-plan.md`, sekcje Verification i TODO).
- Middleware ma już `SessionMiddleware` i `AuthenticationMiddleware` (`talkaitive/settings.py:71-80`); brak wymogu logowania na stronach.
- `/healthz/` to widok bez auth i bez DB (`talkaitive/urls.py:23-25`); Railway health check odpytuje go po HTTP bez sesji.
- Brak testów i narzędzi testowych (`pyproject.toml:13-16` — tylko `ruff` w grupie dev).
- `main` auto-deployuje na Railway, a pre-deploy uruchamia `migrate` (`context/deployment/web-settings.json`).

## Desired End State

- Niezalogowany użytkownik wchodzący na dowolną stronę (poza `/login/`, `/healthz/` i statykami) trafia na `/login/?next=<ścieżka>`.
- Użytkownik loguje się e-mailem i hasłem; wielkość liter w e-mailu nie ma znaczenia. Po zalogowaniu widzi stronę powitalną `/` (po angielsku) z własnym e-mailem. Sesja trwa 2 tygodnie (domyślne Django).
- Właściciel zakłada konta i resetuje hasła w `/admin/`; admin pokazuje wyłącznie konta (i grupy z Django), nigdy dane rozmów.
- Istnieje abstrakcyjny model `UserOwned` z metodą `for_user(user)`; testy dowodzą, że użytkownik A nie widzi danych B i że usunięcie konta usuwa jego dane.
- `uv run pytest` przechodzi; produkcja działa na nowym modelu użytkownika z nowym kontem admina i kontem żony.

### Key Discoveries:

- Django 6.1.1 ma wbudowany `django.contrib.auth.middleware.LoginRequiredMiddleware` (`.venv/.../django/contrib/auth/middleware.py:43`); `LoginView` i `admin.site.login` są już oznaczone `@login_not_required` (`django/contrib/auth/views.py:74`, `django/contrib/admin/sites.py:415`). `/healthz/` trzeba oznaczyć ręcznie.
- `BaseUserManager.get_by_natural_key` szuka dokładnego dopasowania `USERNAME_FIELD` (`django/contrib/auth/base_user.py:36-37`) — to jedyne miejsce, przez które `ModelBackend` szuka użytkownika przy logowaniu, więc tu wstawiamy porównanie bez wielkości liter.
- Django 6.1 udostępnia `UserCreationForm` / `AdminUserCreationForm` / `UserChangeForm` (`django/contrib/auth/forms.py:254,275,592`) — dostosowujemy je przez `Meta.model` i `Meta.fields`, bez pisania od zera.
- `db.sqlite3` lokalnie nie istnieje i jest w `.gitignore` (`.gitignore:16`).
- `/10x-implement` commituje każdą fazę lokalnie, a push na `main` = deploy. Push przed resetem produkcyjnej bazy kończy się błędem `InconsistentMigrationHistory` w pre-deploy (Railway zostawia wtedy poprzednią wersję).

## What We're NOT Doing

- Wylogowanie (FR-002) — zaparkowane w roadmapie.
- Samodzielna rejestracja, zaproszenia mailem, reset hasła przez użytkownika — PRD Non-Goals; konta i hasła obsługuje właściciel w `/admin/`.
- Ochrona przed zgadywaniem hasła (limit prób, np. django-axes) — świadomie odłożone; zapisane w Open Risks.
- Zmiana czasu sesji — zostaje domyślne 2 tygodnie.
- Rejestrowanie danych per użytkownik w adminie — nigdy (PRD: nikt, w tym właściciel, nie widzi cudzych danych).
- Prawdziwe modele rozmów/błędów/pamięci — należą do S-01…S-03; tu tylko wzorzec i próbny model testowy.
- Usuwanie konta przez użytkownika (FR-013) — S-04; tu tylko przygotowanie (`on_delete=CASCADE`).
- `mypy` + `django-stubs`, CI na GitHub Actions, backup `pg_dump` — osobne zadania (CLAUDE.md, `deploy-plan.md` TODO).
- Tłumaczenia UI (i18n) — interfejs po angielsku, `LANGUAGE_CODE` zostaje `en-us`.

## Implementation Approach

Kolejność od fundamentu do produkcji: najpierw model użytkownika (bo wszystko inne od niego zależy, a Django wymaga go przed pierwszą migracją), potem warstwa logowania, potem wzorzec izolacji, na końcu jedno kontrolowane wdrożenie. Fazy 1–3 są commitowane lokalnie, ale **nie pushowane**; push następuje dopiero w fazie 4, po resecie bazy produkcyjnej. Testy w pytest (z `pytest-django`) powstają razem z kodem każdej fazy.

## Critical Implementation Details

- **Timing & lifecycle:** Nie pushować commitów faz 1–3 przed fazą 4. Kolejność w fazie 4 jest sztywna: reset schematu Postgresa → `git push` → `createsuperuser`. Odwrotna kolejność kończy się nieudanym pre-deploy `migrate` (stara wersja zostaje, ale nowa się nie wdroży).
- **State sequencing:** E-mail ma jedną kanoniczną postać — całość małymi literami — zapisywaną w `User.save()`, więc zwykłe `unique=True` wystarcza do blokady duplikatów różniących się wielkością liter. Wyszukiwanie przy logowaniu (`get_by_natural_key`) używa `email__iexact`, żeby wpisane `Anna@Example.DE` znalazło `anna@example.de`.

## Phase 1: Model użytkownika z e-mailem, admin i pytest

### Overview

Nowa aplikacja `accounts` z własnym modelem `User` (e-mail jako login), formularze admina do zakładania kont oraz konfiguracja pytest z pierwszymi testami.

### Changes Required:

#### 1. Zależności testowe

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Dodać pytest i jego integrację z Django jako zależności deweloperskie oraz skonfigurować pytest, żeby używał ustawień testowych.

**Contract**: `uv add --dev pytest pytest-django`. Sekcja `[tool.pytest.ini_options]` z `DJANGO_SETTINGS_MODULE = "talkaitive.settings_test"`, `python_files = ["test_*.py"]`, `pythonpath = ["."]`, `testpaths = ["tests"]`.

#### 2. Ustawienia testowe

**File**: `talkaitive/settings_test.py` (nowy)

**Intent**: Ustawienia używane tylko przez pytest: importują zwykłe ustawienia i (od fazy 3) dokładają próbną aplikację testową. Dzięki temu produkcja nigdy nie widzi modeli testowych.

**Contract**: `from .settings import *` z komentarzem `# noqa: F403`; w fazie 1 bez dodatków poza szybkim hasherem `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]` (przyspiesza testy).

#### 3. Aplikacja `accounts` i model `User`

**File**: `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/migrations/0001_initial.py` (nowe)

**Intent**: Własny model użytkownika, w którym unikalny e-mail jest loginem, bez pola `username`. Manager tworzy zwykłych użytkowników i superużytkowników (dla `createsuperuser`) i szuka użytkownika po e-mailu bez rozróżniania wielkości liter.

**Contract**:
- `class User(AbstractBaseUser, PermissionsMixin)` z polami `email` (`EmailField(unique=True)`), `is_active` (domyślnie `True`), `is_staff` (domyślnie `False`), `date_joined` (domyślnie teraz). `USERNAME_FIELD = "email"`, `EMAIL_FIELD = "email"`, `REQUIRED_FIELDS = []`.
- `User.save()` zapisuje `email` całkowicie małymi literami (po `strip()`). `User.clean()` (po `super().clean()`) robi to samo — `ModelForm` wywołuje `clean()` modelu przed `validate_unique()`, więc formularz admina pokaże błąd „already exists” zamiast `IntegrityError` (500).
- `class UserManager(BaseUserManager)`: `create_user(email, password=None, **extra)`, `create_superuser(email, password=None, **extra)` (wymusza `is_staff=True`, `is_superuser=True`), `get_by_natural_key(email)` → `self.get(email__iexact=email)`.
- Type hints na metodach managera i modelu (CLAUDE.md).

#### 4. Konfiguracja Django

**File**: `talkaitive/settings.py`

**Intent**: Zarejestrować aplikację i wskazać Django nowy model użytkownika.

**Contract**: `"accounts"` w `INSTALLED_APPS` (po aplikacjach `django.contrib.*`); `AUTH_USER_MODEL = "accounts.User"`.

#### 5. Admin dla kont

**File**: `accounts/admin.py`, `accounts/forms.py` (nowe)

**Intent**: Właściciel zakłada konta, ustawia i resetuje hasła oraz dezaktywuje konta w `/admin/`, na formularzach opartych na e-mailu.

**Contract**: Formularze dziedziczące po `AdminUserCreationForm` i `UserChangeForm` z `Meta.model = User` i `Meta.fields = ("email",)`. `UserAdmin` (z `django.contrib.auth.admin`) zarejestrowany dla `User` z `ordering = ("email",)`, `list_display = ("email", "is_active", "is_staff", "date_joined")`, `search_fields = ("email",)` oraz `fieldsets` / `add_fieldsets` bez `username`, `first_name`, `last_name`.

#### 6. Testy modelu i admina

**File**: `tests/__init__.py`, `tests/test_accounts.py` (nowe)

**Intent**: Pierwsze testy w repo — dowód, że model i admin działają zgodnie z decyzjami.

**Contract**: Testy (funkcje pytest z `@pytest.mark.django_db`):
- `create_user("Anna@Example.DE", ...)` zapisuje `anna@example.de`.
- Drugi `create_user` z tym samym e-mailem w innej wielkości liter rzuca `IntegrityError`.
- `get_by_natural_key("ANNA@example.de")` zwraca tego samego użytkownika.
- `create_superuser` ustawia `is_staff` i `is_superuser`; `call_command("createsuperuser", interactive=False, email=...)` z `DJANGO_SUPERUSER_PASSWORD` w środowisku tworzy konto.
- Zalogowany superużytkownik dostaje 200 na `/admin/accounts/user/` i `/admin/accounts/user/add/`, a POST formularza dodawania tworzy użytkownika z e-mailem małymi literami.
- POST formularza dodawania z `ANNA@example.de`, gdy `anna@example.de` już istnieje → 200 z błędem formularza (bez 500), liczba użytkowników bez zmian.

#### 7. Lokalna baza

**File**: `db.sqlite3` (lokalny, poza gitem)

**Intent**: Jeśli lokalna baza istnieje, usunąć ją przed pierwszym `migrate`, bo stara historia migracji `auth` koliduje z nowym modelem.

**Contract**: `rm -f db.sqlite3`, potem `uv run python manage.py migrate`.

### Success Criteria:

#### Automated Verification:

- Migracje generują się bez zmian do zapisania: `uv run python manage.py makemigrations --check --dry-run`
- Lokalna baza migruje od zera: `uv run python manage.py migrate`
- Testy fazy 1 przechodzą: `uv run pytest tests/test_accounts.py`
- Lint i format są czyste: `uv run ruff check . && uv run ruff format --check .`
- Django nie zgłasza problemów: `uv run python manage.py check`

#### Manual Verification:

- Po `uv run python manage.py createsuperuser` i `runserver` można zalogować się do `/admin/` e-mailem i założyć drugie konto z e-mailem pisanym wielkimi literami; na liście widać je małymi literami

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Do NOT push this commit.

---

## Phase 2: Logowanie i wymóg logowania na każdej stronie

### Overview

Strona logowania, strona powitalna `/` i globalny wymóg logowania, z wyjątkiem `/healthz/`.

### Changes Required:

#### 1. Wymóg logowania i adresy przekierowań

**File**: `talkaitive/settings.py`

**Intent**: Każdy widok bez jawnego zwolnienia wymaga zalogowania; Django wie, gdzie jest logowanie i dokąd wrócić po nim.

**Contract**: `"django.contrib.auth.middleware.LoginRequiredMiddleware"` w `MIDDLEWARE` zaraz po `AuthenticationMiddleware`. `LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "home"`. `SESSION_COOKIE_AGE` bez zmian (domyślne 2 tygodnie).

#### 2. Zwolnienie health checka

**File**: `talkaitive/urls.py`

**Intent**: Railway health check musi dostać 200 bez sesji, inaczej każdy deploy by się nie udał.

**Contract**: `healthz` udekorowany `@login_not_required` (`django.contrib.auth.decorators`); odpowiedź bez zmian (`"ok"`, `text/plain`).

#### 3. Widoki i adresy

**File**: `accounts/views.py`, `accounts/urls.py` (nowe), `talkaitive/urls.py`

**Intent**: Strona logowania oparta na wbudowanym `LoginView` i tymczasowa strona powitalna, którą S-01 zastąpi ekranem rozmowy.

**Contract**:
- `path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login")` — tylko widok logowania; bez `django.contrib.auth.urls` (te dokładają reset i zmianę hasła, które są poza zakresem).
- `home(request: HttpRequest) -> HttpResponse` pod `path("", ..., name="home")`, renderuje `accounts/home.html`.
- `talkaitive/urls.py` dołącza `include("accounts.urls")`; `/admin/` i `/healthz/` bez zmian.

#### 4. Szablony

**File**: `accounts/templates/base.html`, `accounts/templates/registration/login.html`, `accounts/templates/accounts/home.html` (nowe)

**Intent**: Minimalne, czytelne strony po angielsku, działające na telefonie (viewport meta, prosty CSS inline w `base.html`).

**Contract**: `login.html`: formularz z polami „Email” i „Password”, `{% csrf_token %}`, ukryte pole `next`, komunikat błędu `form.non_field_errors`. `home.html`: tekst w stylu „Signed in as {{ user.email }}” i informacja, że rozmowy pojawią się wkrótce. Brak linku do wylogowania.

#### 5. Testy logowania

**File**: `tests/test_login.py` (nowy)

**Intent**: Automatyczny dowód, że dostęp jest wymuszony i logowanie działa zgodnie z decyzjami.

**Contract**: Testy z klientem testowym Django (`client` fixture):
- Niezalogowany `GET /` → 302 na `/login/?next=/`.
- Niezalogowany `GET /healthz/` → 200 z treścią `ok`.
- Niezalogowany `GET /login/` → 200.
- Niezalogowany `GET /admin/` → 302 (nie 200).
- `POST /login/` z `Anna@Example.DE` i poprawnym hasłem dla `anna@example.de` → 302 na `/`; następnie `GET /` → 200 i zawiera `anna@example.de`.
- `POST /login/` ze złym hasłem → 200 z błędem formularza, użytkownik niezalogowany.
- Nieaktywny użytkownik (`is_active=False`) nie może się zalogować.
- Zalogowany `GET /login/` → przekierowanie na `/`.

### Success Criteria:

#### Automated Verification:

- Wszystkie testy przechodzą: `uv run pytest`
- Lint i format są czyste: `uv run ruff check . && uv run ruff format --check .`
- Django nie zgłasza problemów: `uv run python manage.py check`
- Kontrola produkcyjna nie zgłasza nowych ostrzeżeń względem stanu sprzed zmiany — oczekiwany exit 1 (przez `mail.E001`), a wynik zawiera dokładnie `mail.E001` i HSTS `security.W004`: `DEBUG=False SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))') ALLOWED_HOSTS=localhost uv run python manage.py check --deploy`

#### Manual Verification:

- Na `runserver`: wejście na `/` w oknie prywatnym przekierowuje na formularz logowania; po zalogowaniu e-mailem pisanym z wielkimi literami widać stronę powitalną z własnym e-mailem
- Formularz logowania wygląda czytelnie na wąskim ekranie (np. tryb mobilny w przeglądarce)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Do NOT push this commit.

---

## Phase 3: Wzorzec izolacji danych per użytkownik

### Overview

Abstrakcyjny model `UserOwned` z metodą `for_user`, próbny model tylko do testów, testy izolacji i zapis reguły dla kolejnych slice'ów.

### Changes Required:

#### 1. Wzorzec `UserOwned`

**File**: `accounts/ownership.py` (nowy)

**Intent**: Jeden wzór dla wszystkich przyszłych danych per użytkownik (rozmowy, błędy, pamięć): każdy rekord ma właściciela, odczyt idzie przez `for_user`, a usunięcie konta usuwa dane (przygotowanie pod S-04).

**Contract**:
- `class UserOwnedQuerySet(models.QuerySet)` z `for_user(self, user) -> Self`: dla zalogowanego użytkownika zwraca `filter(user=user)`, dla niezalogowanego (`not user.is_authenticated`) zwraca `self.none()` (fail closed).
- `class UserOwned(models.Model)`, `abstract = True`, pole `user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="+")`, `objects = UserOwnedQuerySet.as_manager()`.
- Docstring modułu: modele per użytkownik dziedziczą po `UserOwned`, widoki czytają je wyłącznie przez `Model.objects.for_user(request.user)`, a modele nigdy nie są rejestrowane w adminie.

#### 2. Próbna aplikacja testowa

**File**: `tests/ownership_testapp/__init__.py`, `tests/ownership_testapp/apps.py`, `tests/ownership_testapp/models.py`, `tests/ownership_testapp/migrations/0001_initial.py` (nowe); `talkaitive/settings_test.py`

**Intent**: Prawdziwych danych jeszcze nie ma, więc testujemy wzorzec na małym modelu, który istnieje tylko w testach.

**Contract**: Model `OwnedNote(UserOwned)` z polem `text = CharField(max_length=100)`. `settings_test.py` dokłada `"tests.ownership_testapp"` do `INSTALLED_APPS`. Migracja generowana przez `DJANGO_SETTINGS_MODULE=talkaitive.settings_test uv run python manage.py makemigrations ownership_testapp`.

#### 3. Testy izolacji

**File**: `tests/test_ownership.py` (nowy)

**Intent**: Automatyczny dowód guardrailu prywatności z PRD.

**Contract**:
- Notatki Anny i Łukasza: `OwnedNote.objects.for_user(anna)` zwraca tylko notatki Anny (i odwrotnie).
- `for_user(AnonymousUser())` zwraca pusty wynik.
- Usunięcie użytkownika usuwa jego notatki i nie rusza cudzych.
- Rejestr admina (`admin.site._registry`) zawiera wyłącznie modele z listy dozwolonych: `accounts.User` i `auth.Group` — test złapie, gdy przyszły slice zarejestruje dane użytkownika w adminie.

#### 4. Reguła dla kolejnych zmian

**File**: `context/foundation/lessons.md` (dopisanie na końcu, append-only), `CLAUDE.md` (sekcja „TalkAItive — project notes”, poza blokiem 10x-cli)

**Intent**: Kolejne slice'y (S-01…S-04) i agenci znają wzorzec bez czytania tego planu.

**Contract**:
- `lessons.md`: nowy wpis w formacie pliku (Context / Problem / Rule / Applies to): modele danych per użytkownik dziedziczą po `accounts.ownership.UserOwned`, są czytane przez `for_user(request.user)`, nie są rejestrowane w adminie, a test w `tests/test_ownership.py` pilnuje rejestru admina.
- `CLAUDE.md`: punkt o filtrowaniu do `request.user` wskazuje na `UserOwned` / `for_user`; punkt „No tests or type checker yet” zastąpiony informacją, że testy uruchamia `uv run pytest` (pytest-django, ustawienia `talkaitive.settings_test`), a `mypy` nadal jest planowany.

### Success Criteria:

#### Automated Verification:

- Wszystkie testy przechodzą: `uv run pytest`
- Migracje produkcyjne bez zmian do zapisania: `uv run python manage.py makemigrations --check --dry-run`
- Migracje testowe bez zmian do zapisania: `DJANGO_SETTINGS_MODULE=talkaitive.settings_test uv run python manage.py makemigrations --check --dry-run`
- Lint i format są czyste: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Wpis w `lessons.md` i zmiany w `CLAUDE.md` są zrozumiałe i zgodne z decyzjami (przeczytane przez człowieka)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Do NOT push this commit.

---

## Phase 4: Wdrożenie na produkcję z resetem bazy

### Overview

Kontrolowane przejście produkcji na nowy model użytkownika: reset schematu bazy, push, odtworzenie konta admina, założenie konta drugiej osoby i weryfikacja na żywej stronie.

### Changes Required:

#### 1. Kontrola przed resetem (agent)

**File**: — (git)

**Intent**: Upewnić się, że fazy 1–3 są zacommitowane lokalnie i nic z nich nie zostało wypchnięte.

**Contract**: `git status` czysty; `git log origin/main..main` pokazuje commity faz 1–3.

#### 2. Reset schematu bazy produkcyjnej (człowiek, własny terminal)

**File**: — (Railway Postgres)

**Intent**: Usunąć starą historię migracji i stare konto admina, bo nowy model użytkownika nie może zastąpić `auth.User` na istniejącej bazie. Baza zawiera tylko konto admina i nie ma backupu — świadomie akceptowane.

**Contract**: W terminalu z TTY: `railway ssh --service web -i ~/.ssh/id_ed25519_railway` (`deploy-plan.md`: domyślny klucz należy do innego konta Railway). Przed resetem sprawdzić, że to właściwe miejsce: `echo $RAILWAY_ENVIRONMENT` pokazuje `production`, a `python manage.py showmigrations auth | head -3` pokazuje zastosowane (`[X]`) migracje `auth`; jeśli nie — przerwać. Potem `python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('DROP SCHEMA public CASCADE'); c.execute('CREATE SCHEMA public')"`. Od tej chwili do końca kroku 3 działająca stara wersja nie ma tabel — akceptowalne (brak użytkowników poza właścicielem).

#### 3. Push i deploy (agent)

**File**: — (git, Railway)

**Intent**: Wdrożyć nowy kod; pre-deploy `migrate` tworzy wszystkie tabele od zera.

**Contract**: `git push origin main`; potem `railway logs` pokazuje udany pre-deploy `migrate` (w tym `accounts.0001_initial`) i zdany health check.

#### 4. Konto admina i konto drugiej osoby (człowiek)

**File**: — (Railway, `/admin/`)

**Intent**: Odtworzyć konto właściciela na nowym modelu i założyć konto zaproszonej osoby.

**Contract**: `railway ssh --service web -i ~/.ssh/id_ed25519_railway` → `python manage.py createsuperuser` (pyta o e-mail i hasło). Następnie logowanie przez `/login/`, przejście do `/admin/`, dodanie konta drugiej osoby (nie-staff).

#### 5. Zapis w dokumentacji wdrożenia (agent)

**File**: `context/deployment/deploy-plan.md`

**Intent**: Ślad audytowy resetu bazy i odtworzenia konta.

**Contract**: Nowy punkt w „Execution log” / „Status” z datą: schemat `public` zresetowany z powodu `AUTH_USER_MODEL = "accounts.User"`, superuser odtworzony, liczba zastosowanych migracji po deployu. `web-settings.json` bez zmian (ustawienia serwisu się nie zmieniają).

### Success Criteria:

#### Automated Verification:

- Lokalnie przed resetem: brak niezacommitowanych zmian i commity faz 1–3 tylko lokalnie: `git status --porcelain && git log --oneline origin/main..main`
- Health check na produkcji zwraca 200: `curl -s -o /dev/null -w "%{http_code}" https://web-production-5e685.up.railway.app/healthz/`
- Niezalogowany na `/` dostaje przekierowanie na logowanie: `curl -sI https://web-production-5e685.up.railway.app/` (302, `Location: /login/?next=/`)
- Strona logowania zwraca 200: `curl -s -o /dev/null -w "%{http_code}" https://web-production-5e685.up.railway.app/login/`

#### Manual Verification:

- Reset schematu wykonany w terminalu właściciela bez błędów
- `createsuperuser` na produkcji zakończony powodzeniem
- Właściciel loguje się na produkcji przez `/login/` e-mailem pisanym z wielkimi literami i widzi stronę powitalną ze swoim e-mailem
- Konto drugiej osoby założone w `/admin/`; logowanie nim w oknie prywatnym pokazuje stronę powitalną z jej e-mailem
- `/admin/` pokazuje tylko konta użytkowników i grupy

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful.

---

## Testing Strategy

### Unit Tests:

- Model `User`: normalizacja e-maila, unikalność bez względu na wielkość liter, `get_by_natural_key`, `create_superuser`, `createsuperuser` bez TTY.
- `UserOwned.for_user`: izolacja między dwoma użytkownikami, pusty wynik dla niezalogowanego, kaskadowe usunięcie.
- Rejestr admina: tylko dozwolone modele.

### Integration Tests:

- Klient testowy Django: przekierowania niezalogowanego, `/healthz/` bez logowania, pełne logowanie z e-mailem w innej wielkości liter, złe hasło, nieaktywne konto, formularz dodawania użytkownika w adminie.

### Manual Testing Steps:

1. Lokalnie: `createsuperuser`, `runserver`, logowanie do `/admin/`, dodanie konta z wielkimi literami.
2. Lokalnie: okno prywatne → `/` → formularz logowania → strona powitalna; widok mobilny.
3. Produkcja: reset, push, `createsuperuser`, logowanie właściciela i drugiej osoby.

## Performance Considerations

Brak istotnych: dwóch użytkowników, `email` ma indeks unikalny; `email__iexact` przy logowaniu przy tej skali nie ma znaczenia.

## Migration Notes

- Zmiana `AUTH_USER_MODEL` po pierwszej migracji wymaga czystej bazy — lokalnie `rm -f db.sqlite3`, na produkcji reset schematu `public` (faza 4, krok 2). Dane do stracenia: tylko konto admina; brak backupu (zob. `deploy-plan.md` TODO).
- Rollback po fazie 4: revert commitów i ponowny reset schematu (stary model `auth.User` też wymaga czystej bazy). Przy dwóch kontach akceptowalne.

## References

- Roadmap: `context/foundation/roadmap.md` (F-01)
- PRD: `context/foundation/prd.md` (FR-001, NFR Prywatność, Access Control)
- Deploy: `context/deployment/deploy-plan.md`, `context/deployment/web-settings.json`
- Django: `django/contrib/auth/middleware.py:43` (`LoginRequiredMiddleware`), `django/contrib/auth/base_user.py:36` (`get_by_natural_key`), `django/contrib/auth/forms.py:254,275,592`
- Obecny kod: `talkaitive/settings.py:62-80`, `talkaitive/urls.py:23-31`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Model użytkownika z e-mailem, admin i pytest

#### Automated

- [x] 1.1 Migracje generują się bez zmian do zapisania
- [x] 1.2 Lokalna baza migruje od zera
- [x] 1.3 Testy fazy 1 przechodzą
- [x] 1.4 Lint i format są czyste
- [x] 1.5 Django nie zgłasza problemów

#### Manual

- [x] 1.6 Logowanie do /admin/ e-mailem i założenie konta z wielkimi literami zapisuje e-mail małymi literami

### Phase 2: Logowanie i wymóg logowania na każdej stronie

#### Automated

- [ ] 2.1 Wszystkie testy przechodzą
- [ ] 2.2 Lint i format są czyste
- [ ] 2.3 Django nie zgłasza problemów
- [ ] 2.4 Kontrola produkcyjna nie zgłasza nowych ostrzeżeń

#### Manual

- [ ] 2.5 Okno prywatne przekierowuje na logowanie, po zalogowaniu widać stronę powitalną z e-mailem
- [ ] 2.6 Formularz logowania czytelny na wąskim ekranie

### Phase 3: Wzorzec izolacji danych per użytkownik

#### Automated

- [ ] 3.1 Wszystkie testy przechodzą
- [ ] 3.2 Migracje produkcyjne bez zmian do zapisania
- [ ] 3.3 Migracje testowe bez zmian do zapisania
- [ ] 3.4 Lint i format są czyste

#### Manual

- [ ] 3.5 Wpis w lessons.md i zmiany w CLAUDE.md są zrozumiałe i zgodne z decyzjami

### Phase 4: Wdrożenie na produkcję z resetem bazy

#### Automated

- [ ] 4.1 Brak niezacommitowanych zmian i commity faz 1–3 tylko lokalnie
- [ ] 4.2 Health check na produkcji zwraca 200
- [ ] 4.3 Niezalogowany na / dostaje przekierowanie na logowanie
- [ ] 4.4 Strona logowania zwraca 200

#### Manual

- [ ] 4.5 Reset schematu wykonany bez błędów
- [ ] 4.6 createsuperuser na produkcji zakończony powodzeniem
- [ ] 4.7 Właściciel loguje się na produkcji e-mailem z wielkimi literami i widzi stronę powitalną
- [ ] 4.8 Konto drugiej osoby założone i logowanie nim działa
- [ ] 4.9 /admin/ pokazuje tylko konta użytkowników i grupy
