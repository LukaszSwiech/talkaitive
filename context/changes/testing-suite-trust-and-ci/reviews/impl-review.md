<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Suite trust and CI floor

- **Plan**: context/changes/testing-suite-trust-and-ci/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4, 5, 6, 7
- **Date**: 2026-10-15
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 5 observations

Zakres w git: `3f15aa9^..eec9d32` (13 commitów, 20 plików). Kod aplikacji (`accounts/`, `conversations/`, `talkaitive/`) bez zmian.

Kryteria automatyczne sprawdzone ponownie 2026-10-15:
- `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .` — PASS
- `uv run pytest` — 217 passed
- `uv run python scripts/mutation/manual_mutants.py` — 15 mutantów, 15 zgodnych, kod 0
- świeży `uv run mutmut run` (stary `mutants/` przeniesiony) — 31 s, 51 przeżyć, każde z wierszem w `accepted_survivors.md` (51/51)
- `web-settings.json` — poprawny JSON, `input` identyczny jak przed zmianą
- CI zielone: `main` (revert `3d97f46`, `868f3f4`), gałąź `test-mutation-trust` (`7914d18`, `de2e0d3`); kanarek `8ac139b` czerwony
- faza 7: brak „TBD — see §3 Phase 1”, wiersz bramki bez ochrony gałęzi, blok 10x-cli w `CLAUDE.md` nietknięty

Kryteria ręczne: wszystkie `[x]`, każde z dowodem w diffie lub w potwierdzeniu użytkownika w trakcie faz.

Zmiany poza planem, ocenione jako nieszkodliwe: `workflow_dispatch` i `persist-credentials: false` w `ci.yml` (`7914d18`); etykieta `przekazany do test-plan Phase N` zamiast `przekazany do fazy N`; trzy testy z fazy 6 w `test_conversation_views.py` zamiast w pliku modułu mutanta (zachowanie widać tylko przez widok); linia „Odmowa akcji” w PRD (decyzja D2, zaakceptowana).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Cytaty `prd.md:NNN` w testach przesunięte o jedną linię

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Adherence
- **Location**: tests/test_memory.py:90, :110, :185; tests/test_budget.py:256, :335; tests/test_conversation_views.py:376, :437, :895; scripts/mutation/accepted_survivors.md:73; context/changes/testing-suite-trust-and-ci/mutmut-baseline.md:122-123
- **Detail**: Faza 6 dopisała do PRD linię 97 („Odmowa akcji”, decyzja D2), więc wszystko od linii 97 przesunęło się o +1. Testy z faz 4–5 cytują stare numery: `prd.md:107` to teraz pusta linia (kryterium wyboru błędów jest w :108), `:113` to „Rejestracja” (Role w :114), `:114` to „Role” (dzienny limit $1 w :115), `:117` to „Zapomniane hasło” (widoczność danych w :118). Test-plan §6.1 każe trzymać źródło wyroczni w docstringu, więc ślad prowadzi w złe miejsce. Cytaty `:46`, `:94`, `:96`, `:97` są poprawne.
- **Fix A ⭐ Recommended**: Poprawić numery o +1 w 11 cytatach (107→108, 113→114, 114→115, 117→118).
  - Strength: Zostaje konwencja `prd.md:NNN` używana w całym repo (plan, lessons, test-plan); kilka podmian tekstu w docstringach.
  - Tradeoff: Kolejna edycja PRD przed tymi liniami znów je przesunie.
  - Confidence: HIGH — numery sprawdzone `nl -ba context/foundation/prd.md`.
  - Blind spot: `plan.md` i `research.md` tej zmiany też cytują stare numery — to zapis historyczny, nie poprawiamy.
- **Fix B**: Cytować nazwę reguły zamiast numeru (np. „PRD Access Control — Koszty modeli”).
  - Strength: Odporne na przyszłe edycje PRD.
  - Tradeoff: Odchodzi od konwencji repo; trudniej przejść do linii jednym kliknięciem.
  - Confidence: MED — nazwy sekcji też mogą się zmienić, choć rzadziej.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix B — 11 cytatów zamienionych na nazwy reguł PRD (docstringi w `tests/test_memory.py`, `tests/test_budget.py`, `tests/test_conversation_views.py`; `accepted_survivors.md:73`; `mutmut-baseline.md:122-123`). W M1/M2 cała lista `:46, :94, :113` zastąpiona nazwami. pytest 217 passed, ruff czysty.

### F2 — Skrypt ręcznych mutantów może dać fałszywy wynik albo zawisnąć

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/mutation/manual_mutants.py:51, :220-228, :243-246
- **Detail**: Trzy luki w uruchamianiu pytest: (1) kod wyjścia 1 zawsze znaczy `KILLED`. `views.py` ładuje się dopiero przy pierwszym żądaniu HTTP (przez URLconf), więc mutant, który psuje składnię lub import w `views.py` (C1, M1–M3 celują w ten plik), da „zabity” bez prawdziwego testu zachowania, a wyjście pytest idzie do DEVNULL. (2) `subprocess.run` nie ma `timeout=`, więc mutant z nieskończoną pętlą zawiesza skrypt. (3) Jedna kopia repo służy wszystkim mutantom, a Python zapisuje `.pyc`. Unieważnia go po mtime (z dokładnością do sekundy) i rozmiarze pliku. Mutanty o tym samym rozmiarze (M10 `20`→`19`, M13 `1`→`2`) przywrócone w tej samej sekundzie zostawiają ważny bytecode mutanta na kolejne przebiegi. Dziś wyniki są poprawne, bo fragmenty są poprawnym Pythonem, a przebiegi trwają dłużej niż sekundę.
- **Fix**: Przed uruchomieniem `compile(zmutowany_tekst, path, "exec")` (błąd → `ConfigError`); `timeout=` w `run_pytest` z `TimeoutExpired` → `ConfigError`; `env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}` dla procesu potomnego.
- **Decision**: FIXED — `validate()` kompiluje zmutowany tekst (`SyntaxError` → `ConfigError`), `run_pytest(copy, label)` ma `timeout=PYTEST_TIMEOUT_S` (300 s; `TimeoutExpired` → `ConfigError`) i `PYTHONDONTWRITEBYTECODE=1`. Sprawdzone: pełna lista 15/15, kod 0; C1 z dopisanym `(` odrzucony („does not compile”); limit 0,01 s → „did not finish”. Ograniczenie: `compile()` nie łapie `NameError` przy imporcie.

