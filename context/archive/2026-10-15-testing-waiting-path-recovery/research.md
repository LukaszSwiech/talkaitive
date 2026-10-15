---
date: 2026-10-15T14:12:34+02:00
researcher: Claude (Opus 5.5) z LukaszSwiech
git_commit: d175cc6
branch: main
repository: 10xDevs4
topic: "test-plan Phase 2 — Waiting-path recovery (ryzyko #1): zawieszenie, błąd albo pusty wynik dostawcy kończy się komunikatem i działającym „Try again”"
tags: [research, testing, conversations, llm, openai-sdk, timeouts, retry, risk-1]
status: complete
last_updated: 2026-10-15
last_updated_by: Claude (Opus 5.5)
---

# Research: Waiting-path recovery (test-plan Phase 2, ryzyko #1)

**Date**: 2026-10-15T14:12:34+02:00
**Researcher**: Claude (Opus 5.5) z LukaszSwiech
**Git Commit**: d175cc6 (drzewo robocze: niezacommitowana zmiana w `context/foundation/test-plan.md` — status §3 Phase 2)
**Branch**: main
**Repository**: 10xDevs4

## Research Question

Ugruntować rollout Phase 2 z `context/foundation/test-plan.md`. Ryzyko #1: gdy dostawca wisi, zwraca błąd albo pusty wynik, użytkownik w skończonym czasie widzi komunikat i „Try again”, ponowienie naprawdę uruchamia nowe wywołanie, a znacznik „w toku” wygasa. Podważyć: (a) „atrapa, która od razu rzuca wyjątek, odpowiada prawdziwemu zawieszeniu”, (b) „status 200 po ponowieniu = sukces”, (c) „incydent z wywiadu Q2 jest już pokryty testami”. Unikać: tylko happy path, asercji na samym kodzie HTTP, atrap podmieniających wewnętrzną logikę zamiast granicy SDK.

## Summary

