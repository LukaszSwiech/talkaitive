---
date: 2026-10-14T11:41:25+02:00
researcher: Claude (Opus 5.5) dla LukaszSwiech
git_commit: b652de9
branch: main
repository: 10xDevs4 (TalkAItive)
topic: "Faza 1 planu testów (Suite trust and CI floor): czy obecne testy łapią zepsutą logikę krytyczną i jak postawić bramkę CI przed produkcją"
tags: [research, codebase, testing, mutation-testing, mutmut, ci, github-actions, railway, risk-2]
status: complete
last_updated: 2026-10-14
last_updated_by: Claude (Opus 5.5)
---

# Research: Faza 1 — zaufanie do testów i bramka CI

**Date**: 2026-10-14T11:41:25+02:00
**Researcher**: Claude (Opus 5.5) dla LukaszSwiech
**Git Commit**: b652de9 (drzewo robocze: zmieniony `CLAUDE.md`, nowe `context/foundation/test-plan.md` i ten folder — bez zmian w kodzie aplikacji)
**Branch**: main
**Repository**: 10xDevs4 (TalkAItive)

## Research Question

Rollout Phase 1 z `context/foundation/test-plan.md:72`, ryzyko #2 (`test-plan.md:45`, `:58`): udowodnić, że celowe zepsucie krytycznej logiki deterministycznej (izolacja danych, budżet dzienny, stan analizy, wybór pamięci) wywraca testy, i że testy uruchamiają się same, zanim zmiana trafi na produkcję. `change.md:13-14`.

Pytania z „Context `/10x-research` must ground” (`test-plan.md:58`) plus to, czego potrzebuje plan:

1. Które moduły mają przeżywające mutanty (zepsute wersje kodu, przy których testy dalej przechodzą)?
2. Jak dziś zmiana trafia na `main` (PR czy bezpośredni push)?
3. Co Railway robi przy nieudanym starcie?
4. Jakie fakty o narzędziach (mutmut 3.8, GitHub Actions z uv, ochrona gałęzi, Railway „Wait for CI”) ograniczają plan?

## Summary

- **Obecne testy przepuszczają realne błędy w logice krytycznej — zmierzone, nie tylko przewidziane.** Na kopii repo w katalogu tymczasowym wprowadzono ręcznie 15 mutacji, po jednej naraz, i uruchomiono pełne `pytest`. 2 mutacje kontrolne zostały złapane. Z 13 mutacji celowanych w miejsca podejrzane o słabe testy **12 przeżyło** (198/198 testów zielonych), 1 złapano. Przeżyły m.in. trzy wycieki danych między użytkownikami w widokach i jeden w budżecie (szczegóły: tabela w „Pomiar mutacyjny”). To jest zbiór celowany, nie wynik mutacyjny całego kodu.
- **Dziś nie ma żadnego CI.** Brak katalogu `.github/`, API zwraca `{"total_count":0,"workflows":[]}`; `main` wdraża się sam bez bramki (`context/deployment/deploy-plan.md:7`, `:150`: `checkSuites` off).
- **Ochrony gałęzi `main` nie da się włączyć na tym repo.** Repo jest prywatne, a `gh api repos/LukaszSwiech/talkaitive/branches/main/protection` zwraca HTTP 403 „Upgrade to GitHub Pro or make this repository public to enable this feature.” (sprawdzone 2026-10-14). Bramka „merge do `main` tylko po zielonym CI” z `test-plan.md:116` jest więc w obecnym planie GitHub niewykonalna. Wykonalna alternatywa to Railway „Wait for CI”: deploy czeka na workflow GitHub Actions uruchomiony na `push` do `main` i jest pomijany, gdy workflow padnie (docs Railway, niżej).
- **Na `main` trafiają zarówno PR-y, jak i bezpośrednie commity.** W `git log --first-parent main` (59 commitów, 2026-09-25 → 2026-10-09) jest 5 merge'y PR (#12, #13, #15, #17, #18) i 54 commity bezpośrednie. Od S-01 (2026-10-06) kod idzie przez PR, ale `chore(archive)`/`chore(roadmap)` i dokumenty planu dalej idą prosto na `main` — i też uruchamiają deploy. Bramka tylko na `pull_request` nie objęłaby tych pushy.
- **Health check Railway nie sprawdza logiki.** `/healthz/` zawsze zwraca „ok”, bez bazy i logowania (`talkaitive/urls.py:24-27`). Według docs Railway nieudany pre-deploy (`migrate`) albo health check zostawia poprzednią wersję w ruchu; zepsuty widok czy błędna logika przechodzą przez to sito.
- **Stan bazowy pod CI jest zielony i tani.** `uv run pytest`: 198 passed w ~1,7 s; `ruff check .`: „All checks passed!”; `ruff format --check .`: 91 plików sformatowanych (uruchomione 2026-10-14). Testy nie potrzebują sekretów: bez zmiennych środowiskowych DEBUG jest włączony, baza to SQLite, a `settings_test` wstawia sztuczny klucz OpenAI (`talkaitive/settings.py:36-38`, `:164-170`; `talkaitive/settings_test.py`).
- **Luka środowiskowa:** testy biegną na SQLite, produkcja na Postgresie. Kod używa `select_for_update()` (`conversations/services.py:64`), które na SQLite nie blokuje wiersza — zachowanie przy równoległych żądaniach nie jest dziś sprawdzane w żadnym przebiegu testów.
- **mutmut 3.8.0 (2026-09-12) obsługuje Python 3.14 i macOS, ale ma ograniczenia ważne dla tego repo:** mutuje tylko kod wewnątrz funkcji (stałe modułowe, ustawienia, pola modeli — nie), nie ma operatora „usuń wywołanie `.for_user()`/`.filter()`”, `source_paths` trzeba podać jawnie, a `mutmut run` kończy się kodem 0 nawet przy przeżywających mutantach. Współpraca z pytest-django w katalogu `mutants/` nie jest potwierdzona żadnym źródłem ani próbą — to otwarta kwestia dla planu.

