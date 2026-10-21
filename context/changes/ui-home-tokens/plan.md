# Tokeny i komponenty UI na widoku home (ui-home-tokens) — Implementation Plan

## Overview

Aplikacja dostaje pierwszy kontrakt wyglądu (design system): jedno źródło wartości (tokeny CSS o nazwach ról z shadcn, wartości z eksportu tweakcn poprawione do WCAG AA, jasny i ciemny motyw) oraz trzy wspólne komponenty (przycisk z wariantami, lista wyboru, alert). Widok home zostaje na nich przebudowany. Zmiana zamyka zarzuty C1–C5 z `research.md`, pokazuje 7 stanów na stronie kitchen sink, pilnuje wyglądu zrzutami Playwright i zostawia regułę w `CLAUDE.md` oraz strażników w pytest, żeby kolejny agent nie wrócił do wpisanych kolorów.

## Current State Analysis

- Cały CSS aplikacji żyje w dwóch inline `<style>`: globalnym w `accounts/templates/base.html:8-42` (także reguły strony rozmowy: `.transcript`, `.bubble*`, `.mistakes`) i lokalnym `.topbar` w `conversations/templates/conversations/home.html:3-11`. `{% block head %}` renderuje się przed bazowym `<style>` (`base.html:7` vs `:8`), więc styl strony przegrywa z bazowym przy tej samej specyficzności (C4).
- 12 literałów hex (9 wartości) w `base.html:15-41`, zero `var(--…)` w szablonach (C1). Pozostałe szablony (`login.html`, `account_delete.html`, `detail.html`, `_mistakes.html`, `_reset_notice.html`) nie mają ani jednego koloru, `<style>` ani `style=` (grep z 2026-10-20).
- Reguła `button, .button` (`base.html:12`) ustawia tylko układ: `<button>` ma natywny wygląd przeglądarki, `<a class="button">` „Continue conversation” (`home.html:28`) wygląda jak link (C2). Brak `:hover` / `:focus-visible`; jedyny stan to `button:disabled` (`base.html:13`) (C3).
- „Delete account” to zwykły link w pasku obok „Log out” (`home.html:22`) (C5).
- Brak katalogu `static/` w źródłach i `{% load static %}`. Produkcja używa `CompressedManifestStaticFilesStorage` (`talkaitive/settings.py:226-228`, `manifest_strict`), testy zwykłego `StaticFilesStorage` (`talkaitive/settings_test.py:7-10`). `collectstatic` biegnie w starcie na Railway (`context/deployment/web-settings.json:7`) i w `webServer` Playwrighta (`playwright.config.ts:41-47`).
- Kontrast tweakcn (research §d): w jasnym motywie poniżej progu są ring/tło 2.92, biały/destructive 3.76, muted-foreground/tło 4.04, secondary-foreground/secondary 3.17; w ciemnym primary-foreground/primary 3.49 i accent-foreground/accent 3.41. Nowe szare tło obniża zieleń `.correct` do 4.23.
- Strony spoza zakresu używają gołych `<button>` oraz klas `.error` i `.notice` (`login.html:10-23`, `account_delete.html:19-24`, `detail.html:33-88`).

## Desired End State

- `accounts/static/ui/css/tokens.css` jest jedynym miejscem z wartościami kolorów (jasne w `:root`, ciemne w `@media (prefers-color-scheme: dark)`), z komentarzem wskazującym `context/changes/ui-home-tokens/theme-source.css` i każdą poprawkę AA. `accounts/static/ui/css/components.css` używa wyłącznie `var(--…)`. Żaden szablon nie ma `<style>`, `style=` ani literału koloru.
- Home: pasek z „Signed in as …” i „Log out”; aktywna rozmowa z wyraźnym przyciskiem primary „Continue conversation”; limit jako alert warning; tematy jako lista wyboru (karty); „Delete account” na dole strony jako czerwony link, we wszystkich trzech wariantach strony. Działa w jasnym i ciemnym motywie systemu.
- Każdy przycisk i link ma widoczny hover i pierścień fokusu z `--ring`; spinner respektuje `prefers-reduced-motion`.
- `/ui/` (tylko w DEBUG, poza DEBUG 404) pokazuje wszystkie komponenty we wszystkich stanach. Zrzuty Playwright (home default + loading, `/ui/` + focus + hover) w jasnym i ciemnym motywie, na desktopie i telefonie, przechodzą lokalnie.
- pytest w CI pilnuje: pliki CSS istnieją dla `finders`, brak kolorów/`<style>`/`style=` w szablonach i kolorów w `components.css`, kontrast par tokenów ≥ progów AA w obu motywach.
- `CLAUDE.md` ma sekcję UI, która mówi, gdzie są tokeny, komponenty i kitchen sink oraz czego nie robić.

### Key Discoveries:

- Komponenty tej zmiany są **kontraktem klas CSS**, nie szablonami `{% include %}` (research §b proponował include). Powody: `{% include %}` nie przyjmuje treści w środku, a notice o limicie zawiera inny include (`home.html:30-33`); przycisk to jeden atrybut, więc include dodałby więcej kodu, niż oszczędza; `include … only` odcina też `csrf_token` z formularzy tematów (`home.html:39-43`) — da się to obejść jawnym `with csrf_token=csrf_token`, więc to niewygoda, nie blokada.
- Tak samo robi Basecoat (kierunek z `change.md:17`): proste komponenty to klasa + atrybut `data-variant` (`<button class="btn" data-variant="destructive">`, `<div class="alert" data-variant="destructive">`), a szablony z parametrami (makra Jinja/Nunjucks) ma tylko dla złożonych komponentów, np. `select` (dokumentacja Basecoat, Context7, 2026-10-20). Ta zmiana przejmuje tę konwencję zapisu, żeby późniejsza migracja na Basecoat nie wymagała przepisywania markupu.
- Żaden test nie zależy od tagów komunikatów (`message.tags`); jedyne asercje na flash to brak `'class="flash'` (`tests/test_conversation_views.py:1240`, `:1256`).
- Test `tests/test_conversation_views.py:1240`, `:1256` sprawdza brak `'class="flash'`. Znacznik komunikatu musi dalej **zaczynać się** od `class="flash`, inaczej negatywna asercja staje się pusta.
- Przypięty HTML, który musi zostać bez zmian: `'<div class="typing">'` (`detail.html:27`; testy `:640`, `:720`, `:819`), `'class="transcript"'` (`:1156`), `'href="/account/delete/"'` na home (`tests/test_account_deletion.py:540-544`), teksty „Choose a topic”, „Continue conversation”, „Signed in as …”. Skrypt w `base.html:55-98` łapie elementy (`button`, `form`) i id, nie klasy komponentów.
- `TOPICS` to stała 20 tematów (`conversations/topics.py:18`, test `tests/test_conversations.py:182-184`) — stan empty listy tematów jest nieosiągalny.
- W E2E klucz OpenAI jest pusty (`playwright.config.ts:53-54`); kliknięcie tematu tworzy rozmowę (`conversations/views.py:62-70`), więc zrzut stanu loading musi zatrzymać `POST /conversations/start/` i go anulować, zanim dotrze do serwera.
- `ManifestFilesMixin.post_process` nic nie robi przy `--dry-run`, więc sprawdzenie manifestu wymaga prawdziwego `collectstatic` (do gitignorowanego `staticfiles/`).

## What We're NOT Doing

- Restyling stron login, detail i account_delete — dostają tylko to, co dziedziczą z globalnych reguł (tokeny, wygląd gołego `<button>`, fokus). Ich szablony nie są edytowane; każda dostanie własną zmianę `/10x-ui`.
- Wspólny pasek nawigacji dla wszystkich stron (po MVP, `context/foundation/roadmap.md:178`) — markup `.topbar` zostaje w `home.html`.
- Przełącznik motywu w aplikacji — ciemny motyw idzie wyłącznie za ustawieniem systemu.
- Własne pliki czcionek (Inter self-host) i Google Fonts CDN — stos systemowy.
- Tailwind, Basecoat jako zależność, Node w aplikacji, nowe zależności Pythona (od Basecoat bierzemy tylko konwencję zapisu `class` + `data-variant`).
- Szablony komponentów w `accounts/templates/ui/` — żaden z trzech komponentów tej zmiany ich nie potrzebuje; reguła w fazie 5 mówi, kiedy powstaje pierwszy.
- Nowy JS. Zachowanie skryptu (wyłączenie wszystkich przycisków po dowolnym submit, `base.html:63`) zostaje.
- Tokeny bez zastosowania: `--chart-*`, `--sidebar-*`, `--popover*`, składowe cienia, `--tracking-normal`, `--spacing`, `--font-serif`, `--font-mono` (zostają w `theme-source.css`).
- Uruchamianie Playwrighta w CI (decyzja: bramka lokalna przed push).

## Implementation Approach

Kolejność ze skilla `/10x-ui`: środowisko → wartości tokenów → jeden widok → stany. Faza 1 to czysty refaktor (CSS do plików statycznych, wygląd bez zmian), więc każdy późniejszy błąd wyglądu ma jedno źródło. Faza 2 wprowadza tokeny i strażników, zanim powstaną komponenty, żeby komponenty od początku czytały tylko `var(--…)`. Faza 3 przebudowuje home. Faza 4 domyka stany i bramkę wizualną. Faza 5 zostawia regułę.

Komponenty (kontrakt klas w `components.css`, konwencja zapisu Basecoat: klasa komponentu + wariant w atrybucie `data-variant`):
- **Przycisk:** `.btn` bez wariantu = primary (jak w Basecoat); `data-variant="secondary"` i `data-variant="destructive"`; `.btn` działa też na `<a>`. Goły `<button>` bez klasy ma wygląd secondary (własny fallback dla stron spoza zakresu, Basecoat go nie ma).
- **Link:** `.link` z `data-variant="destructive"` dla linku z akcją niebezpieczną (własny komponent w tej samej konwencji).
- **Lista wyboru:** `.choice-list` — pionowa lista, w której każdy element to przycisk na pełną szerokość z powierzchnią karty (`--card`, `--border`, `--radius`, `--shadow-sm`). Nazwa ogólna, bo home dostanie kolejne listy (poziom, język). Własny komponent, bez odpowiednika w Basecoat.
- **Alert:** `.alert` z `data-variant="destructive"` / `"success"` / `"warning"` (Basecoat ma `destructive`; `success` i `warning` to nasze rozszerzenie). Komunikaty Django dostają wariant z `message.level_tag`; dla błędu to `error`, a `.alert[data-variant="error"]` jest w `components.css` aliasem wariantu `destructive` (globalne `MESSAGE_TAGS` zmieniłoby też klasy komunikatów w adminie Django, który barwi je po `li.error`). `.notice` i `.error` zostają jako aliasy dla stron spoza zakresu.

