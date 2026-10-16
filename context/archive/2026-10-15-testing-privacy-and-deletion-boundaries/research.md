---
date: 2026-10-15T20:49:42+02:00
researcher: Claude (Opus 5.5) z LukaszSwiech
git_commit: df25bc5
branch: testing-privacy-and-deletion-boundaries
repository: 10xDevs4 (TalkAItive)
topic: "Rollout Phase 3 — granice prywatności (ryzyko #3) i usuwania konta (ryzyko #6)"
tags: [research, testing, privacy, idor, account-deletion, memory, accounts, conversations]
status: complete
last_updated: 2026-10-15
last_updated_by: Claude (Opus 5.5)
---

# Research: Rollout Phase 3 — granice prywatności i usuwania konta

**Date**: 2026-10-15T20:49:42+02:00
**Researcher**: Claude (Opus 5.5) z LukaszSwiech
**Git Commit**: df25bc5 (drzewo robocze: zmieniony `context/foundation/test-plan.md`, nowy folder tej zmiany; kod aplikacji i testy bez zmian)
**Branch**: testing-privacy-and-deletion-boundaries
**Repository**: 10xDevs4 (TalkAItive)

## Research Question

Rollout Phase 3 z `context/foundation/test-plan.md:74`, ryzyka #3 (`test-plan.md:46`, `:59`) i #6 (`test-plan.md:49`, `:62`). Dla każdego ryzyka: znaleźć prawdziwą ścieżkę awarii w kodzie, zweryfikować (nie przyjmować na wiarę) wskazówki odpowiedzi na ryzyko, znaleźć istniejące testy, wskazać najtańszą użyteczną warstwę testu i oznaczyć ryzyka spekulacyjne lub mylące dowody z hot-spotów (`conversations/`, `accounts/`).

Pytania z kolumny „Context `/10x-research` must ground”:

- #3: pełna lista widoków i punktów odczytu danych per użytkownik; jak powstaje blok pamięci; czy istniejące testy izolacji pokrywają wszystkie widoki.
- #6: lista modeli z relacją do użytkownika; jak działa strażnik; co zostaje poza kaskadą (sesje, log admina).

Badanie lokalne (bez podagentów): kod aplikacji ma ok. 1500 linii, wszystkie istotne pliki przeczytano w całości. Testów nie uruchamiano; przewidywania „mutant X zostałby zabity” są wnioskiem z kodu, nie pomiarem — plan ma je potwierdzić `manual_mutants.py`.

## Summary

