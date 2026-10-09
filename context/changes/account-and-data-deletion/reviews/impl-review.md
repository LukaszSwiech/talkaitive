<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Usunięcie konta wraz z danymi (S-04)

- **Plan**: context/changes/account-and-data-deletion/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-09
- **Verdict**: APPROVED
- **Findings**: 0 critical, 2 warnings, 7 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | WARNING |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

Automatyczne: `pytest` (195 passed), `ruff check` + `ruff format --check` (czysto), `makemigrations --check --dry-run` (No changes detected), grep 3.1–3.3 OK. Treść `plan.md` nie zmieniała się w trakcie implementacji (tylko sekcja Progress). Brak MISSING. Poza planem tylko: test pustego hasła (nieszkodliwy) oraz `tasks-github.md` / `tasks-linear.md` (synchronizacja statusu S-04 wymagana przez `lessons.md`). Kryterium ręczne 3.4 ma dowód: zdanie o OpenAI (30 dni) na `/account/delete/`, NFR „Usuwanie danych” w PRD i reguła 7 dni w `deploy-plan.md` są spójne. Safety & Quality i Pattern Consistency mają tylko obserwacje (F3–F6, F8, F9), bez ostrzeżeń.

## Findings

### F1 — `accounts` zależy od `conversations` przez import typu żądania

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architecture
- **Location**: accounts/views.py:13
- **Detail**: `from conversations.views import AuthenticatedHttpRequest` to jedyny import z `accounts` do `conversations`; w drugą stronę importuje 6 modułów (`models`, `services`, `views`, `budget`, `memory`, `llm`). Plan dopuszczał ten wariant, ale odwraca on kierunek zależności: aplikacja fundamentowa zależy od aplikacji funkcji, a import `accounts.views` ładuje `conversations.views` razem z `services`, `budget` i `llm` (SDK OpenAI). Cyklu importów dziś nie ma; powstałby, gdyby `conversations` kiedyś zaimportowało `accounts.views` albo `accounts.urls`. Typ jest używany tylko w tych dwóch plikach widoków.
- **Fix**: Przenieść `AuthenticatedHttpRequest` do nowego `accounts/http.py` i importować go stamtąd w `accounts/views.py` i `conversations/views.py` (jedna definicja, jak chciał plan).
- **Decision**: FIXED — klasa przeniesiona do nowego `accounts/http.py`; `accounts/views.py` i `conversations/views.py` importują ją stamtąd (jedna definicja, `accounts` nie importuje już nic z `conversations`). `pytest` 195 passed, ruff czysto.

### F2 — Strona główna: nowy CSS w `home.html` zamiast klasy `.actions` z planu

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: conversations/templates/conversations/home.html:3-24
- **Detail**: Plan (faza 1, punkt 2) kazał ułożyć „Log out” w wierszu istniejącą klasą `.actions` (`base.html:28`). Powstał za to pasek `<header class="topbar">` (z przeniesionym `<h1>`) i blok `<style>` w `{% block head %}` z 5 regułami `.topbar` / `.account`. To pierwszy CSS poza jedynym `<style>` w `base.html`: reguły innych stron (`.topics`, `.transcript`, `.mistakes`) są tam, a `block head` służył dotąd tylko do `<meta refresh>` w `detail.html`. `block head` renderuje się przed bazowym `<style>` (`base.html:7-8`), więc reguła strony o tej samej specyficzności przegra z bazową; dziś działa, bo selektory są bardziej szczegółowe. Odstępstwo opisuje tylko commit 9d90a73, nie plan.
- **Fix A ⭐ Recommended**: Przenieść 5 reguł `.topbar` do `<style>` w `base.html` i usunąć `{% block head %}` z `home.html`; wygląd zostaje.
  - Strength: Wraca zasada „cały CSS w `base.html`”, a wygląd, który przeszedł ręczny test 1.3, się nie zmienia.
  - Tradeoff: Dotyka `base.html` (plik wspólny dla wszystkich stron), choć tylko dopisaniem reguł.
  - Confidence: HIGH — to samo miejsce, w którym są `.topics` i `.mistakes`.
  - Blind spot: Nie wiemy, czy pasek był świadomą prośbą w trakcie implementacji (wspomina go tylko commit).
