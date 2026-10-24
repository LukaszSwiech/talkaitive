# Siatka kart tematów na home — Implementation Plan

## Overview

Lista 20 tematów na home staje się siatką kart w 4 kategoriach. Nad siatką stoi przyklejony (sticky) pasek linków do kategorii (warianty A+B). Pod nagłówkiem jest przycisk „Surprise me”, który od razu startuje losowy temat, inny niż temat ostatniej rozmowy (wariant C). Każda karta ma obowiązkową ikonę Tabler (outline, MIT), wklejoną do repo jako szablon SVG. Ikona rysuje się `currentColor` i ma `aria-hidden`. `Topic` dostaje pola `name`, `subtitle`, `category` i `icon`; `title` zostaje. Zmiana zostawia strażników pytest i instrukcję „jak dodać temat lub ikonę” w `CLAUDE.md`.

## Current State Analysis

- `conversations/topics.py:11-15` — `@dataclass(frozen=True) class Topic(key, title, scenario)`, 20 tematów w `TOPICS` (:18-181), `get_topic` (:186). Brak kategorii i ikon.
- Rozmowa kopiuje `topic`, `topic_title`, `topic_scenario` (`conversations/models.py:19-25`). Lista tematów zmienia się więc **bez migracji**. `services.py:235` i `tests/test_conversation_views.py:212` budują `Topic(key, title, scenario)` ręcznie z tej kopii.
- Klucze tematów są używane przez golden-set evalu (`scripts/eval/golden.py`, `tests/test_eval_golden.py:147,164`), pamięć (`memory.py:77-90`) i fixture'y testów. **Klucze się nie zmieniają.**
- Home (`conversations/views.py:39-57`, `conversations/templates/conversations/home.html:15-36`) ma trzy gałęzie: aktywna rozmowa / wyczerpany limit / „Choose a topic” z `<ul class="choice-list">` i formularzem `POST conversation_start` per temat (`data-waits-for-agent`, ukryte pole `topic`).
- `services.start_conversation` (`services.py:126-158`) odrzuca nieznany temat, wyczerpany limit i drugą aktywną rozmowę (`ConversationError`). Widok `conversation_start` (`views.py:60-77`) zamienia błędy na komunikat i przekierowanie.
- `components.css`: `body { max-width: 36rem }` (:7), `.choice-list` (:48-51) stylizuje tylko przyciski, brak jakiegokolwiek `display: grid`. Fokus to jedna globalna reguła (:16) dla `button`/`a`/`input`/`textarea`.
- `base.html:12` — `<body>` bez klasy i bez bloku na nią. JS (:25-40) przy formularzu z `data-waits-for-agent` wyłącza wszystkie przyciski i wstawia „Agent is typing…” za formularzem.
- `tests/test_ui.py:94-123` skanuje **każdy plik** w `templates/` aplikacji projektu (`rglob("*")`): zakaz literałów kolorów (`COLOUR_LITERAL` :40-42, m.in. `#[0-9a-fA-F]{3,8}\b`) i `style=` / `<style`. Kotwica `href="#add-…"`, `#bed`, `#fade` wywróciłaby ten test.
- Kitchen sink (`views.py:168-205`, `accounts/templates/accounts/ui_kitchen_sink.html`) pokazuje `TOPICS[:3]` w sekcji „Choice list” (:38-45). `KITCHEN_SINK_MARKUP` (`tests/test_ui.py:272-295`) wymaga m.in. `'<ul class="choice-list">'`.
- `tests/e2e/ui-home.spec.ts`: lokator `'Walking the dog'` (:62), hover na `'Supermarket'` w regionie `'Choice list'` (:94-95), 20 baseline'ów (`home-default`, `home-loading`, `ui-kitchen-sink`, `ui-focus`, `ui-hover` × 2 motywy × 2 szerokości).
- W repo nie ma żadnego SVG aplikacji, katalogu ikon ani pliku licencji zewnętrznej. W kodzie nie ma żadnego losowania.
- `settings_test.py:6-10` używa zwykłego `StaticFilesStorage`, a produkcja `CompressedManifestStaticFilesStorage` (brakujący plik w `{% static %}` = 500). Ikony jako **szablony** omijają ten problem: brakujący plik to `TemplateDoesNotExist` i łapie go strażnik pytest.

## Desired End State

Zalogowany użytkownik bez aktywnej rozmowy i z wolnym limitem widzi na home (jasny i ciemny motyw, telefon i desktop):

1. Nagłówek „Choose a topic”, pod nim przycisk primary „Surprise me” z ikoną `arrows-shuffle`.
2. Przyklejony pasek `<nav aria-label="Topic categories">` z 4 linkami: Shops & errands, Neighbours & small talk, Appointments & officials, Social life. Na telefonie pasek ma jedną linię z poziomym przewijaniem.
3. Cztery sekcje z nagłówkami `h3` (id `errands`, `small-talk`, `appointments`, `social`). Po kliknięciu linku nagłówek sekcji jest widoczny **pod** paskiem sticky.
4. Siatkę kart: 1 kolumna na telefonie, 2–3 na desktopie (home ma szerszy kontener ~60rem). Karta to przycisk z ikoną, krótką nazwą i podtytułem. Hover, fokus i loading działają jak dotąd.
5. „Surprise me” startuje rozmowę z losowego tematu, innego niż temat ostatniej rozmowy użytkownika.