1. **Wieczne czekanie nie jest osiągalne przy obecnych ustawieniach na zbadanych ścieżkach** (przy założeniu z §3, że limit odczytu httpx ≈ czas próby, bo odpowiedź bez streamingu nie wysyła danych przed końcem). Na tych ścieżkach czekanie ma górną granicę: tura agenta ≤ ok. 60,5 s bez nagłówka `retry-after` i ≤ ok. 180 s z nim; analiza ≤ ok. 150 s (bez ponowień). Znaczniki „w toku” wygasają po 90 s (tura) i 180 s (analiza). Proxy Railway zamyka żądanie dopiero po 5 min bez danych, a gunicorn `gthread` nie ucina długich żądań — oba twierdzenia z komentarza w `talkaitive/settings.py:71-73` potwierdzone w dokumentacji. Ryzyko #1 pozostaje realne jako **ryzyko regresji** (zmiana ustawień albo kodu) i jako dwa nowe, konkretne problemy z punktów 4–5.
2. **Teza (a) — częściowo prawdziwa.** Na granicy `generate_turn` / `analyze_mistakes` prawdziwe zawieszenie kończy się tak samo jak natychmiastowy wyjątek: SDK zamienia timeout na `APITimeoutError` (podklasa `APIError`), a `llm.py` na `LLMError`. Atrapa z natychmiastowym wyjątkiem gubi jednak **wymiar czasu** (co widzą inne żądania w trakcie czekania i co się dzieje, gdy znacznik wygaśnie przed końcem wywołania) oraz **pętlę ponowień SDK** — obecne atrapy (`FakeOpenAI` w `tests/test_llm.py:54-65`, `FakeGenerateTurn` / `FakeAnalyzeMistakes` w `tests/test_conversation_views.py:37-98`, `tests/test_analysis.py:84-88`) całkowicie ją omijają; żaden test nie uruchamia kodu ponowień/timeoutów SDK.
3. **Teza (b) — prawdziwa pułapka, obecne testy jej unikają.** Widoki POST rozmowy zwracają 302 przy sukcesie, odmowie (`ConversationError`) i `LLMError` (`conversations/views.py:54-150`; inny wyjątek daje 500), a GET strony rozmowy zwraca właścicielowi 200 w stanach sukces, porażka i „typing” (`views.py:74-103`). Kod HTTP nie niesie żadnej informacji o sukcesie. Istniejące testy ponowienia sprawdzają stan bazy, liczbę wywołań atrapy i treść strony (`tests/test_conversation_views.py:396-414`, `tests/test_analysis.py:352-376`).
4. **Nowe znalezisko — wyścig znacznika tury z nagłówkiem `retry-after`.** SDK respektuje `retry-after` / `retry-after-ms` do 120 s (`openai/_base_client.py:861-872`, `openai/_constants.py:13`), a `services._agent_turn_timeout` zakłada, że SDK czeka najwyżej `timeout × liczba prób` (`conversations/services.py:69-73`). Gdy pierwsza próba tury dostanie 429/5xx z `retry-after` > ok. 30–60 s, znacznik wygasa w trakcie żywego wywołania: odświeżona strona pokazuje „The agent could not reply” + „Try again”, a kliknięcie uruchamia drugie płatne wywołanie (wynik przegranego jest odrzucany i niewliczany do budżetu — `services.py:199-203`). Nie wiemy, czy OpenAI wysyła taki nagłówek (otwarte pytanie). Analiza nie jest dotknięta (`LLM_ANALYSIS_MAX_RETRIES = 0`).
5. **Nowe znalezisko — pusta odpowiedź `reply=""` jest traktowana jak sukces.** `AgentTurn.reply: str` (`conversations/llm.py:104-106`) akceptuje pusty tekst; tura zapisuje się jako pusta bańka, bez komunikatu i bez „Try again” (`services.py:207-224`). Wytyczna ryzyka #1 („pusty wynik → komunikat i Try again”) i kod się rozjeżdżają — to decyzja produktowa, nie test do napisania na ślepo.
6. **Teza (c) — nie: testy pokrywają mechanikę, nie przyczynę.** Incydent Q2 (potwierdzony przez użytkownika: lokalnie przy S-02) miał przyczynę w ustawieniach: effort `high` + limit 90 s przy analizie trwającej ok. 165 s, więc każda próba — także każde „Try again” — deterministycznie padała na timeoucie. Naprawiono to ustawieniami w `dfe3e7d` (`medium`, 150 s). Testy sprawdzają „porażka → stan nieudany → ponowienie → nowe wywołanie”, ale żaden test z atrapą nie wykryje „limit krótszy niż realny czas modelu”.
7. **Najtańsza warstwa z sygnałem:** integracja z klientem testowym Django i prawdziwą bazą (SQLite w testach) + atrapa na **transporcie HTTP SDK** (`httpx2.MockTransport` wstrzyknięty przez `OpenAI(http_client=...)`), tak żeby wykonała się prawdziwa pętla timeoutów i ponowień SDK oraz mapowanie wyjątków w `llm.py`. Upływ czasu symulować jak dotąd — starszym znacznikiem w bazie albo parametrem `now` serwisów. Do tego testy hermetyczne serwisu dla wyścigów (wzorzec już istnieje dla analizy).
8. **Fazie 2 przekazano z fazy 1 sześć przeżywających mutantów** (`scripts/mutation/accepted_survivors.md:47-52`): `_agent_turn_timeout` `_mutmut_2`, `_3`, `_5`, `_6`, `_7` i `_clear_turn_marker` `_mutmut_4`. Obecny test wygaśnięcia znacznika tury sprawdza tylko 0 s i 2 min (`tests/test_conversation_views.py:557-581`), więc zmiana granicy o dziesiątki sekund przeżywa.

## Detailed Findings

### 1. Ścieżka tury agenta (start, wiadomość, „Try again”)

