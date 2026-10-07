# Lista błędów po zakończeniu rozmowy (S-02) — Plan Brief

> Full plan: `context/changes/post-conversation-error-list/plan.md`

## What & Why

Po zakończeniu rozmowy użytkownik widzi listę swoich błędów: kategoria, fragment błędny → poprawny, oryginalne zdanie i krótkie wyjaśnienie (FR-008). Korekta na żywo (recast) bywa niezauważona; lista po rozmowie domyka tę lukę i daje dane, z których S-03 zbuduje pamięć błędów między rozmowami.

## Starting Point

S-01 zapisuje pełny transkrypt, ale nie wykrywa błędów — tura agenta zwraca tylko `{reply, end_conversation}`. Po zakończeniu (End / pożegnanie / limit) strona rozmowy pokazuje tylko komunikat „This conversation has ended”. S-01 ustalił już kierunek: jedno osobne wywołanie modelu nad całym transkryptem po zakończeniu.

## Desired End State

Pod transkryptem zakończonej rozmowy pojawia się spinner, strona sama uruchamia analizę, a po chwili pokazuje chronologiczną listę błędów („×N” przy powtórzeniach) albo „No mistakes found”. Analiza dzieje się raz na rozmowę, jej koszt liczy się do dziennego limitu, a porażka daje „Try again”. Błędy są danymi użytkownika: niewidoczne dla innych i usuwane razem z kontem.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Sposób wykrywania | Jedno wywołanie nad całym transkryptem po zakończeniu | Szybkie tury i jedno zadanie na wywołanie. | S-01 plan |
| Moment uruchomienia | Osobny POST `/analysis/` wysyłany automatycznie przez stronę (bez JS — przycisk) | Działa dla 3 dróg zakończenia i nie sumuje dwóch wywołań w jednym żądaniu (każde żądanie czeka tylko na jedno wywołanie modelu). | Plan |
| Budżet | Koszt wliczany do dnia, ale analiza rusza zawsze, też po limicie | Każda rozmowa ma listę, a wydatki są prawdziwe; dzień może przekroczyć $1 o jedną analizę. | Plan |
| Pozycja listy | Fragment błędny → poprawny + całe zdanie | Widać dokładnie błąd i jego kontekst; pojedyncze błędy łatwo liczyć w S-03. | Plan |
| Kolejność | Chronologicznie, kategoria jako etykieta | Łatwo powiązać błąd z momentem rozmowy. | Plan |
| Powtórzenia | Identyczna para scalana przez kod w jedną pozycję z „×N” w miejscu pierwszego wystąpienia | Krótsza lista, przewidywalna i testowalna reguła. | Plan |
| Wyjaśnienie | Jedno zdanie po angielsku (język UI) | Lista uczy, a nie tylko wylicza. | Plan |
| Model | Ten sam `gpt-5.4`, reasoning effort `high` (env `LLM_ANALYSIS_REASONING_EFFORT`) | Modelom trudno o dokładne podsumowanie, a trafność listy to kryterium sukcesu PRD. | Plan |
| Zakres błędów | Bez literówek, wielkości liter i interpunkcji (chyba że zmieniają sens) | Spójne z korektą na żywo. | Plan |
| Miejsce na stronie | Pod transkryptem | Najmniejsza zmiana szablonu. | Plan |
| Kolejność i scalanie liczy kod | Model zwraca numer wiadomości ucznia | Deterministyczne sortowanie zamiast ufania kolejności modelu. | Plan |
| Ochrona przed pętlą | `analysis_failed_at` wyłącza auto-wysyłkę | Bez tego nieudana analiza ponawiałaby płatne wywołanie w kółko. | Plan |

## Scope

**In scope:** model `Mistake(UserOwned)` + pola stanu analizy w `Conversation` (migracja `0003`); `llm.analyze_mistakes` ze strukturalną odpowiedzią; `services.analyze_conversation` (jednorazowość, znacznik w toku, scalanie, kolejność, koszt, porażka); `spent_today` z kosztem analiz; widok `/analysis/`, 4 stany strony, auto-wysyłka w `base.html`; testy i ręczny test na prawdziwym modelu.

**Out of scope:** wykrywanie błędów per tura; pamięć i wybór błędów do kolejnej rozmowy (S-03); historia rozmów i edycja błędów; rezerwacja budżetu pod analizę; scalanie „podobnych” błędów; tańszy model; zadania w tle; zmiany ustawień Railway.

## Architecture / Approach

End / pożegnanie / limit → `end_conversation` (bez zmian) → strona rozmowy w stanie „nierozpoczęta” → auto-POST `conversation_analyze` → `services.analyze_conversation`: pod blokadą ustawia znacznik → poza transakcją `llm.analyze_mistakes` (Responses API, `MistakeReport`, effort `high`, timeout 90 s, 0 ponowień) → pod blokadą scalanie i sortowanie w kodzie, zapis `Mistake`, kosztu i `analyzed_at` → redirect → strona z listą. Wzorce znacznika, blokady i obsługi błędów są skopiowane z tur S-01.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Model danych i budżet | `Mistake`, pola analizy, migracja, `spent_today` z analizami | Pominięcie izolacji per użytkownik (pilnują testy) |
| 2. Wywołanie modelu | `analyze_mistakes`, prompt, ustawienia effort/timeout | `gpt-5.4` z effort `high` za wolny lub odrzuca ustawienie |
| 3. Serwis analizy | Jednorazowa analiza, scalanie „×N”, kolejność, koszt, porażka | Wyścig równoległych żądań (dwa płatne wywołania) |
| 4. Widok i ekran | `/analysis/`, 4 stany strony, auto-wysyłka, test na żywo | Pętla auto-wysyłki po porażce; trafność listy |

**Prerequisites:** S-01 zarchiwizowane (done); lokalny `OPENAI_API_KEY` w `.env` do testów ręcznych.
**Estimated effort:** ~3–4 sesje w 4 fazach.

## Open Risks & Assumptions

- Zakładamy, że `gpt-5.4` przyjmuje reasoning effort `high` i że analiza ~20 tur mieści się wyraźnie w 90 s; sprawdzane ręcznie w fazach 2 i 4. Jeśli nie, effort zmienia się zmienną `LLM_ANALYSIS_REASONING_EFFORT` bez zmiany kodu.
- Dzień może przekroczyć $1 o koszt jednej analizy (szacunkowo kilka centów) — świadomie zaakceptowane.
- Trafność listy (kryterium sukcesu PRD) oceniamy tylko ręcznie na kilku rozmowach; brak automatycznej ewaluacji.
- Rozmowy zakończone przed wdrożeniem dostaną listę dopiero po otwarciu ich strony.

## Success Criteria (Summary)

- Po każdym sposobie zakończenia rozmowy użytkownik widzi pod transkryptem trafną, chronologiczną listę błędów z kategoriami.
- Żadne odświeżenie, podwójny klik ani porażka nie powoduje drugiego płatnego wywołania; porażkę naprawia „Try again”.
- Błędy jednej osoby nigdy nie są widoczne dla innej i znikają razem z kontem lub rozmową.
