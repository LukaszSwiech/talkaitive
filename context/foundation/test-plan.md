# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-10-15

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the
   team is worried about X, and the failure would surface somewhere in
   <area>" carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Zasada dodatkowa dla tego projektu: cały obecny zestaw testów napisało AI i sprawdzał go ten sam model (wywiad Q4). Oczekiwany wynik w teście bierzemy z wymagań (PRD, ten plan, wywiad), nigdy z kodu, który test sprawdza. Nowy test na ryzyko z §2 uznajemy za wiarygodny dopiero, gdy pada po celowym zepsuciu sprawdzanego zachowania (mutacja).

Hot-spot scope used for likelihood weighting: `accounts/`, `conversations/`, `talkaitive/`, `tests/` (bez `context/`, migracji i `.venv/`; 26 commitów w 30 dniach do 2026-10-13).

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|-------------------------|--------|------------|--------------------------------|
| 1 | Użytkownik czeka bez końca na odpowiedź agenta albo na listę błędów: gdy API dostawcy odpowiada wolno lub z błędem, wynik się nie pojawia, a „Try again” nie przywraca działania | High | High | wywiad Q1, Q2 (incydent: lista błędów nie pojawiła się, ponowienie też nie zadziałało); roadmap Q-07; PRD NFR „Informacja zwrotna podczas czekania”; hot-spot dir `conversations/` (30 zmian plików/30 dni) |
| 2 | Regresja trafia na produkcję niezauważona: testy nie uruchamiają się automatycznie przed wdrożeniem (brak CI, `main` wdraża się sam) albo przechodzą na zepsutym kodzie, bo pisało je AI i weryfikował ten sam model | High | High | wywiad Q4; `tech-stack.md` (CI na GitHub Actions zaplanowane) vs brak katalogu CI w repo; CLAUDE.md (auto-deploy z `main`); hot-spot dir `talkaitive/` (18 zmian plików/30 dni) |
| 3 | Użytkownik B widzi rozmowy, błędy albo pamięć użytkownika A — przez podmianę identyfikatora w adresie, przez dane podrzędne albo przez pamięć zbudowaną z cudzych rozmów | High | Medium | PRD Guardrails + NFR „Prywatność”; wywiad Q1; `lessons.md` (wzorzec luki IDOR przy pobieraniu rekordu po id z URL-a); hot-spot dir `conversations/` (30), `accounts/` (24) |
| 4 | Dzienny limit $1 nie trzyma się: pojedyncza wiadomość lub analiza kosztuje wielokrotnie więcej niż zwykle, a nieudane lub ponawiane płatne wywołania nie wliczają się do wydatku dnia | High | Medium | wywiad Q1; roadmap Q-07 (próba ucięta timeoutem zapisuje koszt 0, „Try again” bez limitu prób — ryzyko zaakceptowane w MVP); PRD Access Control (limit $1, reset o północy Europe/Berlin) |
| 5 | Zmiana promptu albo modelu po cichu pogarsza naukę: korekta zamienia się w wykład, lista błędów jest nietrafna (pomija błędy, zgłasza literówki, myli kategorie), pamięć powtarza pytania | Medium | High | wywiad Q3 (główne optymalizacje będą w promptach i wyborze modelu); PRD Success Criteria — Secondary („lista błędów jest trafna”) + Guardrails („korekta nie przerywa rozmowy”); archive S-03 (zachowanie pamięci sprawdzane tylko ręcznie) |
| 6 | Po usunięciu konta zostają dane użytkownika, np. z modelu danych dodanego w późniejszym slice | High | Low | PRD FR-013 + NFR „Usuwanie danych”; roadmap S-04 (Risk: wracać przy każdym nowym modelu danych); archive S-04 |

