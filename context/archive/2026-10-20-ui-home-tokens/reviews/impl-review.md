<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Tokeny i komponenty UI na widoku home (ui-home-tokens)

- **Plan**: context/changes/ui-home-tokens/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4, 5
- **Date**: 2026-10-21
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 6 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

Success Criteria: `uv run pytest` 491 passed; `ruff check` i `ruff format --check` czyste; skan literałów kolorów i `<style`/`style=` w szablonach i `components.css` — 0 trafień; `collectstatic` z produkcyjnym storage OK, manifest ma `ui/css/tokens.css` i `ui/css/components.css`; `npx playwright test` 22 passed, `tests/e2e/ui-home.spec.ts` drugi raz pod rząd 21 passed. Uwaga środowiskowa: pierwszy przebieg E2E padł na logowaniu, bo port 8000 trzymał lokalny `runserver` z inną bazą (`reuseExistingServer`); z `E2E_PORT=8001` zielono — zgodnie z `CLAUDE.md`, nie błąd zmiany.

Scope Discipline: dodatki poza planem są nieszkodliwe i w kontrakcie — `@require_GET` na `ui_kitchen_sink` (jak inne widoki), reguła autofill i `::selection` w `components.css:10-13` (tylko tokeny). Nieedytowane: `login.html`, `detail.html`, `account_delete.html`, `_mistakes.html`, `_reset_notice.html`; brak nowych zależności, brak `accounts/templates/ui/`, skrypt `base.html` bez zmian.

## Findings

### F1 — Hover przycisku primary w ciemnym motywie poniżej AA i bez strażnika

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/static/ui/css/components.css:37 (komentarz :32-34)
- **Detail**: `color-mix(in srgb, var(--primary) 90%, var(--background))` z tekstem `--primary-foreground` daje w ciemnym motywie 4.510:1 w liczbach zmiennoprzecinkowych i **4.489:1** po zaokrągleniu do 8-bitowego sRGB, które renderuje przeglądarka (policzone niezależnie dwa razy). Komentarz twierdzi „keeps their text at 4.5:1 in both themes”. Test kontrastu nie parsuje `color-mix()`, więc nic tego nie pilnuje. Jasny motyw 10.4:1; hover destructive 5.51/5.81 i link destructive 6.57/6.95 przechodzą. Mieszanie w stronę ciemnego tła przyciemnia złote tło pod ciemnym tekstem, więc mniejszy udział primary pogarsza wynik.
- **Fix A ⭐ Recommended**: Dodać tokeny `--primary-hover` i `--destructive-hover` jako literały `oklch()` w obu motywach w `tokens.css`, przepiąć na nie reguły hover i dopisać pary `primary-foreground`/`primary-hover` i `destructive-foreground`/`destructive-hover` do `CONTRAST_PAIRS`.
  - Strength: Zgodne z regułą z `CLAUDE.md` (każda nowa para tekst/tło dostaje wiersz w `CONTRAST_PAIRS`); test od razu pilnuje obu motywów.
  - Tradeoff: Dwa nowe tokeny i zmiana wyglądu hovera → aktualizacja zrzutów `ui-hover-*`/`ui-focus-*` tylko jeśli hover trafia w kadr (zrzut hover jest na elemencie listy, więc prawdopodobnie bez zmian).
  - Confidence: HIGH — mechanizm tokenów + `CONTRAST_PAIRS` już działa dla 42 par.
  - Blind spot: Nie sprawdzono, czy któryś zrzut łapie hover przycisku primary.
- **Fix B**: Zostawić `color-mix()`, w ciemnym motywie zmienić kierunek mieszania (np. w stronę `--primary-foreground` lub `--foreground`) albo proporcję, i poprawić komentarz.
  - Strength: Bez nowych tokenów, jedna-dwie linie.
  - Tradeoff: Dalej bez strażnika w teście — kolejna zmiana palety może cicho zepsuć kontrast.
  - Confidence: MED — wymaga ręcznego przeliczenia po każdej zmianie tokenów.
  - Blind spot: Wymaga osobnej reguły dla ciemnego motywu (inny kierunek mieszania niż w jasnym).
- **Decision**: FIXED (Fix A) — tokeny `--primary-hover` / `--destructive-hover` w obu motywach (ciemny primary 90% w stronę `--foreground`: 5.82:1), hover `.btn` czyta tokeny, pary w `CONTRAST_PAIRS`

