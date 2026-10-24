# Tokeny i komponenty UI na widoku home — Plan Brief

> Full plan: `context/changes/ui-home-tokens/plan.md`
> Research: `context/changes/ui-home-tokens/research.md`

## What & Why

Aplikacja nie ma systemu wyglądu: kolory są wpisane w dwa inline `<style>`, przyciski wyglądają tak, jak zdecyduje przeglądarka, a główna akcja na home („Continue conversation”) wygląda słabiej niż poboczne „Log out”. Ta zmiana wprowadza tokeny (zmienne CSS o nazwach ról z shadcn, wartości z tweakcn) i trzy wspólne komponenty, przebudowuje na nie widok home i zostawia strażników, żeby kolejne widoki dziedziczyły kontrakt zamiast literałów.

## Starting Point

Cały CSS siedzi w `accounts/templates/base.html:8-42` (12 literałów hex) i `home.html:3-11` (`.topbar`). Brak plików statycznych, stanów hover/focus i wariantów przycisku; „Delete account” stoi w pasku obok „Log out”. Research zebrał to w pięć zarzutów C1–C5 i policzył kontrast tweakcn (6 par poniżej WCAG AA).

## Desired End State

Home w jasnym i ciemnym motywie systemu: wyraźna główna akcja, tematy jako lista kart, limit jako żółty alert, „Delete account” jako czerwony link na dole strony, widoczny fokus z klawiatury. Wszystkie kolory żyją w jednym pliku `tokens.css`, komponenty w `components.css`, a `/ui/` (tylko DEBUG) pokazuje wszystkie stany. pytest w CI nie przepuści koloru w szablonie ani tokenu poniżej AA.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Stos | Czyste CSS custom properties, nazwy shadcn, bez Tailwinda/Node | Zero nowych zależności; późniejsze przejście na Tailwind v4 + Basecoat zostaje otwarte | change.md |
| Kontrast | WCAG AA; poprawione 4 tokeny jasne, 2 pary ciemne i `--input` w obu motywach (granica pola 3:1), reszta tweakcn 1:1 | Fokus i czerwony przycisk były słabo widoczne; charakter motywu zostaje | Plan |
| Zakres kolorów | Wszystkie 12 literałów, także bańki i `.mistakes` | Nowe szare tło i tak dotyka strony rozmowy; w `base.html` nie zostaje żaden hex | Plan |
| `.topbar` | Reguły do `components.css`, markup zostaje w `home.html` | Cały CSS w jednym miejscu; świadomie otwiera decyzję F2 z 2026-10-07 | Plan |
| „Delete account” | Z paska do stopki home, czerwony link, `href` bez zmian | Na telefonie nie da się go już pomylić z „Log out” | Plan |
| Czcionki | `Inter, system-ui, sans-serif`, bez plików czcionek | Zero bajtów i licencji; na Macu prawie jak Inter | Plan |
| Dark mode | Teraz, za `prefers-color-scheme`, bez przełącznika | Komfort od razu; kontrast pilnowany testem w obu motywach | Plan |
| Komponenty | Kontrakt klas CSS (`btn`, `link`, `choice-list`, `alert`), nie `{% include %}` | Include nie przyjmuje treści w środku (notice ma inny include), a przycisk to jeden atrybut; tak samo robi Basecoat dla prostych komponentów | Plan (koryguje Research §b) |
| Warianty | Atrybut `data-variant` (konwencja Basecoat): `class="btn" data-variant="destructive"`; błąd Django (`error`) → alias wariantu `destructive` w CSS, bez globalnego `MESSAGE_TAGS` (admin zostaje bez zmian) | Późniejsza migracja na Basecoat bez przepisywania markupu | Plan |
| Kiedy szablon | Komponent z >1 elementem HTML powtarzany w 2+ miejscach → `accounts/templates/ui/<nazwa>.html` (te same klasy w środku) | Jasna granica na przyszłość; dobudowa, nie przepisywanie | Plan |
| Goły `<button>` | Wygląd secondary z tokenów | Strony spoza zakresu dostają spójny wygląd i fokus bez edycji szablonów | Plan |
| Bramka | `toHaveScreenshot` (home + `/ui/`, 2 motywy × 2 szerokości) lokalnie + strażnicy pytest w CI | Wszystkie 7 stanów na zrzucie, reguła pilnowana automatycznie | Plan |
| Gałęzie | Jedna gałąź `ui-home-tokens`, jeden PR | Fazy zależne; pół-motyw nie może trafić na produkcję | Plan |