Weryfikacja: `uv run pytest` zielone (w tym nowe strażniki), `npx playwright test tests/e2e/ui-home.spec.ts` zielone z odświeżonymi baseline'ami, ręczny przegląd home.

### Key Discoveries:

- Brak migracji: `conversations/topics.py:1-5` i `models.py:19-20` gwarantują, że rozmowa ma własną kopię tematu.
- Nowe pola `Topic` muszą mieć wartości domyślne, bo `services.py:235` (i test `:212`) tworzy `Topic` z trzech pól.
- `<img src="….svg">` nie dziedziczy `currentColor`, więc ikona musi być inline w HTML. Stąd SVG jako szablony w `accounts/templates/ui/icons/`.
- Istniejący strażnik kolorów (`tests/test_ui.py:112-123`) automatycznie obejmie pliki `.svg`, `LICENSE` i `README.md` w `templates/ui/icons/`.
- `muted-foreground` na `card` jest już w `CONTRAST_PAIRS` (`tests/test_ui.py:63`), na `accent` nie ma. Podtytuł przy hover przejmuje więc `--accent-foreground` (para `accent-foreground`/`accent` już jest, :64).
- `ID_ROUTES` dotyczy tylko tras z id. Nowa trasa `start/random/` go nie wymaga. Nie powstaje nowy model, więc `MODEL_DECISIONS` też bez zmian.

## What We're NOT Doing

- Nie zmieniamy kluczy ani `title`/`scenario` tematów, promptów, evalu ani pamięci.
- Nie zapisujemy kategorii ani ikony w `Conversation` (brak migracji). Strona rozmowy dalej pokazuje `topic_title`.
- Nie dodajemy zależności npm ani pakietu ikon. Tylko wklejony podzbiór 21 plików SVG.
- Nie robimy wyszukiwarki, filtrów, ulubionych ani „Back to top”.
- Nie dodajemy płynnego przewijania ani nowego JS (sticky to czyste CSS).
- „Surprise me” nie pokazuje wylosowanego tematu przed startem i nie pyta o potwierdzenie. Rozmowa startuje od razu.
- Nie zmieniamy szerokości innych stron (logowanie, rozmowa, usuwanie konta zostają na 36rem).
- Nie uruchamiamy prawdziwego startu rozmowy w E2E. POST jest przerywany, jak w obecnym teście loading.
- Playwright dalej nie trafia do CI.

## Implementation Approach

Od danych do pikseli. Faza 1 dodaje pola, kategorie, ikony i strażników bez zmiany wyglądu. Faza 2 dodaje losowanie i trasę bez UI. Faza 3 przebudowuje home i kitchen sink na nowe komponenty. Faza 4 aktualizuje bramkę zrzutów. Faza 5 zapisuje regułę. Każda faza zostawia zielone `uv run pytest` i CI.

Kategorie są danymi w `topics.py` (`Category(key, label)` + `CATEGORIES` w ustalonej kolejności). Widok dostaje gotowe grupy z jednej funkcji, więc szablon nie filtruje. Karta jest szablonem `ui/topic-card.html` (sam przycisk, bez formularza), bo powstaje w dwóch miejscach: na home i w kitchen sinku. Formularz zostaje w `home.html`, a kitchen sink przekazuje `type="button"`.

## Branches and PRs

Jedna gałąź `ui-home-topic-grid` (już istnieje) i jeden PR dla wszystkich faz. Fazy 1–2 dałoby się wdrożyć osobno, ale same w sobie nic nie zmieniają dla użytkownika, a jeden PR pozwala przejrzeć dane, losowanie i wygląd razem.

## Critical Implementation Details

**Pobieranie ikon.** Pobranie plików z GitHuba wymaga wcześniejszej zgody użytkownika w czacie (nazwa pliku, źródło). Źródło: przypięty tag release `tabler/tabler-icons` (najnowszy w dniu implementacji), ścieżka `icons/outline/<nazwa>.svg`. Jeśli któraś nazwa z tabeli nie istnieje w tej wersji, wybierz najbliższą i zapisz zamianę w `README.md` ikon oraz w tabeli w tym planie.

**Pasek sticky a kotwice i fokus.** `html:has(.category-nav)` dostaje `scroll-padding-top` co najmniej równe wysokości paska (plus mały odstęp). Jedna reguła obejmuje skok do kotwicy i przewijanie do elementu z fokusem (Shift+Tab w górę), więc pasek nie zasłania ani nagłówka sekcji, ani karty z fokusem (WCAG 2.2, 2.4.11). Strony bez paska nie dostają tego przesunięcia. Pasek ma jedną linię na każdej szerokości (poziome przewijanie zamiast zawijania), żeby ta wysokość była stała. Pasek ma pełne tło `var(--background)`, bo inaczej karty prześwitują pod nim.