Kiedy komponent staje się szablonem: komponent z więcej niż jednym elementem HTML, powtarzany w 2+ miejscach, dostaje plik `accounts/templates/ui/<nazwa>.html` wywoływany przez `{% include … with … only %}` (w środku używa tych samych klas). Dziś żaden z trzech komponentów tego nie spełnia; regułę zapisuje faza 5.

## Branches and PRs

Jedna gałąź `ui-home-tokens` i jeden PR na wszystkie fazy — fazy zależą od siebie, a scalenie w połowie opublikowałoby na produkcji niedokończony motyw (`main` publikuje się automatycznie).

## Critical Implementation Details

- **Kolejność w `<head>`:** `tokens.css`, potem `components.css`, potem `{% block head %}` — style strony mają przychodzić po wspólnych.
- **`color-scheme: light dark`** ustawiamy razem z ciemnymi tokenami (faza 2), nie wcześniej; wtedy natywne pola formularzy i paski przewijania zgadzają się z motywem.
- **Format tokenów dla testu kontrastu:** każdy token koloru w `tokens.css` to literał `oklch(L C H)` albo alias `var(--inny-token)`; test parsuje tylko te dwie formy. `color-mix()` wolno używać w `components.css` (np. hover), nie w `tokens.css`.
- **`"Source Serif 4"`** w źródle jest bez cudzysłowu (niepoprawne CSS) — nie przenosimy go, bo `--font-serif` jest pominięty.

## Phase 1: Pliki statyczne bez zmiany wyglądu

### Overview

Przenosi oba bloki `<style>` do plików statycznych ładowanych przez `{% static %}`, bez zmiany ani jednej wartości. Wygląd home i pozostałych stron jest identyczny jak przed zmianą.

### Changes Required:

#### 1. Pliki CSS

**File**: `accounts/static/ui/css/tokens.css`, `accounts/static/ui/css/components.css` (nowe)

**Intent**: Założyć dwa pliki kontraktu. `tokens.css` dostaje na razie tylko nagłówek z opisem roli pliku i odwołaniem do `theme-source.css` (wartości przychodzą w fazie 2). `components.css` dostaje dosłownie reguły z `base.html:9-41` i `home.html:5-9`, pogrupowane w sekcje (elementy bazowe, komponenty strony home, reguły strony rozmowy).

**Contract**: Ścieżki `ui/css/tokens.css` i `ui/css/components.css` w przestrzeni nazw statycznych (`AppDirectoriesFinder`, bez zmian w `settings.py`). Selektory i wartości identyczne jak dziś.

#### 2. Ładowanie w szablonach

**File**: `accounts/templates/base.html`, `conversations/templates/conversations/home.html`

**Intent**: `base.html` dostaje `{% load static %}` i dwa `<link rel="stylesheet">` w `<head>` przed `{% block head %}`; inline `<style>` znika. `home.html` traci `{% block head %}` z `<style>`.

**Contract**: Kolejność w `<head>`: meta → title → `tokens.css` → `components.css` → `{% block head %}`. Reszta `base.html` (pętla messages, `#typing-indicator`, skrypt) bez zmian.

#### 3. Strażnik plików statycznych

**File**: `tests/test_ui.py` (nowy)

**Intent**: Test, że `django.contrib.staticfiles.finders.find()` znajduje oba pliki — literówka w ścieżce `{% static %}` nie wywróci pytest (zwykłe storage), a w produkcji dałaby 500 na każdej stronie.

**Contract**: Jeden test sparametryzowany po dwóch ścieżkach; docstring modułu opisuje, że plik zbiera strażników kontraktu UI.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Manifest zawiera oba pliki po prawdziwym `collectstatic` z produkcyjnym storage: `DEBUG=False SECRET_KEY=x OPENAI_API_KEY=x uv run python manage.py collectstatic --noinput` kończy się bez błędu, a `staticfiles/staticfiles.json` ma wpisy `ui/css/tokens.css` i `ui/css/components.css`
- Skan literałów w szablonach daje 0 trafień `<style`: `grep -rn '<style' accounts/templates conversations/templates`

#### Manual Verification:

- Home, login, detail i account_delete wyglądają tak samo jak przed zmianą (zrzut przed/po na desktopie i jednej szerokości telefonu, `uv run python manage.py runserver`)

**Implementation Note**: Po zielonej automatyce zatrzymaj się na ręczne potwierdzenie przed fazą 2.

---

## Phase 2: Tokeny (jasne + ciemne) i strażnicy

### Overview

