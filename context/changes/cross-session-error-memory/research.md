---
date: 2026-10-07T19:24:15+02:00
researcher: Claude (Opus 5.5) dla LukaszSwiech
git_commit: 8b09a3a
branch: main
repository: 10xDevs4 (TalkAItive)
topic: "S-03: pamięć między rozmowami i domykanie pętli błędów (FR-009, FR-010) — co jest w kodzie, gdzie się wpiąć, co trzeba rozstrzygnąć"
tags: [research, codebase, conversations, llm, mistakes, memory, observational-memory, s-03]
status: complete
last_updated: 2026-10-07
last_updated_by: Claude (Opus 5.5)
---

# Research: S-03 — pamięć między rozmowami i domykanie pętli błędów

**Date**: 2026-10-07T19:24:15+02:00
**Researcher**: Claude (Opus 5.5) dla LukaszSwiech
**Git Commit**: 8b09a3a
**Branch**: main
**Repository**: 10xDevs4 (TalkAItive)

## Research Question

Slice S-03 z `context/foundation/roadmap.md:114-124`: użytkownik zaczyna kolejną rozmowę, w której agent (FR-009) uwzględnia wcześniej omawiane wątki pasujące do wybranego tematu i nie powtarza wcześniej zadanych pytań oraz (FR-010) naturalnie stwarza okazje do użycia konstrukcji, w których użytkownik wcześniej się mylił — bez mówienia wprost, że to poprawka (`context/foundation/prd.md:81-84`). Reguła biznesowa: warunek konieczny — błąd pasuje do tematu; pierwszeństwo częstość (błąd w wielu rozmowach), potem świeżość (`prd.md:101-107`).

Pytania badawcze:
1. Co dziś jest zapisane i czego brakuje, żeby zbudować taką pamięć?
2. Gdzie w kodzie pamięć da się odczytać (start rozmowy) i zapisać (po rozmowie)?
3. Jakie ograniczenia narzucają budżet, prompt caching, izolacja danych, usuwanie konta i testy?
4. Co wcześniejsze zmiany (S-01, S-02) już postanowiły albo zostawiły dla S-03?
5. Czym jest Observational Memory (inspiracja z PRD) i co z niej warto wziąć przy tej skali?

## Summary

- **Dziś nie ma żadnej pamięci między rozmowami.** Zapisane są tylko surowe wiadomości (`Message`) i błędy z analizy S-02 (`Mistake`) — bez podsumowania rozmowy, bez listy omówionych wątków i zadanych pytań (`conversations/models.py:8-121`). Prompt rozmowy składa się wyłącznie z instrukcji stałych, języka i sceny oraz historii bieżącej rozmowy (`conversations/llm.py:149-168`).
- **Częstości błędu „w wielu rozmowach” nie da się dziś policzyć sensownie.** `Mistake.occurrences` liczy powtórzenia tylko w obrębie jednej rozmowy (`models.py:113-114`), a scalanie działa tylko na identycznej parze `(wrong, correct)` po normalizacji białych znaków, z zachowaniem wielkości liter (`conversations/services.py:334-365`). S-02 świadomie przekazało „normalizację błędów do zagadnień” do S-03 (`context/archive/2026-10-06-post-conversation-error-list/plan.md:42`, `:47`). S-03 potrzebuje klucza grupującego błędy między rozmowami — to główna decyzja projektowa.
- **„Pasuje do tematu” nie ma oparcia w danych poza kluczem tematu.** `Topic` ma tylko `key`, `title`, `scenario` (`conversations/topics.py:11-15`), bez kategorii czy tagów; `Mistake` nie ma pola tematu — temat jest osiągalny tylko przez `conversation.topic` (`models.py:21`, `:102-104`).
- **Naturalne miejsca wpięcia:** odczyt — `start_conversation` (`services.py:80-108`), z przekazaniem pamięci przez `_generate_and_save` (`services.py:153-173`) do `generate_turn` i `_build_instructions` (`llm.py:149-154`, `:171-177`); zapis — analiza po rozmowie `analyze_conversation` (`services.py:240-315`) i jej schemat `MistakeReport` (`llm.py:105-115`) albo osobne wywołanie po niej.
- **Ograniczenia:** każde nowe wywołanie LLM musi mieć własną kolumnę kosztu doliczaną w `spent_today` (`conversations/budget.py:62-74`); pamięć w prompcie powinna stać po stałym prefiksie i być stała przez całą rozmowę (prompt caching, `llm.py:13-16`); nowy model danych dziedziczy po `UserOwned`, jest czytany przez `for_user` i nie trafia do admina (`accounts/ownership.py:22-30`, `tests/test_ownership.py:47-52`); kasowanie użytkownika usunie go kaskadowo (`ownership.py:22-30`).
- **Observational Memory (Mastra, 2026-02)** zakłada kompresję w trakcie długich wątków (próg 30k tokenów) — przy ~15-minutowych rozmowach się nie uruchomi; sami autorzy oznaczyli współdzieloną pamięć między wątkami (`scope: 'resource'`) jako deprecated. Warto wziąć: obserwacje zapisywane raz po sesji (rola „Observera” już częściowo spełnia analiza S-02), ograniczony rozmiar przez okresowe przepisanie („Reflector” w małej skali), stały blok pamięci na start sesji dla cache'u, oddzielne notowanie pytań agenta od faktów. Wybór błędów do ćwiczenia lepiej zostawić deterministycznemu kodowi nad tabelą `Mistake` niż wolnemu tekstowi.