## Phase 1: Dane tematów, ikony i strażnicy

### Overview

`Topic` dostaje cztery nowe pola, `topics.py` dostaje kategorie, repo dostaje 21 ikon z licencją. Strażnicy pytest pilnują, że każdy temat ma kategorię i istniejącą ikonę. Wygląd strony bez zmian.

### Changes Required:

#### 1. Model danych tematu

**File**: `conversations/topics.py`

**Intent**: Dodać do `Topic` pola widoczne na karcie i stałą z kategoriami w kolejności wyświetlania, plus funkcję grupującą tematy dla widoku. Zaktualizować docstring modułu (co jest pokazywane, co idzie do modelu).

**Contract**:
- `Topic(key, title, scenario, name: str = "", subtitle: str = "", category: str = "", icon: str = "")`. Domyślne `""` zachowują zgodność z `services.py:235`. Każdy wpis w `TOPICS` ma wszystkie cztery pola niepuste (pilnuje test).
- Właściwość `Topic.icon_template -> str` zwraca `"ui/icons/<icon>.svg"`.
- `@dataclass(frozen=True) class Category(key: str, label: str)`, `CATEGORIES: tuple[Category, ...]` w kolejności: `errands` „Shops & errands”, `small-talk` „Neighbours & small talk”, `appointments` „Appointments & officials”, `social` „Social life”.
- `topics_by_category() -> list[tuple[Category, list[Topic]]]` — kategorie w kolejności `CATEGORIES`, tematy w kolejności `TOPICS`.
- Wartości per temat (klucze bez zmian):

| key | name | subtitle | category | icon |
| --- | --- | --- | --- | --- |
| dog-walk | Dog walk | Chatting with another dog owner | small-talk | dog |
| supermarket | Supermarket | Asking where to find something | errands | shopping-cart |
| bakery | Bakery | Ordering breakfast rolls | errands | bread |
| neighbour-stairwell | Stairwell | Small talk with a neighbour | small-talk | stairs |
| neighbour-parcel | Parcel | Picking it up from a neighbour | small-talk | package |
| doctor-appointment | Doctor | Calling for an appointment | appointments | stethoscope |
| pharmacy | Pharmacy | Something for a cold | errands | pill |
| colleague-weekend | Weekend plans | Chatting with a colleague | social | briefcase |
| playground | Playground | Chatting with another parent | small-talk | swing |
| post-office | Post office | Sending a parcel | errands | mail |
| hairdresser | Hairdresser | Explaining the cut you want | errands | scissors |
| restaurant | Restaurant | Ordering and paying | social | tools-kitchen-2 |
| public-transport | Public transport | Ticket problem and directions | appointments | bus |
| train-delay | Train delay | Talking with a fellow passenger | small-talk | train |
| landlord-heating | Broken heater | Reporting it to the landlord | appointments | flame |
| registration-office | Bürgeramt | Registering your address | appointments | id |
| bus-stop-weather | Bus stop | Weather small talk | small-talk | cloud-rain |
| birthday-party | Birthday party | Meeting a friend's friends | social | cake |
| sports-club | Sports club | Joining a local club | social | ball-football |
| car-workshop | Car workshop | Booking a tyre change | errands | car |

Ikona przycisku „Surprise me”: `arrows-shuffle`. Razem 21 plików.

#### 2. Wklejone ikony Tabler

**File**: `accounts/templates/ui/icons/<nazwa>.svg` (21 plików), `accounts/templates/ui/icons/LICENSE`, `accounts/templates/ui/icons/README.md`

**Intent**: Wkleić podzbiór ikon outline z przypiętej wersji Tabler, ujednolicić korzeń `<svg>` pod nasze potrzeby i zapisać licencję MIT oraz pochodzenie plików.

**Contract**:
- Każdy plik to jeden element `<svg>` z `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"` (te trzy zostają z oryginału Tabler; bez nich linia ma grubość 1 i kanciaste końce), `class="icon"`, `aria-hidden="true"`, `focusable="false"`. Bez `width`/`height` (rozmiar z CSS), bez `style=` i bez kolorów (strażnik `tests/test_ui.py:112`). Ścieżki rysunku bez zmian.
- `LICENSE` — pełny tekst licencji MIT Tabler z repozytorium źródłowego.
- `README.md` — wersja (tag release), URL źródła, lista plików z tematami, które ich używają, opis ujednolicenia korzenia `<svg>` i odsyłacz do how-to w `CLAUDE.md`.

#### 3. Strażnicy danych i ikon

**File**: `tests/test_topics.py` (nowy)

**Intent**: Wywrócić CI, gdy temat nie ma nazwy, podtytułu, znanej kategorii albo istniejącej ikony, gdy kategoria jest pusta, albo gdy plik ikony nie spełnia kontraktu.