Wypełnia `tokens.css` wartościami z tweakcn (poprawionymi do AA), dodaje brakujące tokeny i ciemny motyw, przepina wszystkie 12 literałów w `components.css` na `var(--…)` i dokłada testy, które pilnują braku literałów i kontrastu.

### Changes Required:

#### 1. Wartości tokenów

**File**: `accounts/static/ui/css/tokens.css`

**Intent**: Przenieść z `theme-source.css:13-66` tokeny używane przez aplikację: `--background`, `--foreground`, `--card`, `--card-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--muted-foreground`, `--accent`, `--accent-foreground`, `--destructive`, `--destructive-foreground`, `--border`, `--input`, `--ring`, `--radius`, `--shadow-sm`, `--font-sans`. Poprawić do AA w jasnym motywie `--destructive`, `--ring`, `--muted-foreground`, `--secondary-foreground` (punkt wyjścia: kandydaci z research §d), a w obu motywach `--input` — granica pola ≥ 3:1 do `--background` i `--card` (WCAG 1.4.11; w tweakcn jasne `--input` jest jaśniejsze od tła). Dodać tokeny, których tweakcn nie ma: `--success`, `--success-muted` (tło alertu success), `--warning`, `--warning-foreground`, `--destructive-muted` (tło alertu błędu), `--bubble-assistant`, `--bubble-user` (bańka użytkownika zostaje zielona). Każda wartość różna od tweakcn ma obok komentarz z wartością źródłową i powodem.

**Contract**: `:root { color-scheme: light dark; … }` + `@media (prefers-color-scheme: dark) { :root { … } }` z wartościami z `theme-source.css:68-119` i poprawkami AA dla ciemnych par (`--primary-foreground` na `--primary`, `--accent-foreground` na `--accent`, `--destructive` w roli tekstu i tła) oraz ciemnymi odpowiednikami dodanych tokenów. `--font-sans: Inter, system-ui, sans-serif`. Formy wartości: patrz „Format tokenów” w Critical Implementation Details.

#### 2. Przepięcie literałów

**File**: `accounts/static/ui/css/components.css`

**Intent**: Zastąpić wszystkie 12 literałów tokenami według mapowania z research §c (`.error`/`.wrong` → `--destructive`, `.flash` → `--muted`, `.flash.error` → `--destructive-muted`, `.notice` → `--warning`, bańki → `--bubble-*`, `.typing`/`.sentence`/spinner → `--muted-foreground`/`--border`, `.correct` → `--success`). `body` dostaje `background: var(--background)`, `color: var(--foreground)`, `font-family: var(--font-sans)`; pola `input`/`textarea` dostają tło i tekst z tokenów oraz obramowanie `--input` (≥ 3:1 do `--background` i `--card`, pilnuje test kontrastu).

**Contract**: W `components.css` zero literałów koloru (hex, `rgb()`, `hsl()`, `oklch()`); `color-mix()` dozwolony tylko na `var(--…)`.

#### 3. Strażnicy w pytest

**File**: `tests/test_ui.py`

**Intent**: (a) Żaden szablon aplikacji projektu nie zawiera literału koloru, `<style` ani ` style=` — szablony zbierane z katalogów `templates/` aplikacji z `apps.get_app_configs()` leżących w `BASE_DIR` (pomija `.venv/`, `mutants/`, `staticfiles/`). (b) `components.css` nie zawiera literału koloru. (c) Kontrast: test parsuje `tokens.css` (blok jasny i ciemny, aliasy `var()` rozwiązane, w ciemnym brakujący token dziedziczy z jasnego), konwertuje OKLCH → sRGB → luminancję względną WCAG 2.x i sprawdza listę par z progiem.

**Contract**: Regex literału koloru jak w skanie `/10x-ui` (część kolorowa): `#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(`. Lista par (obie motywy) jako stała `CONTRAST_PAIRS` w teście, każda para z progiem: 4.5 — `foreground`/`background`, `foreground`/`card`, `foreground`/`muted`, `foreground`/`destructive-muted`, `foreground`/`success-muted`, `foreground`/`bubble-assistant`, `foreground`/`bubble-user`, `primary-foreground`/`primary`, `secondary-foreground`/`secondary`, `muted-foreground`/`background`, `muted-foreground`/`card`, `accent-foreground`/`accent`, `destructive-foreground`/`destructive`, `destructive`/`background`, `destructive`/`card`, `warning-foreground`/`warning`, `success`/`background`; 3.0 — `ring`/`background`, `ring`/`card`, `input`/`background`, `input`/`card`. Konwersja przycina do gamutu sRGB [0, 1] (research §d). Test nie dodaje zależności.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą, w tym nowi strażnicy: `uv run pytest tests/test_ui.py` i całość `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Skan literałów na szablonach i `components.css` daje 0 trafień: `grep -rnE '#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(' accounts/templates conversations/templates accounts/static/ui/css/components.css`
- Celowe złamanie: wpisanie `color: #fff` do `home.html` wywraca strażnika szablonów, a przywrócenie tweakcn-owego `--ring` (`oklch(0.6325 0.0904 80.9413)`) wywraca test kontrastu; po cofnięciu oba zielone
- `collectstatic` z produkcyjnym storage jak w fazie 1 kończy się bez błędu