- Przebieg: widok POST → serwis pod blokadą wiersza ustawia `agent_turn_started_at = now` → `generate_turn` **poza transakcją** → zapis odpowiedzi pod blokadą tylko, jeśli rozmowa dalej czeka → czyszczenie własnego znacznika → redirect (`conversations/services.py:130-204`, `conversations/views.py:54-129`).
- Porażka: dowolny wyjątek z `generate_turn` czyści znacznik od razu i leci dalej (`services.py:194-197`); widoki łapią `LLMError` i przekierowują na stronę, która w stanie „czeka na agenta, nic nie trwa” pokazuje „The agent could not reply. Please try again.” + „Try again” (`views.py:115-116`, `views.py:127-128`, `conversations/templates/conversations/detail.html:35-46`). Wiadomość użytkownika zostaje zapisana (`services.py:150`).
- Mapowanie błędów w granicy LLM (`conversations/llm.py:250-281`): `APIError` → `LLMError` (komentarz `llm.py:260` — klasa bazowa timeoutu, połączenia, limitu i błędów statusu); `pydantic.ValidationError` (ucięty / zły JSON) → `LLMError`; `output_parsed is None` (odmowa albo pusta odpowiedź) → `LLMError`; `usage is None` → `LLMError`.
- Hierarchia potwierdzona w zainstalowanym SDK (openai 3.24.0): `APITimeoutError(APIConnectionError)`, `APIConnectionError(APIError)`, `RateLimitError` / `InternalServerError` ⊂ `APIStatusError` ⊂ `APIError` (`.venv/.../openai/_exceptions.py:46-161`). `LengthFinishReasonError` i `ContentFilterFinishReasonError` dziedziczą tylko po `OpenAIError` (`_exceptions.py:165,182`), ale parser Responses API ich nie rzuca — w `lib/_parsing/_responses.py` jedyne `raise` to `TypeError` dla nieobsługiwanego `text_format` (`:164`, `:168`; błąd konfiguracji, deterministyczny).
- Wyjątek inny niż `LLMError` (np. `TypeError` powyżej) daje odpowiedź 500, ale znacznik jest już wyczyszczony (`services.py:194-197`), więc po odświeżeniu strona pokazuje „Try again”. Na zbadanych ścieżkach to mało prawdopodobne (wniosek, nietestowane).
- „Try again” (`run_agent_turn`, `services.py:155-169`): odmawia, gdy nic nie czeka (`:163-164`) albo gdy znacznik jest ważny (`:165-166`); inaczej ustawia nowy znacznik i robi **nowe** wywołanie `generate_turn`. Pamięć z początku rozmowy jest ta sama (`memory_prompt`, `services.py:192`).
- Pusta odpowiedź: `AgentTurn(reply: str, end_conversation: bool)` (`llm.py:104-106`) nie wymaga niepustego tekstu; `reply=""` przechodzi walidację, `_save_agent_turn` zapisuje pustą wiadomość i nalicza koszt (`services.py:207-224`), `awaiting_agent_reply` staje się `False` (`conversations/models.py:70-76`), więc strona pokazuje pole „Your message” zamiast komunikatu i „Try again”. Brak testu tego przypadku (wyszukane w `tests/test_llm.py`, `tests/test_conversation_views.py`).

### 2. Ścieżka analizy błędów (lista błędów po rozmowie)

- Strona zakończonej, nieprzeanalizowanej rozmowy bez ważnego znacznika i bez porażki ma formularz `data-auto-submit`; JS wysyła go raz przy zwykłym załadowaniu strony (`detail.html:78-83`, `accounts/templates/base.html:90-95`). Po porażce formularz nie ma `data-auto-submit` — „Try again” wymaga kliknięcia (`detail.html:72-77`), więc nie ma pętli automatycznych ponowień (test: `tests/test_conversation_views.py:833-847`).
- `analyze_conversation` (`services.py:260-339`): pod blokadą odmowa dla aktywnej / przeanalizowanej / trwającej; ustawienie `analysis_started_at`; `analyze_mistakes` poza transakcją; porażka → `_mark_analysis_failed` (czyści własny znacznik; `analysis_failed_at` ustawia tylko, gdy żadne nowsze żądanie nie przejęło wygasłego znacznika — `services.py:342-349`); błąd zapisu po udanym wywołaniu także oznacza porażkę (`services.py:335-338`).
- Stany strony (`detail.html:64-84`): przeanalizowana → lista; znacznik ważny → spinner + `<meta http-equiv="refresh" content="5">` (`detail.html:9`); porażka → komunikat + „Try again”; inaczej → auto-wysyłka.
- Proces ubity w trakcie analizy (np. deploy): znacznik zostaje, `analysis_failed_at` nie jest ustawiane; strona pokazuje spinner do wygaśnięcia znacznika (180 s), potem formularz z auto-wysyłką, który uruchamia nowe wywołanie (wniosek z `detail.html:64-84` i `services.py:247-250`). Test serwisu na wygasły znacznik istnieje (`tests/test_analysis.py:254-269`); testu **strony** po wygaśnięciu znacznika analizy (czy pokazuje auto-wysyłkę, a nie spinner) nie znaleziono.