- **Fix B**: Wrócić do planu: tekst, przycisk i link w jednym `<div class="actions">`, bez nowego CSS.
  - Strength: Dokładnie to, co mówi plan; zero nowych reguł.
  - Tradeoff: Zmienia wygląd strony głównej, który przeszedł już ręczny test 1.3.
  - Confidence: MED — nie sprawdzaliśmy w przeglądarce, jak `.actions` ułoży akapit, formularz i link.
  - Blind spot: Wygląd na wąskim ekranie (telefon).
- **Decision**: ACCEPTED — świadoma decyzja użytkownika w triage: pasek `.topbar` i jego blok `<style>` zostają w `home.html` bez zmian (wygląd przeszedł ręczny test 1.3).

### F3 — Strażnik relacji widzi tylko bezpośrednie relacje do `User`

- **Severity**: OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: tests/test_account_deletion.py:110-138
- **Detail**: Test bierze tylko pola z `related_model is User`. (1) Przyszły model z FK do `Conversation`, `Message` albo `Mistake` z `on_delete=SET_NULL` przejdzie strażnika, a jego wiersze z tekstem użytkownika przetrwają usunięcie konta (z `conversation=NULL`), cicho łamiąc FR-013; z `PROTECT` usunięcie skończy się błędem 500 (`ProtectedError` nie jest łapany; transakcja się wycofa, więc nic nie zginie). (2) Dla M2M do `User` druga asercja nigdy nie przejdzie: `ManyToManyRel` nie ma `on_delete` (zawsze `None`), a komunikat każe ustawić `on_delete=CASCADE`, którego M2M nie ma. (3) Odwołania przez tekstowe id albo `GenericForeignKey` (jak `LogEntry.object_id`) są dla strażnika niewidoczne. Dziś wszystko jest poprawne (`Message.conversation` i `Mistake.conversation` mają CASCADE). Filtr `not field.auto_created` zamiast `concrete` z planu jest lepszy od planu: pola M2M mają w Django `concrete=False`, więc filtr z planu nigdy by ich nie złapał.
- **Fix**: Rozszerzyć strażnika: wyliczyć wszystkie modele osiągalne z `User` przez relacje z CASCADE i wymagać, żeby każde FK/O2O wskazujące na którykolwiek z nich miało CASCADE (albo było na jawnej liście wyjątków); M2M sprawdzać osobno, z własnym komunikatem.
  - Strength: Łapie najbardziej prawdopodobny przyszły przypadek (model-dziecko rozmowy, jak `Message`), czyli dokładnie ryzyko z `roadmap.md` (S-04, Risk).
  - Tradeoff: Test robi się dłuższy i trudniejszy do czytania (pętla, aż zbiór modeli przestanie rosnąć).
  - Confidence: MED — wzorzec jest prosty, ale nowy w tym repo i sam wymaga sprawdzenia.
  - Blind spot: Odwołania przez tekstowe id nadal zostaną niewidoczne; na nie pomoże tylko reguła w `lessons.md`.
- **Decision**: FIXED — nowa funkcja `user_data_models()` (`User` i wszystko, co znika z nim przez CASCADE) i test `test_every_relation_to_user_data_is_known_and_cascades` z jawną listą 6 relacji (doszły `Mistake.conversation` i `Message.conversation`); M2M pomijane przy sprawdzaniu `on_delete`. Eksperyment z modelami-wabikami (poza repo): strażnik łapie FK z `SET_NULL` do `Conversation`, M2M do `User` (komunikat o nieznanej relacji, nie o `on_delete`) i `PROTECT` pod `Message`. Odwołania przez tekstowe id nadal są niewidoczne.

### F4 — Brak `Cache-Control` po zalogowaniu: „Wstecz” po wylogowaniu może pokazać poprzednią stronę