## Detailed Findings

### 1. Pomiar mutacyjny (ręczne mutacje na kopii repo)

Metoda: `rsync` repo do scratchpada (bez `.venv`, `.git`, `db.sqlite3`, `.env`, `context/`), skrypt podmieniający dokładnie jeden fragment tekstu na raz, potem `pytest -q -x` interpreterem z `.venv` projektu, potem przywrócenie oryginału. Przebieg bazowy na kopii: 198 passed. Łączny czas 15 przebiegów: ~29 s (każdy ~1,0–1,5 s). Repo nie było zmieniane.

| # | Obszar | Mutacja (miejsce w kodzie) | Wynik | Skutek dla użytkownika, gdyby to był prawdziwy błąd |
|---|--------|----------------------------|-------|-----------------------------------------------------|
| C1 | izolacja | `_get_conversation` bez `for_user` (`conversations/views.py:25`) | KILLED (kontrola) | — |
| C2 | budżet | `is_exhausted`: `>=` → `>` (`conversations/budget.py:96`) | KILLED (kontrola) | — |
| M1 | izolacja | strona główna: aktywna rozmowa bez `for_user` (`views.py:36`) | **SURVIVED** | B widzi link „Continue” i temat aktywnej rozmowy A |
| M2 | izolacja | start rozmowy, gałąź `LLMError`: aktywna rozmowa bez `for_user` (`views.py:66`) | **SURVIVED** | B zostaje przekierowany na rozmowę A (dalej dostaje 404 dzięki `_get_conversation`, ale wybór celu przekierowania jest cudzy) |
| M3 | izolacja | strona rozmowy: błędy bez filtra `conversation=` (`views.py:95-97`) | **SURVIVED** | na liście błędów rozmowy X pojawiają się błędy z innych rozmów tego samego użytkownika |
| M4 | budżet + izolacja | `is_final_turn` bez `conversation__in=` (`budget.py:104-106`) | **SURVIVED** | koszt ostatniej tury dowolnego użytkownika decyduje, czy rozmowa A kończy się limitem |
| M5 | budżet | `is_exhausted`: `ended_at__gte` → `__gt` (`budget.py:88`) | **SURVIVED** | rozmowa zakończona limitem dokładnie o północy Berlin nie blokuje dnia (granica) |
| M6 | stan analizy | `_mark_analysis_failed` bez `pk=` (`conversations/services.py:347`) | **SURVIVED** | nieudana analiza jednej rozmowy oznacza jako „nieudane” wszystkie nieprzeanalizowane rozmowy użytkownika |
| M7 | stan analizy | znacznik „w toku” nigdy nie ustawiany: `analysis_started_at = None` (`services.py:298`) | **SURVIVED** | brak ochrony przed podwójną płatną analizą i brak spinnera — obszar incydentu z ryzyka #1 |
| M8 | stan tury agenta | `agent_turn_in_progress`: `<` → `<=` (`services.py:79`) | **SURVIVED** | granica wygaśnięcia znacznika (mała waga, ale pokazuje brak testu granicy) |
| M9 | stan tury agenta | timeout tury `+ 30` → `+ 3000` s (`services.py:73`) | KILLED | — (test sprawdza 120 s, więc ogromna zmiana jest łapana; zmiana o kilka sekund — przewidywanie: przeżyje) |
| M10 | pamięć | `MISTAKE_WINDOW_CONVERSATIONS` 20 → 19 (`conversations/memory.py:33`) | **SURVIVED** | pamięć bierze błędy z 19 zamiast 20 rozmów; test sprawdza tylko, że 21. jest pominięta |
| M11 | pamięć | `select_memory` bez filtra `status=ENDED` (`memory.py:82`) | **SURVIVED** | w praktyce prawie równoważne (aktywna rozmowa nie ma `analyzed_at`), ale dwa filtry są testowane jednym przypadkiem |
| M12 | pamięć | sortowanie bez `"-ended_at"` (`memory.py:86`) | **SURVIVED** | „najświeższe” rozmowy liczone po id, nie po dacie zakończenia; testy tworzą rozmowy w kolejności czasu |
| M13 | pamięć → prompt | etykieta „(the most recent)” na 2. zamiast 1. rozmowie (`conversations/llm.py:184-185`) | **SURVIVED** | model dostaje błędną informację, która scena była ostatnia |

