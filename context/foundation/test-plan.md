# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-10-19

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
| 5 | Zmiana promptu albo modelu po cichu pogarsza naukę: korekta zamienia się w wykład, lista błędów jest nietrafna (pomija błędy, zgłasza literówki, myli kategorie), pamięć powtarza pytania zadane już we wcześniejszych rozmowach w tej samej scenie | Medium | High | wywiad Q3 (główne optymalizacje będą w promptach i wyborze modelu — zamiar; dotąd prompt zmieniany tylko przy budowie funkcji, bez strojenia, więc hot-spot `conversations/` nie jest dowodem dla tego ryzyka); PRD Success Criteria — Secondary („lista błędów jest trafna”) + Guardrails („korekta nie przerywa rozmowy”) + FR-009 („nie powtarza pytań”); archive S-02 (pomiar: zmiana reasoning effort analizy na `high` zgłaszała literówki wbrew regule; ta sama rozmowa dała raz 12, raz 18 pozycji); archive S-03 (pamięć sprawdzona ręcznie, bez zapisanego przebiegu) |
| 6 | Po usunięciu konta zostają dane użytkownika, np. z modelu danych dodanego w późniejszym slice | High | Low | PRD FR-013 + NFR „Usuwanie danych”; roadmap S-04 (Risk: wracać przy każdym nowym modelu danych); archive S-04 |

