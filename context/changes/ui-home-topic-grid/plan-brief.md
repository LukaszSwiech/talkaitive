# Siatka kart tematów na home — Plan Brief

> Full plan: `context/changes/ui-home-topic-grid/plan.md`

## What & Why

Lista 20 tematów na home to dziś długa kolumna jednakowych przycisków z pełnymi tytułami. Trudno w niej coś szybko znaleźć, a na telefonie trzeba długo przewijać. Zmiana grupuje tematy w 4 kategorie z przyklejonym paskiem skoków. Każda karta dostaje ikonę, krótką nazwę i podtytuł. Dochodzi „Surprise me” dla osób, które nie chcą wybierać.

## Starting Point

`conversations/topics.py` ma `Topic(key, title, scenario)` i 20 tematów. Home renderuje je jako `<ul class="choice-list">` z formularzem `POST /conversations/start/` per temat. Strona ma 36rem szerokości, w CSS nie ma siatki, w repo nie ma żadnej ikony ani losowania. Rozmowa kopiuje tytuł i scenariusz, więc lista tematów zmienia się bez migracji.

## Desired End State

Home (jasny i ciemny motyw, telefon i desktop) pokazuje nagłówek „Choose a topic”, przycisk „Surprise me” i przyklejony pasek z 4 kategoriami. Pod nimi są sekcje z siatką kart: 1 kolumna na telefonie, 2–3 na desktopie. „Surprise me” od razu startuje losowy temat, inny niż temat ostatniej rozmowy. pytest nie przepuści tematu bez kategorii albo bez istniejącej ikony, a `CLAUDE.md` mówi, jak dodać temat lub ikonę.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Kategorie | Shops & errands (6), Neighbours & small talk (6), Appointments & officials (4), Social life (4); id `errands`, `small-talk`, `appointments`, `social` | Sytuacje z życia, które uczeń rozpozna; id nie wywracają regexu kolorów w strażniku |
| Losowanie | Serwer, równomiernie z tematów bez tematu ostatniej rozmowy (`for_user`, `-created_at`); bez historii lub nieznany klucz → z wszystkich 20 | „Niespodzianka” nigdy nie powtarza tego, co było przed chwilą |
| Trasa | `POST /conversations/start/random/` → `services.start_conversation` | Te same błędy (limit, aktywna rozmowa, LLM) bez kopiowania logiki |
| Ikony | Tabler outline jako szablony `accounts/templates/ui/icons/*.svg`, wstawiane inline przez `{% include %}` | `currentColor` działa (z `<img>` by nie działał), istniejący strażnik kolorów skanuje pliki |
| Licencja | `LICENSE` (MIT) + `README.md` z wersją i źródłem obok ikon | Licencja jedzie razem z plikami, jasne źródło kolejnej ikony |
| Szerokość | Tylko home i kitchen sink ~60rem (`{% block body_class %}` → `page-wide`), siatka `auto-fill` | Więcej tematów naraz; strona rozmowy zostaje czytelna |
| Teksty kart | Ręcznie wpisane `name` + `subtitle` (tabela w planie), `title` bez zmian | Krótkie nazwy także dla tematów bez dwukropka |
| „Surprise me” | Pod nagłówkiem, `btn` primary z ikoną `arrows-shuffle`, `data-waits-for-agent` | Widoczny bez przewijania, ten sam stan loading co karta |
| Linki-skoki | Pasek sticky, jedna linia z poziomym przewijaniem, `scroll-padding-top` na `html:has(.category-nav)` | Zawsze pod ręką; stała wysokość, więc ani nagłówek po skoku, ani karta z fokusem nie chowa się pod paskiem |
| Karta | Szablon `ui/topic-card.html` (sam przycisk), `choice-list` usunięty | Ten sam markup na home i w `/ui/`; brak martwego komponentu |
| E2E | Odświeżone zrzuty + test skoku pod paskiem sticky + test loading po „Surprise me” (POST przerwany) | Przeglądarka sprawdza tylko to, czego pytest nie widzi |
| Gałęzie | Jedna gałąź `ui-home-topic-grid`, jeden PR | Fazy 1–2 same nic nie zmieniają dla użytkownika |

## Scope

**In scope:**
- Pola `name`, `subtitle`, `category`, `icon` w `Topic`; `CATEGORIES`, `topics_by_category()`
- 21 ikon Tabler + `LICENSE` + `README.md`; strażnicy w `tests/test_topics.py`
- `surprise_topic_key()` i trasa `start/random/` z testami
- Home i kitchen sink na `topic-grid`, `topic-card`, `category-nav`, `icon`, `page-wide`
- Spec Playwright: lokatory, 2 nowe testy, odświeżone baseline'y
- Sekcja UI w `CLAUDE.md` z how-to „Adding a topic or icon”

**Out of scope:**
- Zmiana kluczy, tytułów, scenariuszy, promptów, evalu, pamięci; migracje
- Pakiet npm z ikonami, nowy JS, płynne przewijanie, „Back to top”
- Podgląd wylosowanego tematu przed startem; wyszukiwarka i filtry
- Szerokość innych stron; Playwright w CI

## Architecture / Approach

`topics.py` jest jedynym źródłem danych: tematy, kategorie i nazwy ikon. Widok `home` przekazuje `topics_by_category()`, a szablon renderuje pasek, sekcje i karty z `ui/topic-card.html`. Karta wstawia ikonę przez `{% include topic.icon_template %}`. „Surprise me” to osobny formularz POST: serwer losuje klucz i woła tę samą `start_conversation`. Strażnicy pytest łączą dane z plikami ikon, a zrzuty Playwright sprawdzają wygląd.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Dane, ikony, strażnicy | Nowe pola, kategorie, 21 SVG z licencją, `tests/test_topics.py` | Nazwa ikony nieistniejąca w wybranej wersji Tabler; pobieranie wymaga zgody |
| 2. Surprise me (serwer) | `surprise_topic_key()`, trasa `start/random/`, testy brzegowe | Rozjazd zachowania z `conversation_start` przy błędach |
| 3. Siatka na home + `/ui/` | Komponenty CSS, include karty, nowy home i kitchen sink, poprawione testy | Pasek sticky zasłania nagłówek po skoku; złamane przypięte asercje |
| 4. E2E i zrzuty | Nowe lokatory, 2 testy, odświeżone i nowe baseline'y | Niestabilny test geometrii paska na telefonie |
| 5. Reguła | Sekcja UI i how-to w `CLAUDE.md` | Reguła rozjedzie się z nazwami klas |

**Prerequisites:** gałąź `ui-home-topic-grid` (jest); zgoda na pobranie 21 plików SVG i licencji z GitHuba `tabler/tabler-icons`; `.env.e2e` z użytkownikiem E2E.
**Estimated effort:** ~2–3 sesje w 5 fazach (faza 3 największa).

## Open Risks & Assumptions

- Nazwy ikon z tabeli zakładają Tabler v3. Brakującą nazwę implementer zastępuje najbliższą i zapisuje zamianę w README i planie.
- Pasek i stopka na home rozciągną się do ~60rem — świadomie, bez osobnego projektu.
- Zrzuty dalej są zależne od maszyny (sufiks `-darwin`) i działają tylko jako bramka lokalna.

## Success Criteria (Summary)

- Użytkownik w kilka sekund znajduje temat po kategorii albo jednym klikiem startuje losowy, inny niż ostatni.
- Każda karta ma ikonę widoczną w obu motywach, a czytnik ekranu jej nie czyta.
- Kolejny agent, który doda temat bez kategorii lub ikony, dostaje czerwone CI.