## Detailed Findings

### 1. Co jest zapisane dziś (model danych)

- `Conversation(UserOwned)` (`conversations/models.py:8-63`):
  - `topic` — `CharField(50)` z kluczem tematu, celowo bez `choices` (`:18-21`); `topic_title` i `topic_scenario` — kopie z chwili startu (`:22-25`).
  - `language` — `en`/`de`, kopiowany z `User.practice_language` przy starcie (`:26-27`, `accounts/models.py:48-62`, `services.py:100`).
  - `status` `active`/`ended` (`:9-11`), `end_reason` `user`/`agent_goodbye`/`daily_limit` (`:13-16`), `created_at`, `ended_at` (`:30-31`).
  - Pola analizy: `analysis_started_at`, `analysis_failed_at`, `analyzed_at`, `analysis_cost_usd` (`:35-43`).
  - Ograniczenie: najwyżej jedna aktywna rozmowa na użytkownika (`:45-52`).
- `Message` (`models.py:66-88`) — nie dziedziczy po `UserOwned`, właściciel przez `conversation` (CASCADE, `:71-73`). Pola: `role` `user`/`assistant`, `text`, `created_at` (z indeksem, `:76`), dla tur agenta model, tokeny i `cost_usd` (`:77-82`). Pytania agenta z poprzednich rozmów istnieją więc tylko jako surowy `text` wiadomości z `role="assistant"`.
- `Mistake(UserOwned)` (`models.py:91-121`): `conversation` (CASCADE, `:102-104`), `position`, `category` `grammar`/`vocabulary`/`word_order` (`:97-100`, `:107`), `wrong`, `correct` (krótkie fragmenty), `sentence`, `explanation` (jedno zdanie po angielsku, `llm.py:83`), `occurrences` (powtórzenia w tej samej rozmowie, `:113-114`), `created_at`. Brak pola tematu, języka i klucza „ten sam błąd w innej rozmowie”.
- W inspected `conversations/` nie ma modelu podsumowania rozmowy ani pól nieużywanych przygotowanych pod S-03; jedyna wzmianka o pamięci w kodzie to docstring `accounts/ownership.py:1-6` (wynik przeszukania przez podagenta: `conversations/*.py`, szablony, `accounts/ownership.py`).
- Migracje: następny numer w `conversations/migrations/` to `0004` (istnieją `0001_initial`, `0002_conversation_agent_turn_started_at`, `0003_conversation_analysis_cost_usd_and_more`).

### 2. Tematy i „pasuje do tematu”

