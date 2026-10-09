---
date: 2026-10-07T21:12:29+02:00
researcher: Claude (Opus 5.5) for LukaszSwiech
git_commit: ad1a68bdd6eb2d31e4b4f2b70899125c43f496c6
branch: account-and-data-deletion
repository: 10xDevs4
topic: "S-04: co trzeba usunąć i do jakich wzorców musi pasować usuwanie konta wraz z danymi (FR-013, NFR Usuwanie danych)"
tags: [research, codebase, accounts, ownership, conversations, sessions, admin-log, openai, railway]
status: complete
last_updated: 2026-10-08
last_updated_by: Claude (Opus 5.5)
last_updated_note: "Przegląd końcowy: dopisane warunki i źródła (inwentarz modeli, FK w bazie, wpis Added w adminie, 8 wywołań loggera, zakres grepa messages.success, timeout analizy 150 s na próbę)."
---

# Research: usunięcie konta wraz z danymi (S-04)

**Date**: 2026-10-07T21:12:29+02:00
**Researcher**: Claude (Opus 5.5) for LukaszSwiech
**Git Commit**: ad1a68bdd6eb2d31e4b4f2b70899125c43f496c6
**Branch**: account-and-data-deletion
**Repository**: 10xDevs4

## Research Question

Roadmapa S-04 (`context/foundation/roadmap.md:126-136`), PRD FR-013 (`context/foundation/prd.md:63`) i NFR „Usuwanie danych” (`prd.md:95`): użytkownik może usunąć swoje konto wraz ze wszystkimi danymi (rozmowy, błędy, pamięć), a dane są trwale usunięte w ciągu 24 godzin.

Pytania:
1. Jakie dane w bazie należą do użytkownika i co z nimi robi `user.delete()`?
2. Gdzie dane użytkownika żyją poza tym, co obejmuje kaskada (sesje, log admina, kopie zapasowe, OpenAI, logi)?
3. Do jakich istniejących wzorców (URL, middleware, widoki, szablony, testy) musi pasować nowy widok usuwania konta?
4. Jakie wcześniejsze decyzje dotyczą S-04?

## Summary

- **Baza aplikacji: jedno wywołanie ORM wystarcza.** Na tym commicie, w inwentarzu wszystkich `models.py` aplikacji z `INSTALLED_APPS` (poza modelem testowym `OwnedNote` z `settings_test`), dane użytkownika to dokładnie trzy modele: `Conversation`, `Message`, `Mistake` (`conversations/models.py:8,79,104`). `Conversation` i `Mistake` dziedziczą po `UserOwned` z `on_delete=CASCADE` (`accounts/ownership.py:22-25`), `Message` i `Mistake` mają też `CASCADE` do `Conversation` (`conversations/models.py:84-85,115-116`). „Pamięć” nie ma własnej tabeli — to pola `Conversation` plus wiersze `Mistake`; budżet dzienny też jest liczony z tych tabel. `request.user.delete()` usuwa więc wszystkie dane z PRD (rozmowy, błędy, pamięć) natychmiast. Kaskada działa w ORM Django, nie w bazie — usuwać trzeba przez ORM, nie surowym SQL.
- **Poza kaskadą zostają dwa rodzaje wierszy w bazie** (bez treści rozmów): `django_session` (sesje na innych urządzeniach do 14 dni) i wpisy `django_admin_log` o tym użytkowniku, w których `object_repr` to jego e-mail (`accounts/models.py:80-81`).
- **Poza bazą:** kopii zapasowych bazy dziś nie ma (Railway Hobby, `context/deployment/deploy-plan.md:8,186`), ale planowany `pg_dump` (`deploy-plan.md:200`) nie ma jeszcze reguły retencji. OpenAI trzyma logi monitoringu nadużyć dla `/v1/responses` do 30 dni (dokumentacja OpenAI, sprawdzona 2026-10-07) — tego aplikacja nie usunie, a konto nie ma ZDR. Żadne z 8 wywołań loggera w kodzie aplikacji (`conversations/llm.py:262-349`) nie loguje treści rozmów.
- **Wzorce:** w aplikacji nie ma wylogowania (świadoma decyzja F-01), nie ma nawigacji ani linku do konta, `accounts/views.py` nie ma jeszcze widoków. Widok usuwania będzie pierwszym widokiem w `accounts`, musi sam wywołać `logout()` i pasować do stylu `@require_POST` + POST→redirect→GET z `conversations/views.py`.

