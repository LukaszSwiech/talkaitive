# Pierwsza rozmowa z korektą na bieżąco (S-01) — Plan Brief

> Full plan: `context/changes/first-corrected-conversation/plan.md`
> Research: `context/changes/first-corrected-conversation/research.md`

## What & Why

Zalogowany użytkownik wybiera jeden z 20 tematów i prowadzi tekstową rozmowę z agentem, który wplata poprawne formy jego błędów (recast) bez przerywania rozmowy. To gwiazda przewodnia MVP (S-01): najmniejszy kawałek produktu, którego autor i jego żona mogą realnie używać. Pierwsza wersja działa też po angielsku, żeby autor mógł sam ocenić jakość korekty.

## Starting Point

Działa logowanie e-mailem i wzorzec izolacji danych per użytkownik (`UserOwned` + `for_user`, F-01). Strona główna to placeholder; w repo nie ma jeszcze żadnego kodu LLM ani klucza API na Railway.

## Desired End State

Na `/` użytkownik wybiera temat; agent otwiera scenkę w języku ustawionym przy koncie (`en`/`de`), rozmowa toczy się z naturalnym recastem (max 1–2 poprawki na odpowiedź), podczas czekania kręci się spinner z „Agent is typing…”. Rozmowa kończy się przyciskiem „End”, potwierdzonym pożegnaniem albo przez dzienny budżet $1 — wtedy agent się żegna, a strona mówi, od kiedy można rozmawiać ponownie (północ Europe/Berlin). Cały transkrypt jest w bazie, gotowy do analizy błędów w S-02.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Dostawca i model | OpenAI, GPT-5.4 (nazwa modelu w env `LLM_MODEL`) | Jedyny dostawca z dojrzałym API głosowym (Realtime, WebRTC) na przyszłość — ten sam klucz i SDK dla tekstu teraz i głosu po MVP; Anthropic nie ma API głosowego. |
| Jednostka limitu | Budżet kosztów w $ liczony z faktycznego `usage` API | Bezpośrednio chroni koszty, które ponosi aplikacja. |
| Wartość limitu | $1.00 dziennie na użytkownika (env `DAILY_BUDGET_USD`) | Limit nie przeszkadza w nauce; najgorszy przypadek ~$60/mies. dla 2 osób. |
| Reset limitu | Północ Europe/Berlin (z czasem letnim) | Najprostszy do zrozumienia komunikat „od 00:00”. |
| Klucz API | `OPENAI_API_KEY`: lokalnie `.env` + `uv run --env-file .env`, na Railway wymagany (brak = crash startu) | Bez nowej zależności, spójne z wzorcem `SECRET_KEY`; klucz nigdy w repo. |
| Język rozmowy | Pole `User.practice_language` (`en`/`de`, domyślnie `de`), ustawiane w `/admin/` | Autor testuje po angielsku, a żona ćwiczy niemiecki równolegle, bez zmian w UI. |
| Wyłapywanie błędów | Osobna analiza całego transkryptu po rozmowie (JSON), budowana w S-02 | Szybsze tury rozmowy, jedno zadanie na wywołanie i ten sam wzorzec zadziała przy głosie. |
| Zakres S-01 | Rozmowa + pełny transkrypt; analiza i lista błędów w S-02 | S-01 zostaje w zakresie roadmapy; zapisane transkrypty pozwolą S-02 przeanalizować wcześniejsze rozmowy. |
| Recast | Max 1–2 najważniejsze błędy na odpowiedź, bez literówek i interpunkcji | Guardrail z PRD: korekta nie zamienia rozmowy w wykład. |
| Pożegnanie (FR-007) | Agent pyta, czy kończyć; koniec dopiero po potwierdzeniu | Chroni przed „fałszywym pożegnaniem” w scence. |
| Limit w trakcie rozmowy | Gdy kolejna tura przekroczy budżet, agent się w niej żegna i wspomina o limicie | Zgodne z PRD („agent komunikuje”); przekroczenie max o koszt ok. dwóch tur; po pożegnaniu z limitem dzień jest zamknięty do północy. |
| Oczekiwanie | Formularz POST + mały skrypt: zablokowany przycisk, spinner CSS, „Agent is typing…” | Zero nowych zależności, zgodne z `has_realtime: false`; widoczny ruch zamiast samego tekstu. |
| Powrót do rozmowy | Max 1 aktywna rozmowa na osobę (ograniczenie w bazie); `/` proponuje „Continue conversation” | Zamknięta karta nie traci rozmowy ani transkryptu. |
| Tematy | 20 codziennych sytuacji z życia w Niemczech jako stała w kodzie (lista w planie) | Zero tabel i ekranów; nie rusza testu rejestru admina. Pole `topic` bez `choices` (zmiana listy bez migracji), a rozmowa trzyma kopię tytułu i scenariusza. |
| Błąd API | Wiadomość zostaje zapisana, komunikat + „Try again” | Nic nie przepada, użytkownik decyduje. |
| Prywatność po stronie OpenAI | `store=False` w każdym wywołaniu | Responses API domyślnie przechowuje odpowiedzi; PRD wymaga prywatności rozmów. |
| Rezydencja danych | Projekt OpenAI w regionie EU, endpoint `eu.api.openai.com` (env `OPENAI_BASE_URL`), cennik +10% | Prywatne rozmowy zostają w EEA, spójnie z bazą na Railway w EU West; obejmie też przyszłe Realtime API. |