- **#3, widoki z id w URL-u: dziś pokryte w całości, luka jest w przyszłości.** Aplikacja ma dokładnie 5 tras z `<int:pk>` (`conversations/urls.py:8-30`); wszystkie 5 widoków pobiera rozmowę jednym helperem `_get_conversation` → `get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)` (`conversations/views.py:24-25`, wywołania w `:76`, `:109`, `:123`, `:135`, `:142`). Test sparametryzowany po tych samych 5 trasach sprawdza 404 (nie 403), brak zmiany stanu i brak wywołania modelu (`tests/test_conversation_views.py:846-881`). Mutant kontrolny `C1` celuje w ten helper (`scripts/mutation/manual_mutants.py:74-80`). Brakuje mechanizmu, który wywróci test, gdy pojawi się **nowa** trasa z id, a nikt nie dopisze jej do listy parametrów — ta lista jest pisana ręcznie i nic jej nie porównuje z routerem URL.
- **#3, dane podrzędne: brak trasy, która adresuje `Message` albo `Mistake` po id.** `Message` nie ma pola `user` (`conversations/models.py:79-86`) i jest czytany tylko przez już zawężoną rozmowę (`views.py:90`) albo przez `conversation__in=Conversation.objects.for_user(user)` w budżecie (`conversations/budget.py:65-68`, `:103-106`). `Mistake` na stronie rozmowy idzie przez `for_user` **i** filtr `conversation=` (`views.py:95-97`). Jedyna ścieżka do danych podrzędnych innego użytkownika to strona szczegółów, a ta daje 404 (test wyżej).
- **#3, pamięć: logika jest poprawna i podwójnie zawężona, ale test jest słaby i żaden mutant jej nie pilnuje.** `select_memory` czyta rozmowy przez `for_user(user)` (`conversations/memory.py:79-87`), a błędy przez `for_user(user)` **i** `conversation_id__in` z listy własnych rozmów (`memory.py:120`). Istniejący test `test_memory_never_contains_another_users_data` (`tests/test_conversation_views.py:1309-1323`) daje Annie zero własnych danych i sprawdza `memory_prompt == ""` — nie odróżnia „dane B odfiltrowane” od „pamięć A zepsuta albo pusta”. Na liście ręcznych mutantów nie ma mutanta usuwającego `for_user` z `memory.py` (`manual_mutants.py:73-209`), a mutmut takich mutantów nie generuje (`test-plan.md:58`).
- **#6, strażnik relacji nie porównuje listy z samą sobą — ale widzi tylko klucze obce.** `test_every_relation_to_user_data_is_known_and_cascades` (`tests/test_account_deletion.py:110-166`) liczy domknięcie modeli kasowanych kaskadą od `User`, zbiera każdą relację wskazującą na to domknięcie i porównuje z ręcznie wpisanym zbiorem 6 par (`:144-151`). Nowy `ForeignKey` / `OneToOneField` / `ManyToManyField` do `User` lub do modelu kasowanego z nim wywraca test, bez względu na `on_delete`. **Nie wykryje** danych powiązanych z użytkownikiem bez klucza obcego: id albo e-mail zapisany jako tekst lub liczba, `GenericForeignKey` — dokładnie ta klasa, do której należą dwa znane wyjątki: sesje i `LogEntry.object_id` (`accounts/services.py:6-9`).
- **#6, nowa ścieżka awarii, której plan testów nie wymienia: usunięcie użytkownika przez `/admin/`.** `User` jest zarejestrowany w adminie (`accounts/admin.py:8-9`), a `delete_account` (sesje + `LogEntry` o użytkowniku) jest wołane tylko z widoku `account_delete` (`accounts/views.py:28`). Usunięcie konta przez właściciela w `/admin/` idzie zwykłym `delete()` z kaskadą, więc — wniosek z kodu, nie zmierzone — zostają sesje tego użytkownika i wpisy `LogEntry` o nim, w tym nowy wpis o samym usunięciu z `object_repr` = e-mail (`accounts/models.py:80-81`). Czy to jest w zakresie FR-013, to decyzja produktowa (Open Questions).
- **Hot-spoty:** `conversations/` jest trafnym dowodem dla #3 (tam są wszystkie widoki z id i pamięć). `accounts/` jest trafny dla #6 (`services.py`, `ownership.py`), ale dla #3 tylko częściowo: jedyny widok w `accounts/` (`account_delete`) nie ma id w URL-u i działa wyłącznie na `request.user` (`accounts/views.py:20-38`).

## Detailed Findings

### #3.1 Pełna lista tras i widoków (stan na `df25bc5`)

Router: `talkaitive/urls.py:30-35` (admin, `healthz`, `accounts.urls`, `conversations.urls`).

