# Review fixes — auth-and-access-scaffold

Poprawki z `reviews/impl-review.md` odłożone do wykonania przez plan → `/10x-implement` (nie poprawiane w triage).

## F1 — Unikalność e-maila bez wielkości liter w bazie (Fix A)

- **Źródło**: `reviews/impl-review.md`, F1 (WARNING, Impact MEDIUM). Decyzja triage 2026-10-03: Fix A, ale przez plan, bo zawiera migrację, która przy pushu na `main` od razu trafia na produkcję.
- **Problem**: `email` ma zwykłe `unique=True` (rozróżnia wielkość liter); małe litery wymusza tylko `User.save()`/`clean()`. Zapis omijający `save()` (`QuerySet.update()`, `bulk_create`, `loaddata`, migracja danych na modelu historycznym, ręczny SQL) może zapisać `Anna@x.de` obok `anna@x.de`. Wtedy `get_by_natural_key` (`email__iexact`) rzuca `MultipleObjectsReturned`, a `ModelBackend.authenticate` łapie tylko `DoesNotExist` → 500 przy logowaniu. Admin jest bezpieczny (formularz → `clean()` → `validate_unique`).
- **Zakres zmian**:
  - `accounts/models.py`:
    - funkcja modułu `canonical_email(email: str) -> str` (`strip().lower()`), używana przez `User._normalize_email` i `UserManager.get_by_natural_key`;
    - `get_by_natural_key` → `self.get(email=canonical_email(email or ""))` zamiast `email__iexact` (dokładne dopasowanie, indeks, to samo zachowanie na SQLite i Postgresie);
    - `class Meta: constraints = [models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique")]` (`from django.db.models.functions import Lower`); `unique=True` na polu zostaje.
  - `accounts/migrations/0002_*.py` — generowana przez `uv run python manage.py makemigrations accounts`.
  - `tests/test_accounts.py`:
    - nowy test: `User.objects.filter(pk=other.pk).update(email="Anna@Example.DE")` przy istniejącym `anna@example.de` → `IntegrityError`;
    - w `test_admin_add_duplicate_email_shows_form_error` asercja, że błąd jest tylko przy polu `email` (`list(form.errors) == ["email"]`) — formularz pomija sprawdzanie ograniczeń dla pól, które już mają błąd (`django/forms/models.py`, `validate_constraints` + `_get_validation_exclusions`), więc nie ma podwójnego komunikatu.
- **Success criteria**:
  - `uv run pytest` — wszystkie testy przechodzą (w tym istniejące `get_by_natural_key("ANNA@example.de")` i logowanie `Anna@Example.DE`).
  - `uv run python manage.py makemigrations --check --dry-run` oraz z `DJANGO_SETTINGS_MODULE=talkaitive.settings_test`.
  - `uv run ruff check . && uv run ruff format --check .`
  - Po deployu: pre-deploy `migrate` stosuje `accounts.0002` bez błędu; logowanie właściciela i drugiej osoby nadal działa; `/healthz/` 200.
- **Wdrożenie**: push na `main` = auto-deploy; pre-deploy `migrate` tworzy unikalny indeks na `LOWER(email)`. Na produkcji są 2 konta, oba zapisane małymi literami (przez `save()`), więc indeks powstanie bez konfliktu. Bez resetu bazy.
- **Ścieżka wykonania**: nowa mała zmiana (`/10x-new` → `/10x-plan` → `/10x-implement`) albo dopisana faza do istniejącego planu — do decyzji przy planowaniu.