- 20 tematów w `TOPICS` (`conversations/topics.py:18-181`), każdy to `Topic(key, title, scenario)` (`:11-15`); wyszukiwanie po kluczu `get_topic` (`:186-187`). Brak grup, tagów czy słownictwa.
- Lista może się zmieniać bez migracji; stara rozmowa trzyma własną kopię tytułu i sceny (`topics.py:1-5`). Wniosek: klucz tematu ze starej rozmowy może nie istnieć już w `TOPICS` — dopasowanie po kluczu musi to tolerować.
- Dostępne dziś sygnały „pasowania”: (a) równość klucza `conversation.topic`; (b) ocena modelu na podstawie tekstu `scenario`. Nic pośredniego (np. „sklep” ~ „piekarnia”) nie istnieje w danych.
- Wniosek (nie fakt z kodu): tematy to sceny, a błędy dotyczą głównie konstrukcji gramatycznych niezależnych od sceny (np. „bin … gegangen”). Dla FR-009 (wątki) naturalne jest dopasowanie po tym samym kluczu tematu; dla FR-010 (konstrukcje) PRD wymaga tylko, by okazja „naturalnie pasowała do tematu” (`prd.md:83`) — to może oceniać model w trakcie rozmowy, jeśli dostanie krótką listę kandydatów.

### 3. Start rozmowy i budowa promptu (punkt odczytu pamięci)

- Widok `conversation_start` (`conversations/views.py:60-77`) woła `services.start_conversation` (`services.py:80-108`): walidacja tematu (`:86-88`), `is_exhausted` (`:89-90`), utworzenie `Conversation` z kopiami tematu i językiem (`:94-102`), potem synchronicznie, w tym samym żądaniu HTTP, `_generate_and_save` (`:107`).
- `_generate_and_save` (`services.py:153-184`): wysyła całą historię bez przycinania (`:160`), odtwarza `Topic` z kopii w rozmowie (`:161-166`), woła `generate_turn(topic, language, history, final_turn)` poza transakcją (`:167-173`). Ta sama funkcja obsługuje każdą kolejną turę i „Try again”.
- Prompt (`conversations/llm.py`): `_INSTRUCTIONS` — rola, poziom B1–B2, jedna kwestia naraz, recast najwyżej 1–2 błędów bez wykładu, zasady kończenia (`:35-55`); `_build_instructions` = `_INSTRUCTIONS` + `Practice language: …` + `Scene: …` (`:149-154`); `_build_input` — historia jako wiadomości, przy pustej historii wiadomość otwierająca, przy ostatniej turze komunikat `developer` na końcu (`:157-168`).
- API: Responses API `client.responses.parse` ze strukturą `AgentTurn{reply, end_conversation}` (`llm.py:90-92`, `:184-191`), `store=False`. Ustawienia: `LLM_MODEL` domyślnie `gpt-5.4`, `LLM_REASONING_EFFORT` domyślnie `none`, timeout 30 s, 1 ponowienie (`talkaitive/settings.py:59-63`).
- Wniosek: pamięć można policzyć w `start_conversation` po `is_exhausted` i zapisać jako snapshot na `Conversation` (analogicznie do `topic_scenario`), a `_generate_and_save` przekaże ją do `generate_turn` jako nowy argument. Snapshot daje ten sam prompt w każdej turze i przy „Try again”, nawet jeśli w międzyczasie zakończy się analiza poprzedniej rozmowy.

### 4. Koniec rozmowy i analiza S-02 (punkt zapisu pamięci)

