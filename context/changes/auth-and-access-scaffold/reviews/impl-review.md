<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Auth i izolacja danych między użytkownikami

- **Plan**: context/changes/auth-and-access-scaffold/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-10-03
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Success criteria (2026-10-03)

- `makemigrations --check --dry-run` (prod i `settings_test`) — PASS, "No changes detected".
- `migrate` — PASS, "No migrations to apply".
- `uv run pytest` — PASS, 19 passed (10 ostrzeżeń WhiteNoise o braku `staticfiles/` — lokalnie normalne, brak `collectstatic`).
- `ruff check .` / `ruff format --check .` — PASS.
- `manage.py check` — PASS, 0 issues.
- `check --deploy` — zgodnie z planem: exit 1, dokładnie `mail.E001` i `security.W004`.
- Produkcja: `/healthz/` 200; `/` anonimowo 302 → `/login/?next=/`; `/login/` 200.
- 4.1 (commity tylko lokalnie przed resetem) — historyczne, nie do powtórzenia po pushu; ślad w `deploy-plan.md`.
- Manual: wszystkie `[x]`; faza 4 ma ślad w `context/deployment/deploy-plan.md` (reset schematu, 19 migracji, superuser).

## Findings

### F1 — Unikalność e-maila bez wielkości liter pilnowana tylko w `save()`

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/models.py:40, accounts/models.py:44
- **Detail**: `email` ma zwykłe `unique=True` (indeks rozróżnia wielkość liter), a małe litery wymusza tylko `User.save()`/`clean()`. Ścieżki omijające `save()` (`QuerySet.update()`, `bulk_create`, `loaddata`, migracje danych na modelu historycznym, surowy SQL) mogą zapisać `Anna@x.de` obok `anna@x.de`. Wtedy `get_by_natural_key` (`email__iexact`) rzuca `MultipleObjectsReturned`, a `ModelBackend.authenticate` łapie tylko `DoesNotExist` (`django/contrib/auth/backends.py:70-73`) → 500 przy logowaniu obu kont. Dziś żaden kod tych ścieżek nie używa — błąd ukryty. Założenie planu (plan.md:51, „zwykłe `unique=True` wystarcza”) jest prawdziwe tylko, dopóki każdy zapis idzie przez `save()`. Dodatkowo `iexact` na SQLite to `LIKE` (składa tylko ASCII), na Postgresie `UPPER()` — lokalnie i na produkcji zachowanie różni się dla znaków spoza ASCII.
- **Fix A ⭐ Recommended**: Baza jako źródło prawdy — `Meta.constraints = [UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique")]` + `get_by_natural_key` szuka `email=email.strip().lower()` (ta sama normalizacja co `save()`); nowa migracja.
  - Strength: Duplikat jest niemożliwy niezależnie od ścieżki zapisu; logowanie nie może zwrócić dwóch wierszy; to samo zachowanie na SQLite i Postgresie.
  - Tradeoff: Jedna migracja na produkcji (2 konta, oba już małymi literami — bez konfliktu) i test na nowe ograniczenie.
  - Confidence: HIGH — `UniqueConstraint` z wyrażeniem jest wspierane na SQLite i Postgresie w Django 6.1.
  - Blind spot: Nie sprawdzono, jak admin pokaże błąd ograniczenia funkcyjnego (Django waliduje `UniqueConstraint` w `validate_constraints`, więc powinien to być błąd formularza, nie 500 — do potwierdzenia testem).
- **Fix B**: Zaakceptować ryzyko i zapisać regułę w `lessons.md` („nie zapisuj `User.email` przez `update()`/`bulk_create`/surowy SQL”).
  - Strength: Zero zmian w kodzie i bez migracji.
  - Tradeoff: Ochrona zależy od pamięci ludzi i agentów; błąd wychodzi dopiero jako 500 przy logowaniu.
  - Confidence: MED — przy dwóch kontach zakładanych w adminie ryzyko jest małe.
  - Blind spot: Przyszłe migracje danych (np. import kont) mogą ominąć regułę niezauważenie.
- **Decision**: QUEUED — Fix A odłożony do `follow-ups/review-fixes.md` (wykonanie przez plan → `/10x-implement`, bo zawiera migrację na produkcję). Blind spot zweryfikowany: formularz admina pokaże jeden błąd przy `email`.

### F2 — Izolacja `for_user` łatwa do obejścia przez domyślny manager

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: accounts/ownership.py:26
- **Detail**: `for_user` działa poprawnie i „fail closed” (niezalogowany → `none()`). Ale `objects` jest też domyślnym managerem, więc `Model.objects.get(pk=...)`, `.all()` i `get_object_or_404(Model, pk=pk)` nie filtrują po właścicielu. Najbardziej prawdopodobny przyszły wyciek (IDOR — odczyt cudzego obiektu po zgadniętym id) to widok szczegółów rozmowy w S-01 z `get_object_or_404(Conversation, pk=pk)`. Drugie ryzyko: modele podrzędne (np. `Message` → `Conversation`) bez `UserOwned`, pobierane po pk. Dziś nic nie łamie wzorca — to kwestia projektu przed S-01.
- **Fix A ⭐ Recommended**: Dopisać regułę w `lessons.md`: widoki szczegółów używają `get_object_or_404(Model.objects.for_user(request.user), pk=pk)`, a każdy taki widok ma test „B dostaje 404 na obiekt A”; modele podrzędne filtrują przez właściciela rodzica.
  - Strength: Tanio, trafia do każdego agenta przed S-01; uzupełnia istniejącą regułę o UserOwned o konkretny wzorzec widoku.
  - Tradeoff: Nadal konwencja, nie mechanizm — wymaga dyscypliny i testów.
  - Confidence: HIGH — istniejąca reguła o UserOwned już jest czytana przez /10x-plan i /10x-implement.
  - Blind spot: None significant.
