# Rollout Phase 4 — sufit dziennego budżetu — Plan Brief

> Full plan: `context/changes/testing-budget-ceiling/plan.md`
> Research: `context/changes/testing-budget-ceiling/research.md`

## What & Why

Faza 4 test-planu (ryzyko #4) miała udowodnić, że dzienny limit $1 trzyma się także przy błędach, ponowieniach i drogich wywołaniach. Research pokazał, że dziś to nieprawda: nieudane i spóźnione płatne wywołania zapisują koszt 0, a w trwającej rozmowie wysłanie wiadomości i „Try again” nigdy nie są odmawiane z powodu budżetu. Plan najpierw domyka te luki w kodzie, potem przypina je testami potwierdzonymi mutacją.

## Starting Point

Limit jest „miękki z prognozą”: twardo blokuje tylko start rozmowy (`budget.is_exhausted`), w rozmowie tylko przewiduje turę pożegnalną (`is_final_turn`), a ta jest płatna. Koszt zapisujemy tylko dla udanej tury (`Message.cost_usd`) i udanej analizy (`analysis_cost_usd`); timeout, pusta odpowiedź, spóźniony wynik i nieudany zapis nie zostawiają nic. Analiza jest celowo poza limitem (S-02).

## Desired End State

Każde wywołanie, które najpewniej kosztowało, liczy się do sumy dnia — prawdziwym kosztem z `usage` albo szacunkiem dla timeoutu. Gdy suma dnia osiągnie limit, wysłanie i „Try again” tury kończą rozmowę z komunikatem o limicie i godziną resetu, bez wywołania modelu; ponowienie analizy czeka do północy Berlina. Testy mają kwoty i chwile wpisane ręcznie (także 29 marca i 25 października) i padają na celowych mutantach.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Gwarancja limitu | Liczyć nieudane próby + twardy dach na tury | Tylko tak cel fazy z test-planu da się udowodnić; przekroczenie ograniczone do wywołań rozpoczętych poniżej limitu. | Plan |
| Nowy niezmiennik zamiast „suma ≤ limit” | Po osiągnięciu limitu żadne nowe płatne wywołanie tury ani ponowienie analizy | PRD przewiduje płatną turę pożegnalną i analizę po rozmowie, więc „suma ≤ limit” jest sprzeczne z PRD. | Research + Plan |
| Kwota za próbę bez `usage` | Timeout / zły schemat = szacunek (tura: koszt ostatniej tury rozmowy albo 0,03; analiza: 0,07); szybkie 429/5xx = 0; odpowiedź z `usage` = prawdziwy koszt | Liczy to, za co OpenAI najpewniej płaci, bez karania za odrzucone żądania. | Plan |
| Gdzie zapisać koszt | Nowy model-księga `LLMCharge` (`UserOwned`, `charged_at = now`) tylko dla wywołań bez innego zapisu | Własna data przypisuje koszt do właściwego dnia w Berlinie; `Message` i analiza bez zmian. | Plan |
| Co widzi użytkownik przy dachu | Wiadomość niezapisana, rozmowa kończy się `DAILY_LIMIT`, strona pokazuje godzinę resetu | Brak płatnego wywołania i brak wiadomości bez odpowiedzi; PRD: rozmowa kończy się bez „dokończenia”. | Plan |
| Analiza pod dachem | Pierwsza próba zawsze (S-02); ponowienie po błędzie odmawiane do resetu | Ogranicza płatne ponowienia także przy awarii dostawcy. | Plan |
| `max_output_tokens`, limit prób „Try again” | Nie — zostaje ryzykiem Q-07 | Ponowienia zatrzymuje dach dnia; brak ryzyka uciętej analizy. | Plan |
| E2E (Playwright) | Nie w tej fazie | Komunikat to HTML z serwera, a ścieżki pieniędzy są dla serwera E2E (bez modelu) nieosiągalne. | Research + Plan |
| Gałęzie | Jedna gałąź `testing-budget-ceiling`, jeden PR | Migracja tylko dodaje tabelę; faza 2 zależy od fazy 1. | Plan |

## Scope

**In scope:** model `LLMCharge` + migracja; dane o koszcie w `LLMError`; zapis kosztu na ścieżkach timeoutu, pustej odpowiedzi, spóźnienia i nieudanego zapisu; suma dnia z księgą; predykat `limit_reached` i dach w `send_message` / `run_agent_turn` / ponowieniu analizy; godzina resetu zamiast „Try again” analizy; testy unit (w tym dni zmiany czasu) i integracyjne; ręczne mutanty `M25`–`M34`; §6.4 / §6.6 test-planu; dopisek do Q-07.

**Out of scope:** `max_output_tokens` i limit prób; E2E; jedna księga wszystkich wywołań; liczenie każdego żądania HTTP SDK osobno; dach na pierwszą analizę; zmiana prognozy tury pożegnalnej; pokazywanie kosztów użytkownikowi; limit miesięczny w OpenAI.

## Architecture / Approach

`llm.py` mówi tylko, co wie o koszcie nieudanego wywołania (tokeny albo „prawdopodobnie płatne bez `usage`”); `budget.py` zna ceny, szacunki, sumę dnia (tury + analizy + księga) i predykat dachu; `services.py` decyduje, kiedy zapisać wpis księgi i kiedy odmówić. Dach sprawdzany pod blokadą wiersza; zakończenie rozmowy zatwierdzane przed zgłoszeniem odmowy. Oczekiwane wartości w testach to literały z rachunkiem w komentarzu, nigdy wynik funkcji z kodu.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Księga kosztów | Każda płatna próba (nieudana, spóźniona) w sumie dnia; testy ścieżek kosztu; `M25`–`M30` | Kolejność `except` (`APITimeoutError` przed `APIError`); refaktor `is_final_turn` przesuwa fragmenty mutantów `C2` / `M4` |
| 2. Twardy dach | Odmowa i koniec rozmowy po osiągnięciu limitu; ponowienie analizy po resecie; `M31`–`M34` | Odmowa rzucona w transakcji cofnęłaby zakończenie rozmowy; dwa zegary w testach |
| 3. Domknięcie | §6.4 / §6.6 test-planu, pełny mutmut + rejestr, dopisek Q-07 | Nowe przeżycia mutmut w `budget.py` / `services.py` |

**Prerequisites:** gałąź `testing-budget-ceiling` (jest); zielone `uv run pytest`; do ręcznego sprawdzenia fazy 2 klucz `OPENAI_API_KEY` w `.env`.
**Estimated effort:** ~2–3 sesje w 3 fazach (faza 1 największa).

## Open Risks & Assumptions

- Rozliczanie przerwanego żądania bez streamingu przez OpenAI nie ma oficjalnego źródła (tylko społeczność) — szacunek dla timeoutu to założenie, nie pomiar.
- Szacunek analizy 0,07 USD pochodzi z jednego pomiaru (20 tur, `medium`); dłuższa rozmowa kosztuje więcej, więc timeout analizy może być zaniżony.
- Timeout po ponowieniu SDK (2 żądania) to jeden szacunek; timeout, a potem 5xx, daje 0.
- Pojedyncze wywołanie przy bardzo długiej rozmowie dalej nie ma górnej granicy kosztu (Q-07); twardym zabezpieczeniem poza kodem jest limit miesięczny projektu OpenAI — niesprawdzony.

## Success Criteria (Summary)

- Po osiągnięciu dziennego limitu żadne nowe płatne wywołanie tury ani ponowienie analizy nie trafia do dostawcy, a użytkownik widzi powód i godzinę resetu.
- Nieudane i spóźnione próby podnoszą sumę dnia o kwotę zapisaną ręcznie w teście; reset działa o północy Berlina także 29 marca i 25 października.
- Każdy nowy test pada na swoim ręcznym mutancie; mutmut nie ma niewyjaśnionych przeżyć.
