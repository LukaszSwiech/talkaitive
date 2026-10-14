# Suite trust and CI floor — Implementation Plan

## Overview

Rollout Phase 1 z `context/foundation/test-plan.md` (ryzyko #2). Dwa cele: (1) udowodnić mutacjami, że celowe zepsucie krytycznej logiki deterministycznej (izolacja danych, budżet dzienny, stan analizy, wybór pamięci) wywraca testy; (2) uruchamiać ruff + pytest automatycznie na każdym PR i każdym pushu do `main`, a wdrożenie na produkcję wstrzymywać, dopóki CI nie jest zielone (Railway „Wait for CI”).

## Current State Analysis

- Brak CI: brak `.github/`, `main` wdraża się sam (`context/deployment/deploy-plan.md:7`, `:150` — `checkSuites` off). 54 z 59 commitów first-parent na `main` to bezpośrednie pushe (research §4).
- Ochrona gałęzi na prywatnym repo z planem Free zwraca 403; dokumentacja GitHuba: prywatne repo na koncie Free (osobowym lub organizacji) nie ma chronionych gałęzi (sprawdzone 2026-10-14). Decyzja: bramka przez Railway „Wait for CI”, bez GitHub Pro.
- Pomiar mutacyjny (research §1): 12 z 13 celowanych ręcznych mutantów przeżyło (M1–M8, M10–M13; M9 zabity; C1, C2 kontrolne zabite).
- Stan bazowy: `uv run pytest` 198 passed (~1,7 s), `ruff check .` i `ruff format --check .` czyste (2026-10-14). Testy nie potrzebują sekretów ani sieci (`talkaitive/settings_test.py`).
- mutmut nie jest zainstalowany; wersja 3.8.0 (2026-09-12) mutuje tylko kod w funkcjach, nie usuwa wywołań `.for_user()`/`.filter()`, a `mutmut run` zwraca 0 przy przeżyciach. Współpraca z pytest-django w `mutants/` niesprawdzona (research §5).

## Desired End State

- Każdy push do `main` i każdy PR uruchamia workflow `CI` (ruff check, ruff format --check, pytest na SQLite). Railway wdraża commit dopiero po zielonym workflow; czerwony → deployment `SKIPPED`, produkcja zostaje na poprzedniej wersji. Udowodnione celowo czerwonym commitem.
- `uv run python scripts/mutation/manual_mutants.py` podkłada stałą listę ręcznych mutantów (C1, C2, M1–M13) na kopii repo i kończy się kodem 0: każdy mutant zabity albo zaakceptowany z uzasadnieniem w `scripts/mutation/accepted_survivors.md`.
- `uv run mutmut run` na 4 modułach (`conversations/budget.py`, `conversations/memory.py`, `conversations/services.py`, `accounts/ownership.py`) nie zostawia żadnego przeżywającego mutanta bez wpisu w `accepted_survivors.md` („zaufany” = 0 niewyjaśnionych).
- `test-plan.md` §5 opisuje bramkę faktycznie wpiętą, §6.1 ma test referencyjny i wzorzec potwierdzenia mutacją, §6.6 ma notatkę z fazy.

### Key Discoveries:

- Wycieki izolacji M1–M3 są w widokach `conversations/views.py:35-39` (home), `:65-69` (gałąź `LLMError` w start), `:95-97` (lista błędów na stronie rozmowy). Fragmenty M1 i M2 mają identyczny tekst i różnią się tylko wcięciem (4 vs 8 spacji).
- M4: `is_final_turn` (`conversations/budget.py:100-117`); istniejący `tests/test_budget.py:308` sprawdza tylko cudzy *wydatek*, nie cudzą *ostatnią turę* — dlatego mutant przeżył.
- M6: `_mark_analysis_failed` (`conversations/services.py:342-349`); w testach każdy użytkownik ma jedną rozmowę, więc filtr `pk=` nie jest sprawdzany.
- M7: znacznik „w toku” ustawiany w `services.py:298`; `FakeAnalyzeMistakes` (`tests/test_conversation_views.py:62-76`) przyjmuje tylko wyniki i wyjątki, a `FakeGenerateTurn` (`:36-54`) także funkcję wywoływaną w trakcie — ten wzorzec przyda się do M7.
- M10: stała modułowa `MISTAKE_WINDOW_CONVERSATIONS = 20` (`conversations/memory.py:33`) — mutmut jej nie zmutuje; test `tests/test_memory.py:113` sprawdza tylko, że 21. rozmowa wypada.
- M12/M13: sortowanie `-ended_at` (`memory.py:86`) i etykieta „(the most recent)” (`conversations/llm.py:184-185`). PRD `prd.md:107`: pierwszeństwo ma częstość, potem świeżość.
- Wzorzec granic dnia z ręcznie wpisanymi wartościami UTC (niezależna wyrocznia): `tests/test_budget.py:100-140`; inkluzywna północ dla wydatków: `:152`, `:182`.
- Fixture'y dwóch użytkowników: `anna`, `lukasz` (`tests/test_conversation_views.py:113-119`, analogicznie w `test_budget.py`).
- Railway czeka na **wszystkie** workflow Actions na commicie (research §5) — żaden wolny workflow (mutmut) nie może się uruchamiać na push.
- `.gitignore` jest sam ignorowany przez git (CLAUDE.md), więc wpis `mutants/` działa tylko lokalnie; trwałą ochroną przed lintowaniem kopii mutmut jest `extend-exclude` w `pyproject.toml`.

## What We're NOT Doing

- Nie kupujemy GitHub Pro / Team i nie przenosimy repo — przeniesienie na darmową organizację nie daje ochrony gałęzi (docs GitHub, 2026-10-14). Bramka blokuje wdrożenie, nie merge.
- Nie uruchamiamy testów na Postgresie w CI. Wraca w fazie 2 lub 4 razem z pierwszym testem współbieżności (`select_for_update`).
- Nie uruchamiamy mutmut ani skryptu ręcznych mutantów w CI — oba są lokalne i okresowe.
- Nie piszemy testów dla M8 (granica wygaśnięcia znacznika tury co do mikrosekundy) i M11 (filtr `status=ENDED` przy `analyzed_at` — równoważny). Trafiają do `accepted_survivors.md` z uzasadnieniem.
- Nie przepisujemy pięciu istniejących testów z problemem wyroczni (research §3): koszt tury i reguła „wydane + 0.03” → faza 4, timeout analizy → faza 2; reguły pamięci M10/M13 dostają źródło w decyzji użytkownika z 2026-10-14.
- Nie dodajemy testów nowych zachowań z faz 2–4: zawieszenie dostawcy, pełna lista widoków z `pk`, koszt prób nieudanych.
- Nie naprawiamy rozjazdu PRD `prd.md:107` („błąd pasuje do wybranego tematu”) z `select_memory`, które nie filtruje błędów po temacie — to osobna zmiana produktowa.
- Nie dodajemy mypy ani typechecku do CI (test-plan §5: osobny `--refresh`).
- Nie mutujemy widoków, `llm.py`, ustawień, modeli ani migracji przez mutmut — izolację w widokach pokrywa ręczna lista.

## Implementation Approach

Najpierw spike, bo cała część mutacyjna zależy od tego, czy mutmut działa z pytest-django w tym repo. Potem najtańszy i najmocniejszy sygnał — CI + bramka Railway — żeby każdy kolejny nowy test od razu działał w CI. Następnie skrypt ręcznych mutantów, który odtwarza pomiar z researchu (12 przeżywa) i staje się miernikiem dla faz 4–5. Testy zabijające mutanty idą w dwóch fazach według obszaru, potem triage reszty przeżyć mutmut, a na końcu dokumenty.

Zasady wspólne dla faz 4–6:

- Oczekiwany wynik pochodzi z PRD, planu testów albo decyzji użytkownika (2026-10-14), nigdy z kodu. Gdzie wymaganie mówi tylko „dane A nie zależą od danych B”, test jest **metamorficzny** — porównuje wynik dla A bez danych B i z danymi B.
- Każdy nowy test jest potwierdzony ponownym podłożeniem mutanta, w który celuje: `uv run python scripts/mutation/manual_mutants.py <ID>` → `KILLED` (dla mutantów mutmut: `uv run mutmut apply <name>` na czystej kopii roboczej / ponowny `mutmut run` na tym mutancie).
- Testy dopisujemy do istniejących plików `tests/test_<obszar>.py` i istniejących fixture'ów; bez nowych helperów, jeśli fixture już istnieje.

Plan awaryjny spike'a: jeśli mutmut nie ruszy z pytest-django po udokumentowanych poprawkach, dowodem mutacji zostaje skrypt ręcznych mutantów, a faza 6 zmienia się w opis blokady w §6.6 — bez trzeciego narzędzia w tej fazie.

## Critical Implementation Details

**Timing & lifecycle** — Przełącznik „Wait for CI” pojawia się w Railway dopiero, gdy workflow na `push` do `main` jest już na `main`. Kolejność: workflow wypchnięty przez użytkownika → zielony przebieg → włączenie przełącznika → odczyt kontrolny (przełącznik bywa niezapisywany, wątek Railway Station z 2026-10-13) → dopiero wtedy czerwony commit dowodowy.

**State sequencing** — Agent nigdy nie robi `git push` (każdy push wdraża produkcję). Kroki z pushem i z ustawieniami Railway w UI wykonuje użytkownik; agent przygotowuje commit i podaje komendę.

**Debug & observability** — `web-settings.json` jest plikiem `--variables` dla mutacji `serviceInstanceUpdate`. `checkSuites` nie należy do jej `input`, więc trafia do osobnego klucza najwyższego poziomu; obiektu `input` nie zmieniamy.

## Phase 1: Spike — mutmut z pytest-django

### Overview

Zainstalować mutmut 3.8.0 jako zależność dev, skonfigurować go na 4 modułach i doprowadzić do jednego pełnego przebiegu. Wynik: działająca komenda, czas przebiegu i lista przeżywających mutantów (baseline dla fazy 6).

### Changes Required:

#### 1. Zależność dev i konfiguracja

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Dodać mutmut przez `uv add --dev mutmut` (Railway buduje z `--no-dev`, więc produkcja go nie dostanie) i sekcję `[tool.mutmut]` ograniczoną do logiki krytycznej. Wykluczyć `mutants/` z ruff, żeby `ruff check .` nie lintował kopii tworzonej przez mutmut.

**Contract**: `[tool.mutmut]` z jawnymi `source_paths` (repo nie ma `src/`) i zawężeniem do `conversations/budget.py`, `conversations/memory.py`, `conversations/services.py`, `accounts/ownership.py` (`only_mutate` albo glob w CLI — co działa, potwierdza spike). Pakiet `talkaitive` (z `settings_test`) musi być importowalny z `mutants/` (`source_paths` lub `also_copy`). `[tool.ruff] extend-exclude` dostaje `"mutants"`. Lokalnie `mutants/` dopisane do `.gitignore` (nie jest commitowane — `.gitignore` sam jest ignorowany).

#### 2. Przebieg i zapis baseline

**File**: `context/changes/testing-suite-trust-and-ci/mutmut-baseline.md`

**Intent**: Uruchomić `uv run mutmut run`, potem `uv run mutmut results`, i zapisać: wersję, czas przebiegu, liczbę mutantów zabitych / przeżywających / timeout, listę nazw przeżywających mutantów z modułem, oraz każdą poprawkę konfiguracji potrzebną, żeby ruszyło (`pythonpath = ["."]`, wielokrotne `pytest.main()` z pytest-django, `--max-children` przy fałszywych timeoutach — zgłoszenia #504, #545).

**Contract**: Kontrola sensu — mutant odpowiadający C2 (`>=` → `>` w `is_exhausted`) musi być w mutmut zabity; inaczej mutmut nie widzi testów i przebieg jest nieważny. Jeśli udokumentowane poprawki nie wystarczą, zapisać błąd i przejść na plan awaryjny (Implementation Approach).

### Success Criteria:

#### Automated Verification:

- `uv run mutmut run` kończy się bez błędu konfiguracji, a `uv run mutmut results` pokazuje mutanty z 4 modułów
- Mutant `>=` → `>` w `is_exhausted` jest w wynikach mutmut zabity (kontrola sensu)
- `uv run pytest` dalej 198 passed
- `uv run ruff check .` i `uv run ruff format --check .` przechodzą mimo istniejącego katalogu `mutants/`

#### Manual Verification:

- `mutmut-baseline.md` zawiera czas przebiegu, liczby i listę przeżywających mutantów, a użytkownik akceptuje decyzję go/no-go dla mutmut

**Implementation Note**: Po fazie zatrzymaj się na ręczne potwierdzenie decyzji go/no-go.

---

## Phase 2: Próg CI i bramka Railway

### Overview

Workflow GitHub Actions na każdy PR i każdy push do `main`, Railway „Wait for CI” włączony i udowodniony czerwonym commitem, a ustawienia odzwierciedlone w dokumentach wdrożenia.

### Changes Required:

#### 1. Workflow CI

**File**: `.github/workflows/ci.yml`

**Intent**: Uruchamiać na czystym runnerze te same bramki co lokalnie: ruff lint, ruff format check i pytest na SQLite, bez sekretów.

**Contract**: Wyzwalacze `push` (gałąź `main`) i `pull_request`; **bez** filtrów `paths` (Railway czeka na workflow dla każdego commita, także z samymi dokumentami). `permissions: contents: read`, jeden job o unikalnej nazwie, `timeout-minutes`. Kroki: `actions/checkout`, `astral-sh/setup-uv` (pełny tag wydania albo SHA — od v8 brak tagów major; aktualne wersje sprawdzić w dniu implementacji i zapisać datę w komentarzu), `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`. Python z `.python-version` (3.14).

#### 2. Railway „Wait for CI” (wykonuje użytkownik)

**File**: ustawienia serwisu `web` w Railway (UI: Settings → Source → Wait for CI)

**Intent**: Wstrzymać deploy do zakończenia workflow na commicie i pominąć go, gdy workflow padnie — to pokrywa też bezpośrednie pushe na `main`.

**Contract**: `checkSuites = true` dla triggera `main`. Po włączeniu odczyt kontrolny (ponowne otwarcie ustawień albo zapytanie read-only przez `railway`), bo przełącznik bywa niezapisywany. Jeśli Railway poprosi o nowe uprawnienia aplikacji GitHub — akceptuje użytkownik.

#### 3. Dowód działania bramki (wykonuje użytkownik, agent przygotowuje commity)

**File**: `tests/test_ci_gate_canary.py` (tymczasowy, usuwany commitem revert)

**Intent**: Pokazać, że czerwone CI zatrzymuje wdrożenie. Celowo padający test w osobnym pliku testowym — nawet gdyby przełącznik nie zadziałał, na produkcję trafia tylko plik testu, a aplikacja się nie zmienia.

**Contract**: Commit z jednym testem `assert False` z komunikatem „CI gate canary” → push na `main` → workflow czerwony → deployment w Railway `SKIPPED`, `/healthz/` i Railway pokazują poprzedni deployment. Potem commit revert → workflow zielony → deploy się wykonuje. Oba SHA zapisać w `deploy-plan.md`.

#### 4. Kopia ustawień i dokumenty wdrożenia

**File**: `context/deployment/web-settings.json`, `context/deployment/deploy-plan.md`

**Intent**: Railway ignoruje `railway.json`, więc jedyną kopią ustawienia jest repo (CLAUDE.md). `deploy-plan.md` dziś mówi „no CI gate” i „`checkSuites` off” — po tej fazie to nieprawda.

**Contract**: `web-settings.json`: nowy klucz najwyższego poziomu `deploymentTrigger` z `branch: "main"` i `checkSuites: true`; obiekt `input` bez zmian. `deploy-plan.md`: punkt w „Status” (`:7`), wiersz „GitHub repo” w „Live resources” (`:150`: `checkSuites` on od <data>, workflow `ci.yml`, SHA dowodu) i uwaga przy komendzie re-apply, że `deploymentTrigger` ustawia się w UI (Source → Wait for CI), a nie tą mutacją.

### Success Criteria:

#### Automated Verification:

- `.github/workflows/ci.yml` przechodzi lokalnie te same kroki: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest`
- `gh run list --workflow ci.yml` pokazuje zielony przebieg dla commita z workflow na `main`
- `context/deployment/web-settings.json` jest poprawnym JSON-em, a obiekt `input` jest bajtowo taki sam jak przed zmianą

#### Manual Verification:

- PR z dowolną zmianą pokazuje check `CI` (zielony)
- Przełącznik „Wait for CI” jest włączony i po ponownym otwarciu ustawień dalej włączony
- Commit z kanarkiem: workflow czerwony, deployment Railway `SKIPPED`, produkcja na poprzedniej wersji
- Commit revert: workflow zielony, deployment udany, `/healthz/` zwraca 200

**Implementation Note**: Kroki z pushem i Railway wykonuje użytkownik; agent podaje komendy i czeka. Zatrzymaj się po fazie na potwierdzenie.

---

## Phase 3: Skrypt ręcznych mutantów

### Overview

Powtarzalny dowód jedną komendą dla mutantów, których mutmut nie wygeneruje (usunięte `.for_user()`/filtry, stałe modułowe, etykiety w prompcie). Baseline ma odtworzyć pomiar z researchu.

### Changes Required:

#### 1. Lista mutantów i uruchamiacz

**File**: `scripts/mutation/manual_mutants.py`

**Intent**: Dla każdego mutanta z listy: skopiować repo do katalogu tymczasowego (bez `.venv`, `.git`, `db.sqlite3`, `.env`, `context/`, `mutants/`), podmienić dokładnie jeden fragment, uruchomić pytest interpreterem z `.venv` projektu, zapisać `KILLED`/`SURVIVED`. Kopia robocza repo nigdy nie jest zmieniana, więc przerwanie skryptu niczego nie psuje.

**Contract**: Każdy wpis: `id` (C1, C2, M1–M13), obszar, ścieżka pliku, fragment oryginalny, fragment podmieniony, oczekiwanie (`killed` albo `accepted` z odnośnikiem do `accepted_survivors.md`). Wywołanie: `uv run python scripts/mutation/manual_mutants.py [ID ...]` (bez argumentów — wszystkie). Fragment musi wystąpić w pliku **dokładnie raz**; 0 lub >1 wystąpień to błąd skryptu, nie cichy wynik (M1 i M2 mają ten sam tekst — rozróżnia je wcięcie). Wynik: tabela id / wynik / oczekiwanie. Kod wyjścia 0 tylko, gdy każdy wynik zgadza się z oczekiwaniem; inaczej 1. W tej fazie wszystkie M-mutanty mają oczekiwanie `killed` (cel), więc skrypt świadomie kończy się kodem 1.

#### 2. Rejestr zaakceptowanych przeżyć

**File**: `scripts/mutation/accepted_survivors.md`

**Intent**: Jedno miejsce dla każdego przeżywającego mutanta, którego świadomie nie zabijamy — z ręcznej listy i z mutmut.

**Contract**: Tabela: id lub nazwa mutmut, plik i funkcja, klasyfikacja (`równoważny` / `brak wymagania` / `przekazany do fazy N`), uzasadnienie, data. W tej fazie pusty szablon z opisem klasyfikacji.

### Success Criteria:

#### Automated Verification:

- `uv run python scripts/mutation/manual_mutants.py` raportuje C1, C2 i M9 jako `KILLED`, a M1–M8 i M10–M13 jako `SURVIVED` (odtworzenie researchu §1), kod wyjścia 1
- Fragment, którego nie ma w pliku, kończy skrypt błędem (sprawdzone na celowo złym wpisie, który potem jest usuwany)
- `git status` po przebiegu nie pokazuje zmian w `accounts/`, `conversations/`, `talkaitive/`
- `uv run ruff check .` i `uv run ruff format --check .` przechodzą

**Implementation Note**: Zatrzymaj się po fazie na potwierdzenie.

---

## Phase 4: Testy izolacji i budżetu (M1–M5)

### Overview

Testy, które zabijają przeżywające mutanty wycieku danych i granic budżetu. Każdy potwierdzony ponownym podłożeniem swojego mutanta.

### Changes Required:

#### 1. Strona główna nie pokazuje cudzej aktywnej rozmowy (M1)

**File**: `tests/test_conversation_views.py`

**Intent**: Behavior: zalogowany B bez żadnej rozmowy, gdy A ma aktywną rozmowę, widzi stronę startu, a nie link „Continue” ani temat A. Regression: M1 (`views.py:35-39` bez `for_user`). Source: research §1 M1; PRD Prywatność `prd.md:46`, `:94`, `:113`. Edge: B nie ma żadnej rozmowy — jedyny stan, w którym wyciek jest widoczny. Anti-pattern: asercja tylko na kod 200 albo test z jednym użytkownikiem.

**Contract**: Test metamorficzny: kontekst strony B (`active_conversation`) i brak adresu rozmowy A w treści — jednakowe bez rozmowy A i z nią.

#### 2. Błąd startu przekierowuje na własną rozmowę (M2)

**File**: `tests/test_conversation_views.py`

**Intent**: Behavior: gdy A ma starszą aktywną rozmowę, a start rozmowy B kończy się `LLMError`, B trafia na stronę **swojej** nowej rozmowy. Regression: M2 (`views.py:65-69`). Source: research §1 M2; PRD Prywatność. Edge: ścieżka błędu, nie happy path; rozmowa A ma niższe `pk`, więc mutant ją wybiera. Anti-pattern: asercja tylko „302”.

**Contract**: Adres przekierowania równy adresowi rozmowy należącej do B (użyć `fake_llm` z wyjątkiem w kolejce).

#### 3. Strona rozmowy pokazuje tylko jej błędy (M3)

**File**: `tests/test_conversation_views.py`

**Intent**: Behavior: ten sam użytkownik ma dwie zakończone rozmowy X i Y z różnymi błędami; strona X pokazuje błędy X i żadnego z Y. Regression: M3 (`views.py:95-97` bez `conversation=`). Source: research §1 M3; PRD `prd.md:117` (lista błędów po zakończeniu *tej* rozmowy, brak wglądu w poprzednie). Edge: przeciek między rozmowami tego samego użytkownika — testy 404 (`:555`) go nie widzą. Anti-pattern: jedna rozmowa w fixture.

**Contract**: Treść/kontekst `mistakes` strony X zawiera tylko błędy X.

#### 4. Ostatnia tura innego użytkownika nie kończy cudzej rozmowy (M4)

**File**: `tests/test_budget.py`

**Intent**: Behavior: wynik `is_final_turn` dla A jest taki sam bez tur B i po dodaniu nowszej, drogiej tury agenta B. Regression: M4 (`budget.py:103-106` bez `conversation__in=`). Source: research §1 M4; PRD `prd.md:114` (limit $1 per użytkownik). Edge: kwoty dobrane tak, że koszt tury B doliczony do A przekroczyłby $1, a koszt tury A — nie. Anti-pattern: oczekiwany wynik liczony wzorem z `budget.py` — zamiast tego równość metamorficzna (z B vs bez B).

**Contract**: Obok istniejącego `test_is_final_turn_ignores_other_users_spending` (`:308`), który sprawdza wydatek, nie ostatnią turę.

#### 5. Rozmowa zakończona limitem dokładnie o północy blokuje ten dzień (M5)

**File**: `tests/test_budget.py`

**Intent**: Behavior: rozmowa zakończona przez dzienny limit dokładnie o 00:00:00 Europe/Berlin zamyka ten nowy dzień (`is_exhausted` prawda chwilę później tego dnia), a po kolejnej północy już nie. Regression: M5 (`budget.py:88`, `__gte` → `__gt`). Source: research §1 M5; PRD `prd.md:114` (reset o północy Europe/Berlin), dzień jako przedział [północ, następna północ) — ta sama konwencja co `test_spent_today_counts_from_midnight_inclusive` (`:152`). Edge: granica dokładnie o północy. Anti-pattern: północ liczona przez `day_start()` z kodu — czasy wpisane ręcznie w UTC jak w `:100-140`.

**Contract**: Dwie asercje: prawda tego dnia, fałsz po następnej północy.

### Success Criteria:

#### Automated Verification:

- `uv run pytest` przechodzi (198 + nowe testy)
- `uv run python scripts/mutation/manual_mutants.py M1 M2 M3 M4 M5` raportuje wszystkie pięć jako `KILLED`
- `uv run python scripts/mutation/manual_mutants.py C1 C2 M9` dalej `KILLED`
- `uv run ruff check .` i `uv run ruff format --check .` przechodzą
- Workflow `CI` jest zielony na commicie tej fazy

#### Manual Verification:

- Przegląd: każdy nowy test ma w docstringu lub komentarzu źródło oczekiwanej wartości (PRD / decyzja) i nie powtarza wzoru z kodu

**Implementation Note**: Zatrzymaj się po fazie na potwierdzenie.

---

## Phase 5: Testy stanu analizy i pamięci (M6, M7, M10, M12, M13)

### Overview

Testy, które zabijają przeżywające mutanty stanu analizy i wyboru pamięci, oraz wpisy M8 i M11 jako świadomie zaakceptowane.

### Changes Required:

#### 1. Nieudana analiza jednej rozmowy nie oznacza innych (M6)

**File**: `tests/test_analysis.py`

**Intent**: Behavior: użytkownik ma dwie zakończone, nieprzeanalizowane rozmowy X i Y; analiza X kończy się `LLMError` → X jest oznaczona jako nieudana, Y nie (strona Y nie pokazuje stanu „nieudana”). Regression: M6 (`services.py:347` bez `pk=`). Source: research §1 M6; wywiad Q2 (incydent z listą błędów, test-plan ryzyko #1). Edge: ścieżka błędu przy dwóch rozmowach jednego użytkownika. Anti-pattern: fixture z jedną rozmową.

**Contract**: Asercja na stan Y widoczny dla użytkownika (brak „nieudana” / „Try again” na stronie Y) i na X.

#### 2. W trakcie analizy drugie żądanie nie uruchamia płatnego wywołania (M7)

**File**: `tests/test_analysis.py` (oraz atrapa analizy, której używa)

**Intent**: Behavior: w trakcie wywołania modelu rozmowa jest „w toku” — drugie żądanie analizy jest odrzucone bez drugiego wywołania modelu, a strona pokazuje stan oczekiwania. Regression: M7 (`services.py:298`, znacznik nigdy nie ustawiany). Source: research §1 M7; test-plan §2 ryzyko #1 („znacznik w toku”); PRD NFR „Informacja zwrotna podczas czekania”. Edge: żądanie równoległe w trakcie trwającego wywołania. Anti-pattern: asercja na samo pole w bazie zamiast na skutek (liczba płatnych wywołań = 1, stan strony).

**Contract**: Atrapa analizy dostaje obsługę funkcji wywoływanej w trakcie (jak `FakeGenerateTurn`, `tests/test_conversation_views.py:36-54`); jeśli atrapa jest skopiowana w kilku plikach, zmiana tylko tam, gdzie test jej używa.

#### 3. Okno pamięci to 20 rozmów (M10)

**File**: `tests/test_memory.py`

**Intent**: Behavior: błąd występujący tylko w 20. najnowszej przeanalizowanej rozmowie trafia do pamięci. Razem z istniejącym testem 21. rozmowy (`:113`) to obie strony granicy. Regression: M10 (`memory.py:33` 20 → 19). Source: decyzja użytkownika 2026-10-14 (okno = 20 rozmów; PRD nie podaje liczby). Edge: granica 20 / 21. Anti-pattern: źródło „bo tak jest w stałej”.

**Contract**: W teście komentarz ze źródłem decyzji.

#### 4. „Najświeższa” rozmowa to ta zakończona najpóźniej (M12)

**File**: `tests/test_memory.py`

**Intent**: Behavior: rozmowa P utworzona wcześniej, ale zakończona później niż Q, liczy się jako nowsza (np. jej notatki sceny i fakty są pierwsze). Regression: M12 (`memory.py:86` bez `-ended_at`). Source: research §1 M12; PRD `prd.md:107` (świeżość). Edge: kolejność utworzenia ≠ kolejność zakończenia — obecne testy tworzą rozmowy w porządku czasu. Anti-pattern: fixture, w którym kolejność id = kolejność czasu.

**Contract**: Jawnie ustawione `ended_at` odwrotnie do kolejności tworzenia.

#### 5. Etykieta „najnowsza” stoi przy rozmowie zakończonej najpóźniej (M13)

**File**: `tests/test_llm.py` (lub `tests/test_memory.py`, jeśli test buduje pamięć przez `select_memory`)

**Intent**: Behavior: przy dwóch rozmowach z notatkami sceny etykieta „(the most recent)” stoi w bloku pamięci przy notatkach rozmowy zakończonej najpóźniej. Regression: M13 (`llm.py:184-185`). Source: decyzja użytkownika 2026-10-14. Edge: dwie rozmowy w tej samej scenie. Anti-pattern: asercja na dokładny tekst całego promptu — sprawdzamy tylko, przy których notatkach stoi etykieta.

**Contract**: Pamięć zbudowana przez `select_memory`, a nie ręcznie ułożoną listę, żeby test łączył kolejność z etykietą.

#### 6. Wpisy M8 i M11

**File**: `scripts/mutation/accepted_survivors.md`, `scripts/mutation/manual_mutants.py`

**Intent**: M8 (`services.py:79` `<` → `<=`): różnica w chwili wygaśnięcia co do mikrosekundy, niewidoczna dla użytkownika — `równoważny w praktyce`. M11 (`memory.py:82` bez `status=ENDED`): analiza wymaga zakończonej rozmowy, więc aktywna nigdy nie ma `analyzed_at` — `równoważny`. Oba z datą 2026-10-14 i decyzją użytkownika.

**Contract**: W skrypcie oczekiwanie M8 i M11 = `accepted`.

### Success Criteria:

#### Automated Verification:

- `uv run pytest` przechodzi
- `uv run python scripts/mutation/manual_mutants.py` kończy się kodem 0: C1, C2, M1–M7, M9, M10, M12, M13 `KILLED`; M8, M11 `SURVIVED` + `accepted`
- `uv run ruff check .` i `uv run ruff format --check .` przechodzą
- Workflow `CI` jest zielony na commicie tej fazy

#### Manual Verification:

- Przegląd: źródła oczekiwanych wartości w nowych testach (PRD / decyzja 2026-10-14), brak powtórzonych wzorów z kodu
- `accepted_survivors.md` ma czytelne uzasadnienia M8 i M11

**Implementation Note**: Zatrzymaj się po fazie na potwierdzenie.

---

## Phase 6: Triage mutmut do stanu „zaufany”

### Overview

Pełny przebieg mutmut na 4 modułach po fazach 4–5 i decyzja dla każdego pozostałego przeżywającego mutanta. Koniec fazy: 0 przeżywających mutantów bez wpisu w `accepted_survivors.md`.

### Changes Required:

#### 1. Testy dla przeżyć z wymaganiem

**File**: `tests/test_budget.py`, `tests/test_memory.py`, `tests/test_analysis.py`, `tests/test_ownership.py` (wg modułu mutanta)

**Intent**: Dla mutanta, którego zmiana zachowania ma źródło w PRD, planie testów albo decyzjach z 2026-10-14 — test w stylu faz 4–5 (behavior / regression / source / edge / anti-pattern w komentarzu lub docstringu), potwierdzony ponownym przebiegiem mutmut na tym mutancie. Kandydaci przewidziani w researchu §2: `services.py:256` (`_clear_analysis_marker` bez `pk=`), `services.py:279` i `:380` (liczenie wypowiedzi przy scalaniu błędów), `budget.py:107` (bez `role=ASSISTANT`).

**Contract**: Reguła klasyfikacji — kolejność sprawdzania:
1. zmiana bez skutku obserwowalnego → `równoważny` (wpis);
2. zachowanie z wymaganiem w PRD / test-plan / decyzjach → test;
3. zachowanie z nowego zakresu ryzyka #1 (timeouty, znaczniki „w toku”) albo #4 (koszt przy błędach i ponowieniach) → `przekazany do fazy 2` / `przekazany do fazy 4` (wpis);
4. pozostałe bez źródła wymagania → `brak wymagania` (wpis), lista pokazana użytkownikowi przy ręcznym potwierdzeniu fazy.

#### 2. Rejestr

**File**: `scripts/mutation/accepted_survivors.md`, `context/changes/testing-suite-trust-and-ci/mutmut-baseline.md`

**Intent**: Uzupełnić rejestr o mutanty mutmut (klasyfikacje 1, 3, 4) i dopisać do baseline wynik końcowy (liczby przed / po, czas przebiegu).

**Contract**: Każda nazwa przeżywającego mutanta z `uv run mutmut results` ma wiersz w rejestrze.

### Success Criteria:

#### Automated Verification:

- `uv run mutmut run` + `uv run mutmut results`: każdy przeżywający mutant ma wpis w `accepted_survivors.md` (porównanie listy nazw)
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` przechodzą
- `uv run python scripts/mutation/manual_mutants.py` dalej kończy się kodem 0
- Workflow `CI` jest zielony na commicie tej fazy

#### Manual Verification:

- Użytkownik przegląda wpisy `brak wymagania` i `przekazany do fazy N` i akceptuje klasyfikację

**Implementation Note**: Zatrzymaj się po fazie na potwierdzenie.

---

## Phase 7: Plan testów i dokumenty

### Overview

Zapisać w planie testów bramkę faktycznie wpiętą i wzorzec dodawania testu z potwierdzeniem mutacją; poprawić zapisy, które po tej fazie przestały być prawdziwe.

### Changes Required:

#### 1. test-plan.md §5 Quality Gates (oraz wiersze stosu w §4)

**File**: `context/foundation/test-plan.md`

**Intent**: Bramka „merge do `main` tylko po zielonym CI | ochrona gałęzi” jest niewykonalna na tym repo — zastąpić ją tym, co wpięto, i oznaczyć wpięte bramki.

**Contract**: §5: ruff — „local: wired; CI: wired”; pytest — „local + CI (PR i push do `main`) | wired”; wiersz bramki → „wdrożenie na produkcję tylko po zielonym CI | Railway „Wait for CI” + workflow `ci.yml` na push do `main` i PR | wired”, z uwagą: blokuje deploy, nie merge; ochrona gałęzi na prywatnym repo wymaga GitHub Pro / Team (403, sprawdzone 2026-10-14), świadomie nie wybrana. Mutation score — „local, okresowo” z dwiema komendami i kryterium „0 niewyjaśnionych przeżyć” (wired). §4: wiersz mutmut („zainstalowany, checked: <data>”) i wiersz ruff („CI — wired”).

#### 2. test-plan.md §6.1 i §6.6

**File**: `context/foundation/test-plan.md`

**Intent**: §6.1 staje się odpowiedzią na „jak dodać test logiki deterministycznej w tym projekcie”.

**Contract**: §6.1: test referencyjny (test M4 z fazy 4 — wzorzec metamorficzny — oraz test M5 — granica z czasami UTC wpisanymi ręcznie), wzorzec potwierdzenia mutacją (1. oczekiwana wartość z PRD / decyzji, 2. test zielony, 3. podłóż mutant przez skrypt lub mutmut → `KILLED`, 4. nowy mutant ręczny dopisz do listy), komendy: `uv run pytest`, `uv run python scripts/mutation/manual_mutants.py [ID]`, `uv run mutmut run` / `uv run mutmut results`, rejestr `scripts/mutation/accepted_survivors.md`. §6.6: 2–3 linie notatki z fazy (np. M1–M4 — zielone testy nie świadczyły o izolacji; czas przebiegu mutmut; dowód kanarkiem).

#### 3. Nieaktualne zapisy poza planem testów

**File**: `context/foundation/tech-stack.md`, `CLAUDE.md`

**Intent**: `tech-stack.md:35-37` mówi „CI tylko na PR”, a `CLAUDE.md` (notatki projektu) — „`main` auto-deploys” bez bramki. Po tej fazie oba są nieprawdziwe.

**Contract**: `tech-stack.md`: CI na PR i push do `main`, deploy po zielonym CI (Railway „Wait for CI”). `CLAUDE.md`, sekcja „TalkAItive — project notes” (poza blokiem `<!-- BEGIN/END @przeprogramowani/10x-cli -->`): `main` wdraża się po zielonym workflow `CI`; jedna linia z komendami mutacyjnymi i odnośnikiem do test-plan §6.1.

### Success Criteria:

#### Automated Verification:

- `grep -n "ochrona gałęzi" context/foundation/test-plan.md` nie pokazuje już wiersza bramki jako wymaganej ochrony gałęzi
- `grep -n "TBD — see §3 Phase 1" context/foundation/test-plan.md` nie zwraca nic
- Blok `<!-- BEGIN/END @przeprogramowani/10x-cli -->` w `CLAUDE.md` jest bez zmian (`git diff CLAUDE.md` dotyka tylko sekcji projektu)

#### Manual Verification:

- §5 i §6.1 czytane przez użytkownika jako jasna instrukcja „jak dodać test i potwierdzić go mutacją”

**Implementation Note**: Po fazie zmiana jest gotowa do `/10x-impl-review` i archiwizacji.

---

## Testing Strategy

### Unit Tests:

- Budżet: `is_final_turn` niezależny od cudzych tur (metamorficzny), `is_exhausted` przy zakończeniu limitem dokładnie o północy Berlin.
- Pamięć: granica okna 20/21, świeżość po czasie zakończenia, etykieta „najnowsza”.

### Integration Tests:

- Widoki (klient testowy Django, dwóch użytkowników): strona główna, start z `LLMError`, lista błędów na stronie rozmowy.
- Analiza: nieudana analiza jednej z dwóch rozmów; drugie żądanie w trakcie trwającej analizy.

### Mutation checks:

- Ręczna lista (C1, C2, M1–M13) — `scripts/mutation/manual_mutants.py`, lokalnie, okresowo.
- mutmut na 4 modułach — lokalnie, okresowo; „zaufany” = 0 niewyjaśnionych przeżyć.

### Manual Testing Steps:

1. Otwórz PR i sprawdź check `CI`.
2. Wypchnij commit z kanarkiem — Railway pokazuje `SKIPPED`, produkcja na poprzedniej wersji.
3. Wypchnij revert — deploy udany, `/healthz/` 200.

## Performance Considerations

Pełne `pytest` ~1,7 s; workflow CI z instalacją zależności około minuty — tyle wydłuża się czas od pushu do wdrożenia. Czas przebiegu mutmut nieznany do spike'a (forkowanie per mutant); nie wpływa na CI, bo mutmut jest lokalny.

## Migration Notes

Brak migracji danych. Zmiana ustawień Railway jest odwracalna przełącznikiem „Wait for CI”; jej kopia jest w `context/deployment/web-settings.json`.

## References

- Research: `context/changes/testing-suite-trust-and-ci/research.md`
- Plan testów: `context/foundation/test-plan.md` (§2 ryzyko #2, §3 Phase 1, §5, §6.1)
- PRD: `context/foundation/prd.md:46`, `:94`, `:107`, `:113-114`, `:117`
- Lessons: `context/foundation/lessons.md` (for_user, 404 na cudzy obiekt)
- Ustawienia Railway: `context/deployment/web-settings.json`, `context/deployment/deploy-plan.md:7`, `:150`
- Docs GitHub — protected branches i transfer repo (prywatne repo na koncie Free traci chronione gałęzie), sprawdzone 2026-10-14
- Docs Railway — GitHub autodeploys, „Wait for CI” (research §5)
- mutmut 3.8.0 — README/HISTORY (research §5), checked: 2026-10-14

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Spike — mutmut z pytest-django

#### Automated

- [ ] 1.1 `uv run mutmut run` kończy się bez błędu konfiguracji, a `uv run mutmut results` pokazuje mutanty z 4 modułów
- [ ] 1.2 Mutant `>=` → `>` w `is_exhausted` jest w wynikach mutmut zabity (kontrola sensu)
- [ ] 1.3 `uv run pytest` dalej 198 passed
- [ ] 1.4 `uv run ruff check .` i `uv run ruff format --check .` przechodzą mimo istniejącego katalogu `mutants/`

#### Manual

- [ ] 1.5 `mutmut-baseline.md` zawiera czas przebiegu, liczby i listę przeżywających mutantów, a użytkownik akceptuje decyzję go/no-go dla mutmut

### Phase 2: Próg CI i bramka Railway

#### Automated

- [ ] 2.1 `.github/workflows/ci.yml` przechodzi lokalnie te same kroki
- [ ] 2.2 `gh run list --workflow ci.yml` pokazuje zielony przebieg dla commita z workflow na `main`
- [ ] 2.3 `context/deployment/web-settings.json` jest poprawnym JSON-em, a obiekt `input` jest bajtowo taki sam jak przed zmianą

#### Manual

- [ ] 2.4 PR z dowolną zmianą pokazuje check `CI` (zielony)
- [ ] 2.5 Przełącznik „Wait for CI” jest włączony i po ponownym otwarciu ustawień dalej włączony
- [ ] 2.6 Commit z kanarkiem: workflow czerwony, deployment Railway `SKIPPED`, produkcja na poprzedniej wersji
- [ ] 2.7 Commit revert: workflow zielony, deployment udany, `/healthz/` zwraca 200

### Phase 3: Skrypt ręcznych mutantów

#### Automated

- [ ] 3.1 Skrypt raportuje C1, C2 i M9 jako `KILLED`, a M1–M8 i M10–M13 jako `SURVIVED`, kod wyjścia 1
- [ ] 3.2 Fragment, którego nie ma w pliku, kończy skrypt błędem
- [ ] 3.3 `git status` po przebiegu nie pokazuje zmian w `accounts/`, `conversations/`, `talkaitive/`
- [ ] 3.4 `uv run ruff check .` i `uv run ruff format --check .` przechodzą

### Phase 4: Testy izolacji i budżetu (M1–M5)

#### Automated

- [ ] 4.1 `uv run pytest` przechodzi (198 + nowe testy)
- [ ] 4.2 Skrypt raportuje M1, M2, M3, M4, M5 jako `KILLED`
- [ ] 4.3 Skrypt raportuje C1, C2, M9 dalej jako `KILLED`
- [ ] 4.4 `uv run ruff check .` i `uv run ruff format --check .` przechodzą
- [ ] 4.5 Workflow `CI` jest zielony na commicie tej fazy

#### Manual

- [ ] 4.6 Każdy nowy test ma źródło oczekiwanej wartości (PRD / decyzja) i nie powtarza wzoru z kodu

### Phase 5: Testy stanu analizy i pamięci (M6, M7, M10, M12, M13)

#### Automated

- [ ] 5.1 `uv run pytest` przechodzi
- [ ] 5.2 Skrypt kończy się kodem 0: M8, M11 `accepted`, pozostałe `KILLED`
- [ ] 5.3 `uv run ruff check .` i `uv run ruff format --check .` przechodzą
- [ ] 5.4 Workflow `CI` jest zielony na commicie tej fazy

#### Manual

- [ ] 5.5 Źródła oczekiwanych wartości w nowych testach są jawne, bez powtórzonych wzorów z kodu
- [ ] 5.6 `accepted_survivors.md` ma czytelne uzasadnienia M8 i M11

### Phase 6: Triage mutmut do stanu „zaufany”

#### Automated

- [ ] 6.1 Każdy przeżywający mutant z `uv run mutmut results` ma wpis w `accepted_survivors.md`
- [ ] 6.2 `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` przechodzą
- [ ] 6.3 Skrypt ręcznych mutantów dalej kończy się kodem 0
- [ ] 6.4 Workflow `CI` jest zielony na commicie tej fazy

#### Manual

- [ ] 6.5 Użytkownik akceptuje klasyfikację wpisów `brak wymagania` i `przekazany do fazy N`

### Phase 7: Plan testów i dokumenty

#### Automated

- [ ] 7.1 Wiersz bramki w test-plan §5 nie wymaga już ochrony gałęzi
- [ ] 7.2 `grep -n "TBD — see §3 Phase 1" context/foundation/test-plan.md` nie zwraca nic
- [ ] 7.3 Blok 10x-cli w `CLAUDE.md` jest bez zmian

#### Manual

- [ ] 7.4 §5 i §6.1 są jasną instrukcją „jak dodać test i potwierdzić go mutacją”