**Contract** — testy:
- każdy temat w `TOPICS` ma niepuste `name`, `subtitle`, `category`, `icon`;
- `category` każdego tematu należy do kluczy `CATEGORIES`; każda kategoria ma co najmniej 1 temat; klucze kategorii unikalne;
- `get_template(topic.icon_template)` działa dla każdego tematu i dla `ui/icons/arrows-shuffle.svg`;
- każdy plik `*.svg` w katalogu ikon zawiera w korzeniu `aria-hidden="true"`, `stroke="currentColor"` i `stroke-width="2"`;
- w katalogu ikon nie ma plików osieroconych: każdy `.svg` jest ikoną jakiegoś tematu albo należy do jawnego zbioru `{"arrows-shuffle"}` w teście;
- `topics_by_category()` zwraca wszystkie 20 tematów dokładnie raz, w kolejności `CATEGORIES`, a w środku w kolejności `TOPICS`;
- id kategorii nie pasują do `COLOUR_LITERAL` z `tests/test_ui.py` po dodaniu `#` (import wzorca, nie kopia).

### Success Criteria:

#### Automated Verification:

- Nowe strażniki przechodzą: `uv run pytest tests/test_topics.py`
- Cały zestaw testów przechodzi: `uv run pytest`
- Lint i format czyste: `uv run ruff check . && uv run ruff format --check .`
- Django nie zgłasza problemów: `uv run python manage.py check`

#### Manual Verification:

- `README.md` ikon podaje wersję Tabler, źródło i listę 21 plików zgodną z tabelą w tym planie
- Usunięcie jednego pliku `.svg` (próba na chwilę) wywraca `tests/test_topics.py` z czytelnym komunikatem; plik przywrócony

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Surprise me — losowanie i trasa

### Overview

Serwer losuje temat z pominięciem tematu ostatniej rozmowy użytkownika i startuje go tą samą ścieżką co zwykły wybór. Brak zmian w UI.

### Changes Required:

#### 1. Losowanie tematu

**File**: `conversations/services.py`

**Intent**: Dodać funkcję, która wybiera klucz tematu do „Surprise me”.

**Contract**: `surprise_topic_key(user: User) -> str`.
- „Ostatnia rozmowa” = pierwsza z `Conversation.objects.for_user(user).order_by("-created_at", "-id")`, niezależnie od tego, czy jest zakończona.
- Kandydaci = klucze `TOPICS` w ich kolejności, bez klucza ostatniej rozmowy. Bez historii, gdy klucz ostatniej rozmowy nie istnieje już w `TOPICS`, albo gdy lista kandydatów byłaby pusta — wszystkie klucze.
- Wybór: `random.choice(candidates)` z modułu `random` importowanego w `services.py` (testy podmieniają `conversations.services.random.choice`).

#### 2. Widok i trasa

**File**: `conversations/views.py`, `conversations/urls.py`

**Intent**: Dodać trasę „Surprise me”, która losuje klucz i dalej zachowuje się identycznie jak `conversation_start` (te same komunikaty błędów, przekierowania i obsługa `LLMError`). Wspólną część obu widoków wydzielić do prywatnej funkcji pomocniczej, zamiast kopiować.

**Contract**: `POST /conversations/start/random/`, nazwa `conversation_start_random`, `@require_POST`, wymaga logowania (globalny middleware). Wywołuje `services.start_conversation(request.user, services.surprise_topic_key(request.user), now)`. Mutanty M1 i M2 (`scripts/mutation/manual_mutants.py:93-106`) szukają w `views.py` tekstu `active = (` + `Conversation.objects.for_user(request.user)` z wcięciem 4 spacji (home) i 8 spacji (gałąź `LLMError`). Każdy wariant musi wystąpić dokładnie raz. Funkcja pomocnicza nie powiela tego kodu. Jeśli zmieni się wcięcie, popraw w tym samym kroku `original` (i `area`) mutanta.

#### 3. Testy

**File**: `tests/test_conversations.py`, `tests/test_conversation_views.py`

**Intent**: Pokryć regułę losowania i zachowanie trasy, używając istniejących fake'ów LLM z tych plików.

**Contract** — testy:
- bez historii kandydatami są wszystkie 20 kluczy (podmieniony `random.choice` przechwytuje argument);
- ostatnia rozmowa `bakery` → 19 kandydatów, bez `bakery`;
- starsza rozmowa `dog-walk` i nowsza `bakery` → wykluczony tylko `bakery`;
- ostatnia rozmowa innego użytkownika nie wpływa na kandydatów (strażnik PRD: `for_user`);
- klucz ostatniej rozmowy spoza `TOPICS` → wszystkie 20;
- `POST` → przekierowanie na detail nowej rozmowy, której `topic` to wylosowany klucz;
- `GET` → 405; niezalogowany → przekierowanie do logowania;
- aktywna rozmowa → komunikat „You already have a conversation in progress.”; wyczerpany limit → komunikat limitu (jak przy `conversation_start`).

### Success Criteria:

#### Automated Verification:

- Testy losowania i trasy przechodzą: `uv run pytest tests/test_conversations.py tests/test_conversation_views.py`
- Cały zestaw testów przechodzi: `uv run pytest`
- Lint i format czyste: `uv run ruff check . && uv run ruff format --check .`
- Mutanty izolacji w widokach dalej działają: `uv run python scripts/mutation/manual_mutants.py M1 M2` kończy się kodem 0

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Siatka na home i kitchen sink