#### Manual Verification:

- Home, login, detail i account_delete są czytelne w jasnym i ciemnym motywie systemu (macOS: Ustawienia → Wygląd), desktop + telefon
- Wartości kolorów sprawdzone w DevTools (próbnik kontrastu Chrome) dla 2–3 par z listy, zgodne z testem

**Implementation Note**: Po zielonej automatyce zatrzymaj się na ręczne potwierdzenie przed fazą 3.

---

## Phase 3: Widok home na komponentach

### Overview

Dodaje trzy komponenty do `components.css` i przebudowuje `home.html` na nie; przenosi „Delete account” z paska na dół strony.

### Changes Required:

#### 1. Komponenty

**File**: `accounts/static/ui/css/components.css`

**Intent**: Dodać przycisk (`.btn` = primary, `data-variant="secondary"`, `data-variant="destructive"`; `.btn` na `<a>` wygląda jak przycisk; goły `button` bez klasy = wygląd secondary), `.link` z `data-variant="destructive"`, `.choice-list` (elementy jako karty na pełną szerokość, zastępuje `.topics`), `.alert` z `data-variant="destructive"` / `"success"` / `"warning"` oraz `.page-footer`. `.notice` i `.error` zostają jako aliasy (`.notice` = alert warning, `.error` = tekst `--destructive`) dla stron spoza zakresu. Reguły `.topbar` przechodzą na tokeny bez zmiany układu. Martwe selektory znikają: `.button` (z `button, .button`), `.topics` i `.flash.error`; `.flash` traci własne reguły wyglądu i zostaje tylko znacznikiem dla testów (`class="flash`), a wygląd komunikatu daje `.alert`.

**Contract**: Klasy: `btn`, `link`, `choice-list`, `alert`, `page-footer`. Warianty wyłącznie przez atrybut `data-variant` (selektory typu `.btn[data-variant="destructive"]`), nigdy przez klasy `btn-*`. Wartości `data-variant`: przycisk — brak/`secondary`/`destructive`; link — `destructive`; alert — `destructive`/`success`/`warning`, plus `error` jako alias `destructive` tylko dla komunikatów Django (tło `--destructive-muted` / `--success-muted` z tekstem `--foreground`, `--warning` z `--warning-foreground`). Promień z `--radius`, cień listy z `--shadow-sm`. Bez literałów (strażnik z fazy 2).

#### 2. Szablon home

**File**: `conversations/templates/conversations/home.html`

**Intent**: Pasek: „Signed in as …” i „Log out” (`class="btn" data-variant="secondary"`). Aktywna rozmowa: „Continue conversation” jako `<a class="btn">` (primary). Limit: `<p class="alert" data-variant="warning">` z tym samym include `_reset_notice.html`. Tematy: `ul.choice-list` z tymi samymi formularzami (`data-waits-for-agent`, `csrf_token`, ukryte pole). Na końcu, poza gałęziami `if`, `<footer class="page-footer">` z linkiem „Delete account” (`class="link" data-variant="destructive"`). Usunięcie linku z paska świadomie zmienia uzgodnienie z `context/archive/2026-10-07-account-and-data-deletion/plan-brief.md:24` (decyzja w tej zmianie, zarzut C5).

**Contract**: `href="{% url 'account_delete' %}"` bez zmian; link poza `<header class="topbar">`; widoczny we wszystkich trzech gałęziach. Teksty przypięte testami bez zmian.

#### 3. Komunikaty flash

**File**: `accounts/templates/base.html`

**Intent**: Komunikaty z pętli messages renderowane jako komponent alertu z wariantem z poziomu komunikatu. `level_tag` idzie wprost do `data-variant` (bez warunków w szablonie); `error` obsługuje alias `.alert[data-variant="error"]` z §1. Bez `MESSAGE_TAGS` w `settings.py` — to ustawienie globalne i zmieniłoby klasy komunikatów w adminie Django (`talkaitive/urls.py:31`).

**Contract**: `<p class="flash alert" data-variant="{{ message.level_tag }}">` — atrybut `class` nadal zaczyna się od `class="flash` (asercje `tests/test_conversation_views.py:1240`, `:1256`). Aplikacja wysyła dziś tylko `error` (`accounts/views.py:30`, `conversations/views.py:61` i in.) i `success` (`accounts/views.py:37`).

#### 4. Testy markupu

**File**: `tests/test_account_deletion.py` (obok `test_home_links_to_account_deletion`, `:540`)

**Intent**: Test, że link usuwania konta stoi po zamknięciu paska (`</header>`) — strzeże decyzji C5. Istniejąca asercja `href` zostaje. Drugi test (w `tests/test_ui.py`): komunikat błędu (np. z nieudanego startu rozmowy, `conversations/views.py:59-62`) renderuje się z `data-variant="error"`, a `components.css` zawiera selektor `.alert[data-variant="error"]` — strzeże aliasu.

**Contract**: Porównanie podciągów w `response.content.decode()`, zgodnie ze stylem istniejących testów (bez parsera HTML).

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Skan literałów jak w fazie 2 daje 0 trafień
- Celowe złamanie: przeniesienie linku „Delete account” z powrotem do paska wywraca nowy test; po cofnięciu zielony

