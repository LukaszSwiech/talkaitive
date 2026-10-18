# Warstwa evalu AI (test-plan Phase 5) — Plan Brief

> Full plan: `context/changes/testing-ai-eval-layer/plan.md`
> Research: `context/changes/testing-ai-eval-layer/research.md`

## What & Why

Lokalny eval na prawdziwym modelu, który przy zmianie promptu, modelu albo reasoning effort daje liczby zamiast wrażenia: czy analiza znajduje znane błędy, nie zgłasza literówek i trafia w kategorie, czy tura wplata poprawną formę bez wykładu, czy pamięć nie powtarza pytań. Dziś zielone testy dowodzą tylko hydrauliki — atrapy zwracają to, co test im podał.

## Starting Point

`llm.generate_turn` i `llm.analyze_mistakes` da się wywołać bez bazy; reguły jakości istnieją tylko w prompcie. Zmierzono już, że zmiana effort analizy zaczęła zgłaszać literówki, a ta sama rozmowa dała 12 i 18 pozycji. Nie ma żadnego evalu ani zestawu wzorcowego.

## Desired End State

Jedno polecenie (`run_eval.py run`) uruchamia cztery serie — analiza, tura, pamięć, długa analiza — z limitem 5 USD i zapisuje wynik; drugie (`compare`) pokazuje różnicę dwóch wersji per metryka z przedziałem i listą przypadków, które się zmieniły. W repo leży przebieg bazowy, a przebieg na celowo zepsutym prompcie dowiódł, że eval wykrywa pogorszenie. Kod oceniania jest przypięty testami w CI.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Gdzie żyje eval | Skrypt w `scripts/eval/`, poza `tests/` | CI i `uv run pytest` go nie zbierają; wzór `manual_mutants.py` | Research |
| Biblioteka | Brak (DeepEval odrzucony) | Wtyczka `pytest11` ładowałaby się w CI, telemetria domyślnie włączona | Research |
| Źródło wzorca | Korpus MERLIN 1.1 (CC BY-SA 4.0) | Poprawki ekspertów, nie ocenianego modelu; legalny, publiczny | Plan |
| Kategorie wzorca | Przypisane wg reguły podręcznikowej | MERLIN TXT nie ma adnotacji kategorii | Plan |
| Literówki | Poprawki pisowni / interpunkcji z MERLIN jako „nie wolno zgłosić”, niejednoznaczne neutralne | Naturalne literówki uczniów; brak kar za spory | Plan |
| Pamięć (FR-009) | Obie części teraz: notatki w analizie + tura otwierająca | Strojenie listy błędów może niechcący zepsuć notatki; koszt ok. 0,06 USD | Plan |
| Sędzia LLM | Brak w v1 | Metryki deterministyczne z wzorca; naturalność ocenia użytkownik | Plan |
| Powtórzenia i koszt | K=3, twardy limit 5 USD na przebieg | Zmierzona zmienność wymaga powtórzeń; rdzeń ok. 3,1 USD | Plan |
| Częstotliwość | Tylko ręcznie przed i po zmianie promptu, modelu lub effort | 0 USD w miesiącach bez zmian | Plan |
| Czas długiej analizy | Mierzony w każdym przebiegu | Wolniejszy model (> 150 s) wyjdzie od razu; zamyka sprawę z Phase 2 | Plan |
| Mutant `mutmut_47` | Zwykły test jednostkowy | Plan S-03 ustalił wyjaśnienie w pamięci; eval nie zabija mutantów | Plan |
| Gałąź | Jedna gałąź i jeden PR | Bez zmian w kodzie produkcyjnym | Plan |

## Scope

**In scope:**
- Oceniacz (dopasowanie, reguły A1–A5 i T1, metryki, porównanie parami) i licznik kosztu z testami w CI i ręcznymi mutantami
- Zestaw z MERLIN: ok. 12 rozmów analizy, 20 tur, 5 przypadków pamięci, 1 długa rozmowa
- Skrypt `run` / `compare`, przebieg bazowy, przebieg na zepsutym prompcie
- `scripts` w `also_copy` mutmut, test na `mutmut_47`, test-plan §3–§6, punkt w CLAUDE.md

**Out of scope:**
- Sędzia LLM, eval w CI lub cyklicznie, zmiany promptów i modelu
- Prawdziwość faktów o uczniu, język angielski, najgorszy przypadek czasu
- Równoległe wywołania, DeepEval / promptfoo / OpenAI Evals, archiwum MERLIN w repo

## Architecture / Approach

`golden.py` (dane z atrybucją) → `run_eval.py` woła `llm.analyze_mistakes` / `llm.generate_turn` (Django bez bazy, prawdziwy klucz z `.env`, `CostMeter` przed każdym wywołaniem) → `scoring.py` liczy naruszenia i metryki per przypadek → JSON w `scripts/eval/results/` → `compare` dwóch plików: różnica sparowana per przypadek z 95% przedziałem.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Rdzeń oceniania i testy w CI | Oceniacz, licznik kosztu, testy, mutanty, `mutmut_47` | Oczekiwane liczby skopiowane z oceniacza zamiast policzone ręcznie |
| 2. Zestaw z MERLIN i skrypt | Zestaw, `run` / `compare`, przebieg bazowy i na zepsutym prompcie | Za mało wyraźnych błędów szyku w MERLIN; eval nie wykrywa zepsucia |
| 3. Domknięcie | Test-plan §3–§6, CLAUDE.md, pełne mutacje | — |

**Prerequisites:** prawdziwy `OPENAI_API_KEY` w `.env`; zgoda na pobranie `merlin-text-v1.1.zip` (5,78 MB); ok. 5–8 USD na koncie OpenAI na przebiegi tej fazy.
**Estimated effort:** ~3 sesje w 3 fazach (najwięcej pracy: budowa zestawu w fazie 2).

## Open Risks & Assumptions

- Nazwa `gpt-5.4` może u dostawcy wskazać nowszy model bez zmiany po naszej stronie; przy „tylko ręcznie” taka zmiana jakości zostanie niewykryta.
- Kategorie wzorca przypisuje agent wg reguły (bez native speakera); przypadki niejednoznaczne trafiają do neutralnych albo dostają dwie dopuszczalne kategorie.
- Znaczniki wykładu i słowa kluczowe pamięci to przybliżenia: fałszywe alarmy („Regel” w rozmowie o zasadach gry) i przeoczone parafrazy wymagają lektury przypadków.
- Przy ok. 12 rozmowach i 20 turach różnice poniżej rzędu 10 pp są w granicach szumu — `compare` mówi to wprost.
- Pobranie MERLIN może trafić na ochronę przed botami; wtedy pobiera użytkownik w przeglądarce.

## Success Criteria (Summary)

- Przed i po zmianie promptu lub modelu użytkownik dostaje tabelę metryk z werdyktem „różnica” albo „w granicach szumu”, za ok. 3,4 USD.
- Celowo zepsuty prompt daje w `compare` wyraźny spadek — eval nie jest ślepy.
- `uv run pytest` i CI dalej działają bez klucza; kod oceniania i `mutmut_47` są przypięte testami i mutantami.