### 3. Ścieżka timeoutów — obliczenia na obecnych ustawieniach

Ustawienia: `LLM_TIMEOUT_SECONDS = 30`, `LLM_MAX_RETRIES = 1` (`talkaitive/settings.py:62-63`); `LLM_ANALYSIS_TIMEOUT_SECONDS = 150`, `LLM_ANALYSIS_MAX_RETRIES = 0` (`settings.py:74-75`). `settings_test.py` ich nie nadpisuje (cały plik: `talkaitive/settings_test.py:1-16`); `tests/test_analysis.py:95-96` nadpisuje analizę na 90 s / 0 ponowień.

Zachowanie SDK (kod w `.venv/.../openai/_base_client.py`, `_constants.py`; dokumentacja Context7 `/openai/openai-python` README „Timeouts”, „Retries”):
- ponawiane są: błędy połączenia i timeouty, 408, 409, 429, ≥ 500 (`_base_client.py:907-922`; README „Retries”);
- odstęp między próbami: `0,5 s × 2^n`, maks. 8 s, minus 0–25% jittera (`_constants.py:11-12`, `_base_client.py:874-884`) — dla pierwszego ponowienia 0,375–0,5 s;
- **nagłówek `retry-after-ms` / `retry-after` z serwera wygrywa, jeśli 0 < wartość ≤ 120 s** (`_base_client.py:822`, `:869-872`, `MAX_RETRY_AFTER_DELAY = 2 * 60` w `_constants.py:13`); README tego nie opisuje;
- liczba `timeout=30` przechodzi do httpx2 bez zmian (`openai/_httpx2.py:75-76`); według semantyki httpx (dokumentacja httpx, niesprawdzone w źródle httpx2) to ten sam limit dla połączenia, zapisu, puli i **każdego odczytu** — nie łączny limit czasu. Przy odpowiedzi bez streamingu serwer nic nie wysyła do końca generowania, więc w praktyce limit odczytu ≈ czas próby (wniosek).

| Ścieżka | Najgorsze czekanie żądania POST | Wygaśnięcie znacznika | Sufit Railway |
|---|---|---|---|
| Tura, timeout × 2 próby, bez `retry-after` | 30 + 0,5 + 30 ≈ 60,5 s | 30 × 2 + 30 = 90 s (`services.py:69-73`) | 300 s bez danych |
| Tura, 1. próba 429/5xx z `retry-after` = X ≤ 120 s | (czas 1. próby ≤ 30) + X + 30 ≤ 180 s | 90 s — **krótsze niż czekanie, gdy 1. próba + X > 60 s** | 300 s |
| Analiza, 1 próba | ≈ 150 s | 150 × 1 + 30 = 180 s (`services.py:241-244`) | 300 s |

- gunicorn: `--workers 2 --threads 4 --timeout 120` (`context/deployment/web-settings.json:7`). Dokumentacja (Context7 `/benoitc/gunicorn`, settings „timeout”): dla workerów innych niż `sync` timeout dotyczy komunikacji procesu z arbitrem, a nie długości jednego żądania; `gthread` nie ogranicza czasu wykonania żądania. Potwierdza komentarz `settings.py:71-73`.
- Railway (docs.railway.com/networking/public-networking/specs-and-limits, odczyt 2026-10-15): żądanie HTTP może trwać do 15 min, jeśli dane płyną; inaczej zamykane po 5 min bez przesyłu danych. Uwaga historyczna: w marcu 2026 limit był czasowo obniżony do 3 min i przywrócony (commit `4511db5` w `railwayapp/docs`) — limit platformy bywa zmieniany.
- Wniosek: przy obecnych ustawieniach oba czekania mieszczą się pod sufitem proxy. Gdyby ktoś podniósł timeout analizy powyżej ok. 300 s albo tury tak, że `timeout × próby + retry-after` przekroczy 300 s, proxy utnie żądanie przed SDK: przeglądarka dostanie błąd Railway zamiast strony z „Try again”, a wątek gunicorna dalej czeka na model (wniosek; nie testowano).
- Pojemność: 2 × 4 = 8 równoczesnych żądań; każde czekające POST trzyma wątek do 60–180 s, a strony z `meta refresh` co 5 s zajmują wątki na krótko. Przy ≤ 10 użytkownikach (test-plan §7) wyczerpanie jest spekulatywne; test-plan świadomie wyklucza testy obciążenia.