### F2 — Nowa zależność `accounts` → `conversations` (zależność w obie strony)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: accounts/views.py:18-20
- **Detail**: `ui_kitchen_sink` importuje `conversations.budget.next_reset`, `conversations.models.Mistake` i `conversations.topics.TOPICS`. Na `main` żaden plik `accounts/*.py` nie importował `conversations`; kierunek był odwrotny (`conversations/{models,services,memory,budget,llm,views}.py` importują z `accounts`). Teraz aplikacje zależą od siebie nawzajem. Cyklu przy imporcie dziś nie ma tylko dlatego, że `accounts.models`/`accounts.ownership` nie importują `accounts.views`. Szablon kitchen sink też dołącza partiale `conversations/_mistakes.html` i `_reset_notice.html`.
- **Fix A ⭐ Recommended**: Przenieść `ui_kitchen_sink` i `KITCHEN_SINK_NOW` do `conversations/views.py`, trasę `ui/` (nazwa `ui_kitchen_sink`) do `conversations/urls.py`; szablon może zostać w `accounts/templates/accounts/` albo przejść do `conversations/templates/conversations/`.
  - Strength: Przywraca jeden kierunek zależności; obie aplikacje są podpięte pod `""` w `talkaitive/urls.py:33-34`, więc adres `/ui/` i nazwa trasy zostają.
  - Tradeoff: Przeniesienie ~45 linii i aktualizacja ścieżki w `CLAUDE.md` (sekcja UI wskazuje szablon), jeśli szablon też się przeniesie.
  - Confidence: HIGH — zero zmian w zachowaniu, testy używają `reverse("ui_kitchen_sink")` lub `/ui/`.
  - Blind spot: Nie sprawdzono, czy testy importują widok bezpośrednio z `accounts.views`.
- **Fix B**: Zostawić i zapisać decyzję (kitchen sink to strona narzędziowa całego UI) w komentarzu modułu.
  - Strength: Bez zmian w kodzie.
  - Tradeoff: Pierwszy import w drugą stronę ułatwia kolejne; przyszły moduł `accounts` importujący widoki może wywołać cykl.
  - Confidence: MED — dziś działa, ryzyko jest przyszłe.
  - Blind spot: None significant.
- **Decision**: FIXED (Fix A) — `ui_kitchen_sink` i `KITCHEN_SINK_NOW` w `conversations/views.py`, trasa w `conversations/urls.py`; `accounts/views.py` i `accounts/urls.py` jak na `main`; szablon bez zmiany miejsca

### F3 — Wyłączony `<a class="btn">` zmienia kolor na hover

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: accounts/static/ui/css/components.css:36-38
- **Detail**: Plan (faza 4 §1) i komentarz w `:34` mówią, że wyłączony przycisk zachowuje wygląd, także dla wariantów. Reguły hover używają `:hover:not(:disabled)`, a `:disabled` nigdy nie pasuje do `<a>`, więc `<a class="btn" aria-disabled="true">` (kitchen sink :24) dostaje kolor hover. `.link` robi to dobrze (`:not([aria-disabled="true"])`, :45-46). Żaden zrzut tego nie łapie. Drobne: `cursor: progress` (:40) na statycznie wyłączonym linku sygnalizuje „trwa”, co nie pasuje.
- **Fix**: Dopisać `:not([aria-disabled="true"])` do trzech reguł hover `.btn` w :36-38.
- **Decision**: FIXED — `:not([aria-disabled="true"])` w regułach hover `.btn` (primary, secondary, destructive)

### F4 — Komponent `page-footer` nie występuje na `/ui/`

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: accounts/templates/accounts/ui_kitchen_sink.html:28-35; tests/test_ui.py:267-289
- **Detail**: Reguła w `CLAUDE.md` mówi, że `/ui/` pokazuje każdy komponent, a plan (faza 4 §3) — że test z DEBUG sprawdza „wszystkie klasy komponentów”. `page-footer` to jeden z pięciu komponentów, a nie ma go ani w szablonie, ani w `KITCHEN_SINK_MARKUP`. Lista zawartości w fazie 4 §2 też go pomija, więc to luka między listą a intencją.
- **Fix**: Owinąć próbkę linku destructive (:28-35) w `<footer class="page-footer">`, dopisać `'<footer class="page-footer">'` do `KITCHEN_SINK_MARKUP` i zaktualizować zrzuty `ui-kitchen-sink-*` (z opisem w commicie).
- **Decision**: FIXED — próbka linków w `<footer class="page-footer">`, wpis w `KITCHEN_SINK_MARKUP`; 12 zrzutów `ui-*` zaktualizowanych (przesunięcie o stopkę, sprawdzone na diffie)

### F5 — Luki w pokryciu testu kontrastu

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: tests/test_ui.py:48-70
- **Detail**: Używane pary bez wiersza w `CONTRAST_PAIRS`: (a) `card-foreground`/`card` — pola `input`/`textarea` (`components.css:9`) i elementy `.choice-list` (:50); przechodzi dziś (12.6/10.5) tylko dlatego, że równa się `--foreground`. (b) Tekst z `opacity: 0.7` (`.bubble .who` :79, `.mistakes .category` :95, `.count` :98) — jasny motyw 4.53:1 po zaokrągleniu, tuż nad progiem. (c) Zwykłe `<a>` bez `.link` („← Home”, „Cancel”) nie mają tokenu koloru; w ciemnym motywie zależą od tego, jak przeglądarka dopasuje kolor linku do `color-scheme: dark` (strony spoza zakresu).
- **Fix**: Dopisać parę `card-foreground`/`card` (4.5) do `CONTRAST_PAIRS`; (b) i (c) zostawić na zmiany `/10x-ui` stron login/detail/account_delete.
- **Decision**: FIXED — para `card-foreground`/`card` w `CONTRAST_PAIRS`; (b) opacity i (c) gołe `<a>` zostają na zmiany `/10x-ui` stron spoza zakresu

