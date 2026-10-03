# Unikalność e-maila bez wielkości liter w bazie — Implementation Plan

## Overview

Przenosimy pilnowanie unikalności e-maila (bez rozróżniania wielkości liter) z kodu Pythona do bazy danych: ograniczenie `UniqueConstraint(Lower("email"))` plus logowanie przez dokładne dopasowanie znormalizowanego e-maila. To realizacja follow-upu F1 z review zmiany `auth-and-access-scaffold` (Fix A), 1:1 według `context/archive/2026-10-01-auth-and-access-scaffold/follow-ups/review-fixes.md`.

## Current State Analysis

- `User.email` ma zwykłe `unique=True` (`accounts/models.py:44`) — indeks rozróżnia wielkość liter.
- Małe litery wymusza tylko `User._normalize_email()` wywoływane z `save()` i `clean()` (`accounts/models.py:58-67`).
- Logowanie szuka przez `get_by_natural_key` → `self.get(email__iexact=email)` (`accounts/models.py:39-40`).
- Zapis omijający `save()` (`QuerySet.update()`, `bulk_create`, `loaddata`, migracja danych na modelu historycznym, ręczny SQL) może zapisać `Anna@x.de` obok `anna@x.de`. Wtedy `get_by_natural_key` rzuca `MultipleObjectsReturned`, a `ModelBackend.authenticate` łapie tylko `DoesNotExist` → 500 przy logowaniu obu kont. Dziś żaden kod tych ścieżek nie używa — błąd jest ukryty.
- `iexact` na SQLite to `LIKE` (składa tylko ASCII), na Postgresie `UPPER()` — zachowanie lokalne i produkcyjne różni się dla znaków spoza ASCII.
- Admin jest bezpieczny: formularz → `clean()` → `validate_unique` daje błąd formularza (`tests/test_accounts.py:63-79`).
- Jedyna migracja `accounts` to `0001_initial.py`.

## Desired End State

- Baza odrzuca drugi wiersz, którego `LOWER(email)` pokrywa się z istniejącym — niezależnie od ścieżki zapisu.
- `get_by_natural_key` normalizuje wejście tą samą funkcją co `save()` i szuka dokładnego dopasowania — najwyżej jeden wiersz, to samo zachowanie na SQLite i Postgresie.
- Logowanie `Anna@Example.DE` na konto `anna@example.de` nadal działa.
- Admin przy duplikacie w innej wielkości liter pokazuje dokładnie jeden błąd, przy polu `email`.
- Migracja `accounts.0002` zastosowana na produkcji bez konfliktu.

### Key Discoveries:

- `accounts/models.py:39-40` — `get_by_natural_key` z `email__iexact`, do zmiany.
- `accounts/models.py:58-59` — `_normalize_email` (`strip().lower()`), źródło wspólnej normalizacji.
- `tests/test_accounts.py:24-26` i `tests/test_login.py:38-48` — istniejące testy logowania bez wielkości liter muszą dalej przechodzić.
- `tests/test_accounts.py:63-79` — test admina z duplikatem; dostaje dokładniejszą asercję.
- Formularz modelu pomija sprawdzanie ograniczeń dla pól, które już mają błąd (`django/forms/models.py`, `validate_constraints` + `_get_validation_exclusions`) — dlatego nie będzie podwójnego komunikatu (zweryfikowane w triage F1).

## What We're NOT Doing

- Nie usuwamy `unique=True` z pola `email` — zostaje obok nowego ograniczenia.
- Nie dodajemy testu formularza edycji (`UserEditForm`) z duplikatem — poza zakresem F1.
- Nie zmieniamy formularzy (`accounts/forms.py`) ani admina (`accounts/admin.py`).
- Nie zapisujemy reguły do `lessons.md` (Fix B odrzucony w triage).
- Nie resetujemy bazy produkcyjnej.
- Nie ruszamy roadmapy — nie ma w niej pozycji z tym Change ID.

## Implementation Approach