| Trasa | Widok | Id w URL | Jak czyta dane | Test izolacji |
|---|---|---|---|---|
| `/` | `home` (`conversations/views.py:32-51`) | nie | `Conversation.objects.for_user(request.user)` (`:35-39`), `is_exhausted(request.user, …)` | `test_home_never_shows_another_users_active_conversation` (`tests/test_conversation_views.py:370-392`, mutant `M1`) |
| `/conversations/start/` | `conversation_start` (`:54-71`) | nie | `services.start_conversation(request.user, …)`; po `LLMError` `for_user` (`:66-68`) | `test_llm_error_on_start_redirects_to_own_conversation_not_another_users` (`:431-449`, `M2`) |
| `/conversations/<pk>/` | `conversation_detail` (`:74-104`) | tak | `_get_conversation`; wiadomości przez `conversation.messages`; błędy przez `Mistake.objects.for_user(...).filter(conversation=…)` | `test_other_user_gets_404_on_every_conversation_url` (`:846-881`, `C1`); `test_conversation_page_lists_only_its_own_mistakes` (`:1088-1110`, `M3`, ten sam użytkownik) |
| `/conversations/<pk>/messages/` | `conversation_send` (`:107-118`) | tak | `_get_conversation` | jw., parametr `("post", "messages/")` |
| `/conversations/<pk>/retry/` | `conversation_retry` (`:121-130`) | tak | `_get_conversation` | jw. |
| `/conversations/<pk>/end/` | `conversation_end` (`:133-137`) | tak | `_get_conversation` | jw. |
| `/conversations/<pk>/analysis/` | `conversation_analyze` (`:140-151`) | tak | `_get_conversation` | jw. |
| `/account/delete/` | `account_delete` (`accounts/views.py:18-38`) | nie | tylko `request.user` | brak potrzeby testu IDOR; izolacja usuwania: `tests/test_account_deletion.py:85-107` |
| `/login/`, `/logout/` | widoki Django (`accounts/urls.py:8-15`) | nie | — | — |
| `/admin/…` | admin Django | tak (id obiektu) | tylko `User` i `Group` (`accounts/admin.py:8`; strażnik `tests/test_ownership.py:47-52`) | dane per użytkownik nie są zarejestrowane, więc nie ma czego adresować |
| `/healthz/` | `healthz` (`talkaitive/urls.py:24-27`) | nie | bez bazy | — |

Wniosek: zbiór tras z id per użytkownik to dokładnie 5 tras z `conversations/urls.py:8-30`, wszystkie przez jeden helper. Test `:846-881` obejmuje wszystkie 5 i sprawdza to, czego wymaga wskazówka: 404 (nie 403), stan rozmowy bez zmian, `roles == ["assistant"]`, brak nowych wywołań modelu i analizy.

### #3.2 „Zalogowany = uprawniony do obiektu” — weryfikacja

- `LoginRequiredMiddleware` (`talkaitive/settings.py`, lista `MIDDLEWARE`) wymusza tylko zalogowanie; anonimowy dostaje przekierowanie (`tests/test_conversation_views.py:884-904`). Autoryzacja do obiektu wynika wyłącznie z filtra w zapytaniu: `UserOwnedQuerySet.for_user` (`accounts/ownership.py:15-19`). Nie ma żadnego dekoratora ani middleware, który sprawdza właściciela.
- `UserOwned.objects` to zarazem domyślny manager bez filtra (`accounts/ownership.py:27`), więc `Conversation.objects.get(pk=pk)` w nowym widoku przejdzie bez błędu — to dokładnie luka opisana w `lessons.md` („Widoki szczegółów pobierają obiekt przez for_user…”). Wskazówka „challenge: zalogowany = uprawniony” jest więc trafna co do mechanizmu: ochrona zależy od każdego zapytania z osobna.
- `services._lock`, `_clear_turn_marker`, `end_conversation`, `_mark_analysis_failed` używają `for_user(conversation.user)` (`conversations/services.py:60-66`, `:92-96`, `:235-242`, `:364-371`) — użytkownika **rozmowy**, nie żądania. Jest to bezpieczne tylko dlatego, że każdy wywołujący widok najpierw zawęził rozmowę do `request.user` (`views.py:24-25`). Wniosek z kodu: serwisy same nie są granicą izolacji; granicą jest `_get_conversation`.

### #3.3 „Wzorzec z lessons.md jest stosowany wszędzie” — weryfikacja

Sprawdzone punkty odczytu modeli per użytkownik w `conversations/` i `accounts/` (pełny odczyt `views.py`, `services.py`, `budget.py`, `memory.py`, `accounts/services.py`, `accounts/views.py`):