#### Manual Verification:

- Home w trzech wariantach (lista tematów, aktywna rozmowa, limit) w obu motywach, desktop + telefon: główna akcja wyraźnie wyróżniona, „Delete account” na dole i czerwony, tematy jako lista kart
- Kliknięcie tematu nadal pokazuje „Agent is typing…” pod formularzem, a „Log out” nadal wylogowuje
- Komunikat „Your account has been deleted.” na stronie logowania wygląda jak alert success

**Implementation Note**: Po zielonej automatyce zatrzymaj się na ręczne potwierdzenie przed fazą 4.

---

## Phase 4: Stany, kitchen sink i bramka wizualna

### Overview

Domyka stany interakcji, dodaje stronę `/ui/` (tylko DEBUG) pokazującą wszystkie komponenty i stany oraz zrzuty Playwright jako bramkę wizualną. Część E2E można prowadzić przez `/10x-e2e`.

### Changes Required:

#### 1. Stany w CSS

**File**: `accounts/static/ui/css/components.css`

**Intent**: Hover dla przycisków, elementów `.choice-list` i linków (zmiana z tokenów, np. `color-mix()` na `var(--…)`). `:focus-visible` dla `button`, `a`, `input`, `textarea`: `outline` w pełnym kolorze `--ring` z odstępem (bez `/50` z tweakcn). Disabled: wygląd jak dziś (`opacity` + `cursor: progress`), także dla wariantów. `@media (prefers-reduced-motion: reduce)` zatrzymuje albo spowalnia spinner.

**Contract**: Brak `outline: none` bez zamiennika; brak literałów.

#### 2. Strona kitchen sink

**File**: `accounts/views.py`, `accounts/urls.py`, `accounts/templates/accounts/ui_kitchen_sink.html` (nowy; nie w `ui/`, który reguła z fazy 5 rezerwuje na szablony komponentów)

**Intent**: Widok renderuje jedną stronę z każdym komponentem w każdym stanie: przyciski `.btn` primary/secondary/destructive i goły `<button>`, `<a class="btn">`, `.link` destructive (default + disabled); `.choice-list` z trzema tematami jako `<button type="button">` bez `<form>` (ten sam wygląd, bez akcji — Enter na `/ui/` nie startuje płatnej rozmowy); alerty destructive/success/warning (warning z `_reset_notice.html`); blok aktywnej rozmowy; statyczny przykład wskaźnika pisania (loading); pole tekstowe i textarea; próbka bańki asystenta i użytkownika oraz listy `.mistakes` (reguły w `components.css`, które dotyka ta zmiana). Poza `settings.DEBUG` widok zwraca 404. Chroniony jak każda strona przez `LoginRequiredMiddleware`.

**Contract**: Trasa `ui/` o nazwie `ui_kitchen_sink`, zawsze zarejestrowana; `raise Http404` gdy `not settings.DEBUG`. Bez parametru id w adresie, więc bez wpisu w `ID_ROUTES`. Kontekst: `reset_at` i `budget_time_zone` dla `_reset_notice.html`. Strona nie wypisuje `class="flash` (alerty jako `class="alert" data-variant="…"`).

#### 3. Testy widoku

**File**: `tests/test_ui.py`

**Intent**: Zalogowany użytkownik dostaje 404 z `DEBUG=False` i 200 z `override_settings(DEBUG=True)` ze wszystkimi klasami komponentów w odpowiedzi; niezalogowany jest przekierowany na logowanie.

**Contract**: Trzy testy w stylu `login_client` z istniejących testów.

#### 4. Zrzuty Playwright

**File**: `tests/e2e/ui-home.spec.ts` (nowy), baseline'y w `tests/e2e/ui-home.spec.ts-snapshots/`, `tests/e2e/ensure_e2e_user.py`

**Intent**: `toHaveScreenshot` dla: home default; home loading (`page.route('**/conversations/start/')` wstrzymuje żądanie, zrzut ze wskaźnikiem, potem `route.abort()` — rozmowa nie powstaje); `/ui/` cała strona; `/ui/` z fokusem klawiatury (Tab) na przycisku; `/ui/` z hoverem na elemencie listy. Każdy w jasnym i ciemnym motywie (`colorScheme`) oraz na desktopie i telefonie (390×844). E-mail w pasku zamaskowany (`mask`).

**Contract**: Wzorzec `seed.spec.ts`: komentarz `Risk:` na górze, lokatory `getByRole`/`getByText`, bez `waitForTimeout`. Test nie tworzy danych w `e2e.sqlite3`. Warunek „użytkownik E2E bez aktywnej rozmowy i bez wyczerpanego limitu” jest wymuszony, nie zakładany: `ensure_e2e_user.py` przy starcie serwera usuwa `Conversation` i `LLMCharge` użytkownika E2E (skrypt działa tylko na `e2e.sqlite3`), a spec przed zrzutami home sprawdza `getByRole('heading', { name: 'Choose a topic' })` — przy `reuseExistingServer` skrypt nie biegnie ponownie, a porażka tej asercji mówi wprost, że to stan danych, nie wygląd. Baseline'y commitowane; aktualizacja tylko z opisem zmiany wizualnej.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Lint i format: `uv run ruff check . && uv run ruff format --check .`
- Zrzuty przechodzą lokalnie dwa razy pod rząd: `npx playwright test tests/e2e/ui-home.spec.ts`
- Pełny zestaw E2E zielony: `npx playwright test`
- Celowe złamanie: zmiana `--ring` w `tokens.css` wywraca zrzut fokusu; po cofnięciu zielony