## Scope

**In scope:**
- `tokens.css` (jasne + ciemne) i `components.css` w `accounts/static/ui/css/`, ładowane w `base.html`
- Komponenty z wariantami w `data-variant`: przycisk (primary/secondary/destructive), link destructive, lista wyboru, alert (destructive/success/warning)
- Przebudowa `home.html`; komunikaty flash jako alert
- Stany hover, focus-visible, disabled, loading (+ `prefers-reduced-motion`)
- Strona `/ui/` tylko w DEBUG; zrzuty Playwright; strażnicy w `tests/test_ui.py`
- Sekcja UI w `CLAUDE.md`

**Out of scope:**
- Restyling szablonów login, detail, account_delete (dziedziczą tylko globalne reguły)
- Wspólny pasek nawigacji, przełącznik motywu, własne czcionki, nowy JS
- Tokeny bez zastosowania (`--chart-*`, `--sidebar-*`, `--popover*`, serif, mono)
- Playwright w CI

## Architecture / Approach

`base.html` ładuje `tokens.css` → `components.css` → `{% block head %}`. Tokeny to jedyne miejsce z wartościami (`:root` + `@media (prefers-color-scheme: dark)`), komponenty czytają wyłącznie `var(--…)`, szablony używają wyłącznie klas. Strażnicy pytest sprawdzają każdą z tych granic; zrzuty Playwright sprawdzają wynik wizualny.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Pliki statyczne bez zmiany wyglądu | CSS w plikach statycznych, test `finders`, sprawdzony manifest | Literówka w `{% static %}` = 500 w produkcji (pytest jej nie widzi) |
| 2. Tokeny + strażnicy | Wartości AA w obu motywach, 0 literałów, testy literałów i kontrastu | Ciemne wersje dodanych tokenów (bańki, warning) trzeba dobrać od zera |
| 3. Home na komponentach | Przycisk, lista, alert; „Delete account” w stopce | Złamanie przypiętego HTML (`class="flash`, `href`, teksty) |
| 4. Stany + kitchen sink + zrzuty | Hover/focus/disabled/loading, `/ui/`, `toHaveScreenshot` | Niestabilne zrzuty; loading bez tworzenia rozmowy w E2E |
| 5. Reguła | Sekcja UI w `CLAUDE.md`, status zarzutów | Reguła rozjedzie się z faktycznymi nazwami klas |

**Prerequisites:** gałąź `ui-home-tokens` (jest); `.env.e2e` z użytkownikiem E2E bez aktywnej rozmowy i bez wyczerpanego limitu.
**Estimated effort:** ~3–4 sesje w 5 fazach (faza 4 największa).

## Open Risks & Assumptions

- Zmiana wyglądu przycisków, pól i kolorów na stronach spoza zakresu jest świadoma, ale bez ich osobnego audytu.
- Zrzuty są zależne od maszyny (sufiks `-darwin`) i fontu systemu — działają jako bramka lokalna, nie w CI.
- Ciemne wartości dodanych tokenów nie pochodzą z tweakcn; ich jedyną miarą jest test kontrastu i ręczny przegląd.

## Success Criteria (Summary)

- Na home od razu widać, która akcja jest główna, a która niebezpieczna — w jasnym i ciemnym motywie, na telefonie i desktopie.
- Użytkownik klawiatury zawsze widzi, gdzie jest fokus.
- Następny agent, który wpisze kolor w szablon albo pogorszy kontrast tokenu, dostaje czerwone CI.