- `Conversation` — wszystkie odczyty przez `for_user` (`views.py:25`, `:36`, `:66`; `services.py:63`, `:94`, `:239`, `:277`, `:368`; `budget.py:66`, `:70`, `:85`, `:104`; `memory.py:80`). Jedyny zapis bez `for_user` to `Conversation.objects.create(user=user, …)` (`services.py:117`), co jest poprawne (tworzenie).
- `Mistake` — `for_user` w `views.py:95` i `memory.py:120`; zapis `bulk_create` z `user=conversation.user` (`services.py:421-434`).
- `Message` — brak pola `user`; odczyt przez rodzica: `conversation.messages` (`views.py:90`; `services.py:183`, `:300`; `models.py:75`) albo `conversation__in=Conversation.objects.for_user(user)` (`budget.py:65-68`, `:103-106`). Zgodne z drugą regułą `lessons.md`.

Wzorzec jest dziś stosowany we wszystkich sprawdzonych miejscach. Ryzyko #3 nie jest więc „gdzieś dziś jest IDOR”, tylko „nowy widok / nowy model ominie wzorzec i nic tego nie wykryje”. Jedyny mechaniczny strażnik wzorca to rejestr admina (`tests/test_ownership.py:47-52`); dla widoków takiego strażnika nie ma.

### #3.4 Jak powstaje blok pamięci

1. `conversation_start` przekazuje `request.user` (`views.py:57-58`) do `start_conversation` (`services.py:99`).
2. `start_conversation` woła `select_memory(user, topic.key, user.practice_language)` i formatuje wynik `format_memory(...)` (`services.py:110-112`); tekst zapisuje raz do `Conversation.memory_prompt` (`services.py:122`; `models.py:26-30`) i wysyła go przy każdej turze (`services.py:196`).
3. `select_memory` (`memory.py:77-101`): rozmowy `Conversation.objects.for_user(user)` zakończone, przeanalizowane, w tym samym języku; fakty i notatki sceny pochodzą z pól tych rozmów (`learner_facts`, `scene_notes`). Błędy: `Mistake.objects.for_user(user).filter(conversation_id__in=<id własnych rozmów>)` (`memory.py:116-120`).
4. `memory_prompt` nie jest renderowany w żadnym szablonie (przeszukane `conversations/templates`, `accounts/templates`) — trafia tylko do promptu modelu.

Wnioski:

- Usunięcie `for_user` z zapytania o rozmowy (`memory.py:80`) wpuściłoby fakty, notatki i — przez listę id — błędy innego użytkownika. To jest mutant, który ma sens dla ryzyka #3, a nie ma go w `manual_mutants.py`.
- Usunięcie `for_user` z zapytania o błędy (`memory.py:120`) jest w praktyce **równoważne**: `conversation_id__in` zawiera tylko id rozmów użytkownika, a `Mistake.user` jest zawsze użytkownikiem rozmowy (`services.py:423`; docstring `models.py:105-108`). Taki mutant przeżyje każdy test i powinien trafić do `accepted_survivors.md` jako `równoważny`, a nie być „zabijany” na siłę.
- Słabość istniejącego testu (`tests/test_conversation_views.py:1309-1323`): Anna nie ma własnych danych, więc oczekiwanie `memory_prompt == ""` przechodzi także wtedy, gdy wybór pamięci jest zepsuty w sposób, który pomija wszystko. Lepsza wyrocznia to wzorzec metamorficzny z `test-plan.md:136` (§6.1): blok pamięci Anny z danymi Łukasza i bez nich jest identyczny i niepusty. Dodatkowo nowsze rozmowy Łukasza wypchnęłyby starsze rozmowy Anny z okna 20/10/5 (`memory.py:33-36`), gdyby filtr zniknął — ten sam test pokrywa więc też skutek „pamięć A zubożona przez dane B”.

### #3.5 Testy na modelu testowym

`tests/ownership_testapp/models.py:6-7` (`OwnedNote`), instalowany tylko w testach (`talkaitive/settings_test.py:12-13`), jest używany w `tests/test_ownership.py:21-44` do sprawdzenia samego managera `for_user`. To poprawny test jednostkowy wzorca, ale **nie** jest dowodem izolacji widoków — ten dowód dają testy na prawdziwych modelach w `tests/test_conversation_views.py`. Anty-wzorzec z planu („test na modelu testowym zamiast prawdziwych”) dotyczyłby nowych testów fazy 3, gdyby ktoś oparł je o `OwnedNote`; obecne testy widoków go nie popełniają.