## Detailed Findings

### 1. Dane użytkownika w bazie i `user.delete()`

| Model / tabela | Powiązanie z użytkownikiem | `on_delete` | Usunięte przez `user.delete()`? |
|---|---|---|---|
| `accounts.User` | — (korzeń) | — | tak |
| `Conversation(UserOwned)` | `user` z `accounts/ownership.py:23-25`; klasa `conversations/models.py:8` | CASCADE | tak |
| `Message` (bez pola `user`) | `conversation` → `Conversation` (`conversations/models.py:84-85`) | CASCADE | tak, przez `Conversation` |
| `Mistake(UserOwned)` | `user` (dziedziczone) + `conversation` (`conversations/models.py:104,115-116`) | CASCADE (oba) | tak |
| tabele M2M `User.groups` / `User.user_permissions` | `PermissionsMixin` | tabela pośrednia | tak, tylko wiersze powiązań |
| `admin.LogEntry`, w którym użytkownik jest **autorem** akcji | FK `user` w `django/contrib/admin/models.py` | CASCADE | tak |

- **Pamięć:** brak osobnej tabeli. To pola `Conversation.memory_prompt`, `learner_facts`, `scene_notes` (`conversations/models.py:29,51-52`) oraz wiersze `Mistake`, z których `conversations/memory.py:77-120` składa blok pamięci. Znikają z kaskadą.
- **Budżet dzienny:** liczony z `Message.cost_usd` i `Conversation.analysis_cost_usd` (`conversations/budget.py:62-72`), bez własnej tabeli. Po usunięciu konta historia kosztów znika; konto odtworzone na ten sam e-mail ma pełny budżet (ryzyko niskie, konta tworzy tylko właściciel w adminie).
- **Kaskada w ORM, nie w bazie:** migracje nie mają `db_constraint=False`, `RunSQL`, `RunPython` ani `DB_CASCADE` (grep po `*/migrations/`, wynik pusty). Django domyślnie tworzy klucze obce w bazie bez `ON DELETE CASCADE` (kaskadę wykonuje ORM; opcja `DB_CASCADE` nie jest używana), więc `DELETE` w surowym SQL na `accounts_user` przy istniejących rozmowach zostałby odrzucony — usuwanie musi iść przez `user.delete()`.
- Brak sygnałów `pre_delete`/`post_delete` i nadpisanego `delete()`; jedyna nadpisana metoda to `User.save` (`accounts/models.py:90`).
- Brak pól `FileField`/`ImageField`, plików na dysku, tokenów API, modeli z id użytkownika jako zwykłą liczbą i kopii tekstu użytkownika w wierszach innych użytkowników (raport sub-agenta po `models.py`, migracjach i `conversations/{services,budget,memory,llm,views}.py`).

### 2. Dane poza kaskadą