Wniosek dla planu: wynik „zielone testy” nie świadczy dziś o ochronie izolacji na stronach `home`/`start`/`detail` (M1–M3) ani o kilku granicach budżetu, analizy i pamięci. Każdy z wierszy SURVIVED jest gotowym kandydatem na test, którego oczekiwany wynik wynika z PRD (izolacja: `prd.md` Guardrails/NFR „Prywatność”; budżet: Access Control), a nie z kodu.

### 2. Przewidywania z czytania kodu (nie zmierzone)

Analiza statyczna pomocnika (pełny odczyt `accounts/ownership.py`, `conversations/{budget,memory,services,views,models}.py`, `tests/test_{budget,memory,analysis,ownership}.py`) wskazała dodatkowo jako prawdopodobnie przeżywające, bez uruchomienia:

- `services.py:279` `sum(1 …)` → `sum(2 …)` i `services.py:380` `<= learner_messages` → `<` (scalanie błędów, test `tests/test_analysis.py:446`).
- `services.py:256` `_clear_analysis_marker` bez `pk=` — ta sama przyczyna co M6: w testach każdy użytkownik ma jedną rozmowę.
- Agent turn `services.py:73` `+30` → `+31` i `*` → `/` — test sprawdza tylko 0 s i 120 s (`tests/test_conversation_views.py:471-494`).
- `budget.py:107` bez `role=ASSISTANT` — łapane tylko przez test widoku (`test_conversation_views.py:272`), nie przez `test_budget.py`.
- Stałe modułowe (`DAILY_BUDGET_USD` 1.00, `LLM_TURN_COST_ESTIMATE_USD` 0.03, ceny `gpt-5.4` w `talkaitive/settings.py:79-96`) — każdy moduł testów nadpisuje je w fixture'ach autouse (`test_budget.py:26-28`, `test_analysis.py:89-100`, `test_conversation_views.py:100-110`), więc zmiana domyślnej wartości nie wywróci żadnego testu.

Mocne strony (przewidywane KILL, częściowo potwierdzone C1/C2): `for_user` sam w sobie (`tests/test_ownership.py:22-34`), 404 na pięć adresów z `pk` (`test_conversation_views.py:555-578`), granice dnia i zmiana czasu w budżecie (`test_budget.py:100-140` — wartości UTC wpisane ręcznie, niezależna wyrocznia), lista dozwolonych modeli w adminie wpisana ręcznie (`test_ownership.py:8`, `:47-52`).