- Sposoby zakończenia: przycisk (`views.py:138-142` → `end_conversation`, `services.py:211-218`), pożegnanie agenta lub limit dzienny w `_save_agent_turn` (`services.py:205-208`).
- Rozmowa porzucona bez „Zakończ” zostaje `active` bez końca: strona główna pokazuje „Continue conversation”, a constraint blokuje nową rozmowę (`models.py:45-52`; raport podagenta: `home.html:8-9`). To rozbieżność z opisem w PRD, który mówi, że taka sesja „przepada” (`prd.md:74`) — w kodzie jej nie traci się, tylko czeka na dokończenie.
- Analiza: strona zakończonej rozmowy sama wysyła formularz (raport podagenta: `detail.html:78-83`) do `conversation_analyze` (`views.py:145-156`) → `analyze_conversation` (`services.py:240-315`), synchronicznie w żądaniu HTTP. Zablokowane sprawdzenie stanu (`:248-279`), wywołanie `analyze_mistakes` poza transakcją (`:281-285`), zapis błędów, `analyzed_at` i kosztu pod blokadą (`:287-310`), przy błędzie `analysis_failed_at` i „Try again” (`:318-325`). Rozmowa bez wypowiedzi ucznia dostaje pustą listę bez wywołania modelu (`:262-277`).
- `analyze_mistakes`: instrukcje `_ANALYSIS_INSTRUCTIONS` (`llm.py:65-87`) + język; wejście — jeden tekst z numerowanymi wypowiedziami ucznia; wyjście `MistakeReport{mistakes: [FoundMistake{message_number, category, wrong, correct, sentence, explanation}]}` (`llm.py:105-115`). Wysiłek `medium` (zmierzone ok. 52 s na rozmowie z 20 turami), timeout 150 s, 0 ponowień (`settings.py:64-75`). Prompt analizy nie zna tematu ani wcześniejszych błędów.
- `analyzed_at` = `now` żądania, które zleciło analizę (`services.py:295`), nie chwila jej zakończenia — zaakceptowane w S-02 (`context/archive/2026-10-06-post-conversation-error-list/reviews/impl-review.md:56-64`, wg raportu podagenta). Dla świeżości lepszym kandydatem jest `Conversation.ended_at`.
- Rozmowa zakończona, której strona nie została otwarta, może na zawsze zostać z `analyzed_at IS NULL` — S-02 zapisało wprost, że „S-03 musi to obsłużyć” (`context/archive/2026-10-06-post-conversation-error-list/plan.md:44`).
- Wniosek: zapis pamięci można (a) dołożyć do schematu i instrukcji analizy oraz do bloku zapisu `services.py:287-310`, (b) zrobić osobnym wywołaniem po analizie, albo (c) liczyć bez LLM przy starcie następnej rozmowy z istniejących `Mistake` i `Message`.

### 5. Budżet i koszt dodatkowych wywołań

- `turn_cost(model, input, cached, output)` liczy koszt z `LLM_PRICES_USD_PER_MTOK` (`conversations/budget.py:25-43`). Ceny `gpt-5.4`: input 2,50, cached input 0,25, output 15,00 USD za 1M tokenów (`settings.py:79-85`).
- `spent_today` sumuje wyłącznie `Message.cost_usd` z dzisiejszych wiadomości i `Conversation.analysis_cost_usd` rozmów z `analyzed_at` od północy (`budget.py:62-74`). Nie ma ogólnej tabeli kosztów — nowe wywołanie LLM (np. kompresja pamięci) wymaga własnej kolumny kosztu z datą i dopisania jej do `spent_today`; inaczej nie wejdzie do limitu $1.
- Nieudane wywołania (timeout, błąd API, błąd walidacji) nie mają zapisanego kosztu (`llm.py` zamienia je na `LLMError` bez usage; `services.py:174-177`, `:281-285`) — to znane, zaakceptowane ryzyko Q-07 (`roadmap.md:162`).
- Analiza działa niezależnie od pozostałego budżetu (`services.py:13-14`). Nowe wywołanie musi mieć jawnie wybraną regułę: tak samo, czy wstrzymanie przy wyczerpanym limicie.
- Pamięć w prompcie zwiększa input każdej tury. Przykład ilustracyjny (założenie: blok pamięci 500 tokenów, 10 tur agenta, wszystkie bez cache): 5 000 dodatkowych tokenów × 2,50 USD/1M = 0,0125 USD na rozmowę; przy trafieniu w cache te tokeny kosztują 0,25 USD/1M, czyli 10× mniej. `LLM_TURN_COST_ESTIMATE_USD = 0.03` służy tylko wtedy, gdy rozmowa nie ma jeszcze tury agenta (`settings.py:95-96`); w S-01 zaakceptowano, że przy rosnącej historii ostatnia tura może przekroczyć budżet o ok. dwie tury (`context/archive/2026-10-05-first-corrected-conversation/plan-brief.md:75`, wg raportu podagenta). Większy prompt to ryzyko powiększa.

