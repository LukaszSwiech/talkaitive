---
date: 2026-10-16T12:22:02+02:00
researcher: Claude (Opus 5.5) z LukaszSwiech
git_commit: 146c106
branch: testing-budget-ceiling
repository: 10xDevs4
topic: "test-plan Phase 4 — Budget ceiling (ryzyko #4): dzienny limit $1 trzyma się także przy błędach, ponowieniach i drogich wywołaniach"
tags: [research, testing, conversations, budget, llm, openai-sdk, timezone, dst, e2e, risk-4]
status: complete
last_updated: 2026-10-16
last_updated_by: Claude (Opus 5.5)
---

# Research: Budget ceiling (test-plan Phase 4, ryzyko #4)

**Date**: 2026-10-16T12:22:02+02:00
**Researcher**: Claude (Opus 5.5) z LukaszSwiech
**Git Commit**: 146c106 (drzewo robocze: niezacommitowana zmiana w `context/foundation/test-plan.md` — status §3 Phase 4)
**Branch**: testing-budget-ceiling
**Repository**: 10xDevs4

## Research Question

Ugruntować rollout Phase 4 z `context/foundation/test-plan.md` (§2 ryzyko #4, wytyczna w tabeli Risk Response Guidance, `test-plan.md:60`). Udowodnić, że suma kosztów dnia (tury, analizy, nieudane i ponawiane próby) nie przekracza limitu, że po wyczerpaniu nie da się rozpocząć nowego płatnego wywołania i że reset działa o północy Europe/Berlin, także przy zmianie czasu. Podważyć: (a) „próba ucięta timeoutem nic nie kosztuje”, (b) „istnieje limit długości wiadomości lub odpowiedzi”. Unikać: liczenia oczekiwanego kosztu tym samym wzorem co kod; sztywnych dat bez strefy czasowej. Dodatkowo (test-plan §7, 2026-10-16): ocenić wg cost × signal, czy test w przeglądarce stanu „limit wyczerpany” daje sygnał ponad testy integracyjne.

## Summary

1. **Wymaganie „suma dnia nigdy nie przekracza limitu” nie zgadza się ani z PRD, ani z kodem — plan musi je przeformułować, zanim powstanie test.** PRD przewiduje przekroczenie w trakcie rozmowy: „Gdy limit zostanie przekroczony w trakcie rozmowy, agent komunikuje, że musi zakończyć rozmowę” (`context/foundation/prd.md:115`). Kod sprawdza limit twardo tylko przy starcie rozmowy (`conversations/services.py:108` → `budget.is_exhausted`, `conversations/budget.py:77-97`). Na zbadanych ścieżkach wysłanie wiadomości i „Try again” tury nie odmawiają nigdy z powodu budżetu — tylko wyliczają, czy tura ma być ostatnia (`services.py:182`, `budget.py:100-117`), i ta ostatnia tura jest płatna. Analiza po rozmowie celowo nie ma żadnego sprawdzenia budżetu (`services.py:18-19`, przypięte testem `tests/test_analysis.py:148-169`). Wynika z tego, że wydatek dnia może przekroczyć limit o: (i) różnicę między realnym kosztem ostatniej tury a szacunkiem (koszt poprzedniej tury agenta albo 0,03 USD, `budget.py:112-117`, `talkaitive/settings.py:103`), (ii) koszt analizy każdej zakończonej rozmowy, która jeszcze jej nie miała, (iii) nieudane próby, które w ogóle nie są liczone (pkt 2).
2. **Teza (a) „próba ucięta timeoutem nic nie kosztuje” — w księgowości aplikacji prawdziwa, u dostawcy najpewniej fałszywa.** Na każdej zbadanej ścieżce błędu aplikacja zapisuje koszt 0, bo `usage` jest czytane dopiero po wszystkich sprawdzeniach (`conversations/llm.py:283-294`, `:352-364`):
   - `APIError` (timeout, błąd połączenia, 429/5xx po ponowieniach SDK) → `LLMError` (`llm.py:259-267`, `:335-342`);
   - niezgodność ze schematem (`ValidationError`) → `LLMError` (`llm.py:268-272`, `:343-346`);
   - `output_parsed is None` albo pusty `reply` (odpowiedź HTTP 200 z `usage`) → `LLMError` przed odczytem `usage` (`llm.py:274-282`, `:348-351`);
   - spóźniona tura po zakończeniu rozmowy przez użytkownika (`services.py:179-180`, `:205`), spóźniony wynik analizy (`services.py:332-333`), nieudany zapis analizy po opłaconym wywołaniu (`services.py:357-360`).
   Ponowienia wewnątrz SDK też nie są liczone: tura ma `LLM_MAX_RETRIES = 1`, czyli do 2 żądań HTTP na jedno `generate_turn` (`settings.py:63`), analiza `LLM_ANALYSIS_MAX_RETRIES = 0` (`settings.py:82`); koszt liczy się tylko z `usage` ostatniej, udanej odpowiedzi. Po stronie OpenAI nie znalazłem oficjalnego zdania o rozliczaniu żądania bez streamingu przerwanego przez klienta; odpowiedzi społeczności (2023–2025, sekcja „Zewnętrzne fakty”) mówią, że generowanie biegnie do końca i jest rozliczane. To jest **zaakceptowane ryzyko MVP** (roadmap Q-07, `context/foundation/roadmap.md:162`) — test nie może go „udowodnić jako zabezpieczonego”, bo zabezpieczenia nie ma.
3. **Teza (b) „istnieje limit długości wiadomości lub odpowiedzi” — częściowo.** Jest limit wejścia użytkownika: 2000 znaków na wiadomość (`services.py:47-49`, `:144-147`; także `maxlength` w `conversations/templates/conversations/detail.html:51`). Na zbadanych wywołaniach nie ma: `max_output_tokens` (`llm.py:251-258`, `:327-334`), limitu długości historii ani liczby tur (cała historia idzie w każdej turze, `services.py:183`, i w analizie, `services.py:300`). Koszt jednego wywołania nie ma więc górnej granicy w kodzie; rośnie z długością rozmowy. Wytyczna test-planu (`test-plan.md:60`) mówi wprost: brak limitu to decyzja produktowa, nie test.
4. **Wzór kosztu jest poprawny wobec dokumentacji OpenAI.** `turn_cost` liczy `(input − cached)·input + cached·cached_input + output·output` / 1e6 (`budget.py:25-43`) z cennikiem gpt-5.4 2,50 / 0,25 / 15,00 USD za 1M tokenów (`settings.py:86-92`). Dokumentacja OpenAI: tokeny z cache są wliczone w `input_tokens`, tokeny rozumowania w `output_tokens` i rozliczane jak wyjście (Context7, `developers.openai.com/api/docs/guides/agents-api/observability`, `.../guides/reasoning`). Istniejący test `tests/test_budget.py:80-93` sprawdza literał 0,0034 USD z rachunkiem w komentarzu — zgodnie z antywzorcem nie używa wzoru z kodu.
5. **Granica dnia jest zaimplementowana przez `ZoneInfo("Europe/Berlin")` z parametrem `now`** (`budget.py:46-59`, `settings.py:101`; Django `TIME_ZONE = "UTC"`, `USE_TZ = True`, `settings.py:205`, `:209`). Testy granic sprawdzają `day_start` / `next_reset` literałami UTC także w dniach zmiany czasu 2026-03-29 (23 h) i 2026-10-25 (25 h) (`tests/test_budget.py:120`, `:133`). Brakuje testu `spent_today` / `is_exhausted` z kosztami po obu stronach północy w te dwa dni. Jeden test liczy oczekiwaną chwilę funkcją z kodu: `test_is_exhausted_false_after_midnight_reset` używa `next_reset(NOON)` (`tests/test_budget.py:244-251`) — antywzorzec z wytycznej. Uwaga o zegarach: koszt tury jest datowany przez `Message.created_at` (`auto_now_add`, zegar rzeczywisty, `conversations/models.py:89`), a analizy przez `analyzed_at = now` z parametru (`services.py:339`); testy przesuwają `created_at` przez `.update()` (`tests/test_budget.py:61-62`).
6. **„Try again” nie ma limitu prób; równoległe płatne wywołania są blokowane.** Tura i analiza mają znaczniki „w toku” sprawdzane pod blokadą wiersza (`services.py:148-155`, `:165-171`, `:290-321`); błąd zwalnia znacznik od razu, więc kolejna płatna próba jest możliwa natychmiast (`services.py:198-201`, `:364-371`). Liczba kolejnych prób jest nieograniczona (Q-07). Aktywna może być tylko jedna rozmowa użytkownika (`conversations/models.py:59-65`), więc dwie tury tego samego użytkownika nie biegną równolegle; analiza zakończonej rozmowy i tura nowej rozmowy mogą — ale analiza i tak nie sprawdza budżetu.
7. **E2E dla stanu „limit wyczerpany” — niski sygnał przy średnim koszcie; rekomendacja: nie dodawać testu w przeglądarce w tej fazie albo co najwyżej jeden smoke.** Komunikat jest zwykłym HTML-em renderowanym na serwerze (`conversations/templates/conversations/home.html:29-32` + `_reset_notice.html`; na zakończonej rozmowie `detail.html:62`, `conversations/views.py:76-82`), a JS tylko blokuje przyciski (`accounts/templates/base.html:73-95`), więc klient testowy Django widzi ten sam tekst. Serwer E2E działa bez modelu (`OPENAI_API_KEY: ''` w `playwright.config.ts`), więc ścieżki pieniędzy (ostatnia tura, timeouty, ponowienia) są dla przeglądarki nieosiągalne. Stan „limit wyczerpany” wymagałby osobnego użytkownika, osobnego `storageState`, danych zasianych względem daty w Berlinie (wygasają o północy, a plik `e2e.sqlite3` przeżywa między przebiegami) i sprzątania. Szczegóły w „E2E: cost × signal”.
8. **Pokrycie testami i mutacje.** `tests/test_budget.py` ma 28 testów (zielone, uruchomione raz w tym researchu), wszystkie z literałami. Ostatni przebieg mutmut odczytany z dysku (nieuruchamiany ponownie): 107 mutantów `budget.py`, 3 przeżycia, wszystkie w rejestrze (`scripts/mutation/accepted_survivors.md:47-48`, `:70`). Ręczne mutanty na budżecie: C2, M4, M5 (`scripts/mutation/manual_mutants.py:84-128`). Luki: brak testu kosztu nieudanej / ponowionej próby, brak przepływu „tury + analiza → odmowa startu”, brak testu „Try again” / wysłania po wyczerpaniu, brak testu jednego drogiego wywołania przekraczającego resztę limitu, brak DST dla sumy, brak kosztów w `tests/test_waiting_path.py` (mimo że uruchamia prawdziwe `generate_turn` i cennik).

## Detailed Findings

### 1. Płatne wywołania i zapis kosztu

- Na zbadanych ścieżkach są dokładnie dwa płatne wywołania: `generate_turn` (`llm.py:234-295`) i `analyze_mistakes` (`llm.py:315-365`); `conversations/llm.py` jest jedynym modułem importującym `openai`, a `services.py` jedynym wywołującym te funkcje (grep agenta; tematy i pamięć nie wołają modelu).
- Model w koszcie to `settings.LLM_MODEL`, nie `response.model` (`llm.py:291`, `:361`). Nieznany model wywraca start aplikacji (`settings.py:94-98`) i `turn_cost` (`budget.py:32-37`).
- Tura: `Message(role=ASSISTANT, cost_usd=turn_cost(...))` w jednym bloku atomowym razem z ewentualnym zakończeniem rozmowy (`services.py:203-232`).
- Analiza: `analysis_cost_usd` i `analyzed_at = now` w jednym zapisie pod blokadą (`services.py:329-356`). Rozmowa bez wypowiedzi ucznia dostaje pustą listę i koszt 0 bez wywołania modelu (`services.py:304-319`).
- Suma dnia: `spent_today` = suma `Message.cost_usd` z `created_at >= day_start` + suma `analysis_cost_usd` z `analyzed_at >= day_start`, obie przez `for_user` (`budget.py:62-74`). Koszt analizy liczy się do dnia, w którym analiza się udała, nie do dnia rozmowy.

### 2. Gdzie limit jest sprawdzany

| Wejście | Sprawdzenie | Co się dzieje przy wyczerpaniu | Anchor |
|---|---|---|---|
| Start rozmowy | `is_exhausted`: rozmowa zakończona `DAILY_LIMIT` dziś **albo** `spent + 0,03 >= budżet` | odmowa „You have used today's conversation limit.” bez wywołania | `services.py:108-109`, `budget.py:77-97` |
| Strona główna | `is_exhausted` | komunikat + godzina resetu | `views.py:40`, `home.html:29-32` |
| Wysłanie wiadomości | tylko `is_final_turn`: `spent + koszt ostatniej tury agenta (albo 0,03) >= budżet` | tura **wykonuje się** jako pożegnalna, rozmowa kończy się `DAILY_LIMIT` | `services.py:134-156`, `:182`, `:229-230`, `budget.py:100-117` |
| „Try again” tury | jak wyżej | jak wyżej; każda nieudana próba = 0 USD | `services.py:159-172` |
| Otwarcie rozmowy (pierwsza tura) | `is_final_turn` z szacunkiem 0,03 (brak tury agenta) | jak wyżej | `services.py:130`, `:182` |
| Analiza (auto-submit, przycisk, „Try again”) | brak | analiza wykonuje się zawsze | `services.py:18-19`, `:282-327`, `detail.html:80`, `base.html:92-94` |

Wniosek dla planu: obietnica „po wyczerpaniu nie da się rozpocząć nowego płatnego wywołania” jest prawdziwa tylko dla **startu nowej rozmowy**. W trwającej rozmowie po przekroczeniu zawsze odbywa się jedna płatna tura pożegnalna (oraz jej nieograniczone, nieliczone ponowienia przy błędach), a po niej analiza.

### 3. Ścieżki błędu i ich koszt w aplikacji

| Ścieżka | Żądań HTTP | Zapisany koszt | Anchor |
|---|---|---|---|
| Tura: timeout / 5xx / 429, po ponowieniu SDK | do 2 (`LLM_MAX_RETRIES = 1`) | 0 | `llm.py:259-267`, `settings.py:63` |
| Analiza: timeout / błąd | 1 (`LLM_ANALYSIS_MAX_RETRIES = 0`) | 0, stan „nieudana” | `llm.py:335-342`, `services.py:323-327`, `settings.py:82` |
| Odpowiedź 200, ale `ValidationError` | 1 | 0 | `llm.py:268-272`, `:343-346` |
| Odpowiedź 200, `output_parsed is None` / pusty `reply` | 1 | 0 (`usage` było w odpowiedzi, ale nie zostało odczytane) | `llm.py:274-282`, `:348-351` |
| Tura udana na 2. próbie SDK | 2 | koszt tylko 2. próby | `llm.py:287-295` |
| Tura spóźniona (rozmowa zakończona w trakcie) | 1–2 | 0 („dropped”) | `services.py:179-180`, `:205` |
| Analiza spóźniona (inna próba wygrała) | 1 | 0 („unpaid”) | `services.py:332-333`; test `tests/test_analysis.py:274` |
| Analiza: błąd zapisu po udanym wywołaniu | 1 | 0, stan „nieudana”, „Try again” płaci ponownie | `services.py:357-360` |

Dla `output_parsed is None` / pustego `reply` koszt jest znany w chwili błędu (`response.usage` istnieje), więc policzenie go jest zmianą w kodzie, a nie problemem pomiaru. Dla `ValidationError` obiekt odpowiedzi nie jest dostępny w `except` w obecnym kodzie — nie sprawdzałem, czy SDK go udostępnia.

### 4. Limity na wywołanie

- Wejście użytkownika: `MAX_MESSAGE_LENGTH = 2000` znaków, z komentarzem „keeps one pasted text from eating the daily budget” (`services.py:47-49`, `:144-147`). `Message.text` w bazie nie ma limitu.
- Wyjście: brak `max_output_tokens` w obu `responses.parse` (`llm.py:251-258`, `:327-334`).
- Rozumowanie: tura `effort = "none"`, analiza `"medium"` (`settings.py:61`, `:73-75`); pomiar z S-02: 20 tur, `medium` 52 s / 0,067 USD, `high` 165 s / 0,21 USD (`settings.py:69-72`; `context/archive/2026-10-06-post-conversation-error-list/plan.md:141`).
- Historia i liczba tur: brak limitu (`services.py:183`, `:300`). Koszt tury rośnie z długością rozmowy, więc szacunek „koszt poprzedniej tury” (`budget.py:112-116`) zaniża koszt następnej.
- Czas: tura 30 s / próbę, analiza 150 s (`settings.py:62`, `:81`).

### 5. Granica dnia i strefa czasowa

- `_midnight(now, d)` = `datetime.combine(lokalna_data(now) + d, 00:00, tzinfo=Europe/Berlin)` (`budget.py:46-49`); `day_start` d=0, `next_reset` d=1.
- Testy (`tests/test_budget.py:100-140`) wpisują oczekiwane chwile ręcznie jako UTC: lato, zima, 2026-03-29 (północ = 2026-03-28 23:00 UTC; dzień trwa 23 h), 2026-10-25 (dzień trwa 25 h).
- Nie zbadałem, czy w repo jest freezegun / time-machine — agent nie znalazł ich w `pyproject.toml` ani `uv.lock`; kod przyjmuje `now` jako parametr, więc nie są potrzebne dla serwisów. Widoki używają `timezone.now()` (`views.py`), a `created_at` zegara rzeczywistego.

### 6. Atrapa dostawcy a koszt

- `tests/fake_provider.py`: każde `reply()` / `analysis()` zwraca stały blok `usage` 1200 / 1000 / 40 (`fake_provider.py:24-26`, `:166-172`); `fail()` i `hang()` nie zwracają `usage`. Brak parametru do zmiany tokenów per odpowiedź — test „jedno drogie wywołanie” na granicy SDK wymaga małego rozszerzenia (np. `usage=` w `reply` / `analysis`).
- Atrapy nad SDK (`FakeGenerateTurn`, `FakeAnalyzeMistakes`) dostają tokeny z `TurnResult` / `AnalysisResult` (`tests/test_conversation_views.py:31-40`, `tests/test_analysis.py:41-56`) — tam koszt per wywołanie da się ustawić już dziś.

### 7. E2E: cost × signal

- **Sygnał, którego nie da klient testowy:** praktycznie brak. Komunikat i godzina resetu są w HTML z serwera; jedyna logika po stronie przeglądarki to blokowanie przycisków i auto-submit analizy (`base.html:73-95`), a auto-submit analizy przy wyczerpanym budżecie jest zachowaniem zamierzonym (pkt 2), nie sprawdzianem limitu.
- **Koszt:** brak komendy do zasiania wydatku; jedyna ścieżka to skrypt w stylu `tests/e2e/ensure_e2e_user.py` (uruchamiany przez `manage.py shell`, zabezpieczony na `e2e.sqlite3`). Ustawienie `DAILY_BUDGET_USD=0` w `webServer.env` działa na cały serwer i zepsułoby pozostałe testy (`fullyParallel`, jeden serwer, `reuseExistingServer`). Ścieżka pożegnalnej tury jest niedostępna bez atrapy modelu na serwerze E2E.
- **Rekomendacja:** pokryć stan „limit wyczerpany” testem integracyjnym (klient testowy: strona główna pokazuje komunikat i godzinę resetu, brak przycisku startu, POST startu odmawia bez wywołania modelu — częściowo już jest w `tests/test_conversation_views.py:295`, `:330`). E2E tylko jeśli zespół chce jednego smoke'a per faza — wtedy osobny użytkownik z rozmową zakończoną `DAILY_LIMIT` „dziś” wg Berlina, zasianą skryptem, i asercja `getByText` na komunikat. Decyzja dla `/10x-plan`.

## Code References

- `conversations/budget.py:25-43` — `turn_cost`, wzór kosztu
- `conversations/budget.py:46-59` — granica dnia w `BUDGET_TIME_ZONE`
- `conversations/budget.py:62-74` — `spent_today` (tury + analizy)
- `conversations/budget.py:77-97` — `is_exhausted` (jedyne twarde sprawdzenie, tylko start)
- `conversations/budget.py:100-117` — `is_final_turn` (szacunek = koszt ostatniej tury agenta)
- `conversations/llm.py:251-295` — wywołanie tury, ścieżki błędu przed odczytem `usage`
- `conversations/llm.py:327-365` — wywołanie analizy, jw.
- `conversations/services.py:47-49`, `:144-147` — limit 2000 znaków
- `conversations/services.py:108-109` — odmowa startu po wyczerpaniu
- `conversations/services.py:176-232` — tura: `is_final_turn`, błąd → 0 USD, zapis kosztu, koniec `DAILY_LIMIT`
- `conversations/services.py:282-371` — analiza bez sprawdzenia budżetu, spóźniony wynik „unpaid”, błąd zapisu
- `talkaitive/settings.py:59-103` — model, effort, timeouty, ponowienia, cennik, `DAILY_BUDGET_USD`, `BUDGET_TIME_ZONE`, `LLM_TURN_COST_ESTIMATE_USD`
- `conversations/models.py:89` — `Message.created_at` `auto_now_add`
- `tests/test_budget.py:244-251` — test resetu liczący chwilę przez `next_reset` (antywzorzec)
- `tests/test_analysis.py:148-169` — analiza przy wyczerpanym budżecie (zamierzone)
- `tests/fake_provider.py:24-26`, `:166-172` — stałe `usage` atrapy transportu

## Architecture Insights

- Budżet to **miękki limit z prognozą**, nie twarda blokada: przed startem rezerwuje 0,03 USD, w rozmowie prognozuje następną turę kosztem poprzedniej, a po przekroczeniu kończy rozmowę jedną płatną turą pożegnalną (zgodnie z PRD). Analiza jest poza limitem z decyzji S-02 („no budget is reserved for the analysis”, `context/archive/2026-10-06-post-conversation-error-list/plan.md:45`).
- Twardym zabezpieczeniem kosztów poza kodem jest miesięczny limit / alert na projekcie OpenAI (`context/archive/2026-10-05-first-corrected-conversation/plan.md:299-301`) — nie sprawdzałem, czy jest ustawiony.
- Wszystkie funkcje budżetu i serwisów przyjmują `now`, co pozwala testować granice dnia bez zamrażania zegara — z wyjątkiem `Message.created_at`.

## Historical Context (from prior changes)

- `context/archive/2026-10-05-first-corrected-conversation/plan.md:94-97`, `:183-184` — S-01: ustawienia, `is_exhausted`, `is_final_turn`; **supported** przez obecny kod (`budget.py:77-117`).
- `context/archive/2026-10-05-first-corrected-conversation/plan.md:332`, `:444` — ręczna weryfikacja: `DAILY_BUDGET_USD=0.05`, suma `cost_usd` ≈ panel OpenAI. Historyczna, nie powtarzana.
- `context/archive/2026-10-06-post-conversation-error-list/change.md:15` — „próba ucięta timeoutem nie zwraca `usage`, zapisuje 0, choć OpenAI może naliczyć”; **supported** (`llm.py:259-267`, `:335-342`), z poszerzeniem: także odpowiedzi 200 bez użytecznego wyniku zapisują 0 (`llm.py:274-282`).
- `context/foundation/roadmap.md:162` (Q-07) — „timeout zapisuje koszt 0, »Try again« bez limitu prób — ryzyko zaakceptowane w MVP (2026-10-07)”; **supported** w obu częściach.
- `context/archive/2026-10-15-testing-waiting-path-recovery/research.md:80` — przegrana tura w wyścigu znacznika z `retry-after` jest odrzucana i nieliczona; **supported** (`services.py:205`). Faza 2 przekazała koszt nieudanych / pustych / spóźnionych wywołań do fazy 4 (`.../plan.md:41`).

## Related Research

- `context/archive/2026-10-15-testing-waiting-path-recovery/research.md` — ścieżki timeoutów, ponowienia SDK, `retry-after` do 120 s.
- `context/archive/2026-10-14-testing-suite-trust-and-ci/` — mutacje budżetu (C2, M4, M5) i rejestr przeżyć.

## Zewnętrzne fakty (stan na 2026-10-16)

- Rozliczanie żądania bez streamingu przerwanego przez klienta: brak oficjalnej strony OpenAI. Społeczność: generowanie biegnie do końca i jest rozliczane — https://community.openai.com/t/cancel-the-openai-api-request-without-deducting-the-cost-from-the-balance/719556 (2024-04), https://community.openai.com/t/whats-the-timing-openai-charged/516646 (2023-11), https://community.openai.com/t/does-i-get-charge-for-failed-or-pending-llm-api-requests/1269888 (2025-05; szybkie 429 / przeciążenia nie są rozliczane). Źródła nieformalne, część sprzed Responses API.
- openai-python: domyślnie `max_retries=2`, ponawia timeouty i 408/409/429/5xx (README, https://github.com/openai/openai-python); projekt nadpisuje to na 1 (tura) i 0 (analiza). Każde ponowienie to nowe żądanie — rozliczanie każdego to wniosek z punktu wyżej.
- Responses API przy osiągnięciu `max_output_tokens` zwraca `status: "incomplete"` z `usage` i może naliczyć tokeny wejścia i rozumowania bez widocznej odpowiedzi (https://developers.openai.com/api/docs/guides/reasoning). Wprowadzenie `max_output_tokens` ograniczyłoby koszt wywołania, ale obecny kod zamieniłby taką odpowiedź w `LLMError` z kosztem 0.
- Tokeny z cache wliczone w `input_tokens`, rozumowania w `output_tokens` (Context7: `developers.openai.com/api/docs/guides/agents-api/observability`, `.../guides/token-counting`).

## Open Questions

Decyzje produktowe dla `/10x-plan` (research ich nie rozstrzyga):

1. **Jaki niezmiennik test ma dowodzić zamiast „suma ≤ limit”?** Kandydaci zgodni z PRD i kodem: (a) po wyczerpaniu start nowej rozmowy jest odmawiany bez wywołania modelu; (b) w rozmowie po przekroczeniu odbywa się co najwyżej jedna udana płatna tura (pożegnalna), po której rozmowa jest zakończona `DAILY_LIMIT`; (c) przekroczenie dnia ≤ jedna tura + analizy zakończonych rozmów. Czy przyjmujemy któryś jako wymaganie, czy wymagamy twardego limitu (zmiana kodu)?
2. **Czy ta faza zmienia kod, czy tylko go testuje?** Fazy 2 i 3 naprawiały kod. Kandydaci niskiego ryzyka: liczyć `usage` z odpowiedzi 200 bez użytecznego wyniku (`llm.py:274-282`, `:348-351`); dla timeoutu zapisywać szacunek (np. 0,03 USD albo koszt poprzedniej tury). Bez zmiany kodu test może tylko **przypiąć** obecne zachowanie „nieudana próba = 0” jako znane ograniczenie (Q-07), nie udowodnić ochrony.
3. **`max_output_tokens` i limit prób „Try again”** — wytyczna mówi „decyzja produktowa”; Q-07 wskazuje je jako kierunek po MVP. Utrzymać jako zaakceptowane ryzyko?
4. **E2E** — pominąć w tej fazie (rekomendacja) czy jeden smoke stanu „limit wyczerpany” z zasianymi danymi (sekcja 7)?

Luki w dowodach (nieblokujące):

- Brak oficjalnego potwierdzenia OpenAI dla rozliczania przerwanych żądań bez streamingu.
- Nie sprawdzono, czy miesięczny limit na projekcie OpenAI jest ustawiony.
- Wynik mutmut dla `budget.py` odczytany z pliku meta z 2026-10-16 09:53, nieuruchamiany ponownie.
- Dla `ValidationError` nie sprawdzono, czy SDK udostępnia surową odpowiedź z `usage`.