### #6.1 Modele z relacją do użytkownika

Domknięcie kaskadowe od `User` (z `INSTALLED_APPS` w `talkaitive/settings.py` + `tests.ownership_testapp` w testach) i relacje wpisane w strażniku (`tests/test_account_deletion.py:144-151`):

| Model.pole | Cel | `on_delete` | Źródło |
|---|---|---|---|
| `Conversation.user` | `User` | CASCADE | `accounts/ownership.py:23-25` (dziedziczone) |
| `Mistake.user` | `User` | CASCADE | jw. |
| `Mistake.conversation` | `Conversation` | CASCADE | `conversations/models.py:115-117` |
| `Message.conversation` | `Conversation` | CASCADE | `conversations/models.py:84-86` |
| `LogEntry.user` | `User` | CASCADE | Django admin (autor wpisu) |
| `OwnedNote.user` | `User` | CASCADE | model testowy, tylko w `settings_test` |

Dane pamięci (`memory_prompt`, `learner_facts`, `scene_notes`) są polami `Conversation` (`models.py:30`, `:55-56`), więc znikają razem z wierszem rozmowy. Relacje M2M `User.groups` / `User.user_permissions` mają automatyczne tabele pośrednie, które `apps.get_models()` domyślnie pomija; Django usuwa ich wiersze przy `user.delete()`.

### #6.2 Jak działa strażnik i czego nie widzi

Mechanika (`tests/test_account_deletion.py:110-166`):

1. `user_data_models()` (`:110-129`) zaczyna od `{User}` i dokłada każdy model z konkretnym (`concrete`) polem relacji z `on_delete is CASCADE` do modelu już w zbiorze, aż zbiór przestanie rosnąć.
2. Test (`:132-142`) zbiera każdą nie-automatyczną relację (`many_to_one`, `one_to_one`, `many_to_many`), której cel jest w tym zbiorze — **bez względu na `on_delete`**.
3. Porównanie ze zbiorem wpisanym ręcznie (`:144-158`), potem sprawdzenie, że każda relacja FK/O2O ma `CASCADE` (`:159-166`).

Weryfikacja „strażnik porównuje listę z samą sobą”: **nie porównuje** — `expected` to literał, a `found` pochodzi z rejestru modeli Django. Ponadto zepsucie `user_data_models()` tak, by zwracał tylko `{User}`, zgubiłoby `Mistake.conversation` i `Message.conversation` z `found`, więc test i tak by padł (wniosek z kodu).

Weryfikacja „istniejący strażnik na pewno wykrywa nowy model” — **częściowo prawda**:

- Wykryje (wniosek z kodu): nowy model z FK / O2O / M2M do `User` lub do `Conversation`/`Message`/`Mistake`, także z `SET_NULL`, `PROTECT` czy `DO_NOTHING` (krok 2 nie filtruje po `on_delete`, a krok 3 wymaga CASCADE).
- **Nie wykryje**:
  - danych powiązanych z użytkownikiem bez klucza obcego — `IntegerField`/`CharField` z id, kopia e-maila, JSON z identyfikatorem, `GenericForeignKey` (ma `related_model = None`, więc warunek `:139` go pomija). To ta sama klasa co sesje i `LogEntry.object_id`, które już dziś wymagały ręcznej obsługi (`accounts/services.py:6-9`, `:46-53`);
  - danych poza bazą (pliki, cache, zewnętrzne usługi). Dziś ich nie ma: brak `CACHES`, `SESSION_ENGINE`, `MESSAGE_STORAGE` w ustawieniach (domyślne: sesje w bazie), brak użyć `cache.` w kodzie, a logi `conversations/llm.py:262-353` zapisują tylko fakt błędu, bez treści i bez id użytkownika;
  - modelu potomnego w dziedziczeniu wielotabelowym (`parent_ptr` ma `auto_created=True`, więc `:137` go pomija). Bez skutku dla danych — `parent_ptr` jest CASCADE, więc wiersze i tak znikną — tylko brak sygnału „nowy model”.
