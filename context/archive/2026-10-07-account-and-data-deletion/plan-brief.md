# Usunięcie konta wraz z danymi (S-04) — Plan Brief

> Full plan: `context/changes/account-and-data-deletion/plan.md`
> Research: `context/changes/account-and-data-deletion/research.md`

## What & Why

Użytkownik może sam usunąć swoje konto wraz ze wszystkimi danymi — rozmowami, błędami i pamięcią (FR-013, must-have) — z trwałym usunięciem w ciągu 24 h (NFR „Usuwanie danych”). Przy okazji dostaje wylogowanie (FR-002, dotąd Parked), bo usuwanie i tak musi wywołać `logout()`.

## Starting Point

Kaskada `UserOwned` (od F-01) sprawia, że `user.delete()` usuwa już wszystkie dane z PRD; brakuje widoku, potwierdzenia i wylogowania. Poza kaskadą zostają sesje na innych urządzeniach i wpisy logu admina z e-mailem, a poza aplikacją — logi nadużyć OpenAI (do 30 dni) i przyszłe kopie zapasowe.

## Desired End State

Na stronie głównej przy „Signed in as …” są „Log out” i „Delete account”. Strona `/account/delete/` mówi, co zniknie, wspomina o kopiach u OpenAI i wymaga hasła; po potwierdzeniu konto i wszystkie dane (także sesje i wpisy logu admina o użytkowniku) znikają od razu, a użytkownik ląduje na `/login/` z komunikatem. Superuser nie może usunąć się z aplikacji. PRD i `deploy-plan.md` opisują wyjątki od 24 h.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Moment usunięcia | Od razu, twarde `user.delete()` | Spełnia 24 h z zapasem bez crona, którego Railway Hobby nie ma | Plan |
| Ochrona przed pomyłką | Osobna strona + obecne hasło | Chroni też przed kimś przy odblokowanym urządzeniu | Plan |
| Miejsce w UI | Link + przycisk „Log out” przy „Signed in as” | Najmniejsza zmiana; wylogowanie domyka FR-002 przy okazji | Plan |
| Konto superusera | Blokada samousunięcia w aplikacji | Właściciel nie straci jednym klikiem jedynego dostępu do admina | Plan |
| Sesje na innych urządzeniach | Usuwane wszystkie (także wygasłe) | Po usunięciu w bazie nie zostaje nic, co wskazuje na użytkownika | Research → Plan |
| Log admina o użytkowniku | Usuwany | E-mail usuniętej osoby nie zostaje w bazie | Research → Plan |
| OpenAI (logi do 30 dni) | Wyjątek w PRD + zdanie na stronie usuwania | Uczciwe wobec użytkownika, zapisane przy wymogu | Research → Plan |
| Kopie zapasowe | Reguła: zrzuty ≤ 7 dni, wyjątek w PRD | Reguła istnieje, zanim powstanie `pg_dump` | Research → Plan |
| Wyścig z trwającą turą agenta | Akceptujemy 500 w drugiej karcie | Rzadkie, dane i tak znikają w całości; bez zmian w logice rozmów | Plan |
| Ochrona na przyszłość | Test kaskady + strażnik relacji do `User` | Nowy model danych użytkownika wywróci test, dopóki nie zostanie świadomie dopisany | Plan |

## Scope

**In scope:**
- `POST /logout/` (wbudowany `LogoutView`) i przycisk na stronie głównej
- `accounts/services.py` (`delete_account`), widok i szablon `/account/delete/`, link na stronie głównej
- Testy: kaskada na prawdziwych modelach, strażnik relacji do `User`, sesje, log admina, złe hasło, superuser, niezalogowany
- PRD (wyjątek w NFR, usunięty non-goal o wylogowaniu), roadmapa (FR-002 z Parked do S-04), `deploy-plan.md` (retencja 7 dni)

**Out of scope:**
- Soft delete / okno na rozmyślenie, cron
- Obsługa wyścigu z trwającą turą lub analizą
- Wniosek o ZDR w OpenAI, budowa `pg_dump`
- Limit prób hasła, nawigacja w `base.html`, blokada `is_staff`

## Architecture / Approach

Wzorzec z `conversations`: cienki widok `account_delete` (GET: strona potwierdzenia; POST: serwis → `logout` → komunikat → redirect) i serwis `delete_account(user, password)`, który rzuca `AccountDeletionError` dla superusera lub złego hasła, a inaczej w jednej transakcji usuwa sesje użytkownika (`Session.get_decoded()`), wpisy `LogEntry` o nim i samego użytkownika z kaskadą ORM. Bez migracji.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Wylogowanie (FR-002) | `POST /logout/` + przycisk „Log out” | `LogoutView` bez `next_page` szuka nieistniejącego szablonu |
| 2. Usuwanie konta (FR-013) | Strona z hasłem, serwis usuwania, link, pełne testy | Kolejność: usunięcie → `logout()` → komunikat (inaczej stare ciasteczko lub zgubiony komunikat) |
| 3. Dokumenty | Wyjątki od 24 h w PRD i `deploy-plan.md`, FR-002 zdjęte z Parked | Rozjazd liczb (30 dni / 7 dni) między PRD, stroną i `deploy-plan.md` |

**Prerequisites:** F-01 (done); brak nowych zależności i migracji.
**Estimated effort:** ~1–2 sesje w 3 fazach.

## Open Risks & Assumptions

- Usunięcie w trakcie płatnej tury agenta lub analizy daje 500 w drugiej karcie i zmarnowane wywołanie (zaakceptowane).
- Logi nadużyć OpenAI (do 30 dni) są poza kontrolą aplikacji; konto nie ma ZDR.
- Przegląd wszystkich sesji jest liniowy — w porządku dla kilku użytkowników, nie dla dużej skali.
- Retencja logów Railway nie jest opisana w repo; logi aplikacji nie zawierają treści rozmów (research §2).

## Success Criteria (Summary)

- Użytkownik usuwa konto po podaniu hasła i nie może się już zalogować; w bazie nie ma jego rozmów, błędów, pamięci, sesji ani wpisów logu admina o nim, a dane innej osoby są nietknięte.
- Użytkownik może się wylogować przyciskiem „Log out” na stronie głównej.
- PRD uczciwie opisuje, czego aplikacja nie może usunąć (OpenAI, kopie zapasowe).
