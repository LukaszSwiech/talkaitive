# Rollout Phase 5 — warstwa evalu AI: plan implementacji

## Overview

Faza 5 z `context/foundation/test-plan.md` §3 (ryzyko #5). Research pokazał, że obecne testy nic nie mówią o jakości nauki: atrapy zwracają to, co test zakolejkował, a asercje „jakościowe” kończą się na „prompt zawiera napis X”. Plan buduje lokalny eval na prawdziwym modelu, uruchamiany ręcznie przed zmianą i po zmianie promptu, modelu albo reasoning effort: (1) deterministyczny rdzeń oceniania (dopasowanie do wzorca, twarde reguły, metryki, porównanie parami, licznik kosztu z limitem) przypięty zwykłymi testami w CI i ręcznymi mutantami, (2) zestaw wzorcowy z korpusu MERLIN (poprawki ekspertów, CC BY-SA 4.0) i skrypt `run` / `compare` z przebiegiem bazowym i przebiegiem na celowo zepsutym prompcie, (3) domknięcie test-planu i rejestru mutacji. Wynik porównania dwóch wersji to liczba z przedziałem, nie wrażenie.

## Current State Analysis

Źródło: `context/changes/testing-ai-eval-layer/research.md` (zweryfikowane w kodzie na `2978faf`).

- **Dwie ścieżki wywołań, obie bez bazy.** `llm.generate_turn(topic, language, history, final_turn, memory)` → `TurnResult` (`conversations/llm.py:284-354`) i `llm.analyze_mistakes(language, history)` → `AnalysisResult(mistakes, learner_facts, scene_notes, …)` (`llm.py:374-432`). Blok pamięci to tekst z `format_memory(Memory)` (`llm.py:217-256`). Precedens: review S-03 uruchomił 32 tury prawdziwym `generate_turn` bez zapisu do bazy (`context/archive/2026-10-07-cross-session-error-memory/reviews/impl-review.md:48`).
- **Reguły jakości są tylko w prompcie.** Tura: „at most the 1-2 most important … Do not explain rules and do not list mistakes”, „Ignore typos”, „Never interrupt the conversation with a lecture” (`llm.py:47-51`), jedno pytanie naraz (`llm.py:44`). Analiza: tylko wiadomości ucznia, trzy kategorie, bez literówek, `sentence` bez zmian, ≤ 5 faktów, ≤ 8 notatek z pytaniami partnera (`llm.py:73-100`). Zbiór kategorii wymusza schemat (`llm.py:121`), trafności kategorii nic nie sprawdza.
- **Testy nie mierzą jakości.** Atrapy: `tests/test_llm.py:55-66`, `tests/fake_provider.py:85-113`, `tests/fakes.py:23-56`. Testy brzmienia promptu: `tests/test_llm.py:129-139`, `:192-204`, `:471-487`. 0 trafień `typo|recast|lecture` w `tests/`.
- **Szum zmierzony:** ta sama 20-turowa rozmowa z `medium` dała 12 i 18 pozycji; `high` zgłaszał literówki (`context/archive/2026-10-06-post-conversation-error-list/change.md:14`, `talkaitive/settings.py:69-72`).
- **Budżet nie dotyczy evalu:** `spent_today` czyta tylko wiersze `Message`, `Conversation`, `LLMCharge` (`conversations/budget.py:64-81`); eval wołający `llm.*` wprost żadnych nie tworzy.
- **Izolacja od CI:** CI uruchamia `uv run pytest` (`.github/workflows/ci.yml:30`), pytest zbiera `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, bez markerów (`pyproject.toml:33-37`); `settings_test` ustawia `OPENAI_API_KEY = "test-key"` (`talkaitive/settings_test.py:15-16`).
- **Precedens skryptu lokalnego:** `scripts/mutation/manual_mutants.py` (docstring z użyciem i kodami wyjścia 0 / 1 / 2, tabela wyników, `main(argv) -> int`).
- **mutmut** kopiuje do `mutants/` tylko `source_paths` (`accounts`, `conversations`, `talkaitive`), `also_copy` (`manage.py`) i katalogi testów (`pyproject.toml` `[tool.mutmut]`; dokumentacja mutmut, Context7 `/boxed/mutmut`, 2026-10-17). Ręczne mutanty kończą się na `M34`.
- **Przeżyty mutant `memory._mistakes__mutmut_47`** (wyjaśnienie → `None` w bloku pamięci) jest w rejestrze jako `brak wymagania` z odesłaniem do tej fazy (`scripts/mutation/accepted_survivors.md:79`), choć plan S-03 wprost ustalił wyjaśnienie z najnowszego wystąpienia w bloku pamięci (`context/archive/2026-10-07-cross-session-error-memory/plan.md:143`, `:210`).

## Desired End State

- `uv run --env-file .env python scripts/eval/run_eval.py run` uruchamia na prawdziwym modelu cztery serie — analiza, tura, pamięć, długa analiza — każdy przypadek K=3 razy (długa analiza raz), zatrzymuje się przed przekroczeniem 5 USD i zapisuje wynik do `scripts/eval/results/`. Kod 0: przebieg pełny, 0 naruszeń twardych reguł i 0 błędów wywołań; 1: pełny, ale z naruszeniami albo błędami (wypisane z id przypadku); 2: konfiguracja, brak prawdziwego klucza albo limit kosztu.
- `run_eval.py compare A.json B.json` drukuje dla każdej metryki wartość A i B, różnicę sparowaną per przypadek z 95% przedziałem i werdyktem („różnica” albo „w granicach szumu”) oraz przypadki, które zmieniły wynik.
- Zestaw wzorcowy pochodzi z MERLIN: zdania uczniów B1/B2 dosłownie, poprawne formy z wersji poprawionej przez ekspertów, kategorie przypisane wg reguły, poprawki pisowni i interpunkcji jako literówki, których nie wolno zgłosić; plik ma atrybucję i licencję CC BY-SA 4.0.
- Kod oceniania (dopasowanie, reguły, metryki, porównanie, licznik kosztu) i spójność zestawu mają zwykłe testy w `tests/` — działają w CI bez klucza; każde zachowanie oceniacza pada na swoim ręcznym mutancie.
- Przebieg bazowy na obecnym kodzie leży w repo jako punkt odniesienia; przebieg na celowo zepsutym prompcie pokazał, że eval wykrywa pogorszenie.
- `memory._mistakes__mutmut_47` jest zabity zwykłym testem, wiersz rejestru usunięty.
- Test-plan: §3 Phase 5 `complete`, §4 i §5 opisują eval, §6.5 ma cookbook, §6.6 notatkę z wynikiem bazowym i pomiarem czasu długiej analizy (zamyka sprawę przekazaną z Phase 2).

### Key Discoveries:

- Tura poprawia najwyżej 1–2 błędy (`llm.py:47-48`), więc przypadek tury z kilkoma błędami nie ma jednej poprawnej odpowiedzi — przypadki tury mają dokładnie jeden wyraźny błąd.
- Analiza widzi cały transkrypt (`[n] Learner:` / `Partner:`, `llm.py:361-371`), więc przypadki analizy to krótkie rozmowy, nie pojedyncze zdania — kształt jak na produkcji i mniej wywołań.
- `wrong` bywa dłuższy niż „najkrótszy fragment” (S-02 `change.md:14`), więc dopasowanie musi być tolerancyjne (numer wiadomości + słowo kluczowe), nie porównaniem całych napisów.
- Analiza ma dwie role: lista błędów i notatki do pamięci (`llm.py:91-100`); strojenie listy może niechcący usunąć z notatek pytania partnera — seria analizy sprawdza też notatki, w tych samych wywołaniach.
- Responses API nie ma `seed`, `temperature` działa tylko przy effort `none` (research, §Zewnętrzne fakty); produkcja nie ustawia ani jednego (`llm.py:301-308`, `:386-393`), więc eval też nie.
- Plik `merlin-text-v1.1.zip` (5,78 MB, MD5 `93c99fad2795ad2f2a30d2f36d496497`) z repozytorium CLARIN Eurac (http://hdl.handle.net/20.500.12124/6, „Publicly Available”, CC BY-SA 4.0) zawiera tekst ucznia, metadane i wersję poprawioną (target hypothesis), bez adnotacji kategorii błędów (opis paczki, sprawdzone 2026-10-17). Wersja 1.2 (handle `/59`) stoi za ochroną przed botami — nie obchodzimy jej.
- `.gitignore` sam jest w `.gitignore` (CLAUDE.md), więc wpisy w nim nie trafiają do commita — nie da się na nim oprzeć, że plik wyników nie zostanie zacommitowany.

## What We're NOT Doing

- **Sędzia LLM** w tej wersji (decyzja w planowaniu) — naturalność recastu ocenia użytkownik, czytając przypadki, które zmieniły wynik.
- **Eval w CI, w hooku przed pushem, na każdym commicie ani cyklicznie** — tylko ręcznie przed zmianą i po zmianie promptu tury, promptu analizy, tekstu bloku pamięci, `LLM_MODEL` albo reasoning effort (decyzja w planowaniu). Ryzyko: zmiana modelu u dostawcy pod tą samą nazwą zostaje niewykryta (Open Risks w briefie).
- **Zmiany promptów i modelu** — przebieg bazowy mierzy obecny kod; znalezione słabości trafiają do notatki w §6.6, poprawki to osobne zmiany.
- **Prawdziwość faktów o uczniu** (`learner_facts` „only what the learner actually said”) — sprawdzamy tylko limit liczby.
- **Język angielski** — ryzyko i zestaw dotyczą niemieckiego.
- **Najgorszy przypadek czasu analizy** (wiadomości po 2000 znaków) — jedna realistyczna długa rozmowa.
- **Równoległe wywołania** — po kolei, żeby limit kosztu był dokładny; przebieg trwa ok. 20–35 min.
- **DeepEval, promptfoo, OpenAI Evals API** (research §10–§11).
- **Archiwum MERLIN w repo** i formaty z adnotacjami (PAULA, EXMARaLDA) — tylko wybrane, przerobione zdania w pliku danych.
- **Kod oceniania w `[tool.mutmut]` `only_mutate`** — zachowania oceniacza potwierdzają celowane ręczne mutanty; mutmut tylko musi dalej działać.
- **Testy brzmienia promptu** (`tests/test_llm.py:138-139`, `:199-204`) bez zmian — przy przyszłym strojeniu aktualizowane świadomie w diffie.

## Implementation Approach

Najpierw tani i deterministyczny rdzeń oceniania z testami w CI (faza 1), bo płatne przebiegi na błędnym oceniaczu przepalałyby limit i dawały fałszywe liczby. Potem zestaw z MERLIN i skrypt na prawdziwym modelu (faza 2). Na końcu domknięcie (faza 3). Zasada wyroczni (`test-plan.md` §1, §6.1 krok 1): poprawne formy pochodzą od ekspertów MERLIN, kategorie z reguły podręcznikowej, progi i limity z decyzji (PRD, plany S-01…S-03, ten plan) — nigdy z wyniku aplikacji ani z gpt-5.4. Oczekiwane liczby w testach oceniacza są wpisane ręcznie z rachunkiem w komentarzu, nie liczone funkcjami oceniacza. Sam eval potwierdzamy celowym zepsuciem promptu, tak jak testy klasyczne potwierdzamy mutantem.

## Branches and PRs

Jedna gałąź `testing-ai-eval-layer` (już istnieje) i jeden PR dla wszystkich faz — plan nie zmienia kodu produkcyjnego (tylko `scripts/`, `tests/`, konfigurację mutmut i dokumenty), więc wdrożenie z `main` nie zmienia zachowania aplikacji.

## Critical Implementation Details

- **mutmut i import `scripts`:** testy w `tests/` importują `scripts.eval.*`; bez `scripts` w `[tool.mutmut]` `also_copy` kopia w `mutants/` nie ma tego katalogu i przebieg mutmut pada już na zbieraniu testów. Zmiana w `pyproject.toml` wchodzi w fazie 1, razem z pierwszym takim testem.
- **Kolejność startu skryptu:** `DJANGO_SETTINGS_MODULE=talkaitive.settings` i `django.setup()` przed importem `conversations.llm` (moduł importuje `accounts.models`, `llm.py:31`). Pliki w `scripts/eval/` nie mogą pasować do `test_*.py`.
- **Strażnik klucza przed jakimkolwiek wywołaniem:** pusty `OPENAI_API_KEY` albo `"test-key"` (wartość z `settings_test`) → kod 2 bez wywołania modelu. Klucza nigdy nie drukujemy ani nie zapisujemy.
- **Koszt jak w aplikacji:** udany wynik po `usage` (`budget.turn_cost`), `LLMError.usage` po `usage`, `billed_without_usage` szacunkiem (`LLM_TURN_COST_ESTIMATE_USD` / `LLM_ANALYSIS_COST_ESTIMATE_USD`), szybka odmowa 0 (`llm.py:155-196`, `test-plan.md` §6.4). Sprawdzenie limitu przed każdym wywołaniem: wydane + szacunek tego wywołania ≤ limit.
- **Pobrany korpus to dane niezaufane:** własny, nowy, pusty katalog poza repo; czytanie zwykłymi narzędziami tekstowymi; żadnego uruchamiania plików z paczki; sprawdzenie MD5.
- **Celowe zepsucie promptu** robimy w drzewie roboczym i cofamy `git checkout conversations/llm.py`; skrypt oznacza taki przebieg jako `dirty`, a jego pliku wyników nie commitujemy.

## Faza 1: Rdzeń oceniania i testy w CI (#5)

### Overview

Deterministyczny kod oceniania i licznik kosztu w `scripts/eval/`, przypięte testami w `tests/` (CI, bez klucza i sieci) i ręcznymi mutantami; mutmut działa z nowym importem; mutant `mutmut_47` zabity zwykłym testem.

### Changes Required:

#### 1. Typy zestawu wzorcowego

**File**: `scripts/eval/golden.py` (nowy; w tej fazie same typy, dane w fazie 2), `scripts/__init__.py`, `scripts/eval/__init__.py` (nowe, puste)

**Intent**: Jeden kształt danych dla wszystkich serii, z którego korzysta oceniacz, testy i skrypt.

**Contract**: zamrożone dataclassy:
- `GoldMistake(message: int, wrong_key: str, correct_key: str, categories: frozenset[str], rule: str, source: str)` — `wrong_key` / `correct_key` to najkrótsze słowa kluczowe błędu i poprawki, `categories` dopuszcza 1–2 kategorie dla przypadków granicznych, `source` = id tekstu MERLIN;
- `Typo(message: int, token: str, source: str)` (pisownia, wielka litera, interpunkcja — nie wolno zgłosić) i `Neutral(message: int, token: str, source: str)` (poprawka MERLIN niejednoznaczna, np. `dass` / `das` — ani plus, ani minus);
- `AnalysisCase(id, history: tuple[tuple[str, str], ...], mistakes, typos, neutrals, correct_messages: tuple[int, ...], partner_questions: tuple[tuple[str, ...], ...])` — numery wiadomości liczą tylko wiadomości ucznia od 1 (jak `llm.py:361-371`); `partner_questions` to grupy słów kluczowych pytań partnera;
- `TurnCase(id, topic_key, history, wrong_form, correct_forms: tuple[str, ...], category, rule, source)` — ostatnia wiadomość historii to wiadomość ucznia z jednym błędem;
- `MemoryCase(id, topic_key, scene_notes: tuple[tuple[str, ...], ...], forbidden: tuple[tuple[str, ...], ...])` — notatki z pytaniami już zadanymi, grupy słów kluczowych tych pytań po niemiecku;
- stałe `ANALYSIS_CASES`, `TURN_CASES`, `MEMORY_CASES`, `LATENCY_CASE` (puste w fazie 1).

#### 2. Oceniacz

**File**: `scripts/eval/scoring.py` (nowy)

**Intent**: Z wyniku modelu i wzorca liczy twarde naruszenia i metryki per przypadek, agreguje je i porównuje dwa przebiegi parami.

**Contract**:
- `normalize(text)`: `casefold`, zwinięte białe znaki, bez `...` / `…`.
- `score_analysis(case, result: AnalysisResult)`: każda znaleziona pozycja dopasowana do pierwszego niedopasowanego `GoldMistake` z tym samym `message_number`, gdy znormalizowany `wrong` zawiera `wrong_key`, a `correct` zawiera `correct_key` (jedna pozycja ↔ jeden wzorzec). Naruszenia: **A1** numer spoza `1..N` albo słowa `wrong` nieobecne w tej wiadomości ucznia (`llm.py:73-74`); **A2** `sentence` nie jest fragmentem tej wiadomości ucznia (`llm.py:84-85`); **A3** niedopasowana pozycja zawiera `Typo.token` tej wiadomości (`llm.py:76`, S-02 `plan-brief.md:29`); **A4** pozycja w wiadomości z `correct_messages`; **A5** `learner_facts` > 5 albo `scene_notes` > 8 (S-03 `reviews/impl-review.md:38`). Pozostałe niedopasowane: zawierające `Neutral.token` → neutralne, reszta → `extras` (lista do przeglądu). Metryki per powtórzenie: `recall` = dopasowane / wzorce, `category_accuracy` = trafna kategoria / dopasowane (brak, gdy 0 dopasowanych), `extras` (liczba), `typo_free` (1, gdy brak A3), `notes_questions` = grupy `partner_questions` z trafieniem w którejś notatce / wszystkie grupy.
- `score_turn(case, result: TurnResult)`: `recast` = odpowiedź zawiera którąś `correct_forms` i nie zawiera `wrong_form`; `lecture_free` = brak trafień ze stałej `LECTURE_MARKERS` (terminy metajęzykowe DE/EN i zwroty jawnej korekty, np. „Grammatik”, „Dativ”, „Fehler”, „richtig wäre”, „es heißt”, „du meinst”, „grammar”; dopasowanie po granicy słowa; źródło typologii: Lyster i Ranta 1997 w research); `one_question` = najwyżej jeden znak `?` (S-01 `plan.md:199`); naruszenie **T1**: `end_conversation` = `true` (`llm.py:56-57`).
- `score_memory(case, result: TurnResult)`: `no_repeat` = żadna grupa `forbidden` nie trafia w odpowiedź; **T1** jak wyżej.
- Agregacja: wartość metryki per przypadek = średnia z K powtórzeń; wartość przebiegu = średnia przypadków; naruszenia jako lista `(rodzaj, id przypadku, powtórzenie, szczegół)`.
- `compare(a, b)`: dla każdej metryki przypadki wspólne obu przebiegów, `Δ_i = b_i − a_i`, średnia Δ, błąd standardowy `stdev(Δ) / sqrt(n)` (brak przy n < 2), przedział `Δ ± 1,96·SE`, werdykt „różnica”, gdy przedział nie obejmuje zera; lista przypadków z `Δ_i ≠ 0` malejąco po `|Δ_i|`; przypadki obecne tylko w jednym przebiegu zgłoszone osobno.

#### 3. Licznik kosztu z limitem

**File**: `scripts/eval/cost.py` (nowy)

**Intent**: Eval omija dzienny budżet aplikacji, więc sam liczy wydatek tak jak aplikacja i nie zaczyna wywołania, które mogłoby przekroczyć limit.

**Contract**: `CostMeter(cap_usd: Decimal)`; `charge_result(result)` → `budget.turn_cost` z tokenów; `charge_error(error: LLMError, kind: Literal["turn", "analysis"])` → `usage` po cenie, `billed_without_usage` szacunkiem z ustawień, inaczej 0; `can_start(kind)` → `spent + szacunek(kind) <= cap`; `spent` jako `Decimal`.

#### 4. mutmut: `scripts` w kopii

**File**: `pyproject.toml`

**Intent**: Przebieg mutmut nie pada na imporcie `scripts.eval` z testów.

**Contract**: `[tool.mutmut]` `also_copy = ["manage.py", "scripts"]` z komentarzem dlaczego; `only_mutate` bez zmian.

#### 5. Testy oceniacza i licznika

**File**: `tests/test_eval_scoring.py` (nowy)

**Intent**: Zachowanie oceniacza przypięte na ręcznie napisanych wynikach modelu (`FoundMistake`, `AnalysisResult`, `TurnResult` budowane w teście), z oczekiwanymi liczbami wpisanymi ręcznie.

**Contract**: przypadki co najmniej:
- dopasowanie tolerancyjne: wzorzec `habe` / `bin`, pozycja `wrong="habe ... gegangen"`, `correct="bin ... gegangen"` → dopasowana; ta sama pozycja z innym numerem wiadomości → niedopasowana;
- dwie pozycje na jeden wzorzec → jedna dopasowana, druga w `extras`;
- A1 (pozycja z tekstu partnera i numer spoza zakresu), A2 (zmienione `sentence`), A3 (zgłoszona literówka), A4 (pozycja w zdaniu poprawnym), A5 (6 faktów, 9 notatek), pozycja neutralna nie liczy się do `extras`;
- trafna i nietrafna kategoria, kategoria graniczna z dwoma dopuszczalnymi; pusta lista → `recall` 0, brak naruszeń, `category_accuracy` brak;
- `notes_questions` dla 1 z 2 grup;
- tura: poprawna forma wpleciona; odpowiedź powtarza błędną formę; znacznik wykładu (w tym przypadek graniczny: słowo z listy jako część innego słowa nie trafia); dwa pytania; `end_conversation=True` → T1;
- pamięć: zakazane słowo kluczowe trafia / nie trafia;
- agregacja K=3 i `compare` na małym przykładzie: oczekiwana średnia Δ, SE i werdykt z rachunkiem w komentarzu; przypadek tylko w jednym przebiegu zgłoszony;
- licznik: ceny przypięte w fixture (`LLM_PRICES_USD_PER_MTOK`, szacunki 0,03 / 0,07) jak w §6.4; koszt udanego wyniku, `LLMError` z `usage`, z `billed_without_usage`, bez obu; `can_start` na brzegu (dokładnie limit → tak, ponad → nie).

#### 6. Test na `mutmut_47` i rejestr

**File**: `tests/test_memory.py`, `scripts/mutation/accepted_survivors.md`

**Intent**: Wyjaśnienie pary widzianej w jednej rozmowie trafia do pamięci (decyzja S-03 `plan.md:143`, `:210`), więc przeżyty mutant przestaje być „brakiem wymagania”.

**Contract**: test: użytkownik z jedną przeanalizowaną rozmową i jednym błędem z wyjaśnieniem → `select_memory(...).mistakes[0].explanation` równe temu wyjaśnieniu (literał w teście, źródło w docstringu). Po potwierdzeniu w mutmut wiersz `conversations.memory.x__mistakes__mutmut_47` usunięty z rejestru.

#### 7. Ręczne mutanty oceniacza

**File**: `scripts/mutation/manual_mutants.py`

**Intent**: Każde zachowanie oceniacza, na którym opiera się liczba z evalu, ma mutanta, na którym test pada (`test-plan.md` §6.1 krok 4).

**Contract**: nowe mutanty od `M35` (`expected="killed"`), co najmniej: dopasowanie bez sprawdzania numeru wiadomości; wyłączone A3 (literówka liczona jako zwykła pozycja); wyłączone A2; `compare` z werdyktem „różnica” bez względu na SE; licznik bez szacunku dla `billed_without_usage`; `can_start` bez szacunku następnego wywołania. Każdy `original` występuje w pliku dokładnie raz.

### Success Criteria:

#### Automated Verification:

- Testy oceniacza i pamięci przechodzą: `uv run pytest tests/test_eval_scoring.py tests/test_memory.py`
- Cały zestaw przechodzi bez klucza i sieci: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Nowe ręczne mutanty oceniacza zabite (kod 0): `uv run python scripts/mutation/manual_mutants.py <nowe ID>`
- mutmut działa z importem `scripts`, a `memory._mistakes__mutmut_47` jest zabity: `rm -rf mutants && uv run mutmut run && uv run mutmut results`

#### Manual Verification:

- Przegląd testów oceniacza: oczekiwane liczby mają rachunek w komentarzu i nie pochodzą z funkcji oceniacza

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie przeglądu, zanim zaczniesz fazę 2.

---

## Faza 2: Zestaw z MERLIN i skrypt na prawdziwym modelu (#5)

### Overview

Pobranie paczki MERLIN za zgodą użytkownika, zestaw wzorcowy czterech serii z atrybucją, skrypt `run` / `compare` ze strażnikiem klucza i limitem kosztu, przebieg bazowy na obecnym kodzie i przebieg na celowo zepsutym prompcie.

### Changes Required:

#### 1. Pobranie i przygotowanie MERLIN

**File**: brak w repo (katalog poza repo)

**Intent**: Wyrocznia poprawnych form spoza ocenianego modelu.

**Contract**: przed pobraniem zgoda użytkownika na `merlin-text-v1.1.zip` (5,78 MB, CLARIN Eurac, http://hdl.handle.net/20.500.12124/6); MD5 `93c99fad2795ad2f2a30d2f36d496497`; nowy pusty katalog poza repo; jeśli strona pokaże ochronę przed botami, pobiera użytkownik w przeglądarce i podaje ścieżkę. Najpierw README i kilka plików, żeby poznać format; wybór tekstów niemieckich z oceną B1/B2 z metadanych.

#### 2. Zestaw wzorcowy

**File**: `scripts/eval/golden.py`

**Intent**: Stały zestaw przypadków ze znanymi błędami, literówkami i pytaniami.

**Contract**:
- docstring modułu: atrybucja „MERLIN Written Learner Corpus for Czech, German, Italian 1.1 (Wisniewski i in., Eurac Research), http://hdl.handle.net/20.500.12124/6, CC BY-SA 4.0”, opis adaptacji i informacja, że plik z danymi jest udostępniony na CC BY-SA 4.0;
- klasyfikacja różnic tekst ucznia ↔ wersja poprawiona: jednoznaczny błąd reguły → `GoldMistake` (kategoria wg reguły, `rule` nazwany; druga kategoria tylko, gdy sama reguła jest niejednoznaczna — review fazy 1 F6); pisownia, wielka litera, interpunkcja bez zmiany sensu → `Typo`; reszta → `Neutral`; zdania ucznia dosłownie z błędami, poprawne formy z wersji poprawionej;
- `ANALYSIS_CASES`: ok. 12 krótkich rozmów po 4–6 wiadomości ucznia z MERLIN i wiadomości partnera napisane po niemiecku (B1–B2, poprawne), łącznie ok. 36 wzorców z możliwie równym udziałem kategorii, w każdej rozmowie ≥ 1 literówka, ≥ 1 wiadomość poprawna i 2 pytania partnera; w co najmniej 2 rozmowach błąd podłożony w wiadomości partnera (A1);
- `TURN_CASES`: ok. 20 przypadków z jednym wyraźnym błędem, scena z `conversations/topics.py` pasująca do treści rozmowy, kategorie możliwie po równo; `wrong_form` obejmuje też echo partnera w 2. osobie (np. `hast … gegangen`), w razie potrzeby `TurnCase.wrong_form` → `wrong_forms: tuple[str, ...]` (review fazy 1 F6);
- `MEMORY_CASES`: ok. 5 przypadków (różne sceny), notatki po angielsku jak w prompcie analizy (`llm.py:98`), 2–3 zadane pytania na przypadek;
- `LATENCY_CASE`: jedna rozmowa ok. 40 wiadomości (ok. 20 wiadomości ucznia z MERLIN), bez wzorca.

#### 3. Skrypt `run` / `compare`

**File**: `scripts/eval/run_eval.py` (nowy)

**Intent**: Jedno polecenie, które uruchamia serie na prawdziwym modelu, pilnuje kosztu i zapisuje porównywalny wynik; drugie, które porównuje dwa wyniki.

**Contract**:
- docstring jak w `manual_mutants.py`: użycie, serie, koszt, kody wyjścia;
- `main(argv) -> int`; `run [--suite analysis,turn,memory,latency] [--repeats 3] [--max-usd 5] [--out PATH]` i `compare A.json B.json`;
- start: `DJANGO_SETTINGS_MODULE=talkaitive.settings`, `django.setup()`, strażnik klucza (kod 2);
- przed startem wydruk liczby wywołań per seria, szacunku kosztu i limitu;
- pętla: powtórzenia na zewnątrz, serie po kolei, przed każdym wywołaniem `CostMeter.can_start`; po przekroczeniu zapis wyniku częściowego z `"complete": false` i kod 2; `LLMError` liczony w koszcie i zapisany jako błąd przypadku; czas każdego wywołania (`time.monotonic`); długa analiza raz na przebieg, z czasem, kosztem i ewentualnym błędem (timeout analizy 150 s z ustawień, limit proxy Railway 300 s z `context/foundation/infrastructure.md:72` jako stałe raportu);
- wynik JSON: data, commit, `dirty`, `LLM_MODEL`, oba efforty, skróty sha256 instrukcji tury i analizy oraz bloku pamięci dla stałej próbki, K, limit, wydatek, `complete`, informacja o licencji danych, per przypadek i powtórzenie surowe wyjście modelu, naruszenia, metryki, koszt, czas, błąd; agregaty;
- nazwa pliku `scripts/eval/results/<RRRR-MM-DD>-<model>-<commit>[-dirty].json`;
- wydruk: tabela metryk, lista naruszeń z id przypadku, koszt, czas, wynik długiej analizy;
- kody: 0 pełny bez naruszeń i błędów, 1 pełny z naruszeniami lub błędami, 2 konfiguracja / klucz / limit;
- `compare`: tabela z `scoring.compare`, ostrzeżenie, gdy model i skróty promptów są identyczne albo zbiory przypadków się różnią; kod 0, kod 2 przy złym pliku.

#### 4. Testy zestawu i skryptu

**File**: `tests/test_eval_golden.py`, `tests/test_eval_runner.py` (nowe)

**Intent**: Zestaw jest wewnętrznie spójny, a skrypt nigdy nie woła modelu bez prawdziwego klucza i zatrzymuje się na limicie — sprawdzane w CI bez sieci.

**Contract**:
- spójność zestawu: unikalne id; numery wiadomości w zakresie; `wrong_key`, `Typo.token`, `Neutral.token` występują w swojej wiadomości ucznia jako całe słowa; `correct_key` ≠ `wrong_key`; klucze `wrong_key` wzorców jednej wiadomości nie nakładają się (dopasowanie jest zachłanne, review fazy 1 F4); kategorie z dozwolonego zbioru; `source` niepuste; wiadomości z `correct_messages` bez wzorców, literówek i neutralnych; słowa `partner_questions` występują w wiadomościach partnera; w turze ostatnia wiadomość jest ucznia, zawiera `wrong_form`, a żadna `correct_forms` nie zawiera `wrong_form`; `topic_key` istnieje w `conversations/topics.py`; `LATENCY_CASE` ≥ 40 wiadomości; minimalna liczba wzorców na kategorię ustalona przy budowie zestawu i wpisana w test; docstring zawiera „CC BY-SA 4.0” i handle MERLIN;
- skrypt: `main(["run"])` pod `settings_test` → kod 2, bez wywołania `generate_turn` / `analyze_mistakes` (atrapy, które rzucają przy wywołaniu); z kluczem nadpisanym na wartość inną niż testowa i atrapami `llm.*` zwracającymi wyniki o znanym koszcie — limit zatrzymuje przebieg przed przekroczeniem, wynik częściowy ma `"complete": false`, kod 2; `compare` na dwóch ręcznie napisanych plikach w `tmp_path` → oczekiwana Δ w wydruku; nazwa pliku wyników z daty, modelu, commita i `dirty` jako literał.

#### 5. Przebieg bazowy i przebieg na zepsutym prompcie

**File**: `scripts/eval/results/<plik bazowy>.json` (commitowany); plik przebiegu na zepsutym prompcie nie jest commitowany

**Intent**: Punkt odniesienia dla następnej zmiany promptu lub modelu i dowód, że eval wykrywa pogorszenie.

**Contract**:
- bazowy: `uv run --env-file .env python scripts/eval/run_eval.py run` na czystym drzewie (K=3, limit 5 USD);
- zepsuty prompt: w `conversations/llm.py` zamiana reguły literówek w obu promptach na odwrotną („report typos and punctuation as mistakes”) i reguły korekty tury na jawne wyjaśnianie reguły; `run --suite analysis,turn --repeats 1`; `compare <bazowy> <zepsuty>`; `git checkout conversations/llm.py`;
- oczekiwanie: `typo_free` analizy albo `lecture_free` tury spada z werdyktem „różnica”; jeśli nie, eval nie wykrywa tego pogorszenia — stop i rewizja zestawu lub znaczników przed fazą 3.

### Success Criteria:

#### Automated Verification:

- Testy zestawu i skryptu przechodzą: `uv run pytest tests/test_eval_golden.py tests/test_eval_runner.py`
- Cały zestaw przechodzi bez klucza i sieci: `uv run pytest`
- pytest nie zbiera niczego z `scripts/`: `uv run pytest --collect-only -q | grep -c '^scripts/'` zwraca 0
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Pobranie MERLIN za zgodą użytkownika, MD5 zgodne, archiwum poza repo
- Przegląd próbki zestawu (3 rozmowy analizy, 5 przypadków tury, 2 pamięci): zdania ucznia dosłownie z MERLIN, poprawne formy z wersji poprawionej, kategorie z nazwaną regułą, atrybucja w pliku
- Przebieg bazowy kończy się kodem 0 albo 1, wydatek ≤ 5 USD, plik wyników zapisany; naruszenia (jeśli są) i czas długiej analizy zapisane do notatki fazy
- Przebieg na zepsutym prompcie i `compare` pokazują spadek `typo_free` albo `lecture_free` z werdyktem „różnica”; prompt przywrócony (`git status` czysty dla `conversations/llm.py`)

**Implementation Note**: Po zielonej weryfikacji automatycznej poczekaj na potwierdzenie pobrania, przeglądu zestawu i obu przebiegów, zanim zaczniesz fazę 3.

---

## Faza 3: Domknięcie

### Overview

Wzorzec evalu w cookbooku test-planu, opis w §4 i §5, notatka fazy z wynikiem bazowym i pomiarem czasu długiej analizy, linia w CLAUDE.md, pełne przebiegi mutacji.

### Changes Required:

#### 1. Test-plan

**File**: `context/foundation/test-plan.md`

**Intent**: Następny autor zmiany promptu lub modelu wie, kiedy i jak uruchomić eval i jak czytać wynik; status fazy jest aktualny.

**Contract**:
- §3 wiersz 5: Status `complete`;
- §4 wiersz „AI-native eval”: skrypt `scripts/eval/` bez biblioteki, `checked:` z datą; DeepEval odradzany (wtyczka `pytest11` w każdym `uv run pytest` i w CI, domyślna telemetria); zestaw z MERLIN 1.1 (CC BY-SA 4.0); „When NOT to use” bez zmian;
- §5 wiersz „AI eval”: lokalnie, ręcznie przed zmianą i po zmianie promptu tury, promptu analizy, tekstu bloku pamięci, `LLM_MODEL` albo reasoning effort; Required: wired (lokalnie, nie w CI);
- §6.5 (zamiast „TBD”): kiedy uruchamiać (5 wyzwalaczy, tylko ręcznie) i ile to kosztuje (pełny przebieg do ok. 3,4 USD, limit 5 USD, ok. 20–35 min; tańsze `--suite`, `--repeats 1`); tryb pracy przy strojeniu (tanie próby na zmienianej serii, pełny K=3 przed merge); jak dodać przypadek (źródło MERLIN, klasyfikacja wzorzec / literówka / neutralne, test spójności); `run` i `compare`; jak czytać wynik (różnica sparowana z przedziałem, przypadki zmienione, naruszenia twarde, kody wyjścia); aktualizacja pliku bazowego po przyjętej zmianie; wzorzec celowego zepsucia promptu; testy wzorcowe z tej fazy;
- §6.6: notatka „Phase 5 — AI eval layer (data)”: wynik bazowy, wynik przebiegu na zepsutym prompcie, czas i koszt długiej analizy względem 150 s i 300 s (sprawa z Phase 2 zamknięta), znalezione słabości obecnych promptów (bez poprawek), wynik mutacji;
- §8: „AI-native tool references last verified” na datę domknięcia.

#### 2. CLAUDE.md

**File**: `CLAUDE.md`

**Intent**: Agent wie, że eval istnieje, nie jest częścią `uv run pytest` i kiedy go uruchomić.

**Contract**: jeden punkt w sekcji „TalkAItive — project notes”, obok punktu o mutacjach: polecenia `run` / `compare` z `--env-file .env`, „lokalnie i ręcznie, nigdy w CI”, wyzwalacze, koszt, odesłanie do test-planu §6.5. Bez zmian w bloku `<!-- BEGIN/END @przeprogramowani/10x-cli -->`.

#### 3. Mutacje — pełny przebieg

**File**: `scripts/mutation/accepted_survivors.md`

**Intent**: Bramka mutacji z §5: 0 niewyjaśnionych przeżyć po zmianach tej fazy.

**Contract**: `rm -rf mutants/`, `uv run mutmut run`, `uv run mutmut results`; każde przeżycie zabite testem albo z wierszem w rejestrze; cała lista ręczna kończy się kodem 0.

### Success Criteria:

#### Automated Verification:

- Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py`
- Każde przeżycie mutmut ma wiersz w rejestrze: `rm -rf mutants && uv run mutmut run && uv run mutmut results`
- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

- Przegląd §3, §4, §5, §6.5, §6.6 i §8 test-planu oraz punktu w CLAUDE.md: zgodne z decyzjami tego planu

**Implementation Note**: Po zielonej weryfikacji poczekaj na potwierdzenie przeglądu; PR i push wykonuje użytkownik.

---

## Testing Strategy

### Unit Tests:

- Oceniacz: dopasowanie tolerancyjne i jeden-do-jednego, A1–A5, T1, pozycje neutralne, kategorie graniczne, pusta lista, metryki tury i pamięci, agregacja K, `compare` (Δ, SE, werdykt, przypadki tylko w jednym przebiegu).
- Licznik kosztu: udany wynik, `LLMError` z `usage`, z `billed_without_usage`, bez obu; brzeg limitu.
- Pamięć: wyjaśnienie pary z jednej rozmowy w `select_memory` (mutant `mutmut_47`).
- Spójność zestawu wzorcowego.

### Integration Tests:

- Skrypt pod `settings_test`: kod 2 bez wywołania modelu.
- Skrypt z atrapami `llm.*` o znanym koszcie: zatrzymanie na limicie, wynik częściowy, kod 2.
- `compare` na dwóch plikach wyników.

### Manual Testing Steps:

1. Zgoda i pobranie `merlin-text-v1.1.zip`, sprawdzenie MD5, rozpakowanie w nowym katalogu poza repo.
2. Przegląd próbki zestawu (atrybucja, zdania dosłownie, poprawne formy, kategorie z regułą).
3. `uv run --env-file .env python scripts/eval/run_eval.py run` — kod 0 albo 1, wydatek ≤ 5 USD, plik w `scripts/eval/results/`.
4. Zepsuty prompt w `conversations/llm.py`, `run --suite analysis,turn --repeats 1`, `compare <bazowy> <zepsuty>` — werdykt „różnica” dla `typo_free` albo `lecture_free`; `git checkout conversations/llm.py`.
5. Przeczytać przypadki, które zmieniły wynik, i pozycje `extras` z przebiegu bazowego — to jest ocena naturalności i fałszywych alarmów znaczników bez sędziego.

## Performance Considerations

Przebieg po kolei: ok. 36 analiz (rząd 20–50 s każda; 52 s zmierzone dla rozmowy 20-turowej) + ok. 75 tur i tur pamięci (kilka sekund) + 1 długa analiza — ok. 20–35 min. Koszt pełnego przebiegu do ok. 3,4 USD, twardy limit 5 USD (research §6). Jednorazowo w tej fazie: przebieg bazowy + przebieg na zepsutym prompcie (ok. 1 USD) + ewentualna powtórka — ok. 5–8 USD na koncie OpenAI, poza dziennym limitem aplikacji.

## Migration Notes

Brak zmian w bazie i w kodzie produkcyjnym. Wycofanie: revert commitów fazy — `scripts/eval/`, nowe testy, wiersz `also_copy`, nowe mutanty i wpisy w test-planie.

## References

- Research: `context/changes/testing-ai-eval-layer/research.md`
- Test-plan: `context/foundation/test-plan.md` §2 (ryzyko #5, Risk Response Guidance), §6.1 (wzorzec potwierdzenia mutacją), §6.4 (koszt wywołań, ceny przypięte w fixture)
- PRD: `context/foundation/prd.md:42` (lista trafna), `:45` (korekta bez wykładu), `:81` (FR-009), `:106` (kategorie)
- Decyzje: S-01 `context/archive/2026-10-05-first-corrected-conversation/plan.md:199` (kontrakt promptu tury); S-02 `context/archive/2026-10-06-post-conversation-error-list/plan-brief.md:29` (bez literówek), `change.md:14` (pomiar effort i zmienność); S-03 `context/archive/2026-10-07-cross-session-error-memory/plan.md:143`, `:210` (wyjaśnienie w pamięci), `reviews/impl-review.md:38` (limity notatek)
- MERLIN 1.1: http://hdl.handle.net/20.500.12124/6 (CC BY-SA 4.0)
- Wzorzec skryptu lokalnego: `scripts/mutation/manual_mutants.py`
- Wzorzec planu fazy: `context/archive/2026-10-16-testing-budget-ceiling/plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Rdzeń oceniania i testy w CI (#5)

#### Automated

- [x] 1.1 Testy oceniacza i pamięci przechodzą: `uv run pytest tests/test_eval_scoring.py tests/test_memory.py`
- [x] 1.2 Cały zestaw przechodzi bez klucza i sieci: `uv run pytest`
- [x] 1.3 Lint i format: `uv run ruff check . && uv run ruff format --check .`
- [x] 1.4 Nowe ręczne mutanty oceniacza zabite (kod 0): `uv run python scripts/mutation/manual_mutants.py <nowe ID>`
- [x] 1.5 mutmut działa z importem `scripts`, a `memory._mistakes__mutmut_47` jest zabity: `rm -rf mutants && uv run mutmut run && uv run mutmut results`

#### Manual

- [x] 1.6 Przegląd testów oceniacza: oczekiwane liczby mają rachunek w komentarzu i nie pochodzą z funkcji oceniacza

### Phase 2: Zestaw z MERLIN i skrypt na prawdziwym modelu (#5)

#### Automated

- [x] 2.1 Testy zestawu i skryptu przechodzą: `uv run pytest tests/test_eval_golden.py tests/test_eval_runner.py` — 56e6109
- [x] 2.2 Cały zestaw przechodzi bez klucza i sieci: `uv run pytest` — 56e6109
- [x] 2.3 pytest nie zbiera niczego z `scripts/`: `uv run pytest --collect-only -q | grep -c '^scripts/'` zwraca 0 — 56e6109
- [x] 2.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 56e6109

#### Manual

- [x] 2.5 Pobranie MERLIN za zgodą użytkownika, MD5 zgodne, archiwum poza repo
- [x] 2.6 Przegląd próbki zestawu (3 rozmowy analizy, 5 przypadków tury, 2 pamięci): zdania ucznia dosłownie z MERLIN, poprawne formy z wersji poprawionej, kategorie z nazwaną regułą, atrybucja w pliku
- [x] 2.7 Przebieg bazowy kończy się kodem 0 albo 1, wydatek ≤ 5 USD, plik wyników zapisany; naruszenia (jeśli są) i czas długiej analizy zapisane do notatki fazy
- [x] 2.8 Przebieg na zepsutym prompcie i `compare` pokazują spadek `typo_free` albo `lecture_free` z werdyktem „różnica”; prompt przywrócony (`git status` czysty dla `conversations/llm.py`)

### Phase 3: Domknięcie

#### Automated

- [x] 3.1 Wszystkie ręczne mutanty zgodne z oczekiwaniem (kod 0): `uv run python scripts/mutation/manual_mutants.py` — b530072
- [x] 3.2 Każde przeżycie mutmut ma wiersz w rejestrze: `rm -rf mutants && uv run mutmut run && uv run mutmut results` — b530072
- [x] 3.3 Testy przechodzą: `uv run pytest` — b530072
- [x] 3.4 Lint i format: `uv run ruff check . && uv run ruff format --check .` — b530072

#### Manual

- [x] 3.5 Przegląd §3, §4, §5, §6.5, §6.6 i §8 test-planu oraz punktu w CLAUDE.md: zgodne z decyzjami tego planu — b530072