### Overview

Home przechodzi na siatkę kart z paskiem sticky i przyciskiem „Surprise me”. Kitchen sink pokazuje nowe komponenty. `choice-list` (jedyny użytkownik to home) zostaje zastąpiony przez `topic-grid` i usunięty.

### Changes Required:

#### 1. Szerszy kontener tylko dla home

**File**: `accounts/templates/base.html`

**Intent**: Pozwolić stronie ustawić klasę na `<body>`, żeby home mogło być szersze bez zmiany innych stron.

**Contract**: `<body class="{% block body_class %}{% endblock %}">`. `home.html` (i kitchen sink, żeby pokazywał siatkę w tej samej szerokości) ustawia `page-wide`.

#### 2. Komponenty

**File**: `accounts/static/ui/css/components.css`

**Intent**: Dodać komponenty siatki, karty, paska kategorii i ikony, czytające wyłącznie `var(--…)`. Usunąć `choice-list`.

**Contract**:
- `body.page-wide` — `max-width: 60rem`.
- `.category-nav` — `position: sticky; top: 0`, tło `var(--background)`, jedna linia z `overflow-x: auto`, linki jako małe pigułki z hover i stanem fokusu z globalnej reguły.
- `html:has(.category-nav)` — `scroll-padding-top` ≥ wysokość `.category-nav` (kotwice i fokus; patrz Critical Implementation Details). `.topic-section` bez własnego `scroll-margin-top`.
- `.topic-grid` — `display: grid; grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr))`, lista bez punktorów.
- `.topic-card` — przycisk-karta (tło `--card`, tekst `--card-foreground`, `--border`, `--shadow-sm`), ikona po lewej, nazwa (pogrubiona) i podtytuł (`--muted-foreground`) w kolumnie. Hover `:hover:not(:disabled)` jak dawny `choice-list` (`--accent` / `--accent-foreground`); podtytuł przy hover przejmuje `--accent-foreground`. Disabled przez istniejącą regułę.
- `.icon` — rozmiar ~1.5rem, `flex: none`. Kolor dziedziczony (`currentColor`), bez nowego tokenu.
- Każda nowa para tekst/tło trafia do `CONTRAST_PAIRS`. Przy powyższym kontrakcie nie powstaje żadna nowa para.

#### 3. Komponent karty

**File**: `accounts/templates/ui/topic-card.html` (nowy)

**Intent**: Jedno źródło markupu karty dla home i kitchen sinka.

**Contract**: `{% include "ui/topic-card.html" with topic=topic type="submit" only %}` renderuje `<button type="{{ type }}" class="topic-card">` z ikoną (`{% include topic.icon_template %}`), `<span>` nazwy i `<span>` podtytułu. Dostępna nazwa przycisku = „<name> <subtitle>”. Bez formularza, więc bez `csrf_token`.

#### 4. Home

**File**: `conversations/templates/conversations/home.html`, `conversations/views.py`

**Intent**: W gałęzi „Choose a topic” zamienić listę na: formularz „Surprise me”, pasek kategorii i sekcje z siatkami kart. Gałęzie aktywnej rozmowy i limitu bez zmian.

**Contract**:
- Widok `home` przekazuje `topic_groups = topics_by_category()` zamiast `topics`.
- `<h2>Choose a topic</h2>` zostaje (sprawdza go E2E i testy).
- Formularz `POST {% url 'conversation_start_random' %}` z `data-waits-for-agent` i `{% csrf_token %}`; `<button class="btn">` z ikoną `ui/icons/arrows-shuffle.svg` i tekstem „Surprise me”.
- `<nav class="category-nav" aria-label="Topic categories">` z linkami `href="#<category.key>"` i tekstem `category.label`.
- Per kategoria: `<section class="topic-section" id="<key>" aria-labelledby="…">` z `<h3>` i `<ul class="topic-grid">`. Każdy `<li>` ma formularz jak dotąd (`POST conversation_start`, `data-waits-for-agent`, ukryte `topic`) z kartą z include.

#### 5. Kitchen sink

**File**: `accounts/templates/accounts/ui_kitchen_sink.html`, `conversations/views.py` (`ui_kitchen_sink`)

**Intent**: Zastąpić sekcję „Choice list” sekcją „Topic grid”, pokazującą pasek kategorii, przycisk „Surprise me” i po jednej przykładowej karcie z każdej kategorii (pierwszy temat kategorii, ostatnia karta disabled). Nic nie wysyła formularza: wszystko z `type="button"`.

**Contract**:
- Sekcja `<section aria-labelledby="ks-topic-grid">` z nagłówkiem „Topic grid” stoi w miejscu dawnej „Choice list”, czyli po „Buttons”. Test fokusu (`tests/e2e/ui-home.spec.ts:84-87`) zakłada, że pierwszy fokus trafia w „Primary”.
- W środku: pasek z 4 linkami i 4 mini-sekcje `topic-section` z id `ks-<category.key>` (id bez wzorca hex). Każdy link ma cel na tej samej stronie, a id nie kolidują z home.
- Widok `ui_kitchen_sink` przekazuje nowy klucz z próbkami (np. `topic_samples` = `(kategoria, pierwszy temat)` z `topics_by_category()`). Klucz `topics` (`TOPICS[:3]`) **zostaje**, bo sekcja „Active conversation” używa `{{ topics.0.title }}` (`ui_kitchen_sink.html:59`).
- Karta „Supermarket” (pierwszy temat `errands`) jest aktywna, bo test hover (Faza 4) na niej najeżdża.