### F3 — Kopia repo w skrypcie mutantów to lista wykluczeń, nie lista dozwolonych

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/mutation/manual_mutants.py:32-50
- **Detail**: `ignore_patterns(".env")` pasuje tylko do nazwy dokładnie `.env`. Pliki typu `.env.local`, `.env.production`, `*.pem`, `*.key` zostałyby skopiowane do katalogu tymczasowego (prywatny `$TMPDIR`, kasowany przy normalnym wyjściu i Ctrl-C, ale nie przy SIGKILL). Dziś takich plików nie ma.
- **Fix**: Dopisać do `COPY_EXCLUDES` wzorce `.env*`, `*.sqlite3`, `*.pem`, `*.key`.
- **Decision**: FIXED — `.env` → `.env*`, `db.sqlite3` → `*.sqlite3`, dopisane `*.pem`, `*.key`. Sprawdzone: `ignore_patterns` pomija `.env.local`, `.env.production`, `x.pem`, `id.key`, kopiuje `manage.py`; `manual_mutants.py C1 C2` — kod 0.

### F4 — Akcje w CI przypięte tagiem, nie SHA

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: .github/workflows/ci.yml:20, :24
- **Detail**: `actions/checkout@v7.0.1` i `astral-sh/setup-uv@v10.3.0` mają pełne tagi wydań — plan na to pozwalał („pełny tag wydania albo SHA”). Tag da się przesunąć, a `setup-uv` to akcja zewnętrzna, która decyduje o wdrożeniu produkcji. Uprawnienia są minimalne (`contents: read`, bez sekretów), więc szkoda byłaby ograniczona.
- **Fix**: Przypiąć obie akcje do pełnego SHA commita, z tagiem w komentarzu.
- **Decision**: FIXED — `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`, `astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0` (SHA z `gh api repos/<repo>/commits/<tag>`, 2026-10-15). Niezweryfikowane w CI — wymaga pushu gałęzi przez użytkownika i ręcznego uruchomienia (`workflow_dispatch`).

### F5 — Test M2 zabija mutanta tylko dzięki domyślnej kolejności po `pk`

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_conversation_views.py:431
- **Detail**: Pod M2 `.filter(status=ACTIVE).first()` na `Conversation` (bez `Meta.ordering`) zwraca rozmowę o najniższym `pk`, czyli starszą rozmowę Anny — dlatego test pada. Docstring to opisuje. Gdyby `Conversation` dostał `Meta.ordering = ["-created_at"]`, mutant zwróciłby nową rozmowę Łukasza i test przeszedłby mimo wycieku. Skrypt ręcznych mutantów wykryłby to od razu (M2 → `SURVIVED`, kod 1).
- **Fix**: Bez zmiany kodu — świadomie zaakceptować; skrypt mutantów jest strażnikiem tego założenia.
- **Decision**: ACCEPTED — założenie opisane w docstringu testu; zmiana domyślnej kolejności `Conversation` wywróci `manual_mutants.py M2` (SURVIVED, kod 1).

### F6 — Resztki w test-plan.md poza zakresem fazy 7

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: context/foundation/test-plan.md:72, :166-168
- **Detail**: §3 wiersz 1 ma dalej Status `researched` i cel „…testy uruchamiają się same przed merge do `main`” (bramka blokuje wdrożenie, nie merge). Daty w §8 to wciąż 2026-10-13. Plan fazy 7 tego nie obejmował; Status w §3 aktualizuje `/10x-test-plan`.
- **Fix**: Zmienić w celu wiersza 1 „przed merge do `main`” na „przed wdrożeniem z `main`”; Status i §8 zostawić dla `/10x-test-plan` po archiwizacji.
- **Decision**: FIXED — cel §3 wiersz 1: „przed wdrożeniem z `main`”. Status (`researched`) i daty §8 zostają dla `/10x-test-plan`.

### F7 — Decyzje D1–D8 zapisane tylko w mutmut-baseline.md

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: context/changes/testing-suite-trust-and-ci/change.md
- **Detail**: Decyzje użytkownika z fazy 6 (m.in. D2 — nieplanowana linia w PRD, D7 — timeouty tury do test-plan Phase 2 mimo źródła w PRD, czyli odstępstwo od kolejności reguł klasyfikacji) są opisane tylko w `mutmut-baseline.md:130`. `plan.md` i `change.md` o nich nie wspominają, więc łatwo je przeoczyć przy archiwizacji.
- **Fix**: Dopisać w `change.md` (sekcja Notes) jedną linię z odnośnikiem do `mutmut-baseline.md` „Klasyfikacja 51 pozostałych przeżyć” (D1–D8).
- **Decision**: FIXED — linia w Notes `change.md` z odnośnikiem do D1–D8 (D2, D7 wymienione).