**W bazie, bez treści rozmów:**
- **`django_session`:** `SESSION_ENGINE` nie jest ustawiony (w `talkaitive/settings.py` jedyne ustawienie sesji to `SESSION_COOKIE_SECURE` w `:107`), więc działa domyślny backend bazodanowy. Wiersz sesji nie ma FK do użytkownika; trzyma `_auth_user_id`, backend i skrót hasła. `logout(request)` czyści tylko bieżącą sesję. Sesje z innych urządzeń zostają do wygaśnięcia (domyślne `SESSION_COOKIE_AGE` = 2 tygodnie, potwierdzone też w `context/archive/2026-10-01-auth-and-access-scaffold/plan-brief.md:30`), a wygasłe wiersze — dopóki nie zadziała `clearsessions`, którego repo nie uruchamia. Po usunięciu użytkownika takie sesje nie logują (id nie istnieje), ale wiersze trwają dłużej niż 24 h.
- **`django_admin_log` o użytkowniku:** `object_repr = str(user)`, a `User.__str__` zwraca e-mail (`accounts/models.py:80-81`); `object_id` to tekst, nie FK. Konta użytkowników zakłada właściciel w `/admin/` (`deploy-plan.md:194`); dla konta założonego w `/admin/` istnieje co najmniej wpis „Added” z e-mailem i zostaje po usunięciu konta (konto z `createsuperuser` takiego wpisu nie ma). Usunięcie użytkownika *przez admina* dopisuje kolejny wpis „Deleted” z e-mailem; usunięcie z widoku aplikacji go nie tworzy.