#### 6. Testy pytest

**File**: `tests/test_ui.py`, `tests/test_conversation_views.py`

**Intent**: Dostosować przypięte asercje do nowego markupu i dodać asercje nowej struktury.

**Contract**:
- `KITCHEN_SINK_MARKUP`: zamiast `'<ul class="choice-list">'` — `'<ul class="topic-grid">'`, `'class="topic-card"'`, `'class="category-nav"'`.
- `tests/test_conversation_views.py:360-367`: zamiast pełnego tytułu „Bakery: ordering breakfast rolls” — nazwa „Bakery” i podtytuł „Ordering breakfast rolls” (świadoma zmiana UI: pełny tytuł nie jest już pokazywany na home).
- Nowe testy home: 4 linki paska w kolejności `CATEGORIES` i 4 sekcje z pasującymi id; każdy z 20 kluczy w ukrytym polu `topic` dokładnie raz; formularz „Surprise me” celuje w `conversation_start_random` i ma `data-waits-for-agent`; każda karta zawiera `<svg` z `aria-hidden="true"`; w gałęziach „aktywna rozmowa” i „limit” brak „Surprise me” i paska.

### Success Criteria:

#### Automated Verification:

- Testy UI i widoków przechodzą: `uv run pytest tests/test_ui.py tests/test_conversation_views.py`
- Cały zestaw testów przechodzi: `uv run pytest`
- Lint i format czyste: `uv run ruff check . && uv run ruff format --check .`
- W repo nie zostało użycie `choice-list`: `grep -rn "choice-list" accounts conversations tests` zwraca pusty wynik

#### Manual Verification:

- Home w jasnym i ciemnym motywie: siatka 1 kolumna na telefonie (DevTools ~390 px), 2–3 kolumny na desktopie, ikony w kolorze tekstu karty
- Klik w każdy link kategorii: nagłówek sekcji widoczny pod paskiem sticky; pasek na telefonie mieści się w jednej linii i przewija się poziomo
- Klawiatura: Tab przechodzi przez „Surprise me”, linki paska i karty z widocznym fokusem; po przewinięciu w dół Shift+Tab wraca w górę i karta z fokusem nie chowa się pod paskiem
- „Surprise me” z prawdziwym LLM (`uv run --env-file .env python manage.py runserver`) pokazuje „Agent is typing…” i otwiera rozmowę z innym tematem niż poprzednia
- Kitchen sink `/ui/` pokazuje sekcję „Topic grid” ze stanem disabled; inne strony (logowanie, rozmowa) mają dawną szerokość

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: E2E i zrzuty

### Overview

Bramka zrzutów zna nowy home: poprawione lokatory, dwa nowe testy dla ryzyk widocznych tylko w przeglądarce i odświeżone baseline'y.

### Changes Required:

#### 1. Spec Playwright

**File**: `tests/e2e/ui-home.spec.ts`

**Intent**: Dostosować lokatory i dodać dwa testy: skok do kategorii pod paskiem sticky oraz stan oczekiwania po „Surprise me”. Trzymać się zasad z `CLAUDE.md` (role/label/text, bez `waitForTimeout`, niezależne testy).

**Contract**:
- Test loading (:62): `getByRole('button', { name: /Dog walk/ })`.
- Test hover (:94-95): region `'Topic grid'`, przycisk `{ name: /Supermarket/ }`.
- Nowy test „jump link shows the category heading below the sticky bar”: klik w link „Neighbours & small talk” w nawigacji „Topic categories” → strona się przewinęła (`window.scrollY > 0`), nagłówek „Neighbours & small talk” `toBeInViewport()`, a górna krawędź nagłówka jest poniżej dolnej krawędzi paska (porównanie `boundingBox()`). Działa na obu szerokościach i w obu motywach. Nie ostatnia kategoria: sekcja „Social life” razem ze stopką jest niższa niż ekran (720 i 844 px), więc nigdy nie dochodzi do góry i test byłby zielony także bez `scroll-padding-top`.
- Nowy test „Surprise me shows the waiting state”: `page.route` przerywa `POST /conversations/start/random/`, klik w „Surprise me” → „Agent is typing…” widoczne, „Log out” disabled, zrzut `home-surprise-loading`.

#### 2. Baseline'y

**File**: `tests/e2e/ui-home.spec.ts-snapshots/`

**Intent**: Odświeżyć baseline'y po świadomej zmianie wyglądu (home-default, home-loading, ui-kitchen-sink, ui-hover, ui-focus jeśli się zmienił) i dodać 4 nowe `home-surprise-loading-*`. Zmiana opisana w commicie.