### 6. Prompt caching

- Kod jest ułożony pod automatyczny cache prefiksu OpenAI: stałe instrukcje, potem język i scena; zmienny komunikat ostatniej tury jako osobna wiadomość na końcu (`llm.py:13-16`, `:166-167`). Testy pilnują stabilnego prefiksu (`tests/test_llm.py:125`, `:366`, wg raportu podagenta).
- OpenAI cache'uje automatycznie prompty od 1024 tokenów i liczy tylko dokładne dopasowanie prefiksu (https://platform.openai.com/docs/guides/prompt-caching, odczyt podagenta 2026-10-07).
- Wniosek: blok pamięci powinien stać po `Scene:` (albo jako osobna wiadomość na początku `input`) i nie zmieniać się w trakcie rozmowy. Wtedy w obrębie jednej rozmowy każda tura dalej trafia w cache poprzedniej, a wspólny dla wszystkich rozmów prefiks `_INSTRUCTIONS` zostaje nienaruszony.

### 7. Izolacja, usuwanie konta, admin

- `UserOwned`: pole `user` (FK, `on_delete=CASCADE`, `related_name="+"`) i `for_user()`, który dla niezalogowanego zwraca pusty wynik (`accounts/ownership.py:15-30`). Reguły w `context/foundation/lessons.md:54-66`: dane per użytkownik tylko przez `for_user`, pojedynczy rekord przez zawężony queryset, test „B dostaje 404 na obiekt A”.
- Serwisy już filtrują przez `for_user` także wewnętrznie (`services.py:45-51`, `:215`). Zapytanie o wcześniejsze błędy musi iść przez `Mistake.objects.for_user(user)` i filtrować po języku rozmowy.
- Nowy model pamięci dziedziczący po `UserOwned` zostanie skasowany kaskadowo z użytkownikiem; jeśli dostanie FK do rozmowy-źródła, `on_delete` trzeba wybrać świadomie. W kodzie nic dziś nie kasuje użytkowników poza adminem Django (raport podagenta). S-04 ma wracać do każdego nowego modelu danych (`roadmap.md:135`).
- `tests/test_ownership.py:47-52` pilnuje, że w adminie są tylko `User` i `Group` — modelu pamięci nie wolno rejestrować.

### 8. Wzorce testów do ponownego użycia

- Brak `conftest.py`; każdy moduł ma własne fixture'y. Fałszywy klient SDK: `FakeResponses`/`make_response`/`fake_openai` (`tests/test_llm.py:25-63`). Fałszywe funkcje serwisowe z kolejką wyników i zapisem `kwargs`: `FakeAnalyzeMistakes` (`tests/test_analysis.py:53-79`), `FakeGenerateTurn` (`tests/test_conversation_views.py:36-62`), podpinane przez `monkeypatch.setattr(services, ...)`. Ustawienia przypięte w fixture'ach autouse z modelem `"test-model"` (`test_analysis.py:82-95`, `test_conversation_views.py:98-108`). Testy izolacji: `tests/test_ownership.py:21-52`, `tests/test_conversations.py:37`, `:72-104`, `:125`, 404 dla cudzej rozmowy `tests/test_conversation_views.py:553-571` (anchory wg raportu podagenta).
- Wniosek: nowa funkcja LLM (jeśli powstanie) potrzebuje własnego `FakeX` i fixture'u autouse w testach widoków, bo komentarz w testach wymaga, żeby żaden test nie wychodził do sieci.

### 9. Observational Memory i inne wzorce pamięci (źródła zewnętrzne)