- Strażnik jest statyczny. Behawioralny test usuwania (`tests/test_account_deletion.py:85-107`) liczy wiersze tylko 3 nazwanych modeli (`Conversation`, `Message`, `Mistake`). Nowy model dopisany do `expected` nie dostaje automatycznie sprawdzenia „po usunięciu nie ma wierszy” — to zależy od tego, czy autor zastosuje się do komunikatu strażnika (`:153-157`).

### #6.3 Co zostaje poza kaskadą

Obsłużone ręcznie w `delete_account` (`accounts/services.py:44-54`), w jednej transakcji:

- sesje użytkownika, także wygasłe — pętla po wszystkich `Session` i porównanie `_auth_user_id` (`:47-49`); test `tests/test_account_deletion.py:169-184`;
- wpisy `LogEntry` **o** użytkowniku (`object_id` jest tekstem) (`:50-53`); test `:187-196`.

Poza aplikacją (PRD, NFR „Usuwanie danych”, docstring `accounts/services.py:11-12`): kopie u OpenAI do 30 dni i kopie zapasowe bazy.

Ścieżka nieobsłużona (nowe ustalenie): usunięcie zwykłego użytkownika przez właściciela w `/admin/` (`accounts/admin.py:8-47`, `UserAdmin` z Django pozwala usuwać). Ta ścieżka nie woła `delete_account`, więc ręczne kroki z `:46-53` się nie wykonują. Wniosek z kodu Django admina, nie zmierzony testem: zostają sesje usuniętego użytkownika (już bezużyteczne do logowania, bo użytkownika nie ma, ale z jego id), stare wpisy `LogEntry` o nim oraz nowy wpis `DELETION` z `object_repr` = e-mail. Docstring wskazuje `/admin/` jako drogę usuwania **konta właściciela** (`accounts/services.py:36-39`), więc ta ścieżka jest w projekcie przewidziana.

### #6.4 Mutacja usuwania konta

`accounts/services.py` nie jest w `[tool.mutmut]` (`test-plan.md:96`: 4 moduły, bez `accounts/services.py`) i na liście ręcznej nie ma żadnego mutanta usuwania (`manual_mutants.py:73-209`). Przewidywania z kodu (do potwierdzenia ręcznymi mutantami w planie):

| Zepsucie | Który test powinien paść |
|---|---|
| usunięta pętla po sesjach (`services.py:47-49`) | `test_deleting_account_ends_all_sessions_of_that_user_only` (`tests/test_account_deletion.py:169-184`) |
| usunięte kasowanie `LogEntry` o użytkowniku (`:50-53`) | `test_deleting_account_removes_admin_log_entries_about_that_user` (`:187-196`) |
| `LogEntry` bez filtra `object_id=` (kasuje wpisy o wszystkich) | jw. — zostaje wpis o Łukaszu (`:196`) |
| `Mistake.user` / `Message.conversation` z `SET_NULL` (wymaga migracji) | strażnik `:159-166` |
| para usunięta z `expected` | strażnik `:152` (równość zbiorów) |

### #6.5 Prawdopodobieństwo „Low” — weryfikacja