#### Manual Verification:

- Macierz 7 stanów na `/ui/` i home, w obu motywach, desktop + telefon: default, hover, focus-visible (pierścień z `--ring`, widoczny na tle i karcie), disabled (wygląda na wyłączony, tekst czytelny), error (alert `data-variant="destructive"` z `--destructive-muted`, nie sam kolor — tekst komunikatu), empty — N/A: `TOPICS` to stała 20 tematów (`conversations/topics.py:18`), loading (wskaźnik pod formularzem, bez skoku układu; przy `prefers-reduced-motion` spinner nie wiruje)
- Nawigacja samą klawiaturą po home: kolejność Tab logiczna (Log out → tematy → Delete account), fokus zawsze widoczny
- Strony login, detail i account_delete przejrzane w obu motywach (dziedziczą przyciski i fokus) — bez rażących błędów

**Implementation Note**: Po zielonej automatyce zatrzymaj się na ręczne potwierdzenie przed fazą 5.

---

## Phase 5: Reguła dla następnego agenta

### Overview

Zostawia w repo instrukcję, która trzyma kolejne zmiany UI na kontrakcie, i domyka dokumentację zarzutów.

### Changes Required:

#### 1. Sekcja UI w CLAUDE.md

**File**: `CLAUDE.md`

**Intent**: Krótka sekcja UI w „TalkAItive — project notes” (poza blokiem `<!-- BEGIN/END @przeprogramowani/10x-cli -->`): tokeny tylko w `accounts/static/ui/css/tokens.css` (źródło `theme-source.css`, AA w obu motywach, test kontrastu); komponenty w `components.css` z listą klas — sprawdź je przed dodaniem nowego, nowy dodaj tam; warianty wyłącznie przez `data-variant` (konwencja Basecoat), nie przez klasy `btn-*`; komponent z więcej niż jednym elementem HTML powtarzany w 2+ miejscach → szablon `accounts/templates/ui/<nazwa>.html` przez `{% include … with … only %}` (w środku te same klasy; `csrf_token` przekazany jawnie, jeśli komponent zawiera formularz); zero kolorów, `<style>` i `style=` w szablonach (pilnuje `tests/test_ui.py`); `/ui/` jako kitchen sink tylko w DEBUG — każdy nowy komponent lub stan trafia tam; zrzuty `tests/e2e/ui-home.spec.ts` uruchamiane lokalnie, baseline aktualizowany tylko z opisem zmiany; `class="flash` musi zostać na początku znacznika komunikatu.

**Contract**: Jedna nowa sekcja; żadna istniejąca reguła nie zaprasza do jednorazowych wartości (sprawdzone w research C4).

#### 2. Status zarzutów

**File**: `context/changes/ui-home-tokens/research.md`

**Intent**: Dopisać pod tabelą `## Charges` status każdego zarzutu (C1–C5: addressed, z fazą) oraz to, że C4 świadomie otwiera decyzję F2 z 2026-10-07 (reguły `.topbar` w `components.css`, markup w `home.html`), a C5 zmienia miejsce linku z `plan-brief.md:24` tamtej zmiany. Strony spoza zakresu zapisać jako deferred z powodem.

**Contract**: Dopisek, bez usuwania istniejących wierszy.

### Success Criteria:

#### Automated Verification:

- Testy przechodzą: `uv run pytest`
- Blok 10x-cli w `CLAUDE.md` nietknięty: `git diff CLAUDE.md` pokazuje zmiany tylko poza znacznikami `BEGIN/END @przeprogramowani/10x-cli`

#### Manual Verification:

- Sekcja UI w `CLAUDE.md` czytelna i zgodna z faktycznymi ścieżkami i nazwami klas
- Lista kontrolna `.claude/skills/10x-ui/references/ui-quality-checklist.md` przejrzana punkt po punkcie przed `/10x-impl-review`

---

## Testing Strategy

### Unit Tests:

- `tests/test_ui.py`: `finders` dla obu plików CSS; brak literałów koloru, `<style>` i `style=` w szablonach projektu; brak literałów w `components.css`; kontrast `CONTRAST_PAIRS` w jasnym i ciemnym motywie; widok `/ui/` (404 bez DEBUG, 200 z DEBUG, przekierowanie bez logowania).
- `tests/test_account_deletion.py`: link usuwania konta poza paskiem.
- `tests/test_ui.py`: komunikat błędu z `data-variant="error"` i alias `.alert[data-variant="error"]` w `components.css`.
- Istniejące asercje na przypiętym HTML (`typing`, `transcript`, brak `class="flash`, `href`, teksty home) zostają bez zmian i muszą być zielone.

### Integration Tests:

- `tests/e2e/ui-home.spec.ts`: zrzuty home (default, loading) i `/ui/` (cała strona, focus, hover) × jasny/ciemny × desktop/telefon, lokalnie.