Baza jako źródło prawdy. Jedna funkcja modułu `canonical_email()` definiuje kanoniczną postać e-maila i jest używana zarówno przy zapisie, jak i przy wyszukiwaniu. Ograniczenie funkcyjne na `Lower("email")` łapie wszystko, co ominęło `save()`. Najpierw kod + migracja + testy lokalnie (Faza 1), potem push na `main`, który auto-deployuje i uruchamia pre-deploy `migrate` (Faza 2).

## Faza 1: Ograniczenie w modelu, migracja i testy

### Overview

Zmiana modelu `User` i managera, wygenerowana migracja `0002`, dwa testy z F1.

### Changes Required:

#### 1. Model i manager

**File**: `accounts/models.py`

**Intent**: Jedna funkcja normalizująca e-mail dla zapisu i wyszukiwania; logowanie przez dokładne dopasowanie; ograniczenie unikalności na `LOWER(email)` w bazie.

**Contract**:
- Funkcja modułu `canonical_email(email: str) -> str` zwraca `email.strip().lower()`.
- `User._normalize_email()` używa `canonical_email`.
- `UserManager.get_by_natural_key(email: str | None)` → `self.get(email=canonical_email(email or ""))` zamiast `email__iexact`.
- `User.Meta.constraints = [models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique")]` (`from django.db.models.functions import Lower`). `unique=True` na polu zostaje.

#### 2. Migracja

**File**: `accounts/migrations/0002_*.py`

**Intent**: Dodaje ograniczenie do schematu bazy.

**Contract**: Generowana przez `uv run python manage.py makemigrations accounts`, nie pisana ręcznie. Zawiera jedną operację `AddConstraint` z nazwą `accounts_user_email_ci_unique`.

#### 3. Testy

**File**: `tests/test_accounts.py`

**Intent**: Udowodnić, że baza blokuje duplikat zapisany z pominięciem `save()`, i że admin pokazuje jeden błąd.

**Contract**:
- Nowy test: przy istniejącym `anna@example.de` i drugim użytkowniku `other`, `User.objects.filter(pk=other.pk).update(email="Anna@Example.DE")` → `IntegrityError`.
- `test_admin_add_duplicate_email_shows_form_error` dostaje asercję, że błąd jest tylko przy polu `email`: `list(form.errors) == ["email"]`.

### Success Criteria:

#### Automated Verification:

- Wszystkie testy przechodzą, w tym istniejące `get_by_natural_key("ANNA@example.de")` i logowanie `Anna@Example.DE`: `uv run pytest`
- Brak brakujących migracji (ustawienia domyślne): `uv run python manage.py makemigrations --check --dry-run`
- Brak brakujących migracji (ustawienia testowe): `DJANGO_SETTINGS_MODULE=talkaitive.settings_test uv run python manage.py makemigrations --check --dry-run`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Przegląd wygenerowanej migracji `0002`: jedna operacja `AddConstraint` na `Lower("email")`, nic więcej

**Implementation Note**: Po przejściu weryfikacji automatycznej zatrzymaj się na ręczne potwierdzenie przed Fazą 2.

---

## Faza 2: Wdrożenie na produkcję

### Overview

Push na `main` (auto-deploy na Railway). Pre-deploy `migrate` stosuje `accounts.0002` i tworzy unikalny indeks na `LOWER(email)`.

### Changes Required:

#### 1. Push i deploy

**File**: brak zmian w plikach — operacja `git push` na `main`.

**Intent**: Wdrożyć ograniczenie na produkcję. Push jest publiczny i natychmiast trafia na produkcję, więc wymaga wyraźnej zgody użytkownika przed wykonaniem.

**Contract**: Na produkcji są 2 konta, oba zapisane małymi literami przez `save()`, więc indeks powstanie bez konfliktu. Jeśli pre-deploy `migrate` się nie powiedzie, Railway nie przełącza ruchu na nową wersję — stara zostaje aktywna. Adres produkcji i zasoby: `context/deployment/deploy-plan.md`.

### Success Criteria:

#### Automated Verification:

- `/healthz/` na produkcji zwraca 200 (adres z `context/deployment/deploy-plan.md`)

#### Manual Verification:

- Log pre-deploy w Railway pokazuje `Applying accounts.0002_... OK` bez błędu
- Logowanie właściciela działa na produkcji
- Logowanie drugiej osoby działa na produkcji

**Implementation Note**: Faza zamyka zmianę; po niej `/10x-impl-review email-unique-ci`.

---

## Testing Strategy

### Unit Tests:

- `update()` z duplikatem w innej wielkości liter → `IntegrityError` (nowe ograniczenie).
- Istniejące: `create_user` zapisuje małe litery, duplikat przez `create_user` → `IntegrityError`, `get_by_natural_key` bez wielkości liter.

### Integration Tests:

- Admin: duplikat w innej wielkości liter → 200, jeden błąd przy `email`, brak nowego wiersza.
- Logowanie `Anna@Example.DE` (istniejący `tests/test_login.py`).

### Manual Testing Steps:

1. Przejrzyj `accounts/migrations/0002_*.py`.
2. Po deployu sprawdź log pre-deploy w Railway.
3. Zaloguj się na produkcji oboma kontami.

## Performance Considerations

Brak istotnych: dwa konta. Dokładne dopasowanie przy logowaniu korzysta z istniejącego indeksu na `email`.

## Migration Notes

`accounts.0002` tylko dodaje unikalny indeks funkcyjny. Konflikt możliwy wyłącznie, gdy w bazie są już dwa e-maile różniące się wielkością liter — na produkcji ich nie ma (oba konta przez `save()`). Cofnięcie (lokalnie): `uv run python manage.py migrate accounts 0001` usuwa ograniczenie. Na produkcji wystarczy cofnąć kod (`git revert` + push) — ograniczenie zostaje w bazie i nie przeszkadza staremu kodowi. Usunięcie samego ograniczenia wymaga `migrate accounts 0001`, zanim plik `0002` zniknie z repo.

Ryzyko świadomie zaakceptowane: `LOWER()` w SQLite (lokalnie) składa tylko ASCII, więc lokalnie ograniczenie nie złapie np. `Ä` vs `ä` zapisanych z pominięciem `save()`. Na Postgresie (produkcja) `LOWER()` obsługuje Unicode.

## References

- Follow-up: `context/archive/2026-10-01-auth-and-access-scaffold/follow-ups/review-fixes.md` (F1)
- Review: `context/archive/2026-10-01-auth-and-access-scaffold/reviews/impl-review.md` (F1, Fix A)
- Poprzedni plan: `context/archive/2026-10-01-auth-and-access-scaffold/plan.md:51`, `:84-86`
- Kod: `accounts/models.py:39-67`, `tests/test_accounts.py:10-79`, `tests/test_login.py:38-48`
- Deploy: `context/deployment/deploy-plan.md`, `context/deployment/web-settings.json`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Ograniczenie w modelu, migracja i testy

#### Automated

- [x] 1.1 Wszystkie testy przechodzą, w tym istniejące `get_by_natural_key("ANNA@example.de")` i logowanie `Anna@Example.DE`: `uv run pytest` — dce5414
- [x] 1.2 Brak brakujących migracji (ustawienia domyślne): `uv run python manage.py makemigrations --check --dry-run` — dce5414
- [x] 1.3 Brak brakujących migracji (ustawienia testowe): `DJANGO_SETTINGS_MODULE=talkaitive.settings_test uv run python manage.py makemigrations --check --dry-run` — dce5414
- [x] 1.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — dce5414

#### Manual

- [x] 1.5 Przegląd wygenerowanej migracji `0002`: jedna operacja `AddConstraint` na `Lower("email")`, nic więcej — dce5414

### Phase 2: Wdrożenie na produkcję

#### Automated

- [x] 2.1 `/healthz/` na produkcji zwraca 200 (adres z `context/deployment/deploy-plan.md`)

#### Manual

- [x] 2.2 Log pre-deploy w Railway pokazuje `Applying accounts.0002_... OK` bez błędu
- [x] 2.3 Logowanie właściciela działa na produkcji
- [x] 2.4 Logowanie drugiej osoby działa na produkcji
