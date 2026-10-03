<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Auth i izolacja danych między użytkownikami

- **Plan**: context/changes/auth-and-access-scaffold/plan.md
- **Mode**: Deep (weryfikacja kodu inline, bez sub-agenta)
- **Date**: 2026-10-01
- **Verdict**: REVISE → SOUND po triage
- **Findings**: 0 critical, 2 warnings, 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding
6/6 paths ✓, 5/5 symbols ✓ (`LoginRequiredMiddleware`, `@login_not_required` na `LoginView` i `admin.site.login`, `get_by_natural_key` w `base_user.py:36`, formularze w `forms.py:254,275,592`, pomijanie podmienionego modelu w `admin/sites.py:136`), brief↔plan ✓, Progress↔Phase ✓

## Findings

### F1 — Duplikat e-maila w innej wielkości liter daje błąd 500 w adminie

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 — #3 model User, #5 admin, #6 testy
- **Detail**: Plan zamieniał e-mail na małe litery dopiero w `User.save()`, a `ModelForm` sprawdza unikalność wcześniej, na wpisanej wartości. Dodanie `Anna@Example.DE` przy istniejącym `anna@example.de` kończyłoby się `IntegrityError` (500) zamiast błędem formularza.
- **Fix**: `User.clean()` zamienia e-mail na małe litery (wywoływane przed `validate_unique()`); test POST w adminie z duplikatem w innej wielkości liter → 200 z błędem formularza.
- **Decision**: FIXED

### F2 — Repo nie jest czyste przed fazą 1; kontrola z fazy 4 nie zadziała

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Implementation Approach; Phase 4 — #1 i kryterium 4.1
- **Detail**: Przed przeglądem `main` miał 2 niewypchnięte commity (96be91d, a66bb5a), 4 zmienione dokumenty i niezacommitowany folder zmiany. Push dokumentów w trakcie faz 1–3 zabrałby commity faz i wywołał nieudany pre-deploy `migrate`.
- **Fix**: Krok 0 w planie (commit + push dokumentów przed fazą 1).
- **Decision**: FIXED differently — poza planem: commit wszystkich zmian (w tym poprawek z tego przeglądu) i push przez właściciela przed startem fazy 1; plan bez zmian.

### F3 — Kryterium 2.4 (check --deploy) zawsze kończy się błędem

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Success Criteria 2.4
- **Detail**: Na obecnym kodzie komenda zgłasza `mail.E001`, `security.W004` i `security.W009` (krótki `SECRET_KEY=x`) i kończy się kodem 1.
- **Fix**: Losowy klucz 50+ znaków w komendzie; zapisany oczekiwany wynik: exit 1, dokładnie `mail.E001` i `security.W004`.
- **Decision**: FIXED

### F4 — Faza 4: niepełna komenda SSH i brak sprawdzenia przed DROP SCHEMA

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 — #2 i #4
- **Detail**: `deploy-plan.md:154` wymaga `-i ~/.ssh/id_ed25519_railway`, a komenda w planie go nie miała; nieodwracalny `DROP SCHEMA` nie miał kroku potwierdzenia środowiska.
- **Fix**: Pełna komenda `railway ssh --service web -i ~/.ssh/id_ed25519_railway` w #2 i #4; przed resetem `echo $RAILWAY_ENVIRONMENT` i `python manage.py showmigrations auth | head -3`.
- **Decision**: FIXED