- **Severity**: OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: talkaitive/settings.py:124 (MIDDLEWARE); zachowanie sprzed tej zmiany, poza diffem
- **Detail**: Żaden widok ani middleware w projekcie nie ustawia `Cache-Control` (brak `never_cache` / `cache_control`); ma go tylko wbudowany `LogoutView`. Po wylogowaniu albo usunięciu konta przycisk „Wstecz” może więc pokazać poprzednie strony z pamięci przeglądarki (back/forward cache): e-mail, a na stronie rozmowy cały jej zapis — bez pytania serwera. Handler `pageshow` w `base.html:83-89` tylko odblokowuje przyciski, nie chowa treści. Ma to znaczenie na wspólnym komputerze, czyli w głównym powodzie, żeby się wylogować (PRD, NFR „Prywatność”).
- **Fix**: Osobna zmiana: mały middleware, który odpowiedziom dla zalogowanych ustawia `Cache-Control: no-store, private` (albo `never_cache` na widokach z danymi), plus test nagłówka.
  - Strength: Zamyka lukę dla wszystkich stron naraz, także przyszłych.
  - Tradeoff: Dotyka każdej strony; `no-store` zwykle wyłącza back/forward cache, więc „Wstecz” przeładuje stronę (wolniej, ale serwer przekieruje wtedy na logowanie).
  - Confidence: MED — nagłówek jest standardem, ale przeglądarki różnie traktują `no-store` w back/forward cache.
  - Blind spot: Nie sprawdzaliśmy tego w prawdziwej przeglądarce; wniosek opiera się na braku nagłówka i znanym działaniu przeglądarek.
- **Decision**: FIXED (w tej zmianie; poszerza zakres S-04) — nowy `accounts/middleware.py` (`NeverCacheSignedInMiddleware`: `add_never_cache_headers` na każdej odpowiedzi dla zalogowanego) wpięty w `MIDDLEWARE` zaraz po `LoginRequiredMiddleware`; test `test_signed_in_pages_are_not_cached` (`/` i `/account/delete/`) w `tests/test_login.py`. Eksperyment: bez middleware nagłówka `no-store` nie ma. W prawdziwej przeglądarce nie sprawdzone.

### F5 — Komentarz przy `logout()` błędnie opisuje mechanizm; żaden test nie pilnuje tego wywołania

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/views.py:31-33, tests/test_account_deletion.py:172-181
- **Detail**: Komentarz (powtórzony za „Critical Implementation Details” planu) mówi, że `flush()` „podmienia klucz sesji w ciasteczku” i że komunikat musi iść po `logout()`, żeby trafić do ciasteczka. W Django 6.1 po `flush()` sesja jest pusta, więc `SessionMiddleware` usuwa ciasteczko (`django/contrib/sessions/middleware.py:36-42`), a `logout()` w ogóle nie dotyka komunikatów — kolejność nie ma znaczenia. Prawdziwe powody, żeby wołać `logout()`: `request.user` staje się anonimowy do końca żądania, stare ciasteczko sesji jest kasowane, a bez `logout()` każdy zapis do sesji po usunięciu jej wiersza skończyłby się `SessionInterrupted` (400). Test sukcesu przechodzi także bez `logout()` (serwis i tak skasował wiersz sesji), więc nic nie pilnuje tego wywołania.
- **Fix**: Przepisać komentarz na prawdziwe powody i dopisać w `test_successful_deletion_logs_out_and_shows_message` asercję `response.cookies["sessionid"].value == ""`.
- **Decision**: FIXED — komentarz w `accounts/views.py` podaje prawdziwe powody (anonimowy `request.user`, usunięcie starego ciasteczka, brak `SessionInterrupted`); test sukcesu sprawdza `response.cookies["sessionid"].value == ""`. Eksperyment: z `logout()` podmienionym na funkcję, która nic nie robi, test pada.