- **Fix B**: Utwardzić wzorzec w kodzie — domyślny manager nie zwraca danych bez użytkownika (np. tylko `for_user()`, plus osobny `unscoped` manager do zadań wewnętrznych).
  - Strength: Pomyłka w widoku staje się niemożliwa albo bardzo widoczna.
  - Tradeoff: Odejście od idiomu Django; admin, `dumpdata` i relacje mogą wymagać obejść; projekt przed istnieniem prawdziwych modeli.
  - Confidence: LOW — nie sprawdzono, jak to współgra z `_base_manager`, CASCADE i przyszłymi relacjami.
  - Blind spot: Wpływ na kaskadowe usuwanie i serializację.
- **Decision**: FIXED — Fix A: reguła „Widoki szczegółów pobierają obiekt przez for_user, nie przez zwykłe objects” dopisana do `context/foundation/lessons.md`.

### F3 — Niepełne type hinty we wzorcu i w testach

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: accounts/ownership.py:14-15, tests/test_login.py:11
- **Detail**: CLAUDE.md prosi o type hinty w nowych modelach i serwisach (pod przyszły `mypy` + `django-stubs`). `models.py` i `views.py` są otypowane, ale `for_user(self, user)` nie ma typu `user`, a `UserOwnedQuerySet` nie jest sparametryzowany. W `tests/test_login.py` adnotacje `-> "User"` wskazują na zmienną `User = get_user_model()`, której `mypy` nie przyjmie jako typu; fixtures w `tests/test_ownership.py` nie mają hintów wcale.
- **Fix**: Dodać `user: "User | AnonymousUser"` w `for_user`, a w testach adnotować przez `from accounts.models import User`.
- **Decision**: FIXED — `for_user(self, user: AbstractBaseUser | AnonymousUser)` (typ `request.user` wg django-stubs, zgodny z `settings.AUTH_USER_MODEL`); `tests/test_login.py` i `tests/test_ownership.py` importują `User` z `accounts.models` i mają hinty w fixtures/testach. Parametryzacja `QuerySet[...]` pominięta do czasu `mypy`. pytest 19 passed, ruff czysty.

### F4 — Błędy formularza logowania: niepoprawny HTML i brak błędów pól

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/templates/registration/login.html:9-11
- **Detail**: `{{ form.non_field_errors }}` renderuje `<ul class="errorlist">` wewnątrz `<p>` (niepoprawny HTML). Błędy pojedynczych pól (`form.username.errors`, `form.password.errors`) nie są wyświetlane — dziś osiągalne tylko po obejściu `required` w przeglądarce, więc kosmetyka.
- **Fix**: Zamienić `<p>` na `<div>` wokół `non_field_errors` i dodać `{{ form.username.errors }}` / `{{ form.password.errors }}` przy polach.
- **Decision**: FIXED — `<div class="error">` zamiast `<p>`; błędy pól `username`/`password` wyświetlane pod polami. pytest 19 passed.

### F5 — Fixture `admin_client` zasłania wbudowaną z pytest-django

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: tests/test_accounts.py:10-15
- **Detail**: Własna fixture `admin_client` ma tę samą nazwę co wbudowana fixture pytest-django, która już działa z `USERNAME_FIELD = "email"`. Działa, ale myli czytelnika (która wersja jest używana?).
- **Fix**: Usunąć własną fixture i użyć wbudowanej `admin_client` (albo zmienić nazwę, np. `superuser_client`).
- **Decision**: FIXED — własna fixture usunięta; testy admina używają wbudowanej `admin_client` z pytest-django (`admin@example.com`, `force_login`). Logowanie hasłem pokrywa `tests/test_login.py`. pytest 19 passed, ruff czysty.

### F6 — Drobne dodatki spoza planu (`STORAGES` w testach, `list_filter` w adminie)

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: talkaitive/settings_test.py:7-10, accounts/admin.py:14
- **Detail**: `settings_test.py` nadpisuje `STORAGES` na `StaticFilesStorage` (potrzebne — magazyn z manifestem wymaga `collectstatic`, bez tego testy stron admina by padły). `admin.py` dodaje `list_filter` bez `groups` (kosmetyka, usuwa filtr grup z listy kont). Oba nieszkodliwe, ale nieopisane w planie.
- **Fix**: Zaakceptować jako uzasadnione dodatki (bez zmian w kodzie).
- **Decision**: ACCEPTED — oba dodatki uzasadnione (`STORAGES` potrzebne do testów admina bez `collectstatic`; `list_filter` bez `groups` to kosmetyka). Kod bez zmian.