### F6 — `/ui/` otwiera się przewinięta na dół

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/templates/accounts/ui_kitchen_sink.html:80; accounts/templates/base.html:64-66
- **Detail**: Kitchen sink zawiera `<div class="transcript">`, więc skrypt w `base.html` wykonuje `window.scrollTo(0, document.body.scrollHeight)` przy każdym wejściu na `/ui/`. Zrzuty nie cierpią (full page; testy focus/hover przewijają do elementu), ale przy ręcznym oglądaniu strona startuje od dołu. Plan zabrania zmian w zachowaniu skryptu.
- **Fix**: Zostawić skrypt i dopisać komentarz w szablonie kitchen sink, że strona startuje od dołu przez `.transcript`.
- **Decision**: FIXED — komentarz w szablonie kitchen sink

### F7 — Reguła i strażnicy mają ostre krawędzie

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: CLAUDE.md (sekcja „UI: tokens and components”); accounts/static/ui/css/tokens.css:49; tests/test_ui.py:40, 76
- **Detail**: `CLAUDE.md` mówi „Write each value as `oklch(L C H)` or `var(--token)` only”, a `--shadow-sm` w `tokens.css:49` używa `hsl()` (nieszkodliwe — test rozwiązuje tylko tokeny z `CONTRAST_PAIRS`). `COLOUR_LITERAL` nie łapie `lab()`/`lch()`/`oklab()`/`color()`/`hwb()` ani nazw kolorów; `ROOT_BLOCK` pasuje tylko do gołego `:root {`, więc przyszły blok `:root[data-theme="dark"]` zostałby cicho pominięty (dziś go nie ma). Jasne `--warning` (`oklch(0.97 0.045 90)`) leży tuż poza gamutem sRGB — test przycina, efekt pomijalny (~12:1).
- **Fix**: W `CLAUDE.md` zmienić na „each colour token”, a do `COLOUR_LITERAL` dopisać `lab\(|lch\(|oklab\(|color\(|hwb\(`.
- **Decision**: FIXED — `CLAUDE.md`: „each colour value” + wyjątek `--shadow-sm`; `COLOUR_LITERAL` łapie `oklab(`/`lab(`/`lch(`/`hwb(`/`color(`

### F8 — Udokumentowane odstępstwa w stanie loading

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: tests/e2e/ui-home.spec.ts:52-70; plan.md Progress 4.6
- **Detail**: Plan (faza 4 §4) mówił „wstrzymaj żądanie, zrób zrzut, potem `route.abort()`”; spec od razu robi `route.abort('aborted')`, czeka na `requestfailed` i dopiero sprawdza wskaźnik i wyłączony „Log out” — komentarz :52-56 wyjaśnia, że wstrzymane żądanie blokuje lokatory. Intencja zachowana (rozmowa nie powstaje). Kryterium ręczne 4.6 „loading bez skoku układu” odhaczone, choć `form.after(typing)` przesuwa tematy w dół — `research.md:75-77` zapisuje to jako zaakceptowane przez użytkownika 2026-10-21 (plan zabrania nowego JS). Oba odstępstwa są w `research.md`/komentarzu, nie w planie.
- **Fix**: Bez zmian w kodzie; ewentualnie jedno zdanie addendum w `plan.md` przy fazie 4, żeby plan był zgodny z tym, co zrobiono.
- **Decision**: FIXED — addendum w `plan.md` przy fazie 4

### F9 — Istnienie `/ui/` widoczne na produkcji (302/405 zamiast 404)

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/views.py:52-60; accounts/urls.py:17-18
- **Detail**: `LoginRequiredMiddleware` działa przed widokiem, a `@require_GET` przed sprawdzeniem DEBUG, więc niezalogowany GET `/ui/` dostaje 302 na logowanie (nieznany adres — 404), a zalogowany POST — 405. Żadne dane nie wyciekają; zawsze zarejestrowana trasa to świadoma decyzja z planu (testy przełączają DEBUG).
- **Fix**: Zaakceptować (wyciek zerowy) — ewentualnie sprawdzać DEBUG przed `require_GET` w środku widoku.
- **Decision**: ACCEPTED — zalecenie raportu: zero wycieku danych, zawsze zarejestrowana trasa to decyzja planu

## Triage

- **Fixed**: F1, F2 (Fix A), F3, F4, F5, F6, F7, F8 (8)
- **Accepted**: F9 (1)
- **Verification po poprawkach**: `uv run pytest` 497 passed; `ruff check` / `ruff format --check` czyste; `E2E_PORT=8001 npx playwright test` 22 passed (po `--update-snapshots` dla 12 zrzutów `ui-*`).
