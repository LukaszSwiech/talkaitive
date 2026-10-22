---
date: 2026-10-20T14:03:29+02:00
researcher: Claude (Opus 5.5) z LukaszSwiech
git_commit: f46133d
branch: ui-home-tokens
repository: 10xDevs4
topic: "Audyt UI widoku home (/10x-ui): brakujące tokeny, brakujące wspólne komponenty, przypadkowa architektura"
tags: [research, ui, design-tokens, css, templates, accessibility, contrast, staticfiles, whitenoise, playwright, home]
status: complete
last_updated: 2026-10-20
last_updated_by: Claude (Opus 5.5)
---

# Research: Audyt UI widoku home (ui-home-tokens)

**Date**: 2026-10-20T14:03:29+02:00
**Researcher**: Claude (Opus 5.5) z LukaszSwiech
**Git Commit**: f46133d (drzewo robocze: niezacommitowany folder `context/changes/ui-home-tokens/` — `change.md`, `theme-source.css`)
**Branch**: ui-home-tokens
**Repository**: 10xDevs4

## Research Question

Dwustronny audyt UI (z `/10x-ui`) widoku home: `conversations/templates/conversations/home.html` renderowanego w `accounts/templates/base.html`. Wynik: 3–5 zarzutów w `## Charges` (file:line, kategoria: missing token / missing shared component / accidental architecture, jedno zdanie o skutku dla użytkownika), weryfikacja szkicu z pre-audytu oraz odpowiedzi na pytania (a)–(i): miejsce i ładowanie `tokens.css`/`components.css`, komponenty w Django 6.1, wybór i mapowanie tokenów, kontrast, czcionki, dark mode, macierz 7 stanów, klasy przypięte testami, bramka wizualna.

Zakres i kontrakt: `change.md:16-19` (jeden widok; zwykłe CSS custom properties z nazwami tokenów shadcn; bez Tailwinda, Node i nowych zależności; 2–3 wspólne komponenty: button, card/list item, notice/alert; login, detail i account_delete poza zakresem). Źródło tokenów: `theme-source.css` (eksport tweakcn, OKLCH, `:root` w :13-66, `.dark` w :68-119).

## Summary