Zgodne z kodem: dziś są 3 prawdziwe modele aplikacji z danymi użytkownika (`Conversation`, `Message`, `Mistake`), wszystkie z CASCADE, i strażnik pokrywa wszystkie relacje FK. Prawdopodobieństwo rośnie przy modelu bez FK do użytkownika (patrz #6.2) i przy usuwaniu przez admina (#6.3) — ta druga ścieżka istnieje już dziś.

## Odpowiedź na wskazówki z planu (verify, not accept)

| Wskazówka | Werdykt | Korekta dla planu |
|---|---|---|
| #3: „każdy widok z id daje 404 dla cudzego obiektu” | **już spełnione** dla 5 dzisiejszych tras (`tests/test_conversation_views.py:846-881`) | Nie pisać drugiego testu 404 per widok. Dodać test, który wylicza trasy z id z routera URL (`get_resolver()`, wzorce z konwerterem) i porównuje z **ręcznie wpisanym** zbiorem nazw tras objętych testem 404 — nowa trasa z id bez decyzji wywraca test. Unikać wyliczania listy parametrów z tego samego routera, bo to byłoby porównanie listy z samą sobą. |
| #3: „każda ścieżka do danych podrzędnych daje 404” | spełnione: brak tras do `Message`/`Mistake` po id; strona rozmowy daje 404 | Nowy test zbędny; wystarczy, że test tras z id obejmie przyszłe trasy podrzędne. |
| #3: „blok pamięci A nie zawiera danych B” | logika poprawna, **test słaby**, brak mutanta | Test metamorficzny: Anna z własną pamięcią; `memory_prompt` (albo `select_memory`) identyczny z danymi Łukasza i bez nich, i niepusty; dane Łukasza nowsze niż Anny. Ręczny mutant: `memory.py:80` bez `for_user` (`expected="killed"`); mutant `memory.py:120` bez `for_user` → `accepted`, `równoważny`. |
| #3: „sprawdzanie 403 zamiast 404” | kod i test używają 404 (`views.py:25`, test `:876`) | Bez zmian. |
| #3: „test na modelu testowym” | widoki testowane na prawdziwych modelach; `OwnedNote` tylko dla managera | Nowe testy fazy 3 na `Conversation`/`Mistake`/`Message`. |
| #6: „po usunięciu żaden model nie zostawia wierszy” | spełnione dla 3 modeli + sesje + `LogEntry` przez `delete_account` | Rozważyć test behawioralny, który przechodzi po **wszystkich** modelach z `user_data_models()` i wymaga dla każdego fabryki danych (słownik model → fabryka, porównany ze zbiorem z domknięcia); nowy model bez fabryki wywraca test. Otwarta decyzja: ścieżka `/admin/`. |
| #6: „strażnik na pewno wykrywa nowy model” | **tylko dla relacji FK/O2O/M2M** | Nie da się mechanicznie wykryć referencji bez FK. Opcje dla planu: heurystyka nazw pól (`*user*`, `*email*`, `GenericForeignKey`) w modelach aplikacji z listą świadomych wyjątków — tania, ale może dawać fałszywe alarmy; albo pozostawić to regule w `lessons.md`. |
| #6: „strażnik porównujący listę z samą sobą” | nie występuje | Mutacja strażnika: usunięcie pary z `expected` i podmiana `user_data_models()` na `{User}` — obie powinny wywrócić test (przewidywanie). |

## Najtańsza użyteczna warstwa

- **#3 trasy z id**: test bez bazy na routerze URL (`django.urls.get_resolver`) + istniejący test integracyjny 404. Koszt: milisekundy.
- **#3 pamięć**: test integracyjny z bazą na `select_memory` albo przez `POST /conversations/start/` z atrapą `fake_llm` (wzorzec już w `tests/test_conversation_views.py:1309-1323`) + 2 ręczne mutanty.
- **#6**: istniejący strażnik statyczny (bez bazy) + test behawioralny z klientem Django (`tests/test_account_deletion.py`) + ręczne mutanty dla `accounts/services.py` (moduł poza mutmut; można też dopisać go do `[tool.mutmut]`).
- E2E w przeglądarce niepotrzebne: żadna z tych awarii nie zależy od JS (`test-plan.md:199`).

## Code References

- `conversations/urls.py:8-30` — 5 tras z `<int:pk>`
- `conversations/views.py:24-25` — `_get_conversation` przez `for_user`, jedyna granica izolacji widoków
- `conversations/views.py:90`, `:95-97` — wiadomości i błędy na stronie rozmowy
- `accounts/ownership.py:15-27` — `for_user`, `UserOwned`, domyślny manager bez filtra
- `conversations/memory.py:77-101`, `:116-120` — wybór pamięci, dwa filtry `for_user`
- `conversations/services.py:99-131` — start rozmowy, zapis `memory_prompt`
- `conversations/services.py:421-434` — `Mistake.user = conversation.user`
- `conversations/budget.py:62-74`, `:100-117` — odczyty `Message` przez zawężone rozmowy
- `accounts/services.py:28-54` — `delete_account`: sesje, `LogEntry`, `user.delete()`
- `accounts/admin.py:8-47` — `User` w adminie (ścieżka usuwania omijająca `delete_account`)
- `tests/test_conversation_views.py:846-881` — 404 na wszystkich 5 trasach
- `tests/test_conversation_views.py:1309-1323` — test pamięci bez danych B (słaba wyrocznia)
- `tests/test_account_deletion.py:85-107` — usunięcie usuwa dane tylko tego użytkownika
- `tests/test_account_deletion.py:110-166` — strażnik relacji
- `tests/test_ownership.py:21-52` — manager na modelu testowym + strażnik rejestru admina
- `scripts/mutation/manual_mutants.py:73-209` — ręczne mutanty `C1`, `C2`, `M1`–`M15`; brak mutantów pamięci-izolacji i usuwania konta

## Architecture Insights

- Izolacja to filtr w zapytaniu, nie warstwa uprawnień. Jedna granica dla widoków (`_get_conversation`) upraszcza testowanie: jeden helper, jeden mutant `C1`, jeden test sparametryzowany. Ryzyko leży w kodzie, który tej granicy nie użyje.
- Serwisy ufają, że dostały już zawężoną rozmowę (`for_user(conversation.user)`); granica jest w widoku.
- Usuwanie konta ma dwie warstwy: kaskada ORM (pilnowana strażnikiem statycznym) i ręczne kroki dla danych bez FK (pilnowane testami behawioralnymi). Druga warstwa działa tylko na ścieżce `account_delete`.

## Historical Context (from prior changes)

- `context/archive/2026-10-07-account-and-data-deletion/` — slice S-04, z którego pochodzą `delete_account`, strażnik relacji i testy usuwania (nie czytano szczegółowo; zachowanie zweryfikowano w kodzie).
- `context/archive/2026-10-07-cross-session-error-memory/` — slice S-03, źródło `select_memory`.
- `context/archive/2026-10-14-testing-suite-trust-and-ci/` — faza 1: przy 198 zielonych testach przeżywały mutanty izolacji `M1`–`M3` (`test-plan.md:187`); testy `:370-392`, `:431-449`, `:1088-1110` powstały, by je zabić (docstringi „Guards M1/M2/M3”).
- `context/foundation/lessons.md` — reguły „Dane per użytkownik dziedziczą po UserOwned…” i „Widoki szczegółów pobierają obiekt przez for_user…”; ta druga wymaga testu 404 dla każdego widoku z `pk`, co dziś jest spełnione, ale nie wymuszone mechanicznie.

## Related Research

- `context/archive/2026-10-14-testing-suite-trust-and-ci/research.md` — pomiar mutacyjny, w tym mutanty izolacji.

## Open Questions

1. **Usuwanie przez `/admin/`** — czy FR-013 obejmuje usunięcie zwykłego użytkownika przez właściciela w adminie? Jeśli tak: test, który to wykaże, i poprawka (np. sygnał `pre_delete` na `User` albo nadpisanie `delete_model`/`delete_queryset` w `UserAdmin`, które woła tę samą logikę co `delete_account`); jeśli nie: wpis w `test-plan.md` §7. Decyzja produktowa, nie testowa.
2. **Referencje bez FK** — heurystyka nazw pól w strażniku czy tylko reguła w `lessons.md`? Kompromis: fałszywe alarmy vs. brak sygnału.
3. **Test behawioralny „wszystkie modele bez wierszy”** — czy warto rejestru fabryk per model (silniejszy, więcej kodu), czy wystarczy dzisiejszy test 3 modeli + komunikat strażnika?
4. Przewidywania mutacyjne w tym dokumencie (tabela #6.4, mutanty pamięci) nie były uruchomione — plan musi je potwierdzić `manual_mutants.py`.