### 4. Wyścig znacznika tury z `retry-after` (nowe znalezisko)

- Komentarz `services.py:70-71` („Longer than the SDK can wait (timeout x attempts)”) nie uwzględnia `retry-after` do 120 s. Warunek wyścigu: czas 1. próby + X + czas 2. próby > 90 s, np. szybkie 429 i X > 60 s albo 5xx po ok. 30 s i X > 30 s.
- Skutek (wniosek z `services.py:155-204` i `detail.html:25-46`): zakładka, która wysłała POST, dalej pokazuje spinner JS; odświeżenie albo druga zakładka pokazuje „The agent could not reply” + „Try again”; kliknięcie uruchamia drugie płatne wywołanie; pierwsza odpowiedź, która dojdzie, jest zapisywana, druga odrzucana pod blokadą (`services.py:199-203`) i niewliczana do budżetu (styk z ryzykiem #4). `_clear_turn_marker` starszego żądania nie czyści znacznika nowszego dzięki filtrowi `agent_turn_started_at=started_at` (`services.py:88-92`) — to dokładnie scenariusz przeżywającego `_clear_turn_marker__mutmut_4` (`accepted_survivors.md:52`).
- Czekanie nadal jest skończone (≤ 180 s), więc to nie jest „wieczne czekanie”, tylko niespójny stan i podwójny koszt.
- Nie wiadomo, czy API OpenAI wysyła `retry-after` przy 429/5xx (dokumentacja SDK mówi tylko, że SDK go respektuje). Bez tej wiedzy test „znacznik trwa dłużej niż czekanie SDK z `retry-after`” **padnie na obecnym kodzie** — to decyzja dla planu (patrz Open Questions), nie test do dopisania na ślepo.

### 5. Istniejące testy — co jest pokryte

| Zachowanie | Test | Warstwa / atrapa | Uwagi |
|---|---|---|---|
| Błędy SDK (timeout, połączenie, 429, 500) → `LLMError` | `tests/test_llm.py:307-323` | podmieniony cały klient `OpenAI` (`:54-65`) | pętla ponowień SDK nie wykonuje się; wyjątek rzucany z `parse` |
| Pusty `output_parsed`, brak `usage`, zły JSON → `LLMError` (tura i analiza) | `test_llm.py:326-374`, `:544-575` | jw. | `reply=""` nietestowane |
| Klient dostaje timeout i ponowienia z ustawień | `test_llm.py:80-95`, `:413-430` | jw. | sprawdza argumenty konstruktora, nie zachowanie |
| `LLMError` przy wiadomości → zostaje wiadomość, strona ma „Try again”; ponowienie → nowa odpowiedź, brak „Try again” | `tests/test_conversation_views.py:396-414` | `FakeGenerateTurn` zamiast `services.generate_turn` (`:37-63`) | asercje na bazie, treści i liczbie wywołań — nie na kodzie HTTP |
| `LLMError` przy starcie → rozmowa czeka na ponowienie | `test_conversation_views.py:418-449` | jw. | |
| Znacznik ważny → „typing” + refresh, ponowienie odrzucone; znacznik sprzed 2 min → „Try again” | `test_conversation_views.py:550-581` | jw. + ręczny znacznik w bazie | granice tylko 0 s i 120 s → przeżywają `_agent_turn_timeout` `_2/_3/_5/_6/_7` |
| Równoległe ponowienie w trakcie wywołania nie robi drugiego wywołania (wiadomość, start, retry) | `test_conversation_views.py:584-648` | jw. | |
| Analiza: porażka → stan nieudany → ponowienie się udaje | `tests/test_analysis.py:352-376` | `FakeAnalyzeMistakes` zamiast `services.analyze_mistakes` (`:84-88`) | warstwa serwisu |
| Analiza: wygasły znacznik pozwala ruszyć; ważny odmawia | `test_analysis.py:200-269` | jw.; `ANALYSIS_TIMEOUT` = 120 s wpisane ręcznie (`:106-107`) | wzorzec oczekiwanej wartości spoza kodu |
| Analiza: porażka nie nadpisuje nowszej próby / zakończonej | `test_analysis.py:408-449` | jw. | wzorzec do skopiowania dla tury (`_clear_turn_marker__mutmut_4`) |
| Strony analizy: auto-wysyłka, spinner, porażka bez auto-wysyłki, redirect po porażce | `test_conversation_views.py:800-974` | widoki z atrapą | brak: strona po **wygaśnięciu** znacznika analizy; brak: ponowienie analizy przez widok kończące się listą |

Wniosek: ścieżka „błąd → komunikat → Try again → nowe wywołanie” jest pokryta przy atrapach wyżej niż SDK. Niepokryte: zachowanie samego SDK (ponowienia, timeout), granice wygaśnięcia znacznika, wyścig znacznika z żywym wywołaniem dla tury, `reply=""`, strona po wygaśnięciu znacznika analizy, ponowienie analizy przez widok.

### 6. Werdykty dla tez do podważenia

- **(a) „Atrapa z natychmiastowym wyjątkiem = prawdziwe zawieszenie”** — *częściowo*. Stan końcowy jest ten sam (SDK zamienia timeout na `APITimeoutError` po `timeout × (max_retries + 1)` + odstęp; README „Timeouts”, `_base_client` w snippecie Context7). Atrapa gubi: (1) okno czasowe, w którym znacznik jest ustawiony, a inne żądania widzą „typing” albo — po wygaśnięciu — „Try again”; (2) pętlę ponowień SDK i jej czas (2 próby przy `LLM_MAX_RETRIES = 1`); (3) wpływ `retry-after`. Atrapa na transporcie (`httpx2.MockTransport`, sprawdzone: `httpx2 2.13.1`, `MockTransport` dostępny; `OpenAI(http_client=...)` w `openai/_client.py:182`) rzucająca `httpx2.ReadTimeout` uruchamia prawdziwą pętlę SDK bez prawdziwego czekania, jeśli podmieni się uśpienie między próbami (wniosek; do sprawdzenia w planie, jak SDK usypia — `_sleep_for_retry`).
- **(b) „Status 200 po ponowieniu = sukces”** — *pułapka potwierdzona*. POST daje 302 przy sukcesie, odmowie i `LLMError` (`views.py:1-5`, `:54-150`), GET strony właściciela daje 200 w każdym z tych stanów. Sukces trzeba udowodnić: nowa wiadomość agenta w bazie, `awaiting_agent_reply == False`, znacznik `None`, wzrost liczby wywołań na granicy SDK, tekst odpowiedzi na stronie i brak „Try again” (dla analizy: `analyzed_at`, `analysis_failed_at is None`, pozycje listy na stronie).
- **(c) „Incydent Q2 jest już pokryty testami”** — *nie*. Przyczyna potwierdzona przez użytkownika (2026-10-15): lokalnie przy S-02; `a01675b` wprowadził `LLM_ANALYSIS_REASONING_EFFORT = "high"`, `LLM_ANALYSIS_TIMEOUT_SECONDS = 90`, `LLM_ANALYSIS_MAX_RETRIES = 0`; pomiar z `context/archive/2026-10-06-post-conversation-error-list/change.md:14` — `high` 164,8 s; `dfe3e7d` zmienił na `medium` / 150 s. Każde „Try again” uruchamiało nowe wywołanie (mechanika działała), ale wywołanie znowu przekraczało 90 s. Testy z atrapą pokrywają mechanikę (`test_analysis.py:352-376`), nie relację „limit vs realny czas modelu”. Tę relację chroni dziś tylko ręczny pomiar zapisany w archiwum.

## Code References

- `conversations/llm.py:149-157` — `_get_client(timeout, max_retries)`; jedyne miejsce tworzenia klienta (punkt wstrzyknięcia `http_client`)
- `conversations/llm.py:104-106` — `AgentTurn.reply: str` (pusty tekst przechodzi)
- `conversations/llm.py:250-281` — mapowanie błędów tury na `LLMError`
- `conversations/llm.py:322-350` — to samo dla analizy
- `conversations/services.py:69-79` — `_agent_turn_timeout`, `agent_turn_in_progress` (90 s; komentarz zakłada brak `retry-after`)
- `conversations/services.py:88-92` — `_clear_turn_marker` tylko własnego znacznika
- `conversations/services.py:155-204` — `run_agent_turn`, `_generate_and_save` (czyszczenie znacznika przy wyjątku, odrzucenie spóźnionej odpowiedzi)
- `conversations/services.py:241-250` — `_analysis_timeout`, `analysis_in_progress` (180 s)
- `conversations/services.py:260-349` — `analyze_conversation`, `_mark_analysis_failed`
- `conversations/views.py:106-150` — widoki POST, zawsze redirect; łapią tylko `ConversationError` / `LLMError`
- `conversations/templates/conversations/detail.html:5-10` — `meta refresh` co 5 s tylko przy ważnym znaczniku
- `conversations/templates/conversations/detail.html:25-84` — stany strony: typing / „Try again” / formularz; stany analizy
- `accounts/templates/base.html:54-99` — JS: spinner przy wysyłce, blokada podwójnej wysyłki, auto-wysyłka analizy
- `talkaitive/settings.py:62-75` — timeouty i ponowienia (30 s × 2; 150 s × 1) z uzasadnieniem
- `context/deployment/web-settings.json:7` — gunicorn `--workers 2 --threads 4 --timeout 120`
- `.venv/lib/python3.14/site-packages/openai/_base_client.py:812-884`, `:885-922` — `retry-after`, odstęp, które statusy ponawiane
- `.venv/lib/python3.14/site-packages/openai/_constants.py:7-13` — `DEFAULT_TIMEOUT`, `INITIAL_RETRY_DELAY = 0.5`, `MAX_RETRY_DELAY = 8.0`, `MAX_RETRY_AFTER_DELAY = 120`
- `tests/test_llm.py:27-65` — `FakeResponses` / `FakeOpenAI` (zastępuje cały klient)
- `tests/test_conversation_views.py:37-98` — `FakeGenerateTurn`, `FakeAnalyzeMistakes`
- `scripts/mutation/accepted_survivors.md:32`, `:47-52` — mutanty przekazane do Phase 2 (i warunek powrotu `_analysis_timeout__mutmut_6`)

## Architecture Insights

- Wszystko jest synchroniczne: POST trzyma wątek gunicorna przez całe wywołanie modelu; spinner w czasie POST rysuje JS (`base.html:65-71`), a znacznik w bazie służy tylko innym żądaniom (odświeżenie, druga zakładka, proces ubity w trakcie). Testy klientem Django widzą stany renderowane przez serwer; spinner JS w trakcie POST jest poza ich zasięgiem — zgodnie z test-plan §7 (bez Playwright). W zbadanych ścieżkach nie znaleziono awarii widocznej tylko w JS.
- Wzorzec „znacznik z wygasaniem + blokada wiersza + wywołanie poza transakcją + zapis pod blokadą z ponownym sprawdzeniem” jest wspólny dla tury i analizy (`services.py:1-24`); różnią się: analiza ma jawny stan porażki (`analysis_failed_at`), tura wnioskuje porażkę z „czeka na agenta, nic nie trwa”.
- Serwisy przyjmują `now` jako parametr — czas da się symulować bez biblioteki do zamrażania zegara (żadnej nie ma w `pyproject.toml` / `uv.lock`); widoki biorą `timezone.now()`, więc testy widoków symulują czas starszym znacznikiem w bazie (`test_conversation_views.py:574-577`).
- Oczekiwane granice czasu w testach analizy są wpisane ręcznie z komentarzem pochodzenia (`tests/test_analysis.py:106-107`) — dobry wzorzec; wyrocznią dla granicy tury powinien być najgorszy czas czekania SDK wyliczony z dokumentacji / stałych SDK, nie formuła z `services.py`.

## Historical Context (from prior changes)

- `context/archive/2026-10-06-post-conversation-error-list/change.md:14` — pomiar `high` 164,8 s vs limit 90 s; decyzja `medium` / 150 s (znacznik 180 s). *Supported* (zgodne z `dfe3e7d` i `settings.py:68-75`).
- `context/archive/2026-10-06-post-conversation-error-list/change.md:15` — próba ucięta timeoutem zapisuje koszt 0. *Supported* dla analizy (`services.py:301-305` nie zapisuje kosztu); dotyczy ryzyka #4, nie tej fazy.
- `context/archive/2026-10-06-post-conversation-error-list/plan.md:61` — „gunicorn gthread nie ucina, sufitem jest proxy Railway 5 min bez danych”. *Supported* (Context7 gunicorn; docs Railway 2026-10-15).
- `context/archive/2026-10-06-post-conversation-error-list/plan.md:364` — 2 workery × 4 wątki wystarczą przy 2 użytkownikach. *Partial*: test-plan §7 mówi dziś o max 10 użytkownikach; brak pomiaru.
- `context/foundation/roadmap.md:162` (Q-07) — analiza poza żądaniem HTTP i limit prób „Try again” jako zaakceptowane ryzyko MVP. Nadal otwarte; usunęłoby synchroniczne czekanie, ale to zmiana produktu, nie tej fazy testów.
- `context/archive/2026-10-14-testing-suite-trust-and-ci/research.md:60` — M7 (znacznik analizy nigdy nieustawiany) przeżywał; zabity w fazie 1 testem `tests/test_analysis.py:219-250`.
- Commity `7f8d62c` i `52c9c48` (2026-10-07) — poprawki z przeglądu: porażka nie nadpisuje nowszej próby; błąd zapisu pokazuje „Try again”. Mają testy (`test_analysis.py:408-480`).

## Related Research

- `context/archive/2026-10-14-testing-suite-trust-and-ci/research.md` — wyniki mutacji (M1–M9), z których pochodzą mutanty przekazane do tej fazy.
- `context/archive/2026-10-05-first-corrected-conversation/research.md` — wybór dostawcy i dostępność OpenAI (bez danych o `retry-after`).

## Open Questions

1. **Wyścig `retry-after` (tura):** zaakceptować (rzadkie / nieznane), zmienić kod (np. znacznik uwzględnia `MAX_RETRY_AFTER_DELAY`, albo `LLM_MAX_RETRIES = 0` i poleganie na „Try again”), czy tylko udokumentować? Od tego zależy, czy test „znacznik trwa dłużej niż czekanie SDK” ma uwzględniać `retry-after`. Brakujący fakt: czy OpenAI wysyła `retry-after` przy 429/5xx.
2. **`reply=""`:** czy pusta odpowiedź agenta ma być porażką (komunikat + „Try again”, bez zapisu i kosztu), jak mówi wytyczna ryzyka #1? Decyzja produktowa przed testem.
3. **Górna granica czekania:** PRD (`prd.md:96`) wymaga informacji zwrotnej przez cały czas czekania, ale nie podaje maksimum. Bez maksimum mutanty wydłużające znacznik (`_agent_turn_timeout__mutmut_3` +1 próba → 120 s, `_mutmut_7` +1 s) nie mają wyroczni — kandydaci do `accepted_survivors.md` jako `brak wymagania` / `równoważny`, chyba że użytkownik poda limit.
4. **Przyczyna incydentu Q2** (limit krótszy niż realny czas modelu) nie jest testowalna atrapą. Kandydaci: niezmiennik ustawień (`timeout × próby` < 300 s Railway — chroni przed ucięciem przez proxy, nie przed za krótkim limitem), pomiar czasu analizy w evalu Phase 5, albo wpis w test-plan §7. Do decyzji w planie i backportu do test-plan.
5. **Uśpienie między próbami SDK w teście transportowym:** jak deterministycznie podmienić `_sleep_for_retry` / uśpienie bez wiązania testu z prywatnym API SDK — do sprawdzenia przy planowaniu fazy z atrapą transportu.

### Kandydaci do backportu w test-plan (dla `/10x-test-plan`, nie zmieniane tutaj)

- §2 ryzyko #1, Source: dopisać, że incydent Q2 został naprawiony ustawieniami 2026-10-07 (`dfe3e7d`); likelihood „High” opiera się częściowo na naprawionym zdarzeniu.
- §2 Risk Response Guidance #1, Context: dopisać `retry-after` SDK (do 120 s) jako składnik ścieżki timeoutów; „pusty wynik” rozbić na `output_parsed is None` (obsłużone) i `reply=""` (nieobsłużone).
- §4 Stack, „granica LLM”: atrapy w repo są dziś na kliencie `OpenAI` i nad SDK, nie na transporcie; `httpx2.MockTransport` jako narzędzie granicy SDK.
