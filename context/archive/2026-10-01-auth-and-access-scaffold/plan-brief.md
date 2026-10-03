# Auth i izolacja danych między użytkownikami — Plan Brief

> Full plan: `context/changes/auth-and-access-scaffold/plan.md`

## What & Why

F-01 z roadmapy: zaproszony użytkownik loguje się e-mailem i hasłem, każda strona poza logowaniem wymaga zalogowania, a przyszłe rozmowy, błędy i pamięć mają jeden wzorzec izolacji. To fundament pod S-01…S-04 i pod guardrail PRD: dane jednej osoby nigdy nie są widoczne dla innej, w tym dla właściciela.

## Starting Point

Goły `startproject` na Railway: domyślny `auth.User` (login po `username`), tylko `/admin/` i `/healthz/`, brak własnych aplikacji i testów. Produkcyjna baza ma 18 migracji i jedno konto admina, bez backupu.

## Desired End State

Niezalogowany trafia z każdej strony na `/login/`. Po zalogowaniu e-mailem (wielkość liter bez znaczenia) widzi angielską stronę powitalną ze swoim e-mailem; sesja trwa 2 tygodnie. Właściciel zakłada konta w `/admin/`, gdzie widać tylko konta. Testy pytest dowodzą izolacji danych. Produkcja działa na nowym modelu użytkownika.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Model użytkownika | Własny `accounts.User`, e-mail jako unikalny login + reset bazy | Zalecenie Django: teraz to najtańsze (w bazie tylko konto admina), później prawie niemożliwe. |
| E-mail a wielkość liter | Zapis małymi literami, logowanie bez rozróżniania | `Anna@X.de` i `anna@x.de` to jedno konto; brak duplikatów. |
| Izolacja danych | Abstrakcyjny `UserOwned` + `for_user(user)`, `CASCADE` | Jeden wzór dla S-01…S-03, gotowy pod usuwanie konta (S-04), łatwy do testowania. |
| Zakładanie kont | Panel `/admin/` | Działa już na produkcji, bez terminala. |
| Testy | pytest + pytest-django | Standard w całym Pythonie; umiejętność przenośna poza Django. |
| Język UI | Angielski | Wybór użytkownika; zgodne z domyślnymi napisami Django. |
| Strona po zalogowaniu | Prosta strona powitalna z e-mailem | Widać, kto jest zalogowany; S-01 ją zastąpi. |
| Admin a dane użytkowników | Tylko konta, nigdy dane rozmów (test pilnuje) | Dosłownie spełnia PRD („nikt, w tym właściciel”). |
| Ochrona przed zgadywaniem hasła | Odłożona | Dwie osoby, hasła ustawia właściciel. |
| Czas sesji | 2 tygodnie (domyślne Django) | Brak wylogowania; wieczorna sesja zaczyna się od razu od nauki. |

## Scope

**In scope:**
- Aplikacja `accounts`: model `User`, manager, admin z formularzami na e-mailu
- `/login/`, strona powitalna `/`, `LoginRequiredMiddleware`, wyjątek dla `/healthz/`
- `UserOwned` + `for_user`, próbny model tylko w testach
- pytest + pierwsze testy; reguła w `lessons.md` i `CLAUDE.md`
- Reset bazy produkcyjnej, deploy, odtworzenie konta admina, konto drugiej osoby

**Out of scope:**
- Wylogowanie, rejestracja, reset hasła przez użytkownika, limit prób logowania
- Prawdziwe modele rozmów/błędów/pamięci (S-01…S-03), usuwanie konta (S-04)
- `mypy`, CI, backup `pg_dump`, tłumaczenia UI

## Architecture / Approach

`accounts.User` (e-mail) ← `ModelBackend` szuka przez `get_by_natural_key` (`email__iexact`) ← wbudowany `LoginView`. `LoginRequiredMiddleware` blokuje wszystko poza widokami `@login_not_required` (logowanie, admin-login, `/healthz/`). Przyszłe modele dziedziczą po `UserOwned` (FK `user`, `CASCADE`) i są czytane tylko przez `objects.for_user(request.user)`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Model użytkownika, admin, pytest | `accounts.User`, admin na e-mailu, pierwsze testy | Formularze admina nadal oczekują `username` |
| 2. Logowanie i wymóg logowania | `/login/`, `/`, middleware, wyjątek `/healthz/` | Health check zablokowany → nieudane deploye |
| 3. Wzorzec izolacji | `UserOwned` + `for_user`, testy izolacji, reguła w docs | Próbna aplikacja testowa przecieka do produkcji |
| 4. Wdrożenie z resetem bazy | Produkcja na nowym modelu, konta właściciela i drugiej osoby | Push przed resetem → nieudany pre-deploy `migrate` |

**Prerequisites:** dostęp do `railway ssh` w terminalu z TTY (klucz `~/.ssh/id_ed25519_railway`); commity faz 1–3 **nie są pushowane** przed fazą 4.
**Estimated effort:** ~3–4 sesje wieczorne w 4 fazach.

## Open Risks & Assumptions

- Reset bazy kasuje jedyne konto admina, a backupu nie ma. Akceptowane, bo w bazie nie ma innych danych.
- Strona logowania jest publiczna i nie ma limitu prób. Ryzyko jest akceptowane przy dwóch użytkownikach i silnych hasłach.
- Izolacja to konwencja (`for_user`), a nie twarda blokada. Pilnują jej testy i reguła w `lessons.md`.

## Success Criteria (Summary)

- Obie osoby logują się na produkcji swoim e-mailem i widzą tylko własne powitanie.
- Każda strona poza logowaniem przekierowuje niezalogowanego na `/login/`, a Railway health check przechodzi.
- `uv run pytest` dowodzi, że dane jednej osoby nie są widoczne dla drugiej.
