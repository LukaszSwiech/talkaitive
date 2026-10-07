# Pamięć między rozmowami i domykanie pętli błędów (S-03) — Plan Brief

> Full plan: `context/changes/cross-session-error-memory/plan.md`
> Research: `context/changes/cross-session-error-memory/research.md`

## What & Why

Kolejna rozmowa ma pamiętać poprzednie: agent zna fakty o uczniu (imię psa, praca), w tej samej scenie nawiązuje do wcześniejszych wątków i nie powtarza pytań (FR-009), a przy okazji naturalnie daje szansę użyć jednej konstrukcji, w której uczeń wcześniej się mylił — bez mówienia, że to poprawka (FR-010). To przewaga nad zwykłym czatem, którą PRD nazywa wprost.

## Starting Point

Dziś prompt rozmowy to tylko instrukcje, język i scena; nie ma żadnej pamięci. Analiza po rozmowie (S-02) zapisuje błędy jako pary `wrong→correct` w obrębie jednej rozmowy, bez notatek o wątkach ani faktach o uczniu.

## Desired End State

Analiza po rozmowie zapisuje też krótkie notatki (fakty o uczniu, wątki sceny). Przy starcie rozmowy kod wybiera pamięć — do 10 dawnych błędów, fakty z 10 ostatnich rozmów, wątki z 5 ostatnich rozmów w tej scenie — i zapisuje ją jako stały blok promptu dla całej rozmowy. Agent korzysta z niej tylko, gdy pasuje do sceny.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| „Ten sam błąd” między rozmowami | Dokładna para `wrong→correct`, porównana po normalizacji spacji i `casefold` | Deterministyczne, działa od razu na błędach sprzed S-03; wielka litera na początku zdania nie rozbija grupy | Plan |
| Częstość błędu | Liczba różnych rozmów z daną parą; remis → nowszy `ended_at` | Dosłownie „błąd powtarzany w wielu rozmowach” z PRD | Plan |
| Okno i limit błędów | Do 10 par z 20 ostatnich przeanalizowanych rozmów w danym języku | Bez FR-011 tylko okno pozwala opanowanym błędom wypaść | Plan |
| „Pasuje do tematu” (błędy) | Kod wybiera listę bez filtra tematu, agent ocenia dopasowanie do sceny | Konstrukcje gramatyczne rzadko zależą od sceny | Plan (research: opcja 2) |
| Ile konstrukcji na rozmowę | Najwyżej jedna: najwyżej na liście spośród pasujących do sceny | Rozmowa ma brzmieć naturalnie, nie jak ukryty test | Plan |
| Źródło wątków i pytań | Notatki dopisywane przez istniejącą analizę po rozmowie | Bez nowego wywołania LLM i bez zmian w budżecie | Plan (research: opcja 3) |
| Dwa rodzaje notatek | Fakty o uczniu z 10 ostatnich rozmów dowolnego tematu; wątki sceny z 5 ostatnich rozmów tego samego tematu | Sąsiad zna imię psa z parku, ale wątki nie mieszają się między scenami | Plan |
| Observational Memory | Po MVP, osobny issue; teraz fakty z 10 rozmów, w kodzie oznaczone jako tymczasowe | OM wymaga osobnego wywołania LLM, nowej tabeli, kosztu w budżecie i obsługi błędów — rozmiar S-02 | Plan |
| Rozmowy bez analizy | Pomijamy | Bez dodatkowego czekania i kosztu; przypadek rzadki | Plan |
| Język | Pamięć osobno dla `en` i `de` | Błędy z jednego języka nie mogą trafić do drugiego | Research |
| Miejsce pamięci w prompcie | Snapshot `memory_prompt` przy starcie, po `Scene:` | Stały prefiks w obrębie rozmowy, cache działa | Research |

## Scope

**In scope:**
- Pola `learner_facts`, `scene_notes`, `memory_prompt` na `Conversation` (2 migracje)
- Rozszerzenie schematu i instrukcji analizy o notatki
- Moduł `conversations/memory.py` z regułami wyboru
- Blok pamięci w instrukcjach tury (`llm.py`) i snapshot w `start_conversation`
- Testy jednostkowe i integracyjne z fałszywym LLM

**Out of scope:**
- Observational Memory / profil ucznia (issue po MVP)
- Grupowanie błędów po regule, filtr tematu w kodzie
- Analiza zaległych rozmów, uzupełnianie notatek wstecz
- FR-011, widok/edycja pamięci, zmiany budżetu, Q-07

## Architecture / Approach

`analyze_conversation` → `analyze_mistakes` zwraca błędy **i** notatki → zapis na `Conversation`. Przy starcie: `start_conversation` → `memory.select_memory(user, topic, language)` (czyste zapytania przez `for_user`) → `llm.format_memory()` → `Conversation.memory_prompt`. Każda tura: `_generate_and_save` → `generate_turn(memory=...)` → instrukcje = stałe → język → scena → pamięć.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Notatki w analizie po rozmowie | Analiza zapisuje fakty o uczniu i wątki sceny | Druga rola analizy pogorszy listę błędów albo ją spowolni |
| 2. Wybór pamięci | Deterministyczny ranking błędów i wybór notatek, w pełni przetestowany | Para `wrong→correct` rzadko się powtarza, więc ranking to głównie świeżość |
| 3. Pamięć w rozmowie | Agent pamięta ucznia, scenę i ćwiczy jedną dawną konstrukcję | Agent wciska okazje na siłę lub wciąga wątki spoza sceny |

**Prerequisites:** S-01 i S-02 zrobione; lokalny `OPENAI_API_KEY` w `.env` do testów ręcznych.
**Estimated effort:** ~2–3 sesje w 3 fazach.

## Open Risks & Assumptions

- Dokładna para rzadko powtarza się między rozmowami — częstość zadziała słabo, kolejność ustali głównie świeżość (decyzja świadoma).
- Błędny fakt z analizy (np. źle zrozumiane imię) wraca w prompcie, dopóki nie wypadnie z okna 10 rozmów.
- Blok pamięci do ok. 1–1,5 tys. tokenów zwiększa koszt tury; cache od drugiej tury mocno to obniża.
- Rozmowy porzucone (`active`) i nieprzeanalizowane nie zasilają pamięci.
- PRD mówi „tylko niemiecki”, a kod ma `en` i `de` — pamięć jest rozdzielona po języku.

## Success Criteria (Summary)

- W drugiej rozmowie w tej samej scenie partner pamięta poprzednią i nie powtarza pytań.
- W innej scenie agent korzysta z faktów o uczniu, gdy pasują, bez wciągania obcych wątków.
- Najwyżej jedna dawna konstrukcja pojawia się jako naturalna okazja, bez słowa o poprawce.