### 3. Problem wyroczni (oczekiwany wynik skopiowany z implementacji)

Miejsca, w których test powtarza regułę albo wzór z kodu zamiast wymagania (wskazane przez pomocnika, kotwice sprawdzone przy odczycie):

1. Koszt tury: `tests/test_budget.py:89-92` ma wpisane 0.0034, ale komentarz pokazuje, że liczono je tym samym wzorem i tą samą interpretacją `input_tokens` (z tokenami z cache) co `conversations/budget.py:25-43`. Ta sama stała jest skopiowana do `tests/test_analysis.py:44-56` i `tests/test_conversation_views.py:22-33`. Ceny w `settings.py:80-84` nie są porównane z żadnym zewnętrznym źródłem.
2. Reguła „wydane + 0.03 ≥ budżet”: `test_budget.py:203`, `:223`, `:227-230` i `test_analysis.py:153` powtarzają `budget.py:94-97`. PRD mówi tylko o przekroczeniu limitu.
3. Reguła „koszt ostatniej tury agenta” (`test_budget.py:288-298`) powtarza docstring `budget.py:101`.
4. Timeout analizy: `test_analysis.py:103-104` liczy go tym samym wzorem co `services.py:243-244`.
5. Reguły pamięci i scalania błędów w `test_memory.py` i `test_analysis.py:418-471` idą za docstringami (`memory.py:3-21`, `services.py:371-377`) napisanymi przez to samo AI, nie za PRD.