**Poza bazą:**
- **Kopie zapasowe Railway:** brak. Backupy i PITR są tylko na planie Pro (`context/deployment/deploy-plan.md:8,186,199`). Dziś nic nie koliduje z „24 h”.
- **Planowany `pg_dump`:** otwarte TODO (`deploy-plan.md:200`) i ewentualny Pro (`deploy-plan.md:206`). Każdy zrzut zawierałby dane usuniętego użytkownika do czasu wygaśnięcia zrzutu; reguła retencji nie jest nigdzie zapisana.
- **OpenAI:** oba wywołania mają `store=False` (`conversations/llm.py:257,329`); nie są przekazywane `previous_response_id`, `metadata`, `user` ani e-mail (grep sub-agenta). Do OpenAI trafia historia rozmowy, blok pamięci i transkrypt do analizy. Według dokumentacji OpenAI (https://developers.openai.com/api/docs/guides/your-data, odczyt 2026-10-07) `/v1/responses` ma domyślnie 30-dniowe logi monitoringu nadużyć (mogą zawierać prompty i odpowiedzi), a prompt cache trzyma tensory w GPU do 24 h. Wyłączenie wymaga zatwierdzenia ZDR / Modified Abuse Monitoring przez OpenAI; konto go nie ma (`context/archive/2026-10-05-first-corrected-conversation/change.md:15` — odrzucony projekt EU). Uwaga: wzmianka o „30-dniowym monitoringu” w `context/archive/2026-10-05-first-corrected-conversation/research.md:52` dotyczy `/v1/realtime` w regionie EU, nie bieżącego wywołania — aktualne źródło to strona OpenAI wyżej.
- **Logi aplikacji:** brak ustawienia `LOGGING`; jedyny logger to `conversations/llm.py:36`; jego 8 wywołań (`conversations/llm.py:262,271,277,280,333,341,346,349`) loguje stały tekst albo typ wyjątku i status HTTP, bez treści rozmowy (zasada w `conversations/llm.py:11-12`). Gunicorn bez access logu (`context/deployment/web-settings.json`, `startCommand`). Brak `print(`. Retencja logów na Railway nie jest opisana w repo (nie sprawdzono).
- **Cache:** `CACHES` nieustawione (LocMem), nigdzie nieużywane.
- **Wiersze martwe w Postgresie / WAL:** zostają do autovacuum/checkpointu; istotne tylko przy bardzo ścisłym czytaniu „trwale”.

### 3. Wzorce, do których musi pasować widok usuwania

- **URL:** `accounts/urls.py:5` ma tylko `login/` (wbudowany `LoginView`), `accounts/views.py` ma sam docstring („no own views yet”). `talkaitive/urls.py` montuje `accounts.urls` i `conversations.urls` pod `""`.
- **Wylogowania nie ma** (brak `LogoutView`, brak `logout` w `.py`/`.html`); to świadoma decyzja F-01 (`context/archive/2026-10-01-auth-and-access-scaffold/plan-brief.md:42`). `LOGOUT_REDIRECT_URL` nieustawione. Widok usuwania musi sam wywołać `django.contrib.auth.logout(request)` i przekierować np. do `login` (`LOGIN_URL = "login"`, `talkaitive/settings.py:137`).
- **Middleware:** `LoginRequiredMiddleware` włączony (`talkaitive/settings.py:131`) — nowy widok jest chroniony domyślnie, bez dekoratora. `CsrfViewMiddleware` i `messages` włączone.
- **Styl widoków:** funkcje z `@require_GET` / `@require_POST`, zasada „POST views always redirect” (`conversations/views.py:1-5,12`), typ `AuthenticatedHttpRequest` (`conversations/views.py:24-27`), logika w `services`, widok cienki — wzorzec: `conversation_end` (`conversations/views.py:138-142`). Komunikaty przez `messages.error` (np. `conversations/views.py:67`); `messages.success` nie występuje w żadnym pliku `.py` w `accounts`, `conversations`, `talkaitive` (grep, wynik pusty).
- **Szablony:** jeden `accounts/templates/base.html` z blokami `title`/`head`/`content`, flash w `:45-47`, globalny JS w `:54-100` blokuje wszystkie przyciski po wysłaniu formularza. Brak nawigacji — jedyne miejsce „konta” to `Signed in as {{ user.email }}` w `conversations/templates/conversations/home.html:5`. Formularze: `<form method="post">{% csrf_token %}<button>`. Brak frameworka CSS (inline `<style>` w `base.html:8-42`). **Cały interfejs jest po angielsku.**
- **Testy:** katalog `tests/`, bez `conftest.py` i fabryk; fixture per plik (`tests/test_login.py:9-11`), `client.force_login` (`tests/test_conversation_views.py:123-126`), wzorzec „niezalogowany → 302 do `/login/?next=`” (`tests/test_conversation_views.py:580-598`), sprawdzenie wylogowania przez `"_auth_user_id" not in client.session` (`tests/test_login.py:58,69`). Kaskada jest dziś testowana tylko na modelu testowym `OwnedNote` (`tests/test_ownership.py:37-44`); **brak testu kaskady User → Conversation → Message/Mistake**. Strażnik rejestru admina: `tests/test_ownership.py:47-52` (dozwolone `User`, `Group`).
- **Wyścig z trwającym żądaniem:** tura agenta lub analiza (limit czasu jednej próby analizy: 150 s, `talkaitive/settings.py:74`; z ponowieniami SDK może trwać dłużej) może trwać w momencie usunięcia. Po jej zakończeniu `_lock` (`conversations/services.py:60-66`) rzuci `Conversation.DoesNotExist` → błąd 500 i zmarnowane płatne wywołanie, ale bez osieroconych wierszy.

## Code References

- `accounts/ownership.py:22-25` — `UserOwned.user`, `on_delete=CASCADE`, `related_name="+"`
- `accounts/ownership.py:15-19` — `for_user()`, pusty wynik dla niezalogowanego
- `accounts/models.py:80-81` — `User.__str__` zwraca e-mail (trafia do `django_admin_log.object_repr`)
- `conversations/models.py:8,79,104` — `Conversation`, `Message`, `Mistake`
- `conversations/models.py:84-85,115-116` — FK do `Conversation` z CASCADE
- `conversations/llm.py:257,329` — `store=False`
- `conversations/views.py:138-142` — wzorzec widoku POST zmieniającego dane
- `conversations/services.py:60-66` — `_lock`, źródło 500 przy wyścigu
- `talkaitive/settings.py:131,137` — `LoginRequiredMiddleware`, `LOGIN_URL`
- `accounts/urls.py:5` — jedyna trasa w `accounts`
- `accounts/templates/base.html:45-47,54-100` — flash i globalny JS formularzy
- `conversations/templates/conversations/home.html:5` — „Signed in as”, naturalne miejsce na link do konta
- `tests/test_ownership.py:37-44,47-52` — test kaskady (model testowy) i strażnik admina

## Architecture Insights

- Kaskada `UserOwned` była od F-01 projektowana pod S-04; nowy model danych użytkownika, który dziedziczy po `UserOwned`, zostanie usunięty bez zmian w S-04. Model podrzędny bez `user` musi mieć `CASCADE` do rodzica (jak `Message`). Test kaskady na prawdziwych modelach chroniłby tę regułę przy kolejnych slice'ach (zgodnie z ryzykiem w `roadmap.md:135`).
- „Trwale w 24 h” da się spełnić dla bazy aplikacji natychmiastowym twardym usunięciem — nic w repo nie wymaga soft delete ani zadania w tle.
- Granica gwarancji przebiega poza aplikacją: OpenAI (30 dni) i przyszłe zrzuty bazy.

## Historical Context (from prior changes)

- `context/archive/2026-10-01-auth-and-access-scaffold/plan-brief.md:23` i `plan.md:40` — `UserOwned` + `CASCADE` wprowadzone jako przygotowanie pod S-04; samo usuwanie konta odłożone do S-04.
- `context/archive/2026-10-01-auth-and-access-scaffold/plan-brief.md:42` — wylogowanie, rejestracja i reset hasła świadomie poza F-01.
- `context/archive/2026-10-07-cross-session-error-memory/plan.md:31` — pamięć przechowywana na `Conversation`, znika z rozmową.
- `context/archive/2026-10-07-cross-session-error-memory/research.md:100` — dziś użytkowników usuwa tylko Django admin.
- `context/archive/2026-10-05-first-corrected-conversation/change.md:15` — endpoint EU odrzucony (401), brak ZDR.
- `context/foundation/lessons.md:54-66` — reguły `UserOwned` / `for_user` i 404 dla cudzych obiektów.
- Brak w `context/**` decyzji o soft delete, RODO/GDPR ani retencji kopii zapasowych.

## Related Research

- `context/archive/2026-10-07-cross-session-error-memory/research.md` — budowa pamięci z danych użytkownika
- `context/archive/2026-10-05-first-corrected-conversation/research.md` — wybór dostawcy LLM i rezydencja danych

## Open Questions

Decyzje produktowe dla `/10x-plan` (fakty wyżej, wybór należy do użytkownika):

1. **OpenAI a „24 h”:** zaakceptować i zapisać wyjątek (logi nadużyć OpenAI do 30 dni, poza kontrolą aplikacji), czy zmienić PRD? Wniosek o ZDR to proces poza kodem.
2. **Sesje na innych urządzeniach:** usuwać wszystkie wiersze `django_session` użytkownika przy usuwaniu konta (przy kilku użytkownikach przejrzenie i odkodowanie sesji jest tanie), czy uznać, że wiersze z samym id i skrótem hasła nie są „danymi” z PRD?
3. **`django_admin_log` z e-mailem:** usuwać wpisy z `content_type = User` i `object_id = user.pk` razem z kontem?
4. **Potwierdzenie:** jak chronić przed usunięciem przez pomyłkę (PRD `prd.md:64` wspomina ten argument) — osobna strona z potwierdzeniem, ponowne podanie hasła, wpisanie e-maila?
5. **Miejsce w UI:** link przy „Signed in as” na `home.html`, osobna strona konta? Czy przy okazji dodać wylogowanie (dziś poza zakresem, FR-002 nice-to-have)?
6. **Konta z `is_staff`/`is_superuser`:** czy widok ma blokować samousunięcie konta właściciela (jedyny dostęp do admina)?
7. **Przyszły `pg_dump`:** czy S-04 ma zapisać regułę retencji zrzutów (np. ≤ 24 h lub jawny wyjątek), zanim backup powstanie?

Luki faktów (nie blokują planu): retencja logów Railway na Hobby nie jest opisana w repo; zachowanie sesji opisane z domyślnych ustawień Django, bez wglądu w produkcyjną bazę.