**Contract**: `npx playwright test tests/e2e/ui-home.spec.ts --update-snapshots` (z `E2E_PORT=8001`, jeśli port 8000 jest zajęty), potem przebieg bez flagi jest zielony.

### Success Criteria:

#### Automated Verification:

- Spec przechodzi z nowymi baseline'ami: `npx playwright test tests/e2e/ui-home.spec.ts`
- Celowe zepsucie: usunięcie `scroll-padding-top` z `html:has(.category-nav)` wywraca test skoku do kategorii; po przywróceniu znowu zielony
- Cały zestaw pytest przechodzi: `uv run pytest`

#### Manual Verification:

- Przegląd nowych PNG (home w 2 motywach × 2 szerokościach, kitchen sink, surprise-loading): układ, ikony, pasek i fokus wyglądają jak zamierzono

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: Reguła w CLAUDE.md

### Overview

Kolejny agent wie, jakich komponentów użyć i jak dodać temat lub ikonę bez łamania strażników.

### Changes Required:

#### 1. Sekcja UI

**File**: `CLAUDE.md` (sekcja „### UI: tokens and components”, poza blokiem `<!-- BEGIN/END @przeprogramowani/10x-cli -->`)

**Intent**: Zaktualizować listę komponentów i dopisać how-to dla tematów i ikon.

**Contract**:
- Lista komponentów: zamiast `choice-list` — `topic-grid`, `topic-card` (include `ui/topic-card.html`), `category-nav`, `icon`; klasa strony `page-wide` przez `{% block body_class %}`.
- How-to „Adding a topic or icon”: (1) nowy `Topic` w `conversations/topics.py` z `name`, `subtitle`, `category` (klucz z `CATEGORIES`) i `icon` (nazwa Tabler outline); klucz nigdy się nie zmienia; (2) plik ikony z tej samej wersji Tabler co w `accounts/templates/ui/icons/README.md`, korzeń `<svg>` ujednolicony według README, wpis na liście w README; (3) nowa kategoria = wpis w `CATEGORIES`, id bez wzorca hex; (4) `uv run pytest tests/test_topics.py` pilnuje reszty.

### Success Criteria:

#### Automated Verification:

- Sekcja wspomina nowe komponenty i katalog ikon: `grep -n "topic-card\|ui/icons" CLAUDE.md` zwraca wiersze z sekcji UI
- Blok 10x-cli nietknięty: `git diff CLAUDE.md` nie pokazuje zmian między `<!-- BEGIN` a `<!-- END`
- Cały zestaw pytest przechodzi: `uv run pytest`

#### Manual Verification:

- Instrukcję „Adding a topic or icon” da się wykonać krok po kroku bez zaglądania do kodu (przegląd przez użytkownika)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `tests/test_topics.py`: kompletność pól, kategorie, istnienie i kontrakt plików ikon, brak sierot, grupowanie.
- `tests/test_conversations.py`: reguła losowania (bez historii, wykluczenie ostatniego, tylko ostatni, cudza historia, klucz spoza listy).

### Integration Tests:

- `tests/test_conversation_views.py`: trasa `start/random/` (sukces, 405, logowanie, aktywna rozmowa, limit) i struktura home (pasek, sekcje, 20 formularzy, „Surprise me”, ikony, gałęzie bez siatki).
- `tests/test_ui.py`: kitchen sink, strażnik kolorów obejmujący pliki ikon.
- `tests/e2e/ui-home.spec.ts` (lokalnie): skok do kategorii pod paskiem sticky, loading po „Surprise me”, zrzuty.

### Manual Testing Steps:

1. `uv run --env-file .env python manage.py runserver`, zalogować się użytkownikiem bez aktywnej rozmowy.
2. Przejrzeć home w jasnym i ciemnym motywie, na desktopie i w DevTools ~390 px.
3. Kliknąć każdy link kategorii i sprawdzić, że nagłówek nie chowa się pod paskiem.
4. Przejść Tabem przez stronę i sprawdzić widoczny fokus.
5. Zakończyć rozmowę, wrócić na home, kliknąć „Surprise me” kilka razy (z kończeniem rozmów) — temat nigdy nie powtarza poprzedniego.

## Performance Considerations

Home wstawia inline 21 ikon (~0,4 KB każda, ~8–9 KB HTML przed kompresją). Ikony nie są cache'owane osobno, ale strona i tak jest renderowana per użytkownik. Losowanie to jedno zapytanie po indeksowanym kluczu użytkownika. Bez wpływu na LLM i budżet.

## Migration Notes

Brak migracji bazy. Istniejące rozmowy zachowują swoje `topic_title` i `topic_scenario`. Klucze tematów bez zmian, więc pamięć, eval i historia działają jak dotąd.

## References

- Change: `context/changes/ui-home-topic-grid/change.md`
- Poprzednia zmiana (kontrakt UI): `context/archive/2026-10-20-ui-home-tokens/plan.md`, `plan-brief.md`, `research.md`
- Tematy: `conversations/topics.py:11-186`
- Start rozmowy: `conversations/services.py:126-158`, `conversations/views.py:60-77`
- Home: `conversations/views.py:39-57`, `conversations/templates/conversations/home.html:15-36`
- Strażnicy UI: `tests/test_ui.py:40-43`, `:94-123`, `:272-295`
- Bramka zrzutów: `tests/e2e/ui-home.spec.ts:41-95`
- Kontrakt UI: `CLAUDE.md` sekcja „UI: tokens and components”

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Dane tematów, ikony i strażnicy

#### Automated

- [x] 1.1 Nowe strażniki przechodzą: `uv run pytest tests/test_topics.py` — 38975e9
- [x] 1.2 Cały zestaw testów przechodzi: `uv run pytest` — 38975e9
- [x] 1.3 Lint i format czyste: `uv run ruff check . && uv run ruff format --check .` — 38975e9
- [x] 1.4 Django nie zgłasza problemów: `uv run python manage.py check` — 38975e9

#### Manual

- [x] 1.5 `README.md` ikon podaje wersję Tabler, źródło i listę 21 plików zgodną z tabelą w tym planie — 38975e9
- [x] 1.6 Usunięcie jednego pliku `.svg` (próba na chwilę) wywraca `tests/test_topics.py` z czytelnym komunikatem; plik przywrócony — 38975e9

### Phase 2: Surprise me — losowanie i trasa

#### Automated

- [x] 2.1 Testy losowania i trasy przechodzą: `uv run pytest tests/test_conversations.py tests/test_conversation_views.py` — 070e583
- [x] 2.2 Cały zestaw testów przechodzi: `uv run pytest` — 070e583
- [x] 2.3 Lint i format czyste: `uv run ruff check . && uv run ruff format --check .` — 070e583
- [x] 2.4 Mutanty izolacji w widokach dalej działają: `uv run python scripts/mutation/manual_mutants.py M1 M2` kończy się kodem 0 — 070e583

### Phase 3: Siatka na home i kitchen sink

#### Automated

- [x] 3.1 Testy UI i widoków przechodzą: `uv run pytest tests/test_ui.py tests/test_conversation_views.py` — 8c5564b
- [x] 3.2 Cały zestaw testów przechodzi: `uv run pytest` — 8c5564b
- [x] 3.3 Lint i format czyste: `uv run ruff check . && uv run ruff format --check .` — 8c5564b
- [x] 3.4 W repo nie zostało użycie `choice-list`: `grep -rn "choice-list" accounts conversations tests` zwraca pusty wynik — 8c5564b

#### Manual

- [x] 3.5 Home w jasnym i ciemnym motywie: siatka 1 kolumna na telefonie (DevTools ~390 px), 2–3 kolumny na desktopie, ikony w kolorze tekstu karty — 8c5564b
- [x] 3.6 Klik w każdy link kategorii: nagłówek sekcji widoczny pod paskiem sticky; pasek na telefonie mieści się w jednej linii i przewija się poziomo — 8c5564b
- [x] 3.7 Klawiatura: Tab przechodzi przez „Surprise me”, linki paska i karty z widocznym fokusem; po przewinięciu w dół Shift+Tab wraca w górę i karta z fokusem nie chowa się pod paskiem — 8c5564b
- [x] 3.8 „Surprise me” z prawdziwym LLM (`uv run --env-file .env python manage.py runserver`) pokazuje „Agent is typing…” i otwiera rozmowę z innym tematem niż poprzednia — 8c5564b
- [x] 3.9 Kitchen sink `/ui/` pokazuje sekcję „Topic grid” ze stanem disabled; inne strony (logowanie, rozmowa) mają dawną szerokość — 8c5564b

### Phase 4: E2E i zrzuty

#### Automated

- [x] 4.1 Spec przechodzi z nowymi baseline'ami: `npx playwright test tests/e2e/ui-home.spec.ts` — 0b8c6a7
- [x] 4.2 Celowe zepsucie: usunięcie `scroll-padding-top` z `html:has(.category-nav)` wywraca test skoku do kategorii; po przywróceniu znowu zielony — 0b8c6a7
- [x] 4.3 Cały zestaw pytest przechodzi: `uv run pytest` — 0b8c6a7

#### Manual

- [x] 4.4 Przegląd nowych PNG (home w 2 motywach × 2 szerokościach, kitchen sink, surprise-loading): układ, ikony, pasek i fokus wyglądają jak zamierzono — 0b8c6a7

### Phase 5: Reguła w CLAUDE.md

#### Automated

- [x] 5.1 Sekcja wspomina nowe komponenty i katalog ikon: `grep -n "topic-card\|ui/icons" CLAUDE.md` zwraca wiersze z sekcji UI
- [x] 5.2 Blok 10x-cli nietknięty: `git diff CLAUDE.md` nie pokazuje zmian między `<!-- BEGIN` a `<!-- END`
- [x] 5.3 Cały zestaw pytest przechodzi: `uv run pytest`

#### Manual

- [x] 5.4 Instrukcję „Adding a topic or icon” da się wykonać krok po kroku bez zaglądania do kodu (przegląd przez użytkownika)