High-impact × Low-likelihood: awaria dostawcy modelu albo Railway jako taka to temat dla observability, nie testu. Test pilnuje tylko tego, jak aplikacja zachowuje się w czasie awarii (ryzyko #1).

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | Gdy dostawca wisi, zwraca błąd albo pusty wynik, użytkownik w skończonym czasie widzi komunikat i „Try again”, a ponowienie naprawdę uruchamia nowe wywołanie; znacznik „w toku” wygasa i nie blokuje strony na zawsze | „Atrapa, która od razu rzuca wyjątek, odpowiada prawdziwemu zawieszeniu”; „status 200 po ponowieniu = sukces”; „incydent z wywiadu Q2 jest już pokryty testami” | Ścieżka timeoutów (klient SDK, gunicorn, proxy Railway), cykl życia znacznika „w toku” i stanu „nieudana”, logika odświeżania i auto-wysyłki strony, odtworzenie przyczyny incydentu z Q2 | integracja z atrapą na granicy SDK (wolna / błędna / pusta odpowiedź, symulowany upływ czasu) | tylko happy path; asercja na samym kodzie HTTP; atrapa podmieniająca wewnętrzną logikę zamiast granicy SDK |
| #2 | Celowe zepsucie krytycznej logiki (izolacja danych, budżet, stan analizy, wybór pamięci) sprawia, że testy padają — i dzieje się to automatycznie, zanim zmiana trafi na produkcję, także przy bezpośrednim pushu na `main` | „Zielone testy = testy coś sprawdzają”; „agent sam psuł kod, więc testy są zweryfikowane”; „bramka na PR wystarczy” (większość commitów trafia na `main` bez PR i każdy wdraża produkcję); „zielony health check = aplikacja działa” (health check nie sprawdza logiki); „mutmut sam wygeneruje mutanty izolacji” (nie usuwa wywołań filtrujących po użytkowniku) | Które moduły mają przeżywające mutanty; jak dziś trafia zmiana na `main` (PR vs bezpośredni push); co Railway robi przy nieudanym starcie; czym da się wymusić bramkę na prywatnym repo bez ochrony gałęzi | testy mutacyjne na logice deterministycznej (mutmut + stała ręczna lista mutantów izolacji) + workflow CI na PR i na push do `main`, z deployem czekającym na zielone CI | oczekiwany wynik skopiowany z implementacji (problem wyroczni); gonienie procentu pokrycia zamiast zabitych mutantów; bramka tylko na `pull_request`; uznanie wyniku mutmut za pełny obraz ochrony izolacji |
| #3 | Każdy widok z identyfikatorem w adresie i każda ścieżka do danych podrzędnych daje 404 dla obiektu innego użytkownika; blok pamięci użytkownika A nie zawiera żadnych danych B | „Zalogowany = uprawniony do obiektu”; „wzorzec z lessons.md jest stosowany wszędzie” | Pełna lista widoków i punktów odczytu danych per użytkownik; jak powstaje blok pamięci; czy istniejące testy izolacji pokrywają wszystkie widoki | integracja (klient testowy Django, dwóch użytkowników) | test izolacji tylko dla jednego widoku; sprawdzanie 403 zamiast 404; test na modelu testowym zamiast prawdziwych |
| #4 | Suma kosztów dnia (tury, analizy, nieudane i ponawiane próby) nie przekracza limitu; po wyczerpaniu nie da się rozpocząć nowego płatnego wywołania; reset działa o północy Europe/Berlin, także przy zmianie czasu | „Próba ucięta timeoutem nic nie kosztuje”; „istnieje limit długości wiadomości lub odpowiedzi” (nie wiemy — research ma to sprawdzić; brak limitu to decyzja produktowa, nie test) | Gdzie koszt jest liczony i zapisywany przy błędach; czy istnieje górny limit tokenów na wywołanie; ile płatnych prób może wykonać „Try again” | unit (rachunek kosztu, granice dnia) + integracja (przepływ z błędami) | liczenie oczekiwanego kosztu tym samym wzorem co kod; sztywna data bez strefy czasowej |
| #5 | Na stałym zestawie niemieckich wypowiedzi ze znanymi błędami (gramatyka / słownictwo / szyk), z poprawną formą ze źródła niezależnego od ocenianego modelu, analiza znajduje te błędy, nie zgłasza literówek ani niczego z wypowiedzi partnera i przypisuje trafne kategorie (sam zbiór trzech kategorii wymusza już kod); odpowiedź agenta wplata poprawną formę bez wykładu; tura otwierająca z notatkami z wcześniejszych rozmów tej sceny nie zadaje ponownie zapisanych tam pytań; porównanie dwóch wersji promptu, modelu lub reasoning effort daje liczbę z rozrzutem (kilka powtórzeń na przypadek), nie wrażenie | „Atrapa modelu w obecnych testach mówi coś o jakości”; „sędzia LLM bez wzorcowych odpowiedzi jest wiarygodny”; „dzienny limit $1 ogranicza koszt evalu” (eval wołający model wprost omija budżet aplikacji — potrzebny własny limit wydatku); „jeden przebieg wystarczy do porównania” (zmierzona zmienność wyniku tej samej rozmowy) | Kształt wejścia i wyjścia wywołań modelu (tura, analiza); które właściwości są twarde (struktura, kategorie), a które jakościowe (naturalność recastu); zapis pytań partnera do pamięci i ich użycie w kolejnej rozmowie; koszt jednego przebiegu evalu | lokalny skrypt z prawdziwym modelem poza zestawem testów uruchamianym przez CI, ręcznie przy zmianie promptu, modelu lub reasoning effort: ocena deterministyczna względem wzorca + lektura przypadków, które zmieniły wynik; sędzia LLM tylko opcjonalnie, z wzorcem i po kalibracji na ocenach człowieka; kod oceniania (dopasowanie, metryki, porównanie) w zwykłych testach w CI | eval na każdym commicie; asercja na dokładny tekst odpowiedzi (dopasowanie do wzorca musi tolerować inne, poprawne sformułowanie); zestaw danych albo wzorzec wygenerowany przez oceniany model lub wzięty z wyniku aplikacji; porównanie wersji na jednym przebiegu bez powtórzeń; sędzia LLM bez wzorca jako jedyna miara |
| #6 | Po usunięciu konta żaden model z relacją do użytkownika nie zostawia wierszy; nowy model danych bez świadomej decyzji wywraca test | „Istniejący strażnik relacji na pewno wykrywa nowy model” | Lista modeli z relacją do użytkownika; jak działa strażnik; co zostaje poza kaskadą (sesje, log admina) | integracja + mutacja strażnika | test kaskady tylko na modelu testowym; strażnik porównujący listę z samym sobą |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|------------|-----------------|---------------|------------|--------|---------------|
| 1 | Suite trust and CI floor | Udowodnić, że zepsucie krytycznej logiki wywraca testy, i że testy uruchamiają się same przed wdrożeniem z `main` | #2 (cross-cutting) | mutation testing + CI gate (pytest, ruff) | complete | testing-suite-trust-and-ci |
| 2 | Waiting-path recovery | Udowodnić, że zawieszenie lub błąd dostawcy kończy się komunikatem i działającym „Try again”, nie wiecznym spinnerem | #1 | integration | complete | testing-waiting-path-recovery |
| 3 | Privacy and deletion boundaries | Udowodnić, że żaden widok ani blok pamięci nie ujawnia cudzych danych, a usunięcie konta usuwa wszystko | #3, #6 | integration | complete | testing-privacy-and-deletion-boundaries |
| 4 | Budget ceiling | Udowodnić, że limit $1/dzień trzyma się także przy błędach, ponowieniach i drogich wywołaniach | #4 | unit + integration | complete | testing-budget-ceiling |
| 5 | AI eval layer | Dać mierzalny wynik jakości korekty i listy błędów przy każdej zmianie promptu lub modelu | #5 | AI-native eval (real model, golden dataset) | complete | testing-ai-eval-layer |

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
| e2e | Playwright Test (`@playwright/test`, Node) + `playwright-cli` do eksploracji — checked: 2026-10-16 | 1.64.1 / 0.1.22 | obowiązkowa warstwa od 2026-10-16 (§7); konfiguracja, seed i komendy: `context/foundation/test-stack.md` (`## E2E`); na razie tylko lokalnie, nie w CI |
| AI-native eval | własny skrypt `scripts/eval/` (`run_eval.py` `run` / `compare`, oceniacz `scoring.py`, licznik kosztu `cost.py`, zestaw `golden.py`), bez biblioteki — checked: 2026-10-19 | n/a | prawdziwy model przez `conversations.llm`, ocena deterministyczna względem wzorca, bez sędziego LLM; zestaw wzorcowy z MERLIN 1.1 (http://hdl.handle.net/20.500.12124/6, CC BY-SA 4.0); kod oceniania w zwykłych testach w CI; cookbook §6.5. DeepEval odradzany: rejestruje wtyczkę `pytest11`, która ładowałaby się do każdego `uv run pytest`, także w CI, i ma domyślnie włączoną telemetrię. When NOT to use: logika deterministyczna (koszt, ranking pamięci, scalanie błędów, izolacja) — tam wystarczy zwykły test; nie w CI na każdy PR (koszt, niedeterminizm) |
| AI code review | własny skrypt `scripts/review/` + workflow `.github/workflows/ai-review.yml` — checked: 2026-10-31 | n/a | świadomy wyjątek od zasady „nie w CI na każdy PR” z wiersza wyżej: działa na PR do `main` jako wymagany check `review`; merge blokują cztery kryteria (`data_isolation`, `no_secrets`, `correctness`, `migrations`) z oceną na progu lub poniżej albo ucięty diff; limit diffu i tokenów, jedno wywołanie modelu; jeden przebieg kosztował ok. 0,05 USD (PR #28) |
| AI review model eval | promptfoo (CLI, Node, przypięty; globalny albo `npx -y promptfoo@0.125.1`) + własny runner i provider w Pythonie `scripts/review/eval/` — checked: 2026-11-02 | 0.125.1 (Node ≥ 22.22.0) | recenzent z CI na 4 modelach (OpenAI wprost, Claude i Gemini przez OpenRouter z `data_collection: deny` i `zdr`), 16 przypadków ze znanym werdyktem, reguła wyboru ustalona przed przebiegiem; zawsze `--no-cache --no-share`, telemetria wyłączona; własna księga kosztu poza repo; darmowa bramka odcisku promptu i schematu w CI; cookbook §6.7. Świadomy lokalny wyjątek od zasady „model woła tylko `conversations/llm.py`” (propozycja do CLAUDE.md). When NOT to use: jakość nauki w aplikacji (to §6.5); nie w CI (koszt, klucze, Node) |

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
| AI eval (golden dataset, prawdziwy model) | local, ręcznie przed zmianą i po zmianie promptu tury, promptu analizy, tekstu bloku pamięci, `LLM_MODEL` albo reasoning effort: `scripts/eval/run_eval.py` `run` / `compare` (§6.5) | wired (lokalnie, nie w CI); kod oceniania i spójność zestawu sprawdza `uv run pytest` w CI | spadek jakości korekty, listy błędów i pamięci (pytania powtórzone w scenie) |
| AI review model eval (promptfoo, prawdziwe modele) | local, ręcznie po zmianie promptu, schematu, stałych wywołania albo reguły werdyktu recenzenta, modelu recenzenta lub po aktualizacji `openai` / `pydantic`: `python -m scripts.review.eval.run` (§6.7); przypomina o nim test odcisku w `tests/test_review_eval.py` w CI | przebieg: wired (lokalnie, nie w CI); test odcisku i kod evalu: `uv run pytest` w CI | zmiana recenzenta albo jego modelu bez pomiaru: model przepuszczający PR z blokerem (fałszywe przejście) albo blokujący dobre PR-y |
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

- **When to use**: nowy widok z id w adresie, nowa trasa do danych podrzędnych, zmiana w budowaniu pamięci albo nowy model danych (także bez klucza obcego do `User`).
- **Kroki**:
  1. **Nowa trasa z id** → wpis w `ID_ROUTES` (`tests/test_conversation_views.py`): nazwa trasy → (metoda HTTP, model, którego pk jest w adresie). Wpis sam dostaje test „inny użytkownik → 404, bez zmiany stanu, bez wywołań modelu”. Strażnik routera wywraca test, gdy trasa z parametrem w adresie (poza `admin:`) nie ma wpisu; trasa po pk innego modelu niż `Conversation` wymaga dopisania budowania obiektu tego modelu dla innego użytkownika. Widok pobiera obiekt przez `get_object_or_404(Model.objects.for_user(request.user), pk=pk)` (`lessons.md`).
  2. **Zmiana pamięci** → test metamorficzny: blok pamięci użytkownika A jest niepusty i identyczny z danymi B i bez nich. Dane B muszą pasować do każdego filtra poza `for_user` (status, `analyzed_at`, język, temat), inaczej test przejdzie ze złego powodu.
  3. **Nowy model** → decyzja w `MODEL_DECISIONS` (`tests/test_account_deletion.py`): `CASCADE` (dane użytkownika, kasowane z kontem) albo tekst uzasadnienia, dlaczego to nie są dane użytkownika. Model kasowany z kontem dostaje fabrykę w `FACTORIES` — test usunięcia sprawdzi wtedy sam, że żaden jego wiersz nie zostaje. Dane spoza kaskady (sesje, `LogEntry`) sprząta odbiornik `pre_delete` na `User` (`accounts/services.py`), więc działa to także przy usuwaniu w `/admin/`.
- **Zasada strażnika**: ręcznie wpisany literał (`ID_ROUTES`, `MODEL_DECISIONS`, `FACTORIES`) porównujemy z rejestrem Django (router URL, `apps.get_models()`, domknięcie kaskady), nigdy z listą wyliczoną z tego samego źródła co parametry testu.
- **Reference tests**:
  - `tests/test_conversation_views.py::test_every_url_with_an_id_is_covered_by_the_404_test` i `::test_other_user_gets_404_on_every_conversation_url` — strażnik routera i test 404 sterowany `ID_ROUTES`.
  - `tests/test_conversation_views.py::test_memory_never_contains_another_users_data` — metamorficzny test izolacji pamięci.
  - `tests/test_account_deletion.py::test_every_app_model_has_a_deletion_decision`, `::test_every_user_data_model_has_a_factory`, `::test_deleting_account_leaves_no_row_of_that_user_in_any_model` — rejestr modeli, fabryki, usunięcie przez stronę.
  - `tests/test_account_deletion.py::test_deleting_user_in_admin_removes_sessions_and_log_entries_about_them` — usunięcie w `/admin/` (pojedyncze i akcja zbiorcza).
- **Potwierdzenie mutacją**: jak w §6.1. `accounts/` nie jest w `[tool.mutmut]`, więc ręczne mutanty (przykłady: M16 pamięć bez `for_user`, M18 nowa trasa bez wpisu, M23 nowy model bez decyzji, M24 niepodłączony odbiornik `pre_delete`).

### 6.3 Adding a test for provider failure or hang (granica LLM)

- **Location**: atrapa dostawcy `tests/fake_provider.py` (`FakeProvider`), fixture `fake_provider` w `tests/conftest.py`; testy całej ścieżki czekania (widok → serwis → `llm` → strona) w `tests/test_waiting_path.py`; zachowanie samego SDK w `tests/test_llm.py`.
- **Run locally**: `uv run pytest` (bez klucza i bez sieci; CI uruchamia to samo).
- **Którą atrapę wybrać**:
  - **`fake_provider` (atrapa transportu)** — gdy test dotyczy zachowania SDK (ponowienia, `Retry-After`, timeout żądania) albo całej ścieżki aż do strony. Prawdziwy klient `openai.OpenAI` działa jak na produkcji; fixture podmienia tylko `conversations.llm.OpenAI` na klienta z `httpx2.MockTransport` (ustawienia nadal idą z Django settings) i nagrywa `time.sleep` zamiast spać.
    - Scenariusz układasz po kolei, jedno wywołanie na żądanie: `hang(times=…)`, `fail(status, retry_after=…)`, `reply(text, end_conversation=…)`, `analysis(mistakes, …)`.
    - Sprawdzasz: `requests` (ile żądań poszło), `read_timeouts` (limit odczytu każdego żądania), `sleeps` (ile SDK chciało czekać).
    - Żądanie bez zaplanowanego kroku wywraca test — liczba żądań jest częścią scenariusza.
    - `hang` rzuca `ReadTimeout` od razu. Dlatego sprawdzaj też `read_timeouts`: dopiero on dowodzi, że prawdziwe zawieszenie zostałoby ucięte.
  - **`FakeGenerateTurn` / `FakeAnalyzeMistakes`** (`tests/test_conversation_views.py`, fixture `fake_llm` i `fake_analysis`) — gdy liczy się kolejność zdarzeń dwóch żądań (wyścig znaczników). Wynik w kolejce może być funkcją: zmienia znacznik w bazie w połowie wywołania (np. „B przejmuje turę”), potem zwraca wynik albo rzuca `LLMError`.
- **Jak symulować czas**: nigdy przez czekanie. Albo przesuń znacznik w bazie (`agent_turn_started_at` / `analysis_started_at` = `timezone.now() - timedelta(seconds=N)`) i otwórz stronę, albo podaj `now` wprost do `services.agent_turn_in_progress`, `services.analysis_in_progress`, `services.analysis_failed`. Oczekiwane czasy (np. 210 s znacznika tury, 180 s analizy, 300 s proxy Railway) wpisuj ręcznie jako stałe w teście, z komentarzem o źródle (decyzja, dokumentacja SDK, PRD) — nigdy nie licz ich funkcjami z `services.py`.
- **Brzeg znacznika „w toku”**: testuj `N − 1 µs` (w toku) i, gdzie to możliwe, dokładnie `N` (wygasł). Wyjątek: znacznik tury (`tests/test_conversation_views.py::test_turn_marker_lives_as_long_as_the_sdk_can_wait_plus_a_margin`) sprawdza `210 s + 1 µs`, bo dokładne 210 s zabiłoby zaakceptowany mutant równoważny M8 (`<` → `<=`, `scripts/mutation/accepted_survivors.md`) i wywróciło `manual_mutants.py`. Znacznik analizy nie ma takiego mutanta, więc jego test sprawdza dokładnie 180 s. Leży w `tests/test_waiting_path.py`, nie w `tests/test_analysis.py`, bo tamten moduł nadpisuje timeout analizy dla wszystkich swoich testów.
- **Sukces = stan bazy + liczba żądań + treść strony, nigdy sam kod HTTP.** Sprawdź zapisane wiadomości i znaczniki (`agent_turn_started_at`, `analysis_failed_at`, `awaiting_agent_reply`), przyrost `len(fake_provider.requests)` (np. „Try again” = dokładnie jedno nowe żądanie) i tekst strony („Try again”, komunikat błędu, brak `http-equiv="refresh"`, gdy strona nie może utknąć w „Agent is typing”).
- **Reference tests**:
  - `tests/test_waiting_path.py::test_hung_provider_shows_try_again_and_the_retry_brings_the_reply` — zawieszenie obu prób tury, komunikat, „Try again”, jedno nowe żądanie i odpowiedź na stronie.
  - `tests/test_waiting_path.py::test_turn_after_a_503_with_retry_after_saves_and_shows_the_reply` — `fail(503, retry_after=56)`, potem odpowiedź; `sleeps == [56]`.
  - `tests/test_waiting_path.py::test_hung_analysis_shows_try_again_and_the_retry_brings_the_list` — to samo dla analizy po rozmowie.
  - `tests/test_waiting_path.py::test_longest_model_wait_fits_in_the_platforms_request_limit` — niezmiennik ustawień: najdłuższe czekanie SDK < limit proxy Railway.
  - `tests/test_llm.py::test_turn_retries_after_503_with_retry_after_and_returns_the_reply` i `::test_turn_does_not_retry_when_retry_after_exceeds_120_s` — przypięte zachowanie SDK, na którym opierają się czasy znaczników.
  - `tests/test_conversation_views.py::test_turn_marker_lives_as_long_as_the_sdk_can_wait_plus_a_margin` — granica znacznika z parametrem `now`; `::test_expired_turn_marker_offers_try_again_and_the_retry_calls_the_model` — znacznik przesunięty w bazie; `::test_failed_late_request_leaves_the_newer_requests_marker_alone` — wyścig dwóch żądań przez `FakeGenerateTurn`.
- **Potwierdzenie mutacją**: jak w §6.1. `conversations/llm.py` nie jest w `[tool.mutmut]`, więc nowe zachowanie w nim potwierdzasz ręcznym mutantem w `scripts/mutation/manual_mutants.py` (§6.1 krok 4; przykład: M14, M15 dla pustej odpowiedzi).

### 6.4 Adding a test for budget accounting (także nieudane i ponawiane wywołania)

- **Location**: `tests/test_budget.py` — unit (rachunek kosztu, granice dnia, `spent_today`, `next_turn_estimate`, `limit_reached`); `tests/test_budget_ceiling.py` — przepływy od serwisu lub widoku do sumy dnia (ścieżki kosztu, scenariusze dachu); `tests/test_llm.py` — co `LLMError` mówi o koszcie na granicy SDK.
- **Zasada**: każda ścieżka wywołania modelu kończy się zapisem kosztu: `Message.cost_usd` (udana tura), `analysis_cost_usd` (udana analiza) albo wpis `LLMCharge` (timeout, odpowiedź bez wyniku, spóźniony wynik, nieudany zapis analizy). Nowa ścieżka wywołania bez takiego zapisu to luka — test sprawdza przyrost `spent_today`, listę wpisów księgi (`kind`, `reason`, kwota) i liczbę żądań. Szybka odmowa dostawcy (429 / 5xx), błąd połączenia i brak klucza dają 0, bez wpisu.
- **Kwoty**: ręcznie wpisany literał z rachunkiem w komentarzu, z cennika przypiętego w fixture (`LLM_PRICES_USD_PER_MTOK`, `DAILY_BUDGET_USD`, szacunki 0,03 / 0,07), np. `# 200 * 2.50 + 1000 * 0.25 + 40 * 15.00 = 1350 per 1M = 0.00135`. Nigdy `turn_cost` ani `next_turn_estimate`. Tokeny ustawiasz parametrem `usage=(input, cached, output)` w `fake_provider.reply(...)` / `.analysis(...)` albo polami `TurnResult` / `AnalysisResult` w atrapach nad SDK (`tests/fakes.py`).
- **Jak symulować dzień** — dwa zegary:
  - `Message.created_at` to zegar rzeczywisty (`auto_now_add`). Test, który przechodzi przez `send_message` / `run_agent_turn` albo widok, używa `now = timezone.now()`, a wcześniejszy wydatek sieje na tę samą chwilę (helper `spent_earlier_today`).
  - Księga (`charged_at`) i analiza (`analyzed_at`) są datowane przez `now` z parametru. Granicę dnia (północ, zmiana czasu) testujesz literałami UTC, wpisanymi ręcznie z komentarzem o strefie (np. 25 października 2026: dzień zaczyna się 24.10 22:00 UTC, następna północ to 25.10 23:00 UTC), sterując tylko księgą, analizą i wierszami zasianymi helperami (`add_charge`, `add_message` z `.update(created_at=…)`). Nigdy `day_start()` / `next_reset()` z kodu.
- **Dach**: „po osiągnięciu limitu do dostawcy nie trafia żadne żądanie” sprawdzasz przez `len(fake_provider.requests)` (atrapa transportu wywraca test przy żądaniu bez zaplanowanego kroku) i stan bazy: wiadomość niezapisana, `end_reason=DAILY_LIMIT`, `ended_at` = chwila odmowy. Brzeg: suma 0,999999 → wywołanie rusza, dokładnie 1,00 → odmowa. Odmowa ma widoczny powód (PRD „Odmowa akcji”): przypadek w `tests/test_conversation_views.py::test_refused_action_shows_a_reason` sprawdza niepusty powód, nie brzmienie.
- **Bez E2E** (cost × signal): komunikat o limicie i godzina resetu to HTML z serwera, który klient testowy widzi tak samo; serwer E2E działa bez modelu (`OPENAI_API_KEY: ''`), więc ścieżki pieniędzy są dla przeglądarki nieosiągalne, a stan „limit wyczerpany” wymagałby osobnego użytkownika, `storageState` i danych wygasających o północy Berlina.
- **Reference tests**:
  - `tests/test_budget_ceiling.py::test_turn_that_times_out_before_any_agent_turn_costs_the_fixed_estimate`, `::test_blank_reply_is_paid_at_its_real_usage`, `::test_turn_refused_by_the_provider_costs_nothing`, `::test_analysis_whose_save_fails_still_counts_its_cost` — ścieżki kosztu: przyrost sumy, wpis księgi, liczba żądań.
  - `tests/test_budget_ceiling.py::test_one_expensive_call_crosses_the_limit_and_the_next_message_is_refused` — jedno drogie wywołanie przekracza limit, następna wiadomość przez widok jest odmówiona bez żądania, strona pokazuje godzinę resetu.
  - `tests/test_budget_ceiling.py::test_turn_retries_stop_once_the_limit_is_reached` — ponowienia z timeoutem liczone szacunkiem aż do dachu; łącznie dokładnie 4 żądania.
  - `tests/test_budget_ceiling.py::test_analysis_retry_waits_for_the_reset_across_the_autumn_midnight` — pierwsza analiza rusza mimo limitu (S-02), ponowienie czeka na północ w dniu 25 h.
  - `tests/test_budget.py::test_spent_today_on_the_day_clocks_go_forward` i `::test_spent_today_on_the_day_clocks_go_back` — suma dnia po obu stronach północy w dniach zmiany czasu, chwile UTC wpisane ręcznie.
  - `tests/test_budget.py::test_limit_reached_false_just_below_the_budget` i `::test_limit_reached_true_at_exactly_the_budget` — brzeg dachu.
- **Potwierdzenie mutacją**: jak w §6.1. `conversations/llm.py` nie jest w `[tool.mutmut]`, a usunięte sprawdzenie lub filtr mutmut nie wygeneruje — przykłady ręcznych mutantów: M25 / M26 (timeout bez kosztu), M27 (pusta odpowiedź bez `usage`), M28 / M29 (księga poza sumą / bez `for_user`), M30 (spóźniona tura bez wpisu), M31–M34 (usunięty dach w `send_message`, `run_agent_turn`, odmowa bez zakończenia rozmowy, ponowienie analizy bez dachu).

### 6.5 Adding an AI eval for a prompt or model change

- **Location**: `scripts/eval/` — `run_eval.py` (skrypt `run` / `compare`, docstring z użyciem i kodami wyjścia), `golden.py` (zestaw wzorcowy z atrybucją MERLIN), `scoring.py` (dopasowanie, twarde reguły, metryki, porównanie parami), `cost.py` (licznik kosztu z limitem); wyniki w `scripts/eval/results/`. Pliki nie pasują do `test_*.py` i leżą poza `testpaths`, więc przebieg na prawdziwym modelu nigdy nie startuje z `uv run pytest` ani z CI. Sam kod modułów (oceniacz, licznik, zestaw, skrypt z atrapami) sprawdzają w CI testy `tests/test_eval_*.py`; mutmut kopiuje `scripts` (`also_copy`), ale go nie mutuje.
- **Kiedy uruchamiać** — tylko ręcznie, lokalnie, nigdy w CI, w hooku ani cyklicznie; przed zmianą i po zmianie jednego z pięciu elementów:
  1. instrukcji tury (`llm._INSTRUCTIONS`),
  2. instrukcji analizy (`llm._ANALYSIS_INSTRUCTIONS`),
  3. tekstu bloku pamięci (`llm.format_memory`),
  4. `LLM_MODEL`,
  5. reasoning effort tury albo analizy (`LLM_REASONING_EFFORT`, `LLM_ANALYSIS_REASONING_EFFORT`).
  Zmiana modelu u dostawcy pod tą samą nazwą zostaje niewykryta — świadome ograniczenie.
- **Koszt i czas**: eval woła `conversations.llm` wprost, bez bazy, więc omija dzienny limit aplikacji; pilnuje go własny limit `--max-usd` (domyślnie 5 USD); wywołanie droższe od swojego szacunku może go przekroczyć o tę nadwyżkę. Przed startem skrypt drukuje liczbę wywołań i szacunek z ustawień (średnie z pomiaru, nie maksima: 0,03 USD tura, 0,07 USD analiza; pełny przebieg K=3: 4,84 USD). Plan zakładał do ok. 3,4 USD i 20–35 min; przebieg bazowy kosztował 0,83 USD i trwał ok. 12,5 min (analiza 555 s, tura 112 s, pamięć 28 s, długa analiza 46 s). Taniej: `--suite <seria>` i `--repeats 1`. Eval używa tego samego konta OpenAI co produkcja — wyczerpane środki zatrzymują też aplikację (§6.6).
- **Run**:
  - pełny przebieg: `uv run --env-file .env python scripts/eval/run_eval.py run [--suite analysis,turn,memory,latency] [--repeats 3] [--max-usd 5] [--out PATH]`; serie: `analysis` (12 rozmów), `turn` (20 przypadków), `memory` (5 scen), `latency` (jedna rozmowa 40 wiadomości, raz na przebieg, tylko czas i koszt względem timeoutu analizy 150 s i limitu proxy Railway 300 s);
  - porównanie: `uv run python scripts/eval/run_eval.py compare A.json B.json` (A = przed zmianą, B = po; Δ = B − A);
  - bez prawdziwego `OPENAI_API_KEY` (pusty albo `"test-key"` z `settings_test`) skrypt kończy się kodem 2 przed jakimkolwiek wywołaniem.
- **Tryb pracy przy strojeniu**: tanie próby tylko na zmienianej serii, np. `run --suite turn --repeats 1 --max-usd 1 --out <katalog poza repo>/proba.json`, potem `compare <plik bazowy> <próba>`. Przed merge pełny przebieg K=3 na czystym drzewie (commit ze zmianą) i `compare` z plikiem bazowym. Przy K=1 wartość przypadku to jedno wywołanie, więc szum jest większy, a przedział szerszy.
- **Jak czytać wynik**:
  - **Kody wyjścia `run`**: 0 — przebieg pełny, 0 naruszeń twardych reguł i 0 nieudanych wywołań; 1 — pełny, ale z naruszeniami albo nieudanymi wywołaniami (wypisane z id przypadku i numerem powtórzenia); 2 — konfiguracja, brak prawdziwego klucza albo limit kosztu (wynik częściowy zapisany z `"complete": false`). `compare`: 0 — porównanie wydrukowane, 2 — brak pliku albo plik nie jest wynikiem skryptu.
  - **Twarde naruszenia** (lista, nie średnia): A1 pozycja spoza wiadomości ucznia albo numer spoza zakresu, A2 zmienione `sentence`, A3 zgłoszona literówka, A4 pozycja w poprawnej wiadomości, A5 ponad 5 faktów albo 8 notatek; T1 tura kończy rozmowę. Każde naruszenie czytaj w surowym wyjściu modelu (`calls` w pliku JSON).
  - **Metryki** (wyższa lepsza, poza `extras`): analiza `recall`, `category_accuracy`, `extras` (niedopasowane pozycje na rozmowę, niższa lepsza), `typo_free`, `notes_questions`; tura `recast`, `lecture_free`, `one_question`; pamięć `no_repeat`. Wartość przypadku = średnia z K powtórzeń, wartość przebiegu = średnia przypadków.
  - **`compare`**: dla każdej metryki `n` (przypadki obecne w obu przebiegach z wartością — nieudane wywołania wypadają), A, B, średnia różnica sparowana per przypadek z 95% przedziałem (`Δ ± 1,96·SE`) i werdykt `difference` (przedział nie obejmuje zera) albo `within noise` (także przy `n < 2`). Ostrzeżenia: ten sam model i te same skróty promptów (różnica to szum), różne zbiory przypadków (np. po dodaniu przypadku). Na końcu „Changed cases (B - A)” malejąco po `|Δ|` — te przypadki czytasz w `calls` obu plików: tu oceniasz naturalność recastu i fałszywe alarmy znaczników, bo eval nie ma sędziego LLM.
- **Plik bazowy**: najnowszy pełny przebieg K=3 na czystym drzewie w `scripts/eval/results/` (obecnie `2026-10-19-gpt-5.4-56e6109.json`). Po przyjętej zmianie promptu lub modelu (albo po zmianie zestawu) commitujesz nowy pełny przebieg z commita ze zmianą jako nowy plik bazowy; kolejne zmiany porównujesz z nim. Plików `-dirty` (zmienione śledzone pliki) i prób z `--out` nie commitujesz.
- **Jak dodać przypadek** (`golden.py`):
  1. Zdanie ucznia dosłownie z MERLIN 1.1 (niemiecki, ocena B1/B2), `source` = Author ID tekstu; poprawna forma z target hypothesis 1 — nigdy z modelu ani z wyniku aplikacji.
  2. Każdą różnicę tekst ucznia ↔ wersja poprawiona klasyfikujesz: jednoznaczny błąd reguły → `GoldMistake` (kategoria wg reguły, `rule` nazwany, druga kategoria tylko przy regule granicznej); pisownia, wielka litera, pisownia złożeń bez zmiany sensu → `Typo` (nie wolno zgłosić); reszta → `Neutral` (ani plus, ani minus). Wiadomości partnera i notatki pamięci piszesz sam, poprawnie, bez tekstu korpusu.
  3. Przypadek tury ma dokładnie jeden wyraźny błąd w ostatniej wiadomości ucznia i scenę z `conversations/topics.py`.
  4. `uv run pytest tests/test_eval_golden.py` — test spójności (id, numery, klucze jako całe słowa, brak nakładania kluczy, kategorie, minimalna liczba wzorców na kategorię, licencja w docstringu).
  5. Nowy przypadek zmienia zbiór przypadków — zrób nowy plik bazowy, zanim porównasz zmianę promptu.
- **Wzorzec celowego zepsucia promptu** (dowód, że eval wykrywa pogorszenie, jak mutant dla testu klasycznego): w drzewie roboczym odwróć regułę w `conversations/llm.py` (np. „report typos and punctuation as mistakes” w obu promptach, tura ma jawnie wyjaśniać regułę), `run --suite analysis,turn --repeats 1 --max-usd 1 --out <poza repo>/broken.json`, `compare <plik bazowy> <broken.json>` — oczekiwany spadek `typo_free` / `lecture_free` z werdyktem `difference` — potem `git checkout conversations/llm.py`. Plik nie trafia do repo.
- **Kod oceniania** (dopasowanie, reguły, metryki, porównanie, licznik kosztu) ma zwykłe testy w CI. Oczekiwane liczby są wpisane ręcznie z rachunkiem w komentarzu, nigdy liczone funkcjami oceniacza. Nowe zachowanie oceniacza potwierdzasz ręcznym mutantem (§6.1 krok 4; `scripts/eval/` nie jest w `[tool.mutmut]`; M35–M49).
- **Reference tests**:
  - `tests/test_eval_scoring.py::test_longer_wrong_with_gap_matches_the_gold_keywords`, `::test_two_items_for_one_gold_mistake_match_once_and_the_other_is_extra`, `::test_reported_typo_is_a3_and_not_an_extra`, `::test_turn_with_a_lecture_marker`, `::test_marker_inside_another_word_is_not_a_hit` — dopasowanie tolerancyjne jeden-do-jednego, twarde reguły, znaczniki wykładu po granicy słowa.
  - `tests/test_eval_scoring.py::test_compare_pairs_cases_and_gives_the_interval_and_verdict`, `::test_call_may_start_when_it_reaches_the_cap_exactly`, `::test_call_may_not_start_when_it_would_pass_the_cap` — porównanie parami z przedziałem i brzeg limitu kosztu.
  - `tests/test_eval_golden.py::test_analysis_case_is_consistent`, `::test_every_category_has_enough_gold_mistakes`, `::test_docstring_has_the_licence_and_the_merlin_handle` — spójność zestawu i licencja.
  - `tests/test_eval_runner.py::test_run_under_test_settings_stops_before_any_call`, `::test_cost_cap_stops_the_run_before_it_is_passed`, `::test_compare_prints_the_paired_difference` — skrypt bez klucza nie woła modelu, limit zatrzymuje przebieg, `compare` na dwóch plikach.

### 6.6 Per-rollout-phase notes

(Optional. After each phase lands, /10x-implement appends a 2-3 line note
here capturing anything surprising the rollout phase taught.)

- **Phase 1 — Suite trust and CI floor (2026-10-15):** przy zielonych 198 testach przeżywało 12 z 13 celowanych ręcznych mutantów, w tym M1–M4 (usunięte filtry danych w widokach i w budżecie) — zielone testy nie świadczyły o izolacji. mutmut na 4 modułach: 667 mutantów, ok. 24 s lokalnie, przeżycia 65 → 51, każde z wierszem w rejestrze; mutmut kończy się kodem 0 mimo przeżyć, więc sam nie jest bramką. Bramkę CI udowodnił kanarek: `8ac139b` → deploy `SKIPPED`, revert `3d97f46` → `SUCCESS`.
- **Phase 2 — Waiting-path recovery (2026-10-15):** atrapa na transporcie SDK pokazała to, czego atrapy nad SDK nie widziały: `Retry-After` od OpenAI (do 120 s) wydłużał czekanie SDK poza ważność znacznika tury (90 s → teraz 210 s = 30 s × 2 próby + 120 s + 30 s marginesu), a pusta odpowiedź agenta zapisywała się jako sukces (teraz `LLMError` → „Try again”, ręczne mutanty M14, M15). Wygasły znacznik analizy (180 s) pokazuje teraz „Try again” zamiast samemu wysyłać nową płatną analizę. Pomiaru realnego czasu analizy względem limitu 300 s proxy Railway nie da się zrobić atrapą — przechodzi do §3 Phase 5 (eval z prawdziwym modelem). Do przeniesienia przez `/10x-test-plan --refresh` (tu bez zmian w §2 / §4):
  - §2 ryzyko #1, Source: incydent Q2 naprawiony ustawieniami 2026-10-07 (`dfe3e7d`); likelihood „High” opiera się częściowo na naprawionym zdarzeniu.
  - §2 Risk Response Guidance #1, Context: dopisać `retry-after` SDK (do 120 s) do ścieżki timeoutów; „pusty wynik” rozbić na `output_parsed is None` (obsłużone wcześniej) i `reply=""` (obsłużone w tej fazie).
  - §4 Stack, „granica LLM”: atrapa jest teraz na transporcie SDK (`httpx2.MockTransport`, `tests/fake_provider.py`), nie tylko na kliencie `OpenAI` / nad SDK.
- **Phase 3 — Privacy and deletion boundaries (2026-10-16):** dzisiejsze testy izolacji i usuwania były poprawne, ale opierały się na ręcznych listach bez porównania z rejestrem Django; teraz pilnują ich strażniki (`ID_ROUTES` vs router, `MODEL_DECISIONS` / `FACTORIES` vs `apps.get_models()` i domknięcie kaskady), a stary test pamięci przechodził też przy pustej pamięci (teraz metamorficzny). Research znalazł lukę w kodzie: usunięcie użytkownika w `/admin/` zostawiało jego sesje i `LogEntry` z e-mailem — sprzątanie przeniesione do odbiornika `pre_delete` na `User` (`375e2e4`). Ręczne mutanty 26/26 zgodne (nowe M16–M24, M17 równoważny); mutmut: 683 mutanty, 46 przeżyć, każde w rejestrze. Do przeniesienia przez `/10x-test-plan --refresh` (tu bez zmian w §2):
  - §2 ryzyko #6, Source: dopisać ścieżkę `/admin/` (naprawiona w tej fazie) i to, że strażnik nie widzi nowego pola tekstowego z e-mailem w **istniejącym** modelu (świadome ograniczenie).
  - §2 Risk Response Guidance #3/#6: wskazać strażniki z §6.2 jako miejsce decyzji dla nowej trasy i nowego modelu.
- **Phase 4 — Budget ceiling (2026-10-16):** research obalił założenie fazy: „suma dnia ≤ limit” nie była prawdą. Każda nieudana lub spóźniona płatna próba (timeout, zła lub pusta odpowiedź, wynik po zakończeniu rozmowy, nieudany zapis analizy) zapisywała koszt 0, a w trwającej rozmowie wysłanie wiadomości i „Try again” nigdy nie były odmawiane z powodu budżetu (twardo sprawdzany był tylko start). Zmiany w kodzie: księga `LLMCharge` dla wywołań bez `Message` ani wyniku analizy (prawdziwy koszt z `usage` albo szacunek 0,03 / koszt ostatniej tury / 0,07) i twardy dach `limit_reached` — po osiągnięciu limitu wysłanie i ponowienie tury są odmawiane z zakończeniem rozmowy `DAILY_LIMIT`, a ponowienie analizy czeka na reset (pierwsza próba analizy rusza zawsze, S-02). Ręczne mutanty 36/36 zgodne (nowe M25–M34); mutmut: 841 mutantów na 4 modułach, 60 przeżyć przed domknięciem → 57 po trzech nowych asercjach (odmowy bez powodu `None`, `ended_at` przy odmowie ponowienia tury) → 56 po review implementacji (`x_send_message__mutmut_7` zabity testem `test_message_as_long_as_the_field_allows_is_accepted`: wyrocznią jest `maxlength` pola, więc wiadomość o maksymalnej długości musi przejść), każde w rejestrze. Do przeniesienia przez `/10x-test-plan --refresh` (tu bez zmian w §2):
  - §2 Risk Response Guidance #4, „What would prove protection”: zamiast „suma kosztów dnia nie przekracza limitu” niezmiennik dachu — po osiągnięciu limitu żadne nowe płatne wywołanie się nie zaczyna, a dzień może przekroczyć limit tylko o wywołania rozpoczęte poniżej niego (najwyżej jedna tura w toku) i pierwsze próby analiz.
  - §2 ryzyko #4, Source: roadmap Q-07 częściowo zaadresowane (koszt nieudanych prób liczony, ponowienia zatrzymane dachem); otwarte zostają `max_output_tokens` i praca poza żądaniem HTTP.
- **Phase 5 — AI eval layer (data) (2026-10-19):** obecne testy nic nie mówiły o jakości nauki (atrapy zwracają to, co test zakolejkował); teraz lokalny eval na prawdziwym modelu z zestawem z MERLIN 1.1 (§6.5). Przebieg bazowy `scripts/eval/results/2026-10-19-gpt-5.4-56e6109.json` (gpt-5.4, effort tury `none`, analizy `medium`, K=3, czyste drzewo): kod 1, 0,83 USD, 0 nieudanych wywołań; analiza `recall` 0,887, `category_accuracy` 0,851, `extras` 0,694, `typo_free` 0,917, `notes_questions` 0,819; tura `recast` 0,783, `lecture_free` 0,950, `one_question` 0,967; pamięć `no_repeat` 0,467. Długa analiza (40 wiadomości): 46,5 s i 0,057 USD — daleko poniżej timeoutu analizy 150 s i limitu proxy Railway 300 s; sprawa przekazana z Phase 2 zamknięta (jedna realistyczna rozmowa, nie najgorszy przypadek z wiadomościami po 2000 znaków). Przebieg na celowo zepsutym prompcie (reguła literówek odwrócona w obu promptach, tura ma wyjaśniać regułę; `--suite analysis,turn --repeats 1`): `typo_free` 0,917 → 0,000 (n=12) i `lecture_free` 0,950 → 0,000 (n=20), oba `difference`; `extras` +1,056, `recast` −0,683 i `recall` −0,091 też `difference`; `category_accuracy`, `notes_questions` i `one_question` `within noise`; 0 nieudanych wywołań, 0,36 USD. Pierwsza próba tego przebiegu (2026-10-19) była niepełna: 15 wywołań (14 z 20 tur, 1 analiza) padło na `RateLimitError` 429 — wyczerpane środki na koncie OpenAI, w tym samym czasie produkcja też nie wysyłała wiadomości; powyższe liczby to powtórka po doładowaniu konta. Słabości obecnych promptów (bez poprawek, to osobne zmiany):
  - pamięć `no_repeat` 0,467: tura otwierająca zadaje ponownie pytania z notatek sceny (np. „Wie heißt Ihr Hund?”, „Möchten Sie etwas trinken?”, „Haben Sie eine Reservierung?”, „Wohin fahren Sie?”; `memory-restaurant` i `memory-train-delay` 0/3, `memory-dog-walk` 1/3);
  - A3 ×3 w `schwimmbad`: analiza zgłasza literówkę „Mochtest” jako błąd; A4 ×2 w `wohnung-neuburg`: zgłoszone poprawne „eine neue Arbeit”;
  - tura bez recastu w części przypadków (`paket-bitte`, `hund-urlaub` 0/3; `spielplatz-baby`, `verein-pruefung`, `party-frau` 1/3), wykład w `paket-hilfe` („sagt man” 3/3), dwa pytania w `bus-bank` (2/3) — do przeczytania w `calls` przed pierwszym strojeniem (część może wynikać z wąskich `correct_forms`, nie z modelu);
  - analiza najsłabsza w `au-pair` i `wohnen-miete` (`recall` 0,67, `category_accuracy` 0,5, `extras` 1,67–2,0).
  Mutacje: ręczne mutanty oceniacza M35–M49; `memory._mistakes__mutmut_47` zabity zwykłym testem, wiersz rejestru usunięty. Pełny przebieg po domknięciu (2026-10-19): ręczne mutanty 51/51 zgodne; mutmut 841 mutantów na 4 modułach, 786 zabitych, 55 przeżyć (56 po Phase 4 minus `mutmut_47`), każde w rejestrze — 0 niewyjaśnionych.

### 6.7 AI review model eval (promptfoo)

- **Co mierzy i po co**: czy recenzent z CI (`scripts/review/`, wymagany check `review`) na innym modelu nadal zatrzymuje złe PR-y i przepuszcza dobre. Ten sam prompt produkcyjny (`_build_input`, `truncate_diff`), schemat `Review` i reguła werdyktu `final_verdict` z `criteria.py` — bez strojenia pod model, więc różnice pochodzą z modelu. Cztery modele: `gpt-5.4` (bazowy, obecny `LLM_MODEL`) i `gpt-6.1-terra` wprost przez OpenAI (`responses.parse`, jak produkcja), `claude-sonnet-5.5` i `gemini-3.8-flash` przez OpenRouter (`chat.completions.parse`, ścisły `json_schema` z tej samej klasy pydantic). 16 przypadków ze znanym werdyktem (`cases.py`), diffy budowane w czasie przebiegu z historii git (merge'e na stałych SHA i podstawienia w pliku z commita `12dccd1`), nigdy commitowane:
  - **tier `hard`** (14) — jednoznaczny bloker albo czysty diff; tylko one decydują o dyskwalifikacji i rankingu;
  - **tier `soft`** (2, subtelne prawdziwe błędy) — tylko czułość w raporcie, poprawny recenzent może je ocenić 4–6;
  - **kind**: `clean` (7, oczekiwany `pass`), `blocker` (4 hard: `data_isolation`, `no_secrets`, `correctness`, `migrations` + 2 soft `correctness`, oczekiwany `fail` z nazwanym blokerem), `warning` (2: `tests`, `openai_boundary` — ostrzeżenie z założenia nie oblewa review, więc oczekiwany `pass` plus niska ocena ostrzeżenia), `injection` (1: IDOR z wstrzykniętą instrukcją w diffie, oczekiwany `fail` mimo niej).
  Fałszywy sekret i tekst wstrzyknięcia składa kod z kawałków w czasie przebiegu — w repo nie ma ich jako ciągłego literału (pilnuje tego test). Moduły w `scripts/review/eval/` (`cases.py`, `models.py`, `provider.py`, `assertion.py`, `budget.py`, `fingerprint.py`, `run.py`, `promptfooconfig.yaml`); ich kod sprawdzają w CI zwykłe testy `tests/test_review_eval.py` (bez sieci i bez kluczy).
- **Kiedy uruchamiać** — tylko ręcznie, lokalnie, nigdy w CI ani w hooku; po zmianie czegokolwiek, co wchodzi w odcisk (fingerprint, sha256 z `fingerprint.py`): instrukcji recenzenta (`_INSTRUCTIONS`, `_TRUNCATED_INSTRUCTION`), schematu `Review`, stałych wywołania (`MAX_OUTPUT_TOKENS`, `REASONING_EFFORT`, `MAX_DIFF_CHARS`, `EXCLUDED_PATHS`), reguły werdyktu (`FAIL_FLOOR`, `BLOCKERS`) — albo modelu recenzenta. Odcisk obejmuje też kod źródłowy `run_review._build_input`, `criteria.final_verdict`, `criteria.failed_blockers` i `criteria._at_or_below_floor`, więc zmiana sposobu opakowania promptu albo decyzji o werdykcie też wymaga nowego pliku wyniku. Przypomina o tym bramka w CI: test w `tests/test_review_eval.py` czyta najnowszy plik z `scripts/review/eval/results/` i robi się czerwony, gdy jego `fingerprint` różni się od bieżącego, gdy `scripts.review.run_review.LLM_MODEL` nie jest wśród zmierzonych modeli albo gdy plik nie jest pełnym przebiegiem (`test_newest_result_matches_current_fingerprint`, `::test_newest_result_measures_current_model`, `::test_newest_result_is_complete`; komunikat podaje komendę ponownego przebiegu); zielony wraca dopiero z nowym zacommitowanym plikiem wyniku. Przejście na model już zmierzony w najnowszym pliku zostaje zielone. Uwaga: aktualizacja `openai` albo `pydantic` może zmienić wygenerowany schemat (`to_strict_json_schema(Review)`), a więc odcisk, bez zmiany naszego kodu — wtedy też potrzebny jest nowy przebieg.
- **Run** (jedna komenda; klucze `OPENAI_API_KEY` i `OPENROUTER_API_KEY` z `.env`):
  - pełny przebieg: `uv run --env-file .env python -m scripts.review.eval.run --repeats 3 --max-usd 10 --share`;
  - `--repeats N` (domyślnie 3) — ile razy cały zestaw przechodzi przez wszystkie modele, jedno wywołanie promptfoo na powtórzenie;
  - `--max-usd X` (domyślnie 10) — limit księgi kosztu (niżej);
  - `--models a,b` — tylko podzbiór modeli po etykiecie (`gpt-5.4`, `gpt-6.1-terra`, `claude-sonnet-5.5`, `gemini-3.8-flash`); plik wyniku zawiera wtedy tylko zmierzone modele;
  - `--dry-run` — sprawdza Node, klucze i stan drzewa (na brudnym drzewie też działa), drukuje najgorszy koszt na powtórzenie i ile powtórzeń mieści się w budżecie, kończy kodem 0 przed promptfoo; nic nie wydaje;
  - `--fake` — prawdziwe promptfoo z providerem w trybie atrapy (stała poprawna recenzja, bez sieci, bez wydatku w księdze); sprawdza most promptfoo ↔ Python za darmo; wymaga `--out`;
  - `--smoke` — jeden mały przypadek (`pass-settings-env`), raz na model; wymaga `--out`;
  - `--share` — po pełnym przebiegu `promptfoo share <evalId>` dla każdego powtórzenia, linki trafiają do pliku wyniku; odrzucone z `--fake` i `--dry-run`;
  - `--out DIR` — próba: katalog musi być poza repo, brudne drzewo dozwolone, wynik i surowe wyjście lądują w `DIR` (nie w `results/`);
  - `--ledger PATH` (domyślnie `~/.cache/talkaitive-review-eval/ledger.json`) — plik księgi kosztu.
  - **Kody wyjścia**: 0 — przebieg pełny (`complete: true`); 1 — błąd w czasie przebiegu (promptfoo zakończone innym kodem niż 0/100, nieczytelna księga, nieoczekiwany wyjątek — drukowany jest tylko typ, bo treść mogłaby cytować model); 2 — konfiguracja (zły argument, brak klucza albo `.venv`, Node za stary, brudne drzewo bez `--out`, `--out` w repo, ani jedno powtórzenie nie mieści się w budżecie) albo rezerwacja odrzucona w środku powtórzenia (wynik częściowy, `complete: false`).
- **Budżet i księga**: promptfoo nie ma limitu kosztu, a limit klucza OpenRouter nie obejmuje wywołań wprost do OpenAI — dlatego jedna księga w pliku poza repo, wspólna dla wszystkich procesów workerów, smoke'a i pełnego przebiegu. Efektywny limit = `--max-usd` − 0,50 USD marginesu (domyślnie 9,50). Każde wywołanie najpierw rezerwuje swój najgorszy koszt (wejście 1 znak = 1 token, najwyższa możliwa cena modelu, pełne 6000 tokenów wyjścia); otwarta rezerwacja liczy się jak wydana, więc crash może koszt tylko zawyżyć. Rozliczenie: OpenAI — tokeny × ceny z `models.py`; OpenRouter — `usage.cost` z odpowiedzi (inaczej tokeny × najgorsze ceny); koszt wyższy od rezerwacji zapisuje się w pełnej wysokości. Gdy rezerwacja przekroczyłaby limit, wywołanie nie startuje (wiersz z błędem `budget`, kod 2). Powtórzenie startuje tylko wtedy, gdy jego cały najgorszy koszt mieści się w tym, co zostało; powtórzenia, które się nie mieszczą, są pomijane i zapisane w `repeats_skipped_budget` (przebieg dalej kończy się kodem 0). Księga jest skumulowana: limit dotyczy sumy wszystkich przebiegów zapisanych w tym pliku, więc na nowy budżet podaj nowy `--ledger` zamiast kasować stary. Eval omija dzienny limit aplikacji i używa tych samych kont co produkcja (OpenAI) i recenzent w CI.
- **promptfoo**: przypięte 0.125.1 — runner używa globalnego `promptfoo`, jeśli `--version` daje dokładnie tę wersję, inaczej `npx -y promptfoo@0.125.1`; Node ≥ 22.22.0 (starszy → kod 2). Zawsze `--no-cache --no-share`: cache promptfoo dla providera w Pythonie ignoruje numer powtórzenia, więc powtórzenia byłyby kopią pierwszego wyniku zamiast nowych wywołań; automatyczne udostępnianie (gdy jesteś zalogowany do promptfoo cloud) wysłałoby prompty i diffy — z fałszywym sekretem i wstrzyknięciem — bez decyzji. Udostępnienie jest tylko jawne, przez `--share`, po pełnym przebiegu. Środowisko: `PROMPTFOO_DISABLE_TELEMETRY=1`, `PROMPTFOO_DISABLE_UPDATE=1`, `PROMPTFOO_DISABLE_SHARING=true`, `PROMPTFOO_PYTHON` = bezwzględna ścieżka do `.venv/bin/python`, `PYTHONPATH` = repo, `-j 4`.
- **Gdzie leżą wyniki**:
  - surowe wyjście (diffy, fałszywy sekret, odpowiedzi modeli, logi promptfoo, kopia wyniku) — poza repo: `~/.cache/talkaitive-review-eval/runs/<run-id>/` (przy `--out` w `<DIR>/raw/<run-id>/`); nigdy go nie commitujesz;
  - plik wyniku — `scripts/review/eval/results/<YYYY-MM-DDTHHMMSS>-<shortsha>.json` + `.md` z macierzą (znacznik czasu UTC; „najnowszy” = największy leksykograficznie). Zwarty JSON: metadane, `fingerprint`, wersje promptfoo i Node, modele z cenami, przypadki z oczekiwaniami, jeden wpis na (przypadek, model) z tablicą powtórzeń (`verdict`, `failed`, `low`, `error`, `usd`, `regular_usd`, `ms`, `served`), `aggregate`, linki, `repeats_requested` / `repeats_completed` / `repeats_skipped_budget`, `complete`; bez promptów i diffów. Zapis odmawia powyżej 20 000 znaków i nigdy nie nadpisuje istniejącego pliku.
  - Commitujesz tylko wynik pełnego przebiegu (`complete: true`) z czystego drzewa (bez `--out`; na brudnym drzewie runner odmawia). Wyników prób (`--out`, `--fake`, `--smoke`) nie commitujesz.
  - Latest result: see `scripts/review/eval/results/`.
- **Jak czytać macierz** (kolumny `aggregate` na model):
  - `hard_false_passes` — werdykt `pass` na przypadku hard z oczekiwanym blokerem; ≥ 1 w dowolnym ukończonym powtórzeniu → `disqualified: true`;
  - `false_fails` / `hard_pass_runs` → `false_fail_rate` — dobry PR (hard, oczekiwany `pass`) zablokowany; błąd modelu też się tu liczy, bo produkcja kończy się wtedy kodem 1 i blokuje merge;
  - `wrong_blocker` — dobry werdykt `fail`, ale bez oczekiwanego blokera w `failed_blockers`; osobna kolumna, nie fałszywe przejście;
  - `model_errors` → `model_error_rate` — tylko błędy modelu (`schema`, `no_output`, `incomplete`); na przypadku `fail` nie są fałszywym przejściem (produkcja i tak blokuje), ale liczą się w tej stopie;
  - `infra_errors` (`budget`, `config`, `api:*`) — wyłączone ze wszystkich stóp i wypisane osobno; `unmeasured_hard` — przypadki hard niezmierzone przez taki błąd;
  - `warnings_detected` / `warning_runs` → `warning_rate` — wykrycie ostrzeżenia (niska ocena `tests` / `openai_boundary`) na przypadkach `warning`; poza regułą wyboru;
  - `soft_detected` / `soft_runs` → `soft_rate` — czułość na przypadkach soft; poza regułą wyboru;
  - `mean_usd` (rzeczywista cena), `mean_regular_usd` (Gemini po cenie regularnej od 2027-01-01; dla reszty to samo), `median_ms`;
  - `stability` — odsetek przypadków, w których wszystkie powtórzenia dały ten sam werdykt (albo ten sam błąd); `n/a` przy mniej niż 2 ukończonych powtórzeniach.
- **Reguła wyboru** (ustalona przed przebiegiem, `pick_winner` w `run.py`): (1) odpada model z `hard_false_passes > 0` albo z `unmeasured_hard > 0`; (2) wśród reszty wygrywa najniższy `false_fail_rate`, potem najniższy `mean_regular_usd`, potem najniższa `median_ms`; pełny remis wygrywa model wymieniony wcześniej. Gdy odpadają wszystkie, wynik brzmi „no model qualifies: keep gpt-5.4”. Eval tylko rekomenduje: zmiana modelu recenzenta to osobna zmiana (własne ustawienie, ceny w `LLM_PRICES_USD_PER_MTOK`, nowy przebieg).
- **Routing OpenRouter**: każde żądanie niesie `provider: {data_collection: "deny", require_parameters: true, zdr: true, only: [...]}`; `only` = endpointy z `structured_outputs`: Claude `google-vertex`, `azure`, Gemini `google-vertex` (przy `zdr: true` Azure dla Claude odpada, więc w praktyce oba idą do google-vertex). Pole `served` to nazwa wyświetlana OpenRouter, nie slug: `Google` oznacza tu google-vertex (AI Studio pokazuje się jako `Google AI Studio`, Azure jako `Azure`); runner nie porównuje `served` z `only` — czytasz to w wyniku. Wywołania OpenAI mają `store=False`, jak produkcja. Klient bez ponowień SDK (`max_retries=0`), żeby nie płacić za niewidoczne próby.
- **Czas**: `ms` mierzy sam provider wokół wywołania SDK (bez narzutu promptfoo). Trasy OpenRouter mają dodatkowe opóźnienie routingu, więc czasy tras bezpośrednich (OpenAI) i przez OpenRouter nie są w pełni porównywalne; latencja jest dopiero trzecim kryterium.
- **Wyjątek od granicy modelu**: CLAUDE.md mówi, że w aplikacji model woła tylko `conversations/llm.py` (wyjątek: `scripts/review/`). `scripts/review/eval/` to świadomy, lokalny wyjątek (poza aplikacją, nigdy w CI, z własnym limitem kosztu) — dopisanie go do CLAUDE.md jest propozycją w raporcie zmiany `ai-review-model-eval`, nie obowiązującą regułą.

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Obciążenie i wydajność** — aplikacja jest dla max 10 użytkowników, a bez observability nie ma czym analizować wydajności. Re-evaluate, gdy pojawi się observability albo więcej użytkowników (priorytet wzrośnie — autor jest performance engineerem). (Source: Phase 2 interview Q5.)
- ~~**Pełne e2e w przeglądarce (Playwright)**~~ — wykluczenie zniesione 2026-10-16: e2e w przeglądarce (Playwright) jest teraz obowiązkową warstwą testów. Świadoma decyzja zespołu, gdy poziom projektu na to pozwolił; konfiguracja i seed: `context/foundation/test-stack.md` (`## E2E`). Pierwotny powód wykluczenia: Phase 2 interview Q3.

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-10-13
- Stack versions last verified: 2026-10-13
- AI-native tool references last verified: 2026-10-19

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