Fakty (źródła pierwotne Mastra: blog https://mastra.ai/blog/observational-memory i https://mastra.ai/research/observational-memory z 2026-02-09, dokumentacja https://mastra.ai/docs/memory/observational-memory oraz https://mastra.ai/reference/memory/observational-memory, odczyt 2026-10-07):
- Dwa agenty w tle: **Observer** zamienia surowe wiadomości w „obserwacje” po przekroczeniu `messageTokens` (domyślnie 30 000 tokenów), **Reflector** przepisuje cały log po przekroczeniu 40 000 tokenów (scala, usuwa nieaktualne). Log to tekst: listy punktowane pogrupowane po datach, priorytety 🔴/🟡/🟢. Obserwacje idą do wiadomości systemowej na początku kontekstu; log tylko rośnie przez dopisywanie, więc prefiks jest stabilny i cache'owalny.
- Według aktualnej strony referencyjnej `scope: 'resource'` (jeden log dla wszystkich wątków użytkownika) jest deprecated — autorzy zalecają dla pamięci między wątkami narzędzie `recall` albo „working memory” (mały uporządkowany profil).
- Wyniki benchmarków (LongMemEval) pochodzą tylko od Mastra i mierzą przypominanie faktów, nie pedagogikę.

Inne wzorce:
- **Notatki po sesji dopisywane do promptu następnej sesji** — Duolingo Video Call (https://blog.duolingo.com/ai-and-video-call/, 2025-04-22): po rozmowie LLM wyciąga fakty o użytkowniku do „List of Facts”, która trafia do instrukcji następnej rozmowy. Ryzyko: utrwalenie błędnego faktu („context poisoning”, OpenAI cookbook https://developers.openai.com/cookbook/examples/agents_sdk/session_memory).
- **Profil + skonsolidowane notatki wstrzykiwane na start** — OpenAI cookbook „Context Engineering for Personalization” (https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization, 2026-01-05): notatki z sesji → konsolidacja na końcu sesji (deduplikacja, nowsze wygrywa) → wstrzyknięcie na początku z regułą pierwszeństwa bieżącej wiadomości.
- **mem0** (https://arxiv.org/abs/2504.19413, 2025-04-28): ekstrakcja faktów po każdej parze wiadomości + baza wektorowa + operacje ADD/UPDATE/DELETE. Kilka wywołań na sesję i dodatkowy magazyn do czyszczenia przy usuwaniu konta.

Wnioski (inferencja podagenta i moja, nie fakty ze źródeł):
- Rozmowa ~15 min to rząd kilku tysięcy tokenów, więc kompresja w trakcie sesji (Observer na progu 30k) nie ma zastosowania.
- Pasuje: jedna „obserwacja” po sesji (S-02 już pełni część roli Observera — dokumenty projektu nazywają tak analizę: `context/foundation/shape-notes.md:215-218`, wg raportu podagenta), ograniczony rozmiar pamięci przez okresowe przepisanie (mały „Reflector”), stały blok pamięci budowany raz na start, osobne notowanie pytań agenta (pod FR-009).
- mem0 / baza wektorowa / narzędzie `recall` — przesadne dla 2 użytkowników i 20 tematów.
- Badania nad recastami (szybki przegląd, niepełny): częstsza ekspozycja na recast pomaga przyswojeniu (SSLLT, 2024-07-11, https://pressto.amu.edu.pl/index.php/ssllt/article/view/30085). Nie znaleziono solidnego źródła o powtórkach rozłożonych w czasie zastosowanych do wzorców błędów w rozmowie.

## Code References

- `conversations/models.py:8-63` — `Conversation`: temat (klucz + kopie), język, status, powody końca, pola analizy, jedna aktywna rozmowa.
- `conversations/models.py:66-88` — `Message`: surowe wypowiedzi, tokeny i koszt tur agenta.
- `conversations/models.py:91-121` — `Mistake`: kategoria, `wrong`/`correct`, `sentence`, `explanation`, `occurrences` w obrębie rozmowy; brak tematu i klucza grupującego.
- `conversations/topics.py:11-15`, `:18-181`, `:186-187` — definicja i lista 20 tematów, `get_topic`.
- `conversations/services.py:80-108` — `start_conversation` (miejsce odczytu pamięci i ewentualnego snapshotu).
- `conversations/services.py:153-184` — `_generate_and_save` (przekazanie pamięci do każdej tury).
- `conversations/services.py:240-315` — `analyze_conversation` (miejsce zapisu pamięci po rozmowie).
- `conversations/services.py:334-365` — `_normalize`, `_merge_mistakes`: scalanie tylko identycznych par w jednej rozmowie.
- `conversations/llm.py:13-16` — zasada prompt cachingu.
- `conversations/llm.py:35-55`, `:149-168` — instrukcje rozmowy, `_build_instructions`, `_build_input`.
- `conversations/llm.py:65-87`, `:105-115` — instrukcje i schemat analizy błędów.
- `conversations/budget.py:25-43`, `:62-74` — `turn_cost`, `spent_today` (tylko koszty tur i analiz).
- `accounts/ownership.py:15-30` — `UserOwned`, `for_user`, CASCADE.
- `accounts/models.py:48-62` — `PracticeLanguage` (`en`, `de`) i `User.practice_language`.
- `tests/test_ownership.py:47-52` — strażnik rejestru admina.

## Architecture Insights

- **Jedno miejsce kontaktu z OpenAI** (`conversations/llm.py:1-11`): każda nowa funkcja LLM pamięci powinna tam trafić, zwracać zwykły dataclass i rzucać `LLMError`; serwisy wołają ją poza transakcją i zapisują wynik pod blokadą wiersza (wzorzec `services.py:1-16`).
- **Snapshot w rozmowie** to już przyjęty wzorzec (`topic_title`, `topic_scenario`, `language` kopiowane przy starcie, `models.py:22-27`). Ten sam wzorzec pasuje do bloku pamięci: stabilny prompt przez całą rozmowę i „Try again”, zgodność z cache.
- **Koszt żyje na wierszach**, nie w osobnej księdze — każdy nowy płatny krok dokłada kolumnę i sumę w `spent_today`.
- **Język jako wymiar danych:** produkt ma dwa języki ćwiczeń (`accounts/models.py:48-50`), mimo że PRD mówi „tylko niemiecki” (`prd.md:127`). Autor ćwiczy `en`, żona `de` (`context/archive/2026-10-05-first-corrected-conversation/plan.md:29`, wg raportu podagenta). Pamięć musi być filtrowana po `conversation.language`, inaczej błędy z angielskiego trafią do rozmowy po niemiecku (wniosek).
- **Wszystkie wywołania LLM są synchroniczne w żądaniu HTTP** (Q-07, `roadmap.md:162`). Dodatkowe wywołanie przy starcie wydłuża otwarcie rozmowy; dodatkowe po rozmowie wydłuża ekran „Show my mistakes” albo wymaga osobnego kroku.

## Historical Context (from prior changes)

- `context/archive/2026-10-06-post-conversation-error-list/plan.md:42` — pamięć, wybór błędów i normalizacja do „zagadnień” wprost przekazane do S-03 (zweryfikowane).
- `context/archive/2026-10-06-post-conversation-error-list/plan.md:44` — rozmowy z `analyzed_at IS NULL` po zakończeniu: „S-03 musi to obsłużyć” (zweryfikowane).
- `context/archive/2026-10-06-post-conversation-error-list/plan.md:47` — S-02 nie scala „prawie identycznych” błędów ani błędów z tą samą regułą (zweryfikowane).
- `context/archive/2026-10-06-post-conversation-error-list/plan.md:75`, `plan-brief.md:24` — błędy zapisane jako pojedyncze pary, „łatwo liczyć w S-03” (wg raportu podagenta). Częściowo aktualne: liczyć łatwo w obrębie rozmowy; między rozmowami brak klucza.
- `context/archive/2026-10-06-post-conversation-error-list/reviews/impl-review.md:56-64` — `analyzed_at` to czas zlecenia analizy; recenzent sugeruje inną wartość, „jeśli S-03 potrzebuje prawdziwego czasu zakończenia” (wg raportu podagenta; potwierdzone kodem `services.py:295`).
- `context/archive/2026-10-05-first-corrected-conversation/plan.md:64`, `:196` — kolejność promptu pod cache; `store=False`, więc pamięć musi pochodzić z Postgresa (wg raportu podagenta; potwierdzone kodem `llm.py:13-16`).
- `context/foundation/shape-notes.md:84`, `:215-218` — zamysł OM w projekcie: wnioski z sesji zapisywane „po kompresji (nie surowy zapis rozmowy)”; skrócona lista błędów wstrzykiwana do promptu następnej lekcji z instrukcją, by subtelnie stworzyć okazje bez wspominania o poprawce (wg raportu podagenta). Żaden dokument nie projektuje pamięci wątków i pytań (FR-009).
- `context/foundation/prd.md:117`, `:123`, `roadmap.md:169-171` — użytkownik nie widzi ani nie edytuje pamięci; FR-011 (opanowanie po N użyciach) i statystyki są po MVP.

## Related Research

- `context/archive/2026-10-05-first-corrected-conversation/research.md` — wybór modelu/dostawcy LLM; m.in. pamięć z Postgresa w kodzie Django, nie na platformie agentowej.

## Open Questions

Decyzje do rozstrzygnięcia w `/10x-plan` (fakty powyżej, wybór należy do użytkownika):

1. **Klucz „ten sam błąd” między rozmowami** (warunek dla częstości z `prd.md:107`). Opcje: (a) dokładna para `(wrong, correct)` — deterministyczne, ale rzadko się powtórzy między rozmowami; (b) model w analizie S-02 dodaje etykietę konstrukcji (np. „Perfekt z sein przy czasownikach ruchu”) i dostaje listę dotychczasowych etykiet użytkownika, żeby ich używać; (c) osobny krok konsolidacji (mały „Reflector”) przepisujący listę zagadnień użytkownika.
2. **Co znaczy „pasuje do tematu”**: dla wątków i pytań (FR-009) — ten sam klucz tematu? Dla konstrukcji (FR-010) — preselekcja w kodzie (top N po częstości/świeżości, bez filtra tematu) i ocena „czy naturalnie pasuje” zostawiona modelowi w trakcie rozmowy, czy filtr tematu już przy zapisie/wyborze?
3. **Skąd „wcześniej zadane pytania”**: surowe wypowiedzi agenta z ostatnich N rozmów na tym samym temacie (bez LLM, ale więcej tokenów) czy skompresowane notatki o wątkach i pytaniach tworzone po rozmowie (dodatkowe pola w analizie albo osobne wywołanie)?
4. **Rozmowy bez analizy** (`analyzed_at IS NULL`, `plan.md:44` S-02): uruchamiać ich analizę przy starcie kolejnej rozmowy (koszt i czas w żądaniu startu), pomijać, czy korzystać tylko z danych bez LLM?
5. **Rozmiar i koszt pamięci**: ile błędów i pytań w bloku pamięci (limit tokenów), czy nowe wywołanie LLM wlicza się do `spent_today` i czy działa przy wyczerpanym limicie (jak analiza, `services.py:13-14`)?
6. **Świeżość**: `Conversation.ended_at` czy `analyzed_at` (czas zlecenia, nie zakończenia analizy)?
7. **Język**: potwierdzić, że pamięć jest rozdzielona per `conversation.language` (wniosek z sekcji Architecture Insights).
8. **Rozbieżność PRD ↔ kod przy porzuconej rozmowie**: PRD mówi, że sesja bez „Zakończ” przepada (`prd.md:74`), kod zostawia ją aktywną do dokończenia. Nie blokuje S-03 (taka rozmowa po prostu jeszcze nie zasila pamięci), ale warto to uwzględnić w opisie zachowania.
