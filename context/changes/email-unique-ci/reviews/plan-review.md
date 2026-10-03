<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Unikalność e-maila bez wielkości liter w bazie

- **Plan**: context/changes/email-unique-ci/plan.md
- **Mode**: Deep
- **Date**: 2026-10-03
- **Verdict**: SOUND
- **Findings**: 0 critical, 0 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | PASS |

## Grounding
7/7 paths ✓, 4/4 symbols ✓, brief↔plan ✓, Progress↔Faza ✓ (1.1–1.5, 2.1–2.4)

## Verified claims

- Jeden błąd w adminie: `ModelForm._post_clean` woła `validate_unique` (błąd przy `email` z `unique=True`, po `clean()` → małe litery), potem `validate_constraints` z `email` w `exclude`; `UniqueConstraint.validate` dla wyrażeń pomija ograniczenie, gdy wyrażenie odwołuje się do wykluczonego pola (Django 6.1.1, `db/models/constraints.py`, „Ignore constraints with excluded fields”).
- `UserCreationForm.clean_username` (`username__iexact`) nie działa dla pola `email` — brak drugiej ścieżki walidacji.
- Testy lokalne na SQLite: `unique=True` rozróżnia wielkość liter, więc test `update()` → `IntegrityError` dowodzi nowego ograniczenia.
- Brak innych wywołań `iexact` / `get_by_natural_key` w kodzie projektu.
- Pre-deploy `migrate --noinput` skonfigurowany w Railway (`context/deployment/web-settings.json`); DDL w Postgresie jest transakcyjny.

## Findings

### F1 — Plan cofania opisuje tylko bazę lokalną, nie produkcję

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Migration Notes
- **Detail**: `uv run python manage.py migrate accounts 0001` działa tylko lokalnie i wymaga istniejącego pliku `0002`. Po `git revert` + push plik znika, a ograniczenie zostaje w bazie (nieszkodliwe dla starego kodu). Plan nie opisywał cofania na produkcji ani kolejności kroków.
- **Fix**: Dopisać w Migration Notes zdanie o cofaniu na produkcji i kolejności (`migrate accounts 0001` przed usunięciem pliku `0002`).
- **Decision**: FIXED — dopisano w Migration Notes.