## Scope

**In scope:**
- Pole `practice_language` przy użytkowniku (+ admin).
- Aplikacja `conversations`: modele `Conversation` i `Message` (z tokenami i kosztem), 20 tematów.
- `llm.py` (OpenAI Responses API, wyjście `{reply, end_conversation}`), `budget.py`, `services.py`.
- Ekrany: strona główna, rozmowa, „End”, „Try again”, komunikat o limicie, spinner.
- Wdrożenie: klucz lokalnie i na Railway, limit wydatków w panelu OpenAI, aktualizacja `deploy-plan.md` i `CLAUDE.md`.

**Out of scope:**
- Analiza i lista błędów (S-02), pamięć między rozmowami (S-03), usuwanie konta (S-04).
- Głos, streaming, htmx, historia rozmów, wybór języka w UI, podgląd pozostałego budżetu, tematy w adminie.

## Architecture / Approach

Widoki (POST → redirect → GET) wołają `services.py`, który sprawdza budżet (`budget.py`), wywołuje `llm.generate_turn(...)` i zapisuje wiadomość agenta z kosztem. `llm.py` to jedyny moduł importujący `openai`: buduje instrukcje (scenka, język, poziom B1–B2, zasady recastu i pożegnania) i wywołuje `client.responses.parse(..., text_format=AgentTurn, store=False)`. Testy podmieniają `generate_turn` atrapą, więc nie dotykają sieci. Koszt tury = tokeny z `usage` × cennik z ustawień; „wydane dziś” = suma od ostatniej północy w Europe/Berlin.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Fundament danych i ustawień | Zależności, ustawienia, `practice_language`, modele, migracje, tematy | Błąd w ograniczeniu „1 aktywna rozmowa” albo rejestracja modelu w adminie |
| 2. Moduł LLM i budżet | `llm.py` i `budget.py` z testami jednostkowymi na atrapie | Granice dnia przy zmianie czasu; nazwy parametrów SDK OpenAI (weryfikacja w Context7) |
| 3. Ekrany i przepływ rozmowy | Strona główna, czat, start/wysyłanie/retry/end, spinner, testy widoków i IDOR | Stan „czeka na odpowiedź” po błędzie API; podwójne wysłanie |
| 4. Wdrożenie z prawdziwym modelem | Klucz lokalnie i na Railway, ręczny test jakości po angielsku, deploy | Push przed ustawieniem `OPENAI_API_KEY` wywali produkcję; jakość recastu do dostrojenia promptem |

**Prerequisites:** F-01 zrobione (✓); konto OpenAI z kluczem API i ustawionym limitem wydatków (użytkownik, faza 4).
**Estimated effort:** ~4 sesje, po jednej na fazę.

## Open Risks & Assumptions

- Dostępność `gpt-5.4` w projekcie z regionem EU nie jest jeszcze sprawdzona — weryfikacja na początku fazy 4; w razie braku zmiana `LLM_MODEL` i cennika.
- Nie ma aktualnego porównania modeli w recaście po niemiecku (`research.md`, Open Question 1) — model jest wymienny przez `LLM_MODEL`, ocena jakości po realnym użyciu.
- Ceny i nazwy modeli OpenAI pochodzą ze stanu na 2026-10; cennik w ustawieniach trzeba zaktualizować przy zmianie modelu, inaczej budżet liczy źle (twardy limit w panelu OpenAI to druga linia obrony).
- Jakość recastu i trafność pożegnania zależą od promptu — strojenie po ręcznym teście w fazie 4.
- Szacunek kosztu tury (koszt poprzedniej tury) jest lekko zaniżony, bo historia rośnie z każdą turą — budżet może zostać przekroczony o koszt ok. dwóch tur — świadomie zaakceptowane.
- Wiedza o API OpenAI pochodzi z dokumentacji (Context7), nie z doświadczenia w tym repo — implementacja weryfikuje parametry (`reasoning.effort`, `store`) przed użyciem.

## Success Criteria (Summary)

- Autor przeprowadza po angielsku pełną rozmowę na wybrany temat i widzi naturalnie wplecione poprawki, bez wykładu.
- Rozmowa kończy się poprawnie każdą z trzech dróg (przycisk, potwierdzone pożegnanie, limit) z czytelnym komunikatem.
- Żaden użytkownik nie widzi rozmów innego (404), a koszty nie przekraczają $1/dzień/osobę (± ok. dwie tury).
