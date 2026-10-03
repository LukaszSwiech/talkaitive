# Unikalność e-maila bez wielkości liter w bazie — Plan Brief

> Full plan: `context/changes/email-unique-ci/plan.md`
> Follow-up (źródło zakresu): `context/archive/2026-10-01-auth-and-access-scaffold/follow-ups/review-fixes.md` (F1)

## What & Why

Baza danych ma sama blokować dwa konta z tym samym e-mailem w różnej wielkości liter (`Anna@x.de` obok `anna@x.de`). Dziś pilnuje tego tylko `User.save()`, więc zapis z pominięciem `save()` (`update()`, `bulk_create`, `loaddata`, ręczny SQL) może utworzyć duplikat, a wtedy logowanie obu kont kończy się błędem 500.

## Starting Point

`User.email` ma zwykłe `unique=True` (rozróżnia wielkość liter), małe litery wymusza `_normalize_email()` w `save()`/`clean()`, a logowanie szuka przez `email__iexact` (`accounts/models.py:39-67`). Migracja `accounts` jest jedna (`0001_initial`).

## Desired End State

Duplikat różniący się wielkością liter jest niemożliwy niezależnie od ścieżki zapisu. Logowanie `Anna@Example.DE` nadal działa i zawsze znajduje najwyżej jeden wiersz — tak samo na SQLite i Postgresie. Admin przy duplikacie pokazuje jeden błąd przy polu `email`. Produkcja ma nowe ograniczenie.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Źródło prawdy | `UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique")` w bazie | Blokuje duplikat niezależnie od ścieżki zapisu. | Follow-up F1 (Fix A) |
| `unique=True` na polu | Zostaje | Dokładne dopasowanie przy logowaniu korzysta z tego indeksu. | Follow-up F1 |
| Normalizacja | Jedna funkcja `canonical_email()` (`strip().lower()`) dla zapisu i wyszukiwania | Zapis i logowanie nie mogą się rozjechać. | Follow-up F1 |
| Logowanie | `get(email=canonical_email(email or ""))` zamiast `email__iexact` | Najwyżej jeden wiersz, to samo zachowanie na SQLite i Postgresie. | Follow-up F1 |
| Testy | `update()` z duplikatem → `IntegrityError`; admin: `list(form.errors) == ["email"]` | Dowód ograniczenia i braku podwójnego komunikatu. | Follow-up F1 |
| Ścieżka wykonania | Osobna mała zmiana, 2 fazy (lokalnie → produkcja) | Push na `main` = deploy, więc produkcja to osobny krok z osobną zgodą. | Plan |

## Scope

**In scope:**
- `accounts/models.py`: `canonical_email`, nowy `get_by_natural_key`, `Meta.constraints`
- `accounts/migrations/0002_*.py` (wygenerowana)
- `tests/test_accounts.py`: nowy test `update()` + dokładniejsza asercja w teście admina
- Push na `main` i weryfikacja produkcji

**Out of scope:**
- Usunięcie `unique=True` z pola
- Test formularza edycji (`UserEditForm`) z duplikatem
- Zmiany w `accounts/forms.py`, `accounts/admin.py`
- Reguła w `lessons.md` (Fix B odrzucony), reset bazy, zmiany w roadmapie

## Architecture / Approach

`canonical_email()` → używana przez `User._normalize_email()` (zapis) i `UserManager.get_by_natural_key()` (logowanie). Ograniczenie funkcyjne na `LOWER(email)` w bazie łapie wszystko, co ominęło `save()`. Migracja `0002` dodaje je przez `AddConstraint`; na produkcji stosuje ją pre-deploy `migrate`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Ograniczenie w modelu, migracja i testy | Kod + migracja `0002` + 2 testy, zielone lokalnie | Podwójny komunikat w adminie — pokryty asercją `["email"]` |
| 2. Wdrożenie na produkcję | `accounts.0002` na produkcji, logowanie działa | Konflikt przy tworzeniu indeksu — mało prawdopodobny (2 konta, oba małymi literami) |

**Prerequisites:** czyste drzewo na `main`; dostęp do Railway (log pre-deploy); zgoda użytkownika na push.
**Estimated effort:** ~1 krótka sesja na fazę 1, kilka minut na fazę 2.

## Open Risks & Assumptions

- Zakładamy, że na produkcji nie ma e-maili różniących się tylko wielkością liter (2 konta przez `save()`). Jeśli jest inaczej, pre-deploy `migrate` się nie powiedzie i stara wersja zostanie aktywna.
- `LOWER()` w SQLite składa tylko ASCII — lokalnie ograniczenie nie złapie np. `Ä` vs `ä` zapisanych z pominięciem `save()`. Na Postgresie (produkcja) działa dla Unicode. Ryzyko zaakceptowane.

## Success Criteria (Summary)

- Zapis duplikatu w innej wielkości liter, nawet z pominięciem `save()`, jest odrzucany przez bazę.
- Logowanie bez względu na wielkość liter działa lokalnie i na produkcji.
- `uv run pytest`, `makemigrations --check` i `ruff` są zielone.