1. **Szkic pre-audytu jest w większości trafny, z trzema korektami.**
   - (1) Literałów hex jest **12 wystąpień, 9 różnych wartości**, nie 11 — linia `base.html:31` ma dwa (`#ccc` i `#555`). Reszta szkicu (#b00020 ×2, #555 ×3, brak źródła tokenów) się zgadza.
   - (2) Przyciski **nie wyglądają tak samo** — wyglądają *przypadkowo różnie*. Reguła `button, .button` (`base.html:12`) ustawia tylko układ (display, margin, padding, font-size), bez tła, ramki i koloru. `<button>` zostaje więc w natywnym wyglądzie przeglądarki, a `<a class="button">` (`home.html:28`) wygląda jak zwykły podkreślony link z paddingiem. Główna akcja „Continue conversation” wygląda słabiej niż poboczne „Log out”.
   - (3) Prawda, że w CSS nie ma reguły `:hover`, `:focus` ani `:focus-visible` (`base.html:8-42`, `home.html:4-10`; grep po `*.html` w `accounts/` i `conversations/` nic nie znalazł). Ale nie ma też `outline: none`, więc **dziś działa domyślny pierścień fokusu przeglądarki**. Ryzyko pojawia się dopiero wtedy, gdy komponent przycisku dostanie własne tło i ramkę, a ring przejdzie na token z tweakcn (2.92:1 na tle, poniżej 3:1).
2. **Pięć zarzutów** (szczegóły w `## Charges`): C1 brak tokenów kolorów, C2 brak komponentu przycisku z wariantami, C3 brak kontraktu stanów (hover/focus/disabled), C4 CSS w dwóch inline `<style>` z przypadkową kolejnością, C5 „Delete account” jako zwykły link obok „Log out”.
3. **Pliki statyczne nie psują testów.** `settings_test.py:7-10` podmienia storage na zwykłe `StaticFilesStorage`, więc `{% static %}` działa w pytest bez `collectstatic`. Druga strona: literówka w ścieżce `{% static %}` **nie** wywróci pytest, a w produkcji (`CompressedManifestStaticFilesStorage`, `settings.py:226-228`, `manifest_strict = True`) da `ValueError` i błąd 500 na każdej stronie z `base.html`. Potrzebny tani test-strażnik przez `staticfiles.finders.find(...)`.
4. **Kontrast tweakcn ma 4 pary poniżej progu w jasnym motywie, który faktycznie trafi na home**: ring na tle 2.92:1 (próg 3:1), biały na destructive 3.76:1, muted-foreground na tle 4.04:1, secondary-foreground na secondary 3.17:1 (próg 4.5:1 dla tekstu). Twoje szacunki: ring 2.9 — trafny; destructive 3.4 → faktycznie 3.76 (nadal nie przechodzi); ciemny primary 3.2 → faktycznie 3.49 (nadal nie przechodzi). Nowe, szare tło strony (`--background` = #e8ebed zamiast białego) psuje też obecną zieleń `.correct` (#1b7f3b: 5.07 → 4.23).
5. **Rekomendacje do potwierdzenia w planie** (wybory, nie fakty): komponenty jako klasy CSS dla przycisku + `{% include … with … only %}` dla notice/list item; pliki w `accounts/static/ui/css/` i `accounts/templates/ui/`; dark mode odłożyć; czcionki: stos systemowy teraz albo self-host (nigdy Google Fonts CDN); bramka wizualna: lokalny `toHaveScreenshot` na istniejącym Playwright, bez strony kitchen-sink.

## Charges

| # | Kategoria | Gdzie | Zarzut | Skutek dla użytkownika |
|---|---|---|---|---|
| C1 | missing token | `accounts/templates/base.html:15-41` | 12 literałów hex (9 wartości) wpisanych w reguły, zero zmiennych CSS (`var(--` nie występuje w żadnym szablonie). Te same znaczenia mają różne wartości w różnych miejscach (czerwony błędu i „wrong” to ten sam #b00020, ale szare tła flash/bańki to trzy różne odcienie). | Zmiana koloru (np. nowe szare tło z tweakcn) nie ma jednego miejsca, więc łatwo zostawić tekst, który przestaje być czytelny — zieleń poprawki `.correct` spadłaby do 4.23:1, poniżej progu AA. |
| C2 | missing shared component | `base.html:12`; `home.html:20`, `:22`, `:28`, `:42` | Jedna reguła `button, .button` tylko z układem, bez wariantów primary / secondary / destructive. `<button>` = natywny wygląd, `<a class="button">` = link z paddingiem. „Log out” (:20) wygląda jak każdy z 20 przycisków tematów (:42); główna akcja „Continue conversation” (:28) wygląda jak link; „Delete account” (:22) to zwykły link. Ten sam wzorzec poza zakresem: `detail.html:33/44/56` (End) obok `:52` (Send); `account_delete.html:20` (usunięcie konta) obok `:21` (Cancel jako link). | Użytkownik nie widzi, która akcja jest główna, która poboczna, a która niebezpieczna, bo wygląd przycisku wynika z przeglądarki, a nie ze znaczenia akcji. |
| C3 | missing shared component (kontrakt stanów) | `base.html:8-42`, `home.html:4-10` (brak reguł); `base.html:13`, `:63` | Brak reguł `:hover`, `:focus-visible`; jedyny zdefiniowany stan to `button:disabled` (:13, opacity 0.6 + `cursor: progress`). Dziś ratuje to natywny wygląd przycisków. Gdy C2 nada przyciskom własne tło, natywny hover znika, a ring z tweakcn (`--ring`, w źródle `outline-ring/50`, `theme-source.css:123`) ma 2.92:1 na tle już przy pełnym kryciu. Skrypt wyłącza **wszystkie** przyciski na stronie po dowolnym submit (:63), także „Log out”. | Po restylingu użytkownik z klawiaturą może stracić widoczny fokus, a myszą — informację, że coś da się kliknąć. |
| C4 | accidental architecture | `home.html:3-11`; `base.html:7-8`; `base.html:8-42` | Cały CSS aplikacji żyje w dwóch inline `<style>`: globalnym w `base.html` (z regułami innych stron: `.transcript`, `.mistakes`) i lokalnym w `home.html`. `{% block head %}` renderuje się **przed** bazowym `<style>` (`base.html:7` vs `:8`), więc reguła strony o tej samej specyficzności przegrywa z bazową; dziś działa tylko dlatego, że selektory `.topbar …` są bardziej szczegółowe. W `CLAUDE.md` nie ma żadnej reguły o UI/CSS (jedyne trafienie „CSS” to zakaz selektorów CSS w E2E, `CLAUDE.md:68`). | Każda nowa funkcja dopisuje własne style w losowym miejscu, więc strony z czasem wyglądają niespójnie, a poprawka wyglądu jednej strony może po cichu zmienić inną. |
| C5 | accidental architecture | `home.html:16-23` (link :22) | „Delete account” stoi w pasku obok „Log out”, z odstępem 0.5–0.75rem (`home.html:7`) i bez wyróżnienia jako akcja niebezpieczna. Łagodzi to strona potwierdzenia z hasłem (`account_delete.html:16-22`), więc pomyłka nie kasuje danych. Miejsce wybrano świadomie (`context/archive/2026-10-07-account-and-data-deletion/plan-brief.md:24`). | Na telefonie łatwo trafić w „Delete account” zamiast „Log out” i wylądować na stronie usuwania konta — to stres i strata czasu, nie utrata danych. |

Uwagi do zarzutów:

- **C4 dotyka wcześniejszej decyzji użytkownika.** W impl-review F2 z 2026-10-07 użytkownik zdecydował: pasek `.topbar` i jego `<style>` „zostają w `home.html` bez zmian” (`context/archive/2026-10-07-account-and-data-deletion/reviews/impl-review.md:36-53`). Wspólny pasek nawigacji dla wszystkich stron jest odłożony po MVP (`context/foundation/roadmap.md:178`). Przeniesienie `.topbar` do `components.css` (bez zmiany wyglądu) to ponowne otwarcie tej decyzji → pytanie otwarte Q1.
- **C5: zmiana miejsca linku to decyzja produktowa.** W zakresie tej zmiany mieści się wizualne oznaczenie (wariant destructive / link drugorzędny), nie przeniesienie → pytanie otwarte Q2.
- **Test przypina adres linku:** `tests/test_account_deletion.py:540` sprawdza literalny `href="/account/delete/"` na home. Restyling C5 nie może zmienić tego atrybutu.

### Status zarzutów (2026-10-21, po fazach 1–5 planu)

| # | Status | Faza | Co zrobiono |
|---|---|---|---|
| C1 | addressed | 2 | `accounts/static/ui/css/tokens.css` (jasny i ciemny motyw, wartości tweakcn poprawione do AA z komentarzem o źródle); wszystkie 12 literałów przepięte na `var(--…)`; strażnicy w `tests/test_ui.py`: brak literałów w szablonach i `components.css`, kontrast `CONTRAST_PAIRS` w obu motywach. |
| C2 | addressed | 3 | Komponenty w `components.css`: `btn` (primary, `data-variant="secondary"` / `"destructive"`), `link`, `choice-list`, `alert`, `page-footer`; home na komponentach („Continue conversation” jako primary, „Log out” jako secondary, tematy jako lista kart). |
| C3 | addressed | 4 | Hover, `:focus-visible` z pełnym `--ring`, disabled (`button:disabled`, `a[aria-disabled="true"]`), spinner zatrzymany przy `prefers-reduced-motion`; stany na `/ui/` i w zrzutach `tests/e2e/ui-home.spec.ts`. Wyłączanie wszystkich przycisków po dowolnym submit (`base.html`, także „Log out”) zostaje świadomie — plan wyklucza nowy JS. |
| C4 | addressed | 1 (+5) | Oba inline `<style>` przeniesione do `accounts/static/ui/css/`, ładowane przed `{% block head %}`; reguła UI w `CLAUDE.md` (faza 5). |
| C5 | addressed | 3 | „Delete account” w `<footer class="page-footer">` jako `class="link" data-variant="destructive"`, we wszystkich trzech gałęziach home; test `tests/test_account_deletion.py:548` pilnuje, że link stoi po `</header>`. |

Decyzje, które ta zmiana świadomie otwiera:

- **C4 otwiera decyzję F2 z 2026-10-07** (`context/archive/2026-10-07-account-and-data-deletion/reviews/impl-review.md:36-53`: pasek `.topbar` i jego `<style>` miały zostać w `home.html`). Reguły `.topbar` są teraz w `components.css` (sekcja „Home page”, przepięte na tokeny, układ bez zmian), a markup paska zostaje w `home.html`. Wspólny pasek dla wszystkich stron nadal jest po MVP (`context/foundation/roadmap.md:178`).
- **C5 zmienia miejsce linku** uzgodnione w `context/archive/2026-10-07-account-and-data-deletion/plan-brief.md:24` („Link + przycisk »Log out« przy »Signed in as«”): przy „Signed in as” zostaje tylko „Log out”, link usuwania konta jest na dole strony.

Deferred (poza zakresem `change.md:19`):

- **Strony login, detail (rozmowa) i account_delete** — ich szablony nie były edytowane; dziedziczą tylko tokeny, wygląd gołego `<button>` (secondary), pierścień fokusu i aliasy `.notice` / `.error`. Dotyczy to też wzorca z C2 poza home (`detail.html:33/44/56` obok `:52`, `account_delete.html:20` obok `:21`). Powód: zmiana obejmuje jeden widok; każda z tych stron dostanie własną zmianę `/10x-ui`.

Znany otwarty punkt:

- **Skok układu przy loading na home.** Skrypt w `base.html` wstawia `#typing-indicator` za klikniętym formularzem (`form.after(typing)`), czyli w środku listy tematów, więc kolejne tematy przesuwają się w dół. Zaakceptowane przez użytkownika 2026-10-21; poprawka wymaga zmiany JS, którą ta zmiana wyklucza.

## Detailed Findings

### (a) Gdzie `tokens.css` i `components.css`, jak je ładować, czy testy się wywrócą

- Dziś: żadnego katalogu `static/` w źródłach (jest tylko gitignorowany wynik `collectstatic` w `staticfiles/`), żadnego `{% load static %}`, brak `STATICFILES_DIRS` (`settings.py:219-228`). Finder-y są domyślne (FileSystemFinder + AppDirectoriesFinder), więc pliki w `<app>/static/` znajdą się same.
- Rekomendacja: `accounts/static/ui/css/tokens.css` i `accounts/static/ui/css/components.css` — obok `accounts/templates/base.html`, z podfolderem `ui/` jako przestrzenią nazw (pliki statyczne, tak jak szablony, wygrywa pierwszy znaleziony). Alternatywa: osobna mała aplikacja `ui` (jedna linia w `INSTALLED_APPS`) — czystsza nazwa, ale to nowa aplikacja dla dwóch plików.
- W `base.html`: `{% load static %}` na górze, potem w `<head>` **przed** `{% block head %}`:
  `<link rel="stylesheet" href="{% static 'ui/css/tokens.css' %}">` i `<link rel="stylesheet" href="{% static 'ui/css/components.css' %}">`. Tokeny przed komponentami. Taka kolejność naprawia też problem z C4: style strony z `block head` przyjdą po wspólnych.
- **Testy:** nie wywrócą się. `settings_test.py:7-10` ustawia `StaticFilesStorage`, którego `url()` tylko skleja `STATIC_URL` z nazwą i nie sprawdza istnienia pliku. Runner testów wymusza `DEBUG=False`, a przy storage z manifestem to właśnie dałoby wyjątek przy każdym `{% static %}` — podmiana w `settings_test` temu zapobiega.
- **Produkcja:** `CompressedManifestStaticFilesStorage` (whitenoise 6.12.0, `uv.lock:923-924`) dziedziczy `manifest_strict = True`; brak wpisu w `staticfiles.json` → `ValueError: Missing staticfiles manifest entry` → 500. `collectstatic` biegnie w komendzie startowej na Railway (`context/deployment/web-settings.json:7`) i w `webServer` Playwrighta (`playwright.config.ts:37-57`), więc nowe pliki zostaną zahashowane przy deployu. Post-processing manifestu przepisuje `url()` w CSS — zły `url()` (np. do czcionki) wywróci `collectstatic`, a więc start kontenera, choć pytest zostanie zielony.
- Strażnik do planu: test `assert finders.find("ui/css/tokens.css")` (i `components.css`), plus lokalnie `DEBUG=False SECRET_KEY=x uv run python manage.py collectstatic --noinput --dry-run` (wzmianka w `context/deployment/deploy-plan.md:100`).

### (b) Komponenty w Django 6.1 i katalog szablonów

- Django w projekcie: 6.1.1. Template partials są wbudowane od 6.0: `{% partialdef nazwa %}…{% endpartialdef %}` (opcja `inline` renderuje też w miejscu), `{% partial nazwa %}`, oraz nazwa `"plik.html#nazwa"` w `{% include %}` / `render()`. Docs: https://docs.djangoproject.com/en/6.1/ref/templates/language/#template-partials
- **`{% partial %}` nie przyjmuje argumentów** — w źródle `partial_func` dopasowuje dokładnie `"partial", partial_name` (`.venv/…/django/template/defaulttags.py:1277-1281`). Partial widzi bieżący kontekst. Dlatego partials nadają się do fragmentów powtarzanych w obrębie jednego pliku, nie do komponentów z parametrami.
- `{% include "ui/notice.html" with tone="warning" text=… only %}` — `with` przekazuje zmienne, `only` odcina resztę kontekstu, więc komponent ma jawne wejścia. Docs: https://docs.djangoproject.com/en/6.1/ref/templates/builtins/#include . Include z nazwą `#partial` też działa z `with … only` (wniosek ze źródła `Engine.get_template`, bez przykładu w dokumentacji — niepewne, nie opierać na tym planu).
- Ograniczenie include: nie przyjmie bloku treści (np. formularza w środku karty). Dlatego:
  - **przycisk** najlepiej jako **kontrakt klas CSS** (`class="btn btn-primary"` itd.) — przyciski siedzą w formularzach z `csrf_token`, ukrytymi polami i atrybutami `data-waits-for-agent` (`home.html:39`), których include nie opakuje sensownie;
  - **notice/alert** i **element listy tematów** jako include z `only` (tekst + wariant).
- Katalog: przy `APP_DIRS=True` i `DIRS=[]` (`settings.py:154-158`) loader szuka w `templates/` aplikacji w kolejności `INSTALLED_APPS`, pierwszy trafiony wygrywa. `django.contrib.admin` jest przed `accounts` (`settings.py:124-133`), ale admin nie ma nic w `ui/`, więc `accounts/templates/ui/` nie koliduje. Rekomendacja: `accounts/templates/ui/` (zero zmian w settings, obok `base.html`). Alternatywa `DIRS=[BASE_DIR / "templates"]` zawsze wygrywa z aplikacjami, także z adminem — większa siła, większe ryzyko przypadkowego nadpisania.

### (c) Które tokeny tweakcn zostawić, które dodać, mapowanie literałów

Zostawić (używane przez home i 2–3 komponenty): `--background`, `--foreground`, `--card`, `--card-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--muted-foreground`, `--accent`, `--accent-foreground`, `--destructive`, `--destructive-foreground`, `--border`, `--input`, `--ring`, `--radius`, `--font-sans` / `--font-serif` / `--font-mono`, `--shadow-sm` (karta).

Pominąć: `--chart-1…5` (`theme-source.css:33-37`, brak wykresów), `--sidebar-*` (:38-45, brak sidebara), `--popover*` (:18-19, brak popoverów), składowe cienia `--shadow-x…--shadow-color` (:50-55, gotowe cienie są w `--shadow-*`), `--tracking-normal` i `--spacing` (:64-65, mają sens tylko w Tailwindzie). Nazwy shadcn zostają, więc późniejsze przejście na Tailwind v4 + Basecoat (`change.md:17`) może je dodać z powrotem.

Dodać (aplikacja ich potrzebuje, tweakcn ich nie ma): `--success` (tekst `.correct`), `--warning` + `--warning-foreground` (tło `.notice`), `--destructive-muted` albo `color-mix()` dla tła `.flash.error`, `--bubble-assistant` i `--bubble-user` (bańki czatu). `color-mix()` jest Baseline od 2023 — można też zostać przy osobnych tokenach, żeby nie liczyć kontrastu „w locie”.

Mapowanie 12 wystąpień (9 wartości) z `base.html`:

| Linia | Reguła | Literał | Token | Uwaga |
|---|---|---|---|---|
| 15 | `.error` color | #b00020 | `--destructive` (po przyciemnieniu) | obecny tweakcn #ef4444 jako tekst: 3.14 na tle, 3.76 na karcie — za mało |
| 16 | `.flash` bg | #f1f1f1 | `--muted` lub `--card` | także dla `.flash.success` (`accounts/views.py:37`), która nie ma własnej reguły |
| 17 | `.flash.error` bg | #fdecee | `--destructive-muted` (nowy) | dziś #b00020 na #fdecee = 6.42 |
| 18 | `.notice` bg | #fff6dd | `--warning` (nowy) | np. oklch(0.97 0.05 90) ≈ #fff4d0, foreground na nim 11.52 |
| 26 | `.bubble-assistant` bg | #eef1f6 | `--bubble-assistant` → `--card` | poza home (detail), ale reguła jest w `base.html` |
| 27 | `.bubble-user` bg | #dcf3e4 | `--bubble-user` → `--accent` albo nowy zielony | `--accent` jest niebieski (#d6e4f0) — zmiana odcienia to wybór |
| 30 | `.typing` color | #555 | `--muted-foreground` (po przyciemnieniu) | widoczne na home po kliknięciu tematu |
| 31 | `.spinner` border | #ccc | `--border` | dekoracja (`aria-hidden`, `base.html:51`) |
| 31 | `.spinner` border-top | #555 | `--muted-foreground` lub `--primary` | |
| 38 | `.mistakes .wrong` | #b00020 | `--destructive` (po przyciemnieniu) | poza home |
| 39 | `.mistakes .correct` | #1b7f3b | `--success` (nowy) | #1b7f3b na nowym tle: 4.23 — za mało |
| 41 | `.mistakes .sentence` | #555 | `--muted-foreground` (po przyciemnieniu) | poza home |

Wiersze 26, 27, 38, 39, 41 renderuje tylko `detail.html` / `_mistakes.html` (poza zakresem `change.md:19`), ale reguły leżą w `base.html`, więc zmiana tła strony je dotknie. Plan musi zdecydować: zmapować wszystkie 12 w tej zmianie (dzięki temu w `base.html` nie zostanie żaden hex) albo tylko te z home i jawnie zostawić resztę.

### (d) Kontrast (WCAG 2.x, liczony z OKLCH → sRGB, skrypt w scratchpadzie)

Progi: 4.5:1 zwykły tekst, 3:1 duży tekst i elementy UI / pierścień fokusu (WCAG 1.4.3, 1.4.11).

| Para | Jasny | Dark | Werdykt |
|---|---|---|---|
| foreground / background | 10.55 | 12.35 | OK |
| foreground / card | 12.63 | 10.45 | OK |
| primary-foreground / primary | 13.72 | **3.49** | dark: nie (tekst przycisku) |
| destructive-foreground / destructive | **3.76** | **3.76** | nie (tekst przycisku) |
| destructive jako tekst / background | **3.14** | 4.14 | nie |
| muted-foreground / background | **4.04** | 6.17 | jasny: nie |
| muted-foreground / card | 4.83 | 5.22 | OK |
| secondary-foreground / secondary | **3.17** | 5.35 | jasny: nie |
| accent-foreground / accent | 8.00 | **3.41** | dark: nie |
| ring / background | **2.92** | 7.87 | jasny: nie (3:1) |
| ring / card | 3.49 | 6.65 | OK przy pełnym kryciu; `outline-ring/50` (50% krycia) da mniej |
| border / background | 1.18 | 1.58 | dekoracyjne; nie może być jedynym wyróżnikiem przycisku |

Kandydaci do planu (policzeni tym samym skryptem, jasny motyw; „biały” = biały tekst na tym kolorze):

- `--destructive` oklch(0.52 0.2 25) ≈ #c21724: tekst na tle 5.11, na karcie 6.12, biały na nim 6.12 — jeden token działa i jako tekst, i jako tło przycisku.
- `--ring` oklch(0.58 0.0904 80.9) ≈ #967436: 3.61 na tle, 4.32 na karcie (pełne krycie, bez `/50`).
- `--muted-foreground` oklch(0.52 0.0234 264) ≈ #626977: 4.60 na tle, 5.51 na karcie.
- `--success` oklch(0.48 0.13 150) ≈ #067132: 5.14 na tle, 6.16 na karcie.
- `--secondary-foreground` (złoty, = ring w źródle, `theme-source.css:23`, `:32`): jako tekst na `--secondary` potrzebuje tej samej korekty co ring albo zmiany na `--foreground`.
- Dark (jeśli nie odkładamy): `--primary-foreground` musi być ciemny; kolor `--background` na złotym primary daje 4.45 — o włos za mało, więc trzeba jeszcze ciemniejszego.

Ograniczenie: konwersja przycina kolory spoza gamutu sRGB do [0, 1]; dla tych wartości różnice są pomijalne, ale plan powinien zweryfikować ostateczne wartości (np. w DevTools).

### (e) Czcionki

- `--font-sans: Inter, sans-serif` itd. (`theme-source.css:46-48`) — żadna z trzech czcionek nie jest ładowana; dziś `body` ma `system-ui, sans-serif` (`base.html:9`).
- **Błąd w źródle:** `Source Serif 4` bez cudzysłowu jest niepoprawne (CSS Fonts 4 §2.1.1: token zaczynający się cyfrą trzeba escapować — https://drafts.csswg.org/css-fonts-4/#family-name-syntax). W zmiennej zapisze się, ale `font-family: var(--font-serif)` stanie się nieważne. Pisać `"Source Serif 4"`.
- Opcje:
  1. **Stos systemowy** — 0 bajtów, zgodne z „bez nowych zależności” (`change.md:17`), wygląd różni się między systemami (co utrudnia też porównanie zrzutów, punkt (i)).
  2. **Self-host** woff2 (wszystkie trzy na SIL OFL 1.1 — wolno dołączyć, trzeba dołączyć tekst licencji) w `accounts/static/ui/fonts/` + `@font-face` z `font-display: swap` i względnym `url()`. Podzbiory latin (zawierają ä ö ü ß): Inter ~48 KB, Source Serif 4 ~51 KB, JetBrains Mono ~40 KB (pomiar z jsDelivr/Fontsource 5.2.x, 2026-10-20).
  3. **Google Fonts CDN** — odrzucić: LG München I, 20.01.2022, 3 O 17493/20 uznał przekazanie IP odwiedzającego do Google bez zgody za naruszenie RODO (100 € odszkodowania); aplikacja działa w UE (Railway EU West).
- Rekomendacja: (1) teraz, z tokenem `--font-sans` zawierającym `Inter` na początku stosu (zadziała, gdy ktoś ma ją lokalnie), albo (2), jeśli zależy Ci na spójnym wyglądzie. Home używa realnie tylko `--font-sans`; serif i mono można pominąć.

### (f) Dark mode teraz czy później

- Źródło ma kompletny blok `.dark` (`theme-source.css:68-119`), ale w wersji Tailwinda (`@custom-variant dark`, :11). Tłumaczenie na czyste CSS: wkleić ciało `.dark` do `@media (prefers-color-scheme: dark) { :root { … } }` i dodać `color-scheme`. `light-dark()` jest Baseline dopiero od 2024 (jeszcze nie „widely available”), więc media query jest bezpieczniejsze. `oklch()` jest Baseline widely available od 2023.
- Koszty teraz: 2 pary dark nie przechodzą (primary-foreground 3.49, accent-foreground 3.41); macierz 7 stanów i baseline zrzutów rosną ×2; bańki i notice potrzebowałyby ciemnych odpowiedników.
- Rekomendacja: **odłożyć**. Ułożyć `tokens.css` tak, żeby dark był później jednym blokiem `@media`, bez zmian w `components.css` (komponenty używają wyłącznie `var(--…)`). Nie ustawiać jeszcze `color-scheme: light dark`, bo wtedy natywne pola formularzy zrobią się ciemne przy jasnych tokenach.

### (g) Macierz 7 stanów home i stany kontekstowe

Gałęzie wzajemnie się wykluczają: aktywna rozmowa → limit → lista tematów (`home.html:26`, `:29`, `:34`; `views.py:35-40`).

| Stan | Co jest dziś | Skąd |
|---|---|---|
| default | lista 20 tematów jako przyciski w `ul.topics` | `home.html:35-46`, `topics.py:18` |
| hover | brak reguły; natywny hover przycisków, natywny styl linków | `base.html:8-42` |
| focus-visible | brak reguły; natywny pierścień przeglądarki (nic go nie wyłącza) | jw. |
| disabled | `opacity: 0.6; cursor: progress`; po **dowolnym** submit skrypt wyłącza wszystkie przyciski, także „Log out”; odblokowanie po powrocie z bfcache | `base.html:13`, `:57-64`, `:83-89` |
| error | `p.flash.error` **nad** paskiem z `<h1>` (pętla messages jest przed `{% block content %}`); na home trafia błąd startu rozmowy | `base.html:45-47`, `views.py:59-62` |
| empty | nieosiągalny: `TOPICS` to stała krotka 20 tematów (test `tests/test_conversations.py:181`); szablon nie ma `{% empty %}` | `topics.py:18`, `home.html:37-45` |
| loading | po kliknięciu tematu formularz z `data-waits-for-agent` dostaje pod sobą `#typing-indicator` (spinner + „Agent is typing…”); spinner kręci się bez reguły `prefers-reduced-motion` | `home.html:39`, `base.html:50-53`, `:65-70`, `:31-32` |

Stany kontekstowe:

- **Niezalogowany:** home się nie renderuje — `LoginRequiredMiddleware` (`settings.py:142`) przekierowuje na `/login/`. Komunikat `messages.success("Your account has been deleted.")` (`accounts/views.py:37`) pojawia się jako `.flash.success`, dla której nie ma osobnej reguły (dostaje szare `.flash`).
- **Dzienny limit:** `p.notice` z tekstem z `_reset_notice.html` (godzina i data resetu), bez listy tematów (`home.html:29-33`).
- **Aktywna rozmowa:** zdanie z tytułem tematu i link `a.button` „Continue conversation” (`home.html:26-28`) — jedyna akcja na ekranie, a wygląda jak link (C2).

### (h) Klasy i markup przypięte przez pytest

Wszystkie asercje to porównania podciągów na `response.content.decode()` (bez BeautifulSoup / `assertInHTML`).

- `'<div class="typing">'` — `tests/test_conversation_views.py:640`, `:720`, `:819`. Przypina **dokładny** tekst znacznika w `detail.html:27`. Klasa `typing` musi zostać, a ten `div` nie może dostać drugiej klasy ani atrybutu przed `class`. Globalny wskaźnik w `base.html:50` (`id=… class="typing" hidden`) nie jest tym testem objęty.
- `'class="transcript"'` przed `"Your mistakes"` — `:1156`. Klasa `transcript` zostaje dokładnie w tej postaci (`detail.html:16`); używa jej też skrypt (`base.html:96`).
- `'class="flash'` **nie** występuje — `:1240`, `:1256`. Nowy komponent alertu nie może wypisywać `class="flash…` poza pętlą messages (np. ukryty szablon w `base.html` zepsułby test).
- `'<span role="status">Preparing your list of mistakes…</span>'` — `:1062`, `:1127`, `:1209` oraz `tests/test_analysis.py:248` (`detail.html:70`).
- `'action="…" data-auto-submit'` — `:996` (helper) i `tests/test_waiting_path.py:389`; kolejność atrybutów w `detail.html:86`.
- `'href="/account/delete/"'` na home — `tests/test_account_deletion.py:540`.
- Teksty home: „Choose a topic”, „Continue conversation”, „Signed in as …” (`tests/test_conversation_views.py:256`, `:273`, `:288`, `:365`, `:366`, `:393`, `:843`).
- Nie znaleziono asercji na `bubble`, `notice`, `button`, `spinner`, `topics`.
- Skrypt w `base.html` dodatkowo zależy od: `#typing-indicator`, `#typing-text`, selektora `button` (wszystkie), `form`, `.transcript`, atrybutów `data-waits-for-agent`, `data-waiting-text`, `data-enter-sends`, `data-auto-submit` (`base.html:55-98`). Zmiana nazw klas komponentów (`btn` itd.) tego nie dotyka, bo skrypt łapie element `button`, nie klasę.

### (i) Bramka wizualna

- Stan: Playwright 1.64.1 jest (`package.json`, `playwright.config.ts`), projekt `setup` loguje użytkownika E2E bez rozmów, więc home pokazuje listę tematów; E2E nie biegnie w CI (`.github/workflows/ci.yml:22-29`), zgodnie z decyzją „pre-push, nie CI” (pamięć użytkownika). Brak `toHaveScreenshot` i baseline'ów.
- **`toHaveScreenshot` na home** — baseline zapisuje się z sufiksem platformy (`home-chromium-darwin.png`); animacje są domyślnie wyłączane (spinner się zatrzyma), kursor ukryty; `mask` dla e-maila w pasku. Niestabilność między systemami (fonty, antyaliasing) nie przeszkadza, bo bramka biegnie tylko lokalnie na jednej maszynie. Stany limitu i aktywnej rozmowy wymagają dodatkowych danych w bazie E2E (`tests/e2e/ensure_e2e_user.py` tworzy tylko użytkownika).
- **Strona kitchen-sink tylko w DEBUG** — pokazuje wszystkie warianty i stany komponentów na jednej stronie (łatwo zrobić zrzut stanów, których nie da się łatwo wywołać, np. disabled, error). Koszt: nowa trasa, którą trzeba wyłączyć w produkcji, nowy szablon do utrzymania, i ryzyko z lekcji o trasach (`ID_ROUTES` dotyczy tylko tras z id, więc tu nie obowiązuje). Wymaga też `LoginRequiredMiddleware`-exempt albo logowania.
- Rekomendacja: `toHaveScreenshot` na prawdziwej stronie home (default + error + loading przez kliknięcie), bez kitchen-sink w tej zmianie. Hover i focus-visible lepiej sprawdzić ręcznie lub `page.focus()` + zrzut, bo to prawdziwe zachowanie przeglądarki.

## Code References

- `accounts/templates/base.html:8-42` — jedyny globalny `<style>`, 12 literałów hex (:15, :16, :17, :18, :26, :27, :30, :31×2, :38, :39, :41)
- `accounts/templates/base.html:12-13` — `button, .button` (tylko układ) i `button:disabled`
- `accounts/templates/base.html:45-53` — flash messages i globalny wskaźnik pisania
- `accounts/templates/base.html:57-89` — skrypt: blokada przycisków, wskaźnik, bfcache
- `conversations/templates/conversations/home.html:3-11` — lokalny `<style>` `.topbar`
- `conversations/templates/conversations/home.html:14-24` — pasek: e-mail, Log out (:20), Delete account (:22)
- `conversations/templates/conversations/home.html:26-47` — trzy gałęzie stanu
- `conversations/views.py:32-50` — widok home (active, exhausted, topics)
- `conversations/topics.py:18` — stała `TOPICS`
- `talkaitive/settings.py:154-158`, `:219-228` — szablony i storage
- `talkaitive/settings_test.py:6-10` — zwykłe `StaticFilesStorage` w testach
- `context/deployment/web-settings.json:7` — `collectstatic` w komendzie startowej
- `context/changes/ui-home-tokens/theme-source.css:13-66`, `:68-119`, `:121-128` — tokeny jasne, ciemne, blok Tailwind do przetłumaczenia
- `tests/test_conversation_views.py:640`, `:1156`, `:1240` — asercje na `typing`, `transcript`, `flash`
- `tests/test_account_deletion.py:540` — literalny `href` linku usuwania konta

## Architecture Insights

- Kontrakt UI dotąd: „proste inline CSS w `base.html`” (`context/archive/2026-10-01-auth-and-access-scaffold/plan.md:184`), JS tylko jako wygoda — formularze działają bez niego (`base.html:56`). Ta zmiana zastępuje inline CSS plikami statycznymi, ale nie powinna dodawać JS.
- Skrypt łapie elementy (`button`, `form`), nie klasy, więc warstwa komponentów CSS jest od niego niezależna.
- Domyślne serwowanie przez whitenoise z manifestem daje plikom hash w nazwie — zmiana `tokens.css` sama unieważni cache przeglądarki.

## Historical Context (from prior changes)

- `context/archive/2026-10-01-auth-and-access-scaffold/plan.md:184` — decyzja: cały CSS inline w `base.html`, strony czytelne na telefonie. Nadal obowiązuje poza `.topbar`.
- `context/archive/2026-10-05-first-corrected-conversation/plan-brief.md:33` i `plan.md:256` — oczekiwanie = POST + kilka linii JS (wyłączony przycisk, spinner CSS, „Agent is typing…”), bez htmx (`plan-brief.md:51`). Nadal obowiązuje.
- `context/archive/2026-10-07-account-and-data-deletion/plan-brief.md:24` — „Log out” i „Delete account” obok „Signed in as”. Nadal obowiązuje (C5).
- `context/archive/2026-10-07-account-and-data-deletion/reviews/impl-review.md:36-53` — F2 ACCEPTED: `.topbar` zostaje w `home.html`. Nadal obowiązuje; ta zmiana może chcieć ją otworzyć (Q1).
- `context/foundation/roadmap.md:178` — wspólny pasek nawigacji po MVP. Nadal obowiązuje.
- `context/foundation/roadmap.md:64` — „Frontend: absent — no own templates/statics”: nieaktualne co do szablonów (jest 7 plików), aktualne co do plików statycznych (brak).
- `context/foundation/prd.md:144` — dostępność i obsługiwane przeglądarki są niewymienione w wymaganiach niefunkcjonalnych (otwarte pytanie PRD). WCAG AA w tej zmianie to więc wybór, nie wymaganie PRD.

## Related Research

Nie dotyczy — w `context/changes/**` i `context/archive/**` nie ma wcześniejszego researchu o UI, tokenach ani CSS.

## Open Questions

- **Q1:** Czy przenosimy 5 reguł `.topbar` z `home.html:4-10` do `components.css` (wygląd bez zmian), ponownie otwierając decyzję F2 z 2026-10-07? Bez tego C4 zostaje częściowo.
- **Q2:** C5 — tylko wizualne oznaczenie „Delete account” jako akcji drugorzędnej/niebezpiecznej, czy także zmiana miejsca (decyzja produktowa)?
- **Q3:** Mapujemy wszystkie 12 literałów (także reguły detail/mistakes w `base.html`), czy tylko te używane na home?
- **Q4:** Czcionki: stos systemowy czy self-host Inter (~48 KB)?
- **Q5:** Kolor bańki użytkownika: niebieski `--accent` czy osobny zielony token (dziś zielony #dcf3e4)?
- **Q6:** Czy AA (WCAG 2.x) jest celem tej zmiany? PRD go nie wymaga (`prd.md:144`); od tego zależy, czy poprawiamy wartości tweakcn (destructive, ring, muted-foreground, secondary-foreground).