### Manual Testing Steps:

1. `uv run python manage.py runserver`, zaloguj się, obejrzyj home w jasnym i ciemnym motywie systemu na desktopie i w trybie telefonu w DevTools.
2. Przejdź home samym klawiszem Tab; sprawdź widoczność fokusu na każdym elemencie.
3. Otwórz `/ui/` i przejdź macierz 7 stanów.
4. Obejrzyj login, rozmowę i usuwanie konta w obu motywach.

## Performance Considerations

Dwa małe pliki CSS z hashem w nazwie (whitenoise + manifest) zastępują inline `<style>` — przeglądarka buforuje je między stronami. Brak plików czcionek.

## Migration Notes

Brak migracji danych. Rollback = revert PR. `collectstatic` w starcie Railway (`context/deployment/web-settings.json:7`) zbiera nowe pliki automatycznie.

## References

- Research (zarzuty C1–C5, kontrast, mapowanie literałów): `context/changes/ui-home-tokens/research.md`
- Źródło tokenów: `context/changes/ui-home-tokens/theme-source.css`
- Kontrakt zmiany: `context/changes/ui-home-tokens/change.md`
- Skill i lista kontrolna: `.claude/skills/10x-ui/SKILL.md`, `.claude/skills/10x-ui/references/ui-quality-checklist.md`
- Decyzja F2 o `.topbar`: `context/archive/2026-10-07-account-and-data-deletion/reviews/impl-review.md:36-53`
- Wzorzec testu E2E: `tests/e2e/seed.spec.ts`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Pliki statyczne bez zmiany wyglądu

#### Automated

- [x] 1.1 Testy przechodzą: `uv run pytest` — 5510549
- [x] 1.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 5510549
- [x] 1.3 Manifest zawiera oba pliki po prawdziwym `collectstatic` z produkcyjnym storage — 5510549
- [x] 1.4 Skan literałów w szablonach daje 0 trafień `<style` — 5510549

#### Manual

- [x] 1.5 Home, login, detail i account_delete wyglądają tak samo jak przed zmianą — 5510549

### Phase 2: Tokeny (jasne + ciemne) i strażnicy

#### Automated

- [x] 2.1 Testy przechodzą, w tym nowi strażnicy — edd065e
- [x] 2.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — edd065e
- [x] 2.3 Skan literałów na szablonach i `components.css` daje 0 trafień — edd065e
- [x] 2.4 Celowe złamanie wywraca strażnika szablonów i test kontrastu; po cofnięciu oba zielone — edd065e
- [x] 2.5 `collectstatic` z produkcyjnym storage kończy się bez błędu — edd065e

#### Manual

- [x] 2.6 Strony czytelne w jasnym i ciemnym motywie systemu, desktop + telefon — edd065e
- [x] 2.7 Wartości kolorów sprawdzone w DevTools dla 2–3 par, zgodne z testem — edd065e

### Phase 3: Widok home na komponentach

#### Automated

- [x] 3.1 Testy przechodzą: `uv run pytest` — 0405ecb
- [x] 3.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 0405ecb
- [x] 3.3 Skan literałów daje 0 trafień — 0405ecb
- [x] 3.4 Celowe złamanie: link „Delete account” w pasku wywraca nowy test; po cofnięciu zielony — 0405ecb

#### Manual

- [x] 3.5 Home w trzech wariantach w obu motywach, desktop + telefon — 0405ecb
- [x] 3.6 Wskaźnik pisania po kliknięciu tematu i wylogowanie działają — 0405ecb
- [x] 3.7 Komunikat po usunięciu konta wygląda jak alert success — 0405ecb

### Phase 4: Stany, kitchen sink i bramka wizualna

#### Automated

- [x] 4.1 Testy przechodzą: `uv run pytest` — 21e4c26
- [x] 4.2 Lint i format: `uv run ruff check . && uv run ruff format --check .` — 21e4c26
- [x] 4.3 Zrzuty przechodzą lokalnie dwa razy pod rząd — 21e4c26
- [x] 4.4 Pełny zestaw E2E zielony: `npx playwright test` — 21e4c26
- [x] 4.5 Celowe złamanie `--ring` wywraca zrzut fokusu; po cofnięciu zielony — 21e4c26

#### Manual

- [x] 4.6 Macierz 7 stanów na `/ui/` i home, w obu motywach, desktop + telefon — 21e4c26
- [x] 4.7 Nawigacja samą klawiaturą po home: logiczna kolejność, fokus zawsze widoczny — 21e4c26
- [x] 4.8 Strony login, detail i account_delete przejrzane w obu motywach — 21e4c26

### Phase 5: Reguła dla następnego agenta

#### Automated

- [x] 5.1 Testy przechodzą: `uv run pytest`
- [x] 5.2 Blok 10x-cli w `CLAUDE.md` nietknięty

#### Manual

- [x] 5.3 Sekcja UI w `CLAUDE.md` czytelna i zgodna z faktycznymi ścieżkami i klasami
- [x] 5.4 Lista kontrolna `ui-quality-checklist.md` przejrzana przed `/10x-impl-review`