High-impact × Low-likelihood: awaria dostawcy modelu albo Railway jako taka to temat dla observability, nie testu. Test pilnuje tylko tego, jak aplikacja zachowuje się w czasie awarii (ryzyko #1).

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | Gdy dostawca wisi, zwraca błąd albo pusty wynik, użytkownik w skończonym czasie widzi komunikat i „Try again”, a ponowienie naprawdę uruchamia nowe wywołanie; znacznik „w toku” wygasa i nie blokuje strony na zawsze | „Atrapa, która od razu rzuca wyjątek, odpowiada prawdziwemu zawieszeniu”; „status 200 po ponowieniu = sukces”; „incydent z wywiadu Q2 jest już pokryty testami” | Ścieżka timeoutów (klient SDK, gunicorn, proxy Railway), cykl życia znacznika „w toku” i stanu „nieudana”, logika odświeżania i auto-wysyłki strony, odtworzenie przyczyny incydentu z Q2 | integracja z atrapą na granicy SDK (wolna / błędna / pusta odpowiedź, symulowany upływ czasu) | tylko happy path; asercja na samym kodzie HTTP; atrapa podmieniająca wewnętrzną logikę zamiast granicy SDK |
| #2 | Celowe zepsucie krytycznej logiki (izolacja danych, budżet, stan analizy, wybór pamięci) sprawia, że testy padają — i dzieje się to automatycznie, zanim zmiana trafi na produkcję, także przy bezpośrednim pushu na `main` | „Zielone testy = testy coś sprawdzają”; „agent sam psuł kod, więc testy są zweryfikowane”; „bramka na PR wystarczy” (większość commitów trafia na `main` bez PR i każdy wdraża produkcję); „zielony health check = aplikacja działa” (health check nie sprawdza logiki); „mutmut sam wygeneruje mutanty izolacji” (nie usuwa wywołań filtrujących po użytkowniku) | Które moduły mają przeżywające mutanty; jak dziś trafia zmiana na `main` (PR vs bezpośredni push); co Railway robi przy nieudanym starcie; czym da się wymusić bramkę na prywatnym repo bez ochrony gałęzi | testy mutacyjne na logice deterministycznej (mutmut + stała ręczna lista mutantów izolacji) + workflow CI na PR i na push do `main`, z deployem czekającym na zielone CI | oczekiwany wynik skopiowany z implementacji (problem wyroczni); gonienie procentu pokrycia zamiast zabitych mutantów; bramka tylko na `pull_request`; uznanie wyniku mutmut za pełny obraz ochrony izolacji |
| #3 | Każdy widok z identyfikatorem w adresie i każda ścieżka do danych podrzędnych daje 404 dla obiektu innego użytkownika; blok pamięci użytkownika A nie zawiera żadnych danych B | „Zalogowany = uprawniony do obiektu”; „wzorzec z lessons.md jest stosowany wszędzie” | Pełna lista widoków i punktów odczytu danych per użytkownik; jak powstaje blok pamięci; czy istniejące testy izolacji pokrywają wszystkie widoki | integracja (klient testowy Django, dwóch użytkowników) | test izolacji tylko dla jednego widoku; sprawdzanie 403 zamiast 404; test na modelu testowym zamiast prawdziwych |
| #4 | Suma kosztów dnia (tury, analizy, nieudane i ponawiane próby) nie przekracza limitu; po wyczerpaniu nie da się rozpocząć nowego płatnego wywołania; reset działa o północy Europe/Berlin, także przy zmianie czasu | „Próba ucięta timeoutem nic nie kosztuje”; „istnieje limit długości wiadomości lub odpowiedzi” (nie wiemy — research ma to sprawdzić; brak limitu to decyzja produktowa, nie test) | Gdzie koszt jest liczony i zapisywany przy błędach; czy istnieje górny limit tokenów na wywołanie; ile płatnych prób może wykonać „Try again” | unit (rachunek kosztu, granice dnia) + integracja (przepływ z błędami) | liczenie oczekiwanego kosztu tym samym wzorem co kod; sztywna data bez strefy czasowej |
| #5 | Na stałym zestawie niemieckich wypowiedzi ze znanymi błędami (gramatyka / słownictwo / szyk) analiza znajduje te błędy, nie zgłasza literówek i trzyma kategorie; odpowiedź agenta wplata poprawną formę bez wykładu; porównanie dwóch wersji promptu lub modelu daje liczbę, nie wrażenie | „Atrapa modelu w obecnych testach mówi coś o jakości”; „sędzia LLM bez wzorcowych odpowiedzi jest wiarygodny” | Kształt wejścia i wyjścia wywołań modelu (tura, analiza); które właściwości są twarde (struktura, kategorie), a które jakościowe (naturalność recastu); koszt jednego przebiegu evalu | eval AI z prawdziwym modelem, uruchamiany ręcznie przy zmianie promptu lub modelu | eval na każdym commicie; asercja na dokładny tekst odpowiedzi; zestaw danych wygenerowany przez ten sam model, który oceniamy |
| #6 | Po usunięciu konta żaden model z relacją do użytkownika nie zostawia wierszy; nowy model danych bez świadomej decyzji wywraca test | „Istniejący strażnik relacji na pewno wykrywa nowy model” | Lista modeli z relacją do użytkownika; jak działa strażnik; co zostaje poza kaskadą (sesje, log admina) | integracja + mutacja strażnika | test kaskady tylko na modelu testowym; strażnik porównujący listę z samym sobą |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|------------|-----------------|---------------|------------|--------|---------------|
| 1 | Suite trust and CI floor | Udowodnić, że zepsucie krytycznej logiki wywraca testy, i że testy uruchamiają się same przed wdrożeniem z `main` | #2 (cross-cutting) | mutation testing + CI gate (pytest, ruff) | complete | testing-suite-trust-and-ci |
| 2 | Waiting-path recovery | Udowodnić, że zawieszenie lub błąd dostawcy kończy się komunikatem i działającym „Try again”, nie wiecznym spinnerem | #1 | integration | change opened | testing-waiting-path-recovery |
| 3 | Privacy and deletion boundaries | Udowodnić, że żaden widok ani blok pamięci nie ujawnia cudzych danych, a usunięcie konta usuwa wszystko | #3, #6 | integration | not started | — |
| 4 | Budget ceiling | Udowodnić, że limit $1/dzień trzyma się także przy błędach, ponowieniach i drogich wywołaniach | #4 | unit + integration | not started | — |
| 5 | AI eval layer | Dać mierzalny wynik jakości korekty i listy błędów przy każdej zmianie promptu lub modelu | #5 | AI-native eval (real model, golden dataset) | not started | — |

Kolejność: faza 1 jest najtańsza i wzmacnia wszystkie kolejne — wynik mutacji pokazuje fazom 2–4, gdzie obecne testy są puste, a CI od razu uruchamia nowe testy. Fazy 2–4 idą wg impact × likelihood. Faza 5 jest ostatnia, bo jest najdroższa w przebiegu i opłaca się dopiero przed pierwszą optymalizacją promptu lub modelu.

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.
Recommendations in this section must be grounded in local manifests/configs
plus the MCP/tools actually exposed in the current session. If a useful docs
or search MCP such as Context7 or Exa.ai is not available, say that instead
of assuming access.

Profil bazy testów (2026-10-13): `meaningful` (na granicy) — pytest skonfigurowany, 10 plików testów (~3300 linii) w `tests/`, każdy slice F-01…S-04 dowiózł własne testy; brak CI.

| Layer | Tool | Version | Notes |
|-------|------|---------|-------|
| unit + integration | pytest + pytest-django (klient testowy Django) | 9.1.1 / 4.14.0 | ustawienia `talkaitive.settings_test`; bez sieci i bez klucza |
| granica LLM | atrapy w repo na granicy OpenAI SDK | openai 3.24.0 | testy klasyczne nigdy nie wołają prawdziwego API |
| lint + format | ruff | 0.16.8 | lokalnie przez post-edit hook; CI (`.github/workflows/ci.yml`, PR i push do `main`) — wired |
| mutation testing | mutmut — checked: 2026-10-15 | 3.8.0 | zainstalowany (dev), `[tool.mutmut]` w `pyproject.toml` na 4 modułach (`accounts/ownership.py`, `conversations/budget.py`, `conversations/memory.py`, `conversations/services.py`); obok niego ręczna lista `scripts/mutation/manual_mutants.py`; oba lokalnie i okresowo, nie w CI (Railway czeka na wszystkie workflow na commicie) |
| e2e | none — see §7 | — | świadomie bez Playwright, dopóki research nie pokaże awarii widocznej tylko w JS |
| AI-native eval | np. DeepEval albo wtyczka pytest z LLM-as-judge — checked: 2026-10-13 | n/a | §3 Phase 5. When NOT to use: logika deterministyczna (koszt, ranking pamięci, scalanie błędów, izolacja) — tam wystarczy zwykły test; nie w CI na każdy PR (koszt, niedeterminizm) |

**Stack grounding tools (current session):**
- Docs: Context7 — dostępny; nie odpytywany, bo wersje pochodzą z `uv.lock`; API (pytest-django, mutmut, OpenAI SDK) sprawdza `/10x-research` w każdej fazie; checked: 2026-10-13
- Search: Exa.ai — sprawdzono aktualność mutmut (3.8.0, tylko pytest) i narzędzi do evali LLM (DeepEval, wtyczki pytest z LLM-as-judge, zasada „twarde niezmienniki → assert, jakość → wynik liczbowy”); checked: 2026-10-13
- Runtime/browser: wbudowana przeglądarka (Claude Browser) — możliwy ręczny smoke ekranu oczekiwania; nie jest bramką; checked: 2026-10-13
- Provider/platform: GitHub przez `gh` CLI (bez MCP) — miejsce na bramkę CI w §3 Phase 1; Linear MCP — tylko lustro roadmapy, bez roli w bramkach; checked: 2026-10-13

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required for §3 Phase <N>" means the gate is enforced once that rollout
phase lands; before that, the gate is `planned`.

| Gate | Where | Required? | Catches |
|------|-------|-----------|---------|
| lint + format (ruff) | local (post-edit hook) + CI (`ci.yml`) | local: wired; CI: wired | błędy składni, styl, proste błędy logiczne |
| unit + integration (pytest) | local + CI (PR i push do `main`) | wired | regresje logiki i przepływów |
| wdrożenie na produkcję tylko po zielonym CI | Railway „Wait for CI” + workflow `ci.yml` na push do `main` i PR | wired | wdrożenie z czerwonymi testami, także przy bezpośrednim pushu na `main` |
| mutation score na logice krytycznej | local, okresowo: `uv run python scripts/mutation/manual_mutants.py` (kod 0) oraz `uv run mutmut run` / `uv run mutmut results` | wired (lokalnie, nie w CI); kryterium: 0 niewyjaśnionych przeżyć — każde przeżycie ma wiersz w `scripts/mutation/accepted_survivors.md` | testy, które przechodzą na zepsutym kodzie |
| AI eval (golden dataset, prawdziwy model) | local, przy zmianie promptu lub modelu | recommended after §3 Phase 5 | spadek jakości korekty i listy błędów |
| pre-prod smoke (health check Railway) | Railway, przy każdym wdrożeniu | wired | crash startu po zmianie ustawień lub zmiennych środowiskowych |

Bramka CI blokuje wdrożenie, nie merge: czerwony commit może trafić na `main`, ale Railway go nie wdroży (deployment `SKIPPED`, produkcja zostaje na poprzedniej wersji; dowód kanarkiem `8ac139b`, 2026-10-15). Ochrona gałęzi na prywatnym repo wymaga GitHub Pro / Team (403, sprawdzone 2026-10-14) — świadomie nie wybrana. Ustawienie Railway i jego kopia: `context/deployment/deploy-plan.md`, `context/deployment/web-settings.json`.

Typecheck (`mypy` + `django-stubs`) jest zaplanowany w CLAUDE.md, ale żadna faza tego planu go nie podpina — dodaj go przez `--refresh`, gdy zostanie wprowadzony.

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase <N>."

### 6.1 Adding a unit test (logika deterministyczna: koszt, granice dnia, ranking pamięci)

- **Location**: `tests/`, plik `test_<obszar>.py` (z konfiguracji pytest).
- **Run locally**: `uv run pytest`. CI (`ci.yml`) uruchamia to samo, razem z `ruff check` i `ruff format --check`, na każdym PR i każdym pushu do `main`.
- **Reference tests**:
  - `tests/test_budget.py::test_is_final_turn_ignores_other_users_newer_agent_turn` — wzorzec metamorficzny. Gdy wymaganie mówi tylko „wynik dla A nie zależy od danych B”, porównaj wynik dla A bez danych B i z nimi, zamiast liczyć oczekiwaną wartość wzorem z kodu.
  - `tests/test_budget.py::test_daily_limit_end_exactly_at_midnight_closes_that_day` — granica dnia: północ Europe/Berlin wpisana ręcznie jako czas UTC, nie liczona przez `day_start()` z kodu.
- **Wzorzec potwierdzenia mutacją**:
  1. Oczekiwana wartość pochodzi z PRD, tego planu albo zapisanej decyzji; źródło stoi w docstringu testu. Nigdy z kodu, który test sprawdza.
  2. Test jest zielony: `uv run pytest`.
  3. Podłóż mutanta, w którego celuje test, i sprawdź, że jest `KILLED`:
     - ręczny: `uv run python scripts/mutation/manual_mutants.py <ID>` (bez argumentu — cała lista; kod 0 = każdy wynik zgodny z oczekiwaniem);
     - mutmut: usuń katalog `mutants/` (mutmut 3 po samych zmianach w testach pokazuje stare wyniki), potem `uv run mutmut run`, `uv run mutmut results` (tylko przeżyte) i `uv run mutmut show <nazwa>` (diff mutanta).
  4. Zepsucie, którego mutmut nie wygeneruje (usunięte `.for_user()` albo filtr, stała modułowa, etykieta w prompcie), dopisz jako nowy mutant do listy w `scripts/mutation/manual_mutants.py` (domyślnie `expected="killed"`).
  5. Przeżycie, którego świadomie nie zabijasz, dostaje wiersz w `scripts/mutation/accepted_survivors.md` (`równoważny` / `brak wymagania` / `przekazany do test-plan Phase N`) i `expected="accepted"` w skrypcie, jeśli to mutant ręczny.

### 6.2 Adding a test for a view with per-user data (cudzy obiekt → 404)

- TBD — see §3 Phase 3 for the cross-user access denial pattern.

### 6.3 Adding a test for provider failure or hang (granica LLM)

- TBD — see §3 Phase 2 for the slow / failing / empty provider response and recovery pattern.

### 6.4 Adding a test for budget accounting (także nieudane i ponawiane wywołania)

- TBD — see §3 Phase 4 for the daily-cap-under-failure pattern.

### 6.5 Adding an AI eval for a prompt or model change

- TBD — see §3 Phase 5 for the golden-dataset mistake-detection and recast-quality pattern.

### 6.6 Per-rollout-phase notes

(Optional. After each phase lands, /10x-implement appends a 2-3 line note
here capturing anything surprising the rollout phase taught.)

- **Phase 1 — Suite trust and CI floor (2026-10-15):** przy zielonych 198 testach przeżywało 12 z 13 celowanych ręcznych mutantów, w tym M1–M4 (usunięte filtry danych w widokach i w budżecie) — zielone testy nie świadczyły o izolacji. mutmut na 4 modułach: 667 mutantów, ok. 24 s lokalnie, przeżycia 65 → 51, każde z wierszem w rejestrze; mutmut kończy się kodem 0 mimo przeżyć, więc sam nie jest bramką. Bramkę CI udowodnił kanarek: `8ac139b` → deploy `SKIPPED`, revert `3d97f46` → `SUCCESS`.

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Obciążenie i wydajność** — aplikacja jest dla max 10 użytkowników, a bez observability nie ma czym analizować wydajności. Re-evaluate, gdy pojawi się observability albo więcej użytkowników (priorytet wzrośnie — autor jest performance engineerem). (Source: Phase 2 interview Q5.)
- **Pełne e2e w przeglądarce (Playwright)** — ryzyka jakości modelu pokrywają evale AI, a stany strony — testy integracyjne. Re-evaluate, jeśli research pokaże awarię widoczną tylko w JS (np. auto-wysyłka lub odświeżanie). (Source: Phase 2 interview Q3.)

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-10-13
- Stack versions last verified: 2026-10-13
- AI-native tool references last verified: 2026-10-13

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