### F6 — „Log out” po wygaśnięciu sesji kończy się pustą stroną 405

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/urls.py:8
- **Detail**: W Django 6.1 `LogoutView` nie ma `login_not_required` (`django/contrib/auth/views.py:133`; `LoginView` ma, `:74`). Gdy sesja już wygasła albo użytkownik wylogował się w innej karcie, kliknięcie „Log out” trafia do `LoginRequiredMiddleware` i kończy się na `/login/?next=/logout/`. Formularz logowania przekazuje `next` (`accounts/templates/registration/login.html:22`), więc po zalogowaniu przeglądarka robi GET na `/logout/` i dostaje pustą stronę 405.
- **Fix**: `login_not_required(LogoutView.as_view(next_page="login"))` w `accounts/urls.py` i test: niezalogowany `POST /logout/` → 302 na `/login/`.
- **Decision**: FIXED — trasa `logout/` owinięta w `login_not_required` (z komentarzem, dlaczego); nowy test `test_logout_when_already_signed_out_goes_to_login` w `tests/test_login.py`.

### F7 — Test superusera: asercja komunikatu błędu nigdy nie zawiedzie

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: tests/test_account_deletion.py:231
- **Detail**: Kontrakt planu: superuser `POST` z poprawnym hasłem → konto zostaje i jest komunikat błędu. Test sprawdza `"cannot be deleted here"`, ale ten tekst jest na stałe w notce superusera w szablonie (`account_delete.html:25`), więc asercja przejdzie, nawet gdy widok w ogóle nie wywoła `messages.error`. Główna obietnica (konto zostaje, linia 230) jest sprawdzona poprawnie.
- **Fix**: Sprawdzać tekst, który ma tylko komunikat serwisu: `"The owner account cannot be deleted here."` (albo `'class="flash error"'`).
- **Decision**: FIXED — test sprawdza `"The owner account cannot be deleted here."` (zdanie tylko z komunikatu serwisu, nie z szablonu). Eksperyment: z wyłączonym `messages.error` test pada.

### F8 — Hasło w widoku usuwania nie jest oznaczone jako wrażliwe

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/views.py:18
- **Detail**: Widok przyjmuje hasło konta, ale nie ma `@sensitive_post_parameters("password")`, którego Django używa na własnych widokach z hasłem (`django/contrib/auth/views.py:74`, `:256`, `:355`). Dziś bez skutku: projekt nie ma `ADMINS`, `LOGGING` ani Sentry, a w DEBUG filtr i tak jest wyłączony. Zacznie mieć znaczenie, gdy na produkcji pojawi się raportowanie błędów: nieobsłużony wyjątek w tym widoku (np. przypadek `PROTECT` z F3) trafiłby do raportu razem z hasłem zapisanym jawnym tekstem.
- **Fix**: Dodać `@sensitive_post_parameters("password")` na `account_delete` i `@sensitive_variables("password")` na `delete_account` (hasło jest tam też zmienną lokalną w śladzie błędu).
- **Decision**: FIXED — `@sensitive_post_parameters("password")` na `account_delete` (najwyżej w łańcuchu dekoratorów) i `@sensitive_variables("password")` na `delete_account`. Eksperyment z raportem błędu Django (`ExceptionReporter`): hasła w raporcie nie ma; w próbie kontrolnej bez dekoratorów hasło jest.

### F9 — Roadmapa: notatka S-04 w Backlog Handoff nadal mówi `planning`

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: context/foundation/roadmap.md:146
- **Detail**: Kolumna `Notes` w `## Backlog Handoff` dla S-04 ma „`planning` (2026-10-09)”, a `Status:` S-04 w tabeli At a glance (`roadmap.md:48`) i w sekcji `### S-04` to `in-progress` — tak samo jak w lustrach `tasks-github.md` i `tasks-linear.md`. W pozostałych wierszach ta kolumna pokazuje aktualny status.
- **Fix**: Zmienić notatkę na „`in-progress` (2026-10-09), plan: `context/changes/account-and-data-deletion/plan.md`.”
- **Decision**: SKIPPED — nie warto teraz; przy archiwizacji wiersz S-04 i tak dostanie `done`.