Koszt nieudanych wywołań: kod zapisuje 0 przy nieudanej lub porzuconej płatnej próbie (`services.py:194-197`, `:303-305`, `:335-338`), a testy to utrwalają (`test_analysis.py:411`, `test_conversation_views.py:438-459`). To zaakceptowana luka MVP (roadmap Q-07, ryzyko #4) — testy mutacyjne nie wykryją brakującej funkcji; to temat Fazy 4.

### 4. Jak zmiany trafiają na `main` i co robi Railway

- Historia: 59 commitów first-parent na `main`, 5 merge'y PR, 54 bezpośrednie. Wszystkie 5 PR-ów zmergowano w 1,5–51 min od otwarcia; brak PR-ów otwartych lub zamkniętych bez merge'a (`gh pr list --state all`, 2026-10-14).
- Ustawienia repo: merge commit / squash / rebase dozwolone, `allow_auto_merge: false`.
- Railway `web` (kopia ustawień: `context/deployment/web-settings.json:5-11`): pre-deploy `python manage.py migrate --noinput` (timeout 300 s), start `collectstatic` + gunicorn, health check `/healthz/` z timeoutem 120 s, restart `ON_FAILURE` do 10 razy. Build: Railpack z `uv sync --locked --no-dev` (`deploy-plan.md:176`).
- Jedyny sygnał wracający do GitHuba to status commita „talkaitive - web” od Railway; 19 deploymentów od 2026-09-25 do 2026-10-09, żaden nieudany. Commity tylko z dokumentami (np. `b652de9`) też wdrażają produkcję.
- Zachowanie przy awarii (z docs Railway, Context7 `/railwayapp/docs`, nie z incydentu w tym projekcie): nieudany pre-deploy zatrzymuje deploy bez ponowienia; nieudany health check oznacza deploy jako failed, a poprzednia wersja dalej obsługuje ruch. Wniosek (nie sprawdzony w repo): migracja wykonuje się przed health checkiem, więc przy udanej migracji i nieudanym starcie stary kod działa na nowym schemacie (`context/foundation/infrastructure.md:134` mówi, że migracje nie cofają się z kodem).

### 5. Narzędzia — fakty, które ograniczają plan

**mutmut 3.8.0** (PyPI, wydany 2026-09-12; `requires_python >=3.10`, Python 3.14 od 3.4.0; źródła: https://pypi.org/pypi/mutmut/json, https://github.com/boxed/mutmut/blob/main/README.rst, HISTORY.rst):
- Konfiguracja w `[tool.mutmut]` w `pyproject.toml`. `source_paths` trzeba ustawić jawnie, bo repo nie ma `src/`/`lib/` ani katalogu o nazwie cwd (np. `["accounts", "conversations", "talkaitive"]`). `paths_to_mutate` i `tests_dir` są przestarzałe od 3.6.0. Zawężanie: `only_mutate`, `do_not_mutate`, `do_not_mutate_patterns`, glob w CLI `mutmut run "conversations.budget*"`.
- Domyślnie do `mutants/` kopiowane są m.in. `tests/`, `pyproject.toml`, `uv.lock`; `manage.py` i `conftest.py` w katalogu głównym — nie (`also_copy`). `talkaitive.settings_test` musi być importowalne z `mutants/`.
- Uruchamia pytest przez `pytest.main()` wewnątrz `mutants/`, potem forkuje proces na każdy mutant. `pythonpath = ["."]` z `pyproject.toml:34` jest wymienione w kodzie mutmut jako częsta przyczyna błędu „trampoline hits don't match” — trzeba sprawdzić próbą.
- Mutuje tylko kod w funkcjach i metodach. Nie mutuje stałych modułowych, ustawień, pól i `Meta` modeli, `urlpatterns`, migracji. Brak operatora usuwającego wywołanie metody; wywołanie z jednym argumentem staje się `f(None)` (łatwo zabijane), z kilkoma — traci jeden argument (to daje użyteczne mutanty typu M4/M6).
- `mutmut run` zwraca 0 nawet przy przeżywających mutantach — próg w CI trzeba by oskryptować (`mutmut results`, `export-cicd-stats`). Pragmy: `# pragma: no mutate`, `no mutate block`, `no mutate start/end`.
- macOS działa (setproctitle wyłączany automatycznie); Windows tylko przez WSL. Otwarte zgłoszenia: #504 (Django 5.2 + Python 3.14, ustawienia Django uruchamiane wielokrotnie przy kolejnych `pytest.main()`), #545 (fałszywe timeouty przy pełnej równoległości — obniżyć `--max-children`). Brak oficjalnej sekcji o Django/pytest-django.
- Alternatywy: cosmic-ray utrzymywany (8.7.0, 2026-08-09, klasyfikatory do 3.13); mutatest porzucony (ostatnie wydanie 2022).
- Plan testów już zakłada mutmut „okresowo, nie na każdy PR” (`test-plan.md:96`, `:117`). Przy ~1,5 s na pełne `pytest` i forkowaniu per mutant koszt przebiegu jest nieznany do pierwszej próby.

**GitHub Actions z uv** (https://docs.astral.sh/uv/guides/integration/github/; wersje z API wydań GitHub 2026-10-14):
- Zalecane: `astral-sh/setup-uv`, potem `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`. Wersję Pythona bierze z `.python-version` (repo: `3.14`).
- `actions/checkout` — v7 (7.0.1). `astral-sh/setup-uv` — 10.3.0 (2026-10-09); od v8.0.0 action nie publikuje tagów major/minor, więc `@v10` się nie rozwiąże — trzeba pełnego tagu albo SHA. Strona uv nadal pokazuje v9.0.0. (Twierdzenie pomocnika z API wydań; do potwierdzenia przy pisaniu workflow.)

**Ochrona gałęzi / rulesets** (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches oraz …/managing-rulesets/about-rulesets): na GitHub Free dostępne tylko w repo publicznych; repo prywatne wymaga Pro, Team lub Enterprise. Zgodne z 403 zaobserwowanym na tym repo. Workflow i tak się uruchamiają i pokazują wynik na PR — po prostu nie da się ich wymusić przy merge'u.

**Railway „Wait for CI”** (https://docs.railway.com/deployments/github-autodeploys, sekcja „Wait for CI”; https://docs.railway.com/guides/ship-on-merge-pr-canaries):
- Przełącznik pojawia się w ustawieniach serwisu (sekcja Source), gdy repo ma workflow GitHub Actions uruchamiany na `push` do gałęzi wyzwalającej (`main`) i zaakceptowano nowe uprawnienia aplikacji Railway na GitHubie.
- Deploy czeka w stanie `WAITING` na zakończenie wszystkich workflow Actions na commicie; nieudany workflow → `SKIPPED`, produkcja zostaje na poprzedniej wersji; po 2 h bez wyniku deploy jest pomijany; checki innych aplikacji GitHub są ignorowane. Nie wymaga ochrony gałęzi.
- Wątek Railway Station z 2026-10-13 zgłasza, że przełącznik nie zawsze się zapisuje (https://station.railway.com/questions/wait-for-ci-toggle-does-not-persist-an-0da81113) — po włączeniu trzeba sprawdzić, czy został.
- W API pole nazywa się `source.checkSuites`; Railway ignoruje `railway.json` w tym projekcie, więc ustawienie żyje tylko w UI Railway i jego kopii `context/deployment/web-settings.json` (CLAUDE.md).

## Code References

- `accounts/ownership.py:16-19` — `for_user` (pusty wynik dla niezalogowanego)
- `conversations/views.py:24-25` — `_get_conversation` (404 na cudzy obiekt, testowane)
- `conversations/views.py:35-40` — aktywna rozmowa na stronie głównej (M1)
- `conversations/views.py:63-70` — gałąź `LLMError` przy starcie rozmowy (M2)
- `conversations/views.py:95-97` — lista błędów na stronie rozmowy (M3)
- `conversations/budget.py:25-43` — `turn_cost`; `:46-59` — granice dnia Europe/Berlin; `:62-74` — `spent_today`; `:77-97` — `is_exhausted` (M5, C2); `:100-117` — `is_final_turn` (M4)
- `conversations/services.py:64` — `select_for_update()` (bez efektu na SQLite)
- `conversations/services.py:69-79` — timeout i znacznik tury agenta (M8, M9)
- `conversations/services.py:241-257` — timeout, znacznik i czyszczenie znacznika analizy
- `conversations/services.py:298` — ustawienie znacznika analizy (M7)
- `conversations/services.py:342-349` — `_mark_analysis_failed` (M6)
- `conversations/memory.py:33-36` — okna pamięci (M10); `:79-86` — wybór i sortowanie rozmów (M11, M12)
- `conversations/llm.py:182-185` — etykiety scen w bloku pamięci (M13)
- `talkaitive/urls.py:24-27` — `/healthz/` zawsze „ok”
- `talkaitive/settings.py:36-38` — DEBUG domyślnie włączony poza Railway; `:164-170` — SQLite bez `DATABASE_URL`
- `talkaitive/settings_test.py` — szybki hasher, statyczne pliki bez manifestu, `tests.ownership_testapp`, `OPENAI_API_KEY = "test-key"`
- `pyproject.toml:31-35` — konfiguracja pytest (`pythonpath = ["."]`, `testpaths = ["tests"]`); `:22-29` — ruff
- `context/deployment/web-settings.json:5-11` — pre-deploy, start, health check, restart
- `context/deployment/deploy-plan.md:7`, `:150` — auto-deploy z `main`, `checkSuites` off

## Architecture Insights

- Testy: 10 plików, 176 funkcji `test_`, 198 przypadków po parametryzacji (największe: `test_conversation_views.py` 49, `test_llm.py` 39, `test_budget.py` 26). Wszystkie bez sieci — granica OpenAI SDK jest podmieniana atrapami.
- Dobre cele dla mutmut (czysta logika w funkcjach): `conversations/budget.py`, `conversations/memory.py`, analiza w `conversations/services.py:241-412`, `accounts/ownership.py`, czyste helpery `llm.py` (`format_memory`, `_build_input`, `_build_transcript`). Słabe cele: wywołania SDK w `llm.py`, cienkie widoki z dekoratorami, `settings.py`, `models.py`, `admin.py`, `topics.py`, migracje.
- Najważniejsze mutanty izolacji (usunięcie `.for_user()`) mutmut sam nie wygeneruje — M1–M3 powstały ręcznie. Wynik mutmut na `views.py` będzie więc zawyżony względem realnej ochrony.
- Stan „analiza w toku / nieudana” jest częściowo decydowany w szablonie (`conversations/templates/conversations/detail.html:9` — auto-odświeżanie co 5 s, `:65-84` — kolejność „w toku” przed „nieudana”, np. `:67`, `:72`), którego mutmut nie mutuje.

## Historical Context (from prior changes)

- `context/foundation/tech-stack.md:35-37` — „CI on GitHub Actions runs tests on pull requests only, since Railway handles deploys on merge to `main`.” **Częściowo nieaktualne:** zgodne z zamiarem (CI na GitHub Actions), ale „tylko PR” nie wystarczy, jeśli bramką ma być Railway „Wait for CI” (wymaga workflow na `push` do `main`), a 54 z 59 commitów first-parent trafiło na `main` bez PR.
- `context/changes/bootstrap-verification/verification.md:53-54`, `:180-181` — ten sam zamiar; zapisano tylko podpowiedzi `ci_provider: github-actions` / `ci_default_flow: auto-deploy-on-merge`, bez plików workflow.
- `context/deployment/deploy-plan.md:150` — CI odłożone świadomie (decyzja użytkownika 2026-09-28). Wspierane: nadal brak CI na 2026-10-14.
- `context/archive/2026-10-01-auth-and-access-scaffold/plan.md:41` — „mypy + django-stubs, CI na GitHub Actions … osobne zadania”. Wspierane: żadne z nich nie powstało.
- `context/foundation/test-plan.md:116` — bramka „merge do `main` tylko po zielonym CI | ochrona gałęzi”. **Sprzeczne z faktem:** na tym repo (prywatne, Free) ochrona gałęzi jest niedostępna (403).
- W `context/changes/**` i `context/archive/**` brak wcześniejszych decyzji o testach mutacyjnych.

## Related Research

- `context/archive/2026-10-07-cross-session-error-memory/research.md` — projekt pamięci (S-03), źródło reguł z `memory.py:3-21`.
- `context/archive/2026-10-06-post-conversation-error-list/` — analiza błędów (S-02), stan analizy i scalanie.
- `context/archive/2026-10-07-account-and-data-deletion/` — strażnik relacji i kasowanie (dotyczy ryzyka #6, Faza 3).

## Open Questions

Decyzje dla `/10x-plan` (wybory produktowe użytkownika, nie fakty do dalszego badania):

1. **Jak wymusić bramkę, skoro ochrona gałęzi jest niedostępna?** Opcje: (a) workflow na `pull_request` + `push` do `main` i włączenie Railway „Wait for CI” — blokuje deploy, nie merge; (b) GitHub Pro albo repo publiczne — wtedy dochodzi wymagany status check przy merge'u; (c) sam sygnał na PR bez wymuszania. Opcja (a) pokrywa też bezpośrednie pushe na `main`. Każda zmiana ustawień Railway musi trafić do `context/deployment/web-settings.json`, a `test-plan.md:116` wymaga korekty (przez plan lub `/10x-test-plan --refresh`).
2. **SQLite czy Postgres w CI?** SQLite nie wymaga niczego; usługa Postgres w GitHub Actions zbliża testy do produkcji i nadaje sens `select_for_update()`, ale sama nie doda testów współbieżności.
3. **Zakres pierwszej rundy mutmut:** które pliki (`only_mutate`), czy ręczne mutanty izolacji (M1–M4) zapisać jako stałą listę kontrolną obok mutmut, i jaki próg uznajemy za „zaufany” — mutmut sam progu nie ma.
4. **Które przeżywające mutanty naprawia Faza 1, a które przechodzą do faz 2–4?** M7 i timeouty (stan „w toku”) dotyczą ryzyka #1 (Faza 2); M1–M3 — ryzyka #3 (Faza 3); M4–M5 — ryzyka #4 (Faza 4). `change.md:14` obejmuje wszystkie cztery obszary w tej fazie.

Luki w dowodach (do zamknięcia pierwszym krokiem implementacji):

- mutmut 3.8 z pytest-django w tym repo nie był uruchomiony (nie instalowano zależności w ramach researchu). Niepotwierdzone: import `talkaitive.settings_test` w `mutants/`, wpływ `pythonpath = ["."]`, tworzenie testowej bazy przy wielokrotnym `pytest.main()`, czas przebiegu, mutowanie funkcji z dekoratorami (`@require_GET`, `@property`).
- Bieżący stan przełącznika Railway „Wait for CI” (`checkSuites`) nie był odczytany na żywo; „off” pochodzi z `deploy-plan.md:150` (sprawdzone 2026-09-28).
- Zachowanie Railway przy nieudanym health checku pochodzi z dokumentacji, nie z obserwacji w tym projekcie (19 z 19 deploymentów się udało).
- Wersje akcji GitHub (`setup-uv` 10.3.0 bez tagu `@v10`) pochodzą z raportu pomocnika z API wydań; nie sprawdzone ponownie w głównym kontekście.
