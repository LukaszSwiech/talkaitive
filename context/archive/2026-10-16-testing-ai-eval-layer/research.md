---
date: 2026-10-16T22:39:32+02:00
researcher: Claude (Opus 5.5) z LukaszSwiech
git_commit: 2978faf
branch: testing-ai-eval-layer
repository: 10xDevs4
topic: "test-plan Phase 5 — AI eval layer (ryzyko #5): zmiana promptu albo modelu po cichu pogarsza korektę, listę błędów i pamięć"
tags: [research, testing, conversations, llm, openai-sdk, eval, golden-dataset, llm-as-judge, memory, risk-5]
status: complete
last_updated: 2026-10-17
last_updated_by: Claude (Opus 5.5)
last_updated_note: "Backport poprawek §2 do test-planu; §4 i rejestr mutantów zostają dla planu"
---

# Research: AI eval layer (test-plan Phase 5, ryzyko #5)

**Date**: 2026-10-16T22:39:32+02:00
**Researcher**: Claude (Opus 5.5) z LukaszSwiech
**Git Commit**: 2978faf (drzewo robocze: niezacommitowana zmiana w `context/foundation/test-plan.md` — status §3 Phase 5)
**Branch**: testing-ai-eval-layer
**Repository**: 10xDevs4

## Research Question

Ugruntować rollout Phase 5 z `context/foundation/test-plan.md` (§2 ryzyko #5, `test-plan.md:48`; wytyczna w tabeli Risk Response Guidance, `test-plan.md:61`). Udowodnić, że na stałym zestawie niemieckich wypowiedzi ze znanymi błędami (gramatyka / słownictwo / szyk) analiza znajduje te błędy, nie zgłasza literówek i trzyma kategorie; że odpowiedź agenta wplata poprawną formę bez wykładu; że porównanie dwóch wersji promptu lub modelu daje liczbę, nie wrażenie. Podważyć: (a) „atrapa modelu w obecnych testach mówi coś o jakości”, (b) „sędzia LLM bez wzorcowych odpowiedzi jest wiarygodny”. Unikać: evalu na każdym commicie, asercji na dokładny tekst odpowiedzi, zestawu danych wygenerowanego przez oceniany model. Dodatkowo: ustalić kształt wejścia i wyjścia trzech ścieżek (tura, analiza, blok pamięci), rozdzielić twarde niezmienniki od wyników jakościowych, oszacować koszt jednego przebiegu wobec logiki dziennego budżetu, sprawdzić, jak eval zostaje poza CI i poza domyślnym `uv run pytest`, znaleźć istniejące testy, wskazać najtańszą użyteczną warstwę i oznaczyć części spekulatywne (np. „pamięć powtarza pytania”) oraz mylące dowody hot-spot.

## Summary

1. **Teza (a) jest fałszywa: obecne testy nic nie mówią o jakości.** Na zbadanych plikach `tests/` żaden test nie woła prawdziwego modelu (`settings_test.py:15-16` ustawia `OPENAI_API_KEY = "test-key"`, więc przypadkowe prawdziwe wywołanie kończy się 401). Trzy mechanizmy atrap — `fake_openai` (`tests/test_llm.py:55-66`), atrapa transportu `fake_provider` (`tests/fake_provider.py:85-113`) i `FakeGenerateTurn` / `FakeAnalyzeMistakes` (`tests/fakes.py:23-56`) — zwracają dokładnie to, co test zakolejkował. Asercje związane z jakością kończą się na „prompt zawiera napis X” (`tests/test_llm.py:138-139`, `:199-204`, `:482`). `grep -i "typo|recast|lecture"` po `tests/*.py`: 0 trafień.
2. **Ścieżki wywołań są dwie i obie da się wywołać bez bazy danych.** `llm.generate_turn(topic, language, history, final_turn, memory)` → `TurnResult(reply, end_conversation, model, tokeny)` (`conversations/llm.py:284-354`) i `llm.analyze_mistakes(language, history)` → `AnalysisResult(mistakes, learner_facts, scene_notes, model, tokeny)` (`llm.py:374-432`). Blok pamięci to czysty tekst z `format_memory(Memory)` (`llm.py:217-256`), liczony raz na start rozmowy (`services.py:137-139`). Precedens: review S-03 uruchomił 32 tury prawdziwym `generate_turn` „bez zapisu do bazy, koszt 0,117 USD” (`context/archive/2026-10-07-cross-session-error-memory/reviews/impl-review.md:48`).
3. **„Trzyma kategorie” to w połowie twardy niezmiennik, który już jest zagwarantowany.** Zbiór etykiet `grammar` / `vocabulary` / `word_order` wymusza schemat (`llm.py:121`, `Literal[...]`): wartość spoza zbioru daje `ValidationError` → `LLMError` (`llm.py:406-411`). Eval nie musi tego mierzyć. Mierzyć trzeba **trafność** kategorii względem wzorca (czy błąd szyku dostał `word_order`) — to wynik jakościowy.
4. **Twarde niezmienniki vs wyniki jakościowe** (pełna tabela w §4):
   - już zagwarantowane kodem i pokryte zwykłymi testami: schemat odpowiedzi, zbiór kategorii, pusta odpowiedź = błąd, scalanie identycznych par, format bloku pamięci;
   - twarde per przypadek (oczekiwane 0 naruszeń, liczone deterministycznie z wzorca): nic z wiadomości partnera, `sentence` bez zmian, podłożona literówka nie na liście, zdanie poprawne bez pozycji, ≤ 5 faktów i ≤ 8 notatek, `end_conversation = false` w środku rozmowy;
   - wyniki jakościowe (liczby porównywane między wersjami): recall błędów ze wzorca, fałszywe pozycje, trafność kategorii, odsetek odpowiedzi z poprawną formą, odsetek odpowiedzi ze znacznikami wykładu, opcjonalnie naturalność i powtarzanie pytań (sędzia z wzorcem).
5. **„Pamięć powtarza pytania” nie jest spekulacją jako wymaganie, ale jest najsłabiej mierzalną częścią.** To wymaganie must-have: FR-009 „agent … nie powtarza pytań” (`prd.md:81`), US-01 (`prd.md:54`), problem z `prd.md:22`. Mechanizm istnieje: analiza zapisuje pytania partnera w `scene_notes` (`llm.py:95-97`), a blok pamięci każe „do not ask again questions that were already asked” (`llm.py:239-241`). Weryfikacja była tylko ręczna, bez zapisanego dowodu (S-03 `plan.md:336`: punkt odhaczony samym SHA `34437b6`). Wytyczna #5 w test-planie (`test-plan.md:61`) i `change.md:14` w ogóle nie wymieniają pamięci — niespójność planu.
6. **Dzienny limit $1 nie dotyczy evalu i go nie chroni.** `spent_today` sumuje tylko wiersze `Message`, `Conversation.analysis_cost_usd` i `LLMCharge` (`budget.py:64-81`). Eval wołający `llm.*` wprost nie tworzy żadnego wiersza, więc żaden limit go nie ogranicza i nie zużywa budżetu żadnego użytkownika. Eval potrzebuje własnego limitu wydatku. Szacunek jednego przebiegu (§6): górna granica ok. 3,1 USD dla 12 transkryptów analizy i 20 przypadków tury, każdy ×3 (ok. 3,4 USD z opcjonalną serią pamięci i sędzią); realny koszt krótkich transkryptów nie był mierzony.
7. **Szum jest zmierzony, nie hipotetyczny.** Ta sama 20-turowa rozmowa z `medium` dała 12 pozycji w pomiarze i 18 pozycji w aplikacji (`context/archive/2026-10-06-post-conversation-error-list/change.md:14`). Responses API nie ma `seed`, a `temperature` działa tylko przy effort `none` (dokumentacja OpenAI, §Zewnętrzne fakty). Porównanie wersji musi więc być: K powtórzeń na przypadek, różnica sparowana per przypadek z błędem standardowym, lista przypadków, które zmieniły wynik.
8. **Teza (b) jest słaba w świetle źródeł; sędzia nie jest potrzebny w pierwszej wersji.** Sędzia z wzorcem myli się rzadziej niż bez niego (Zheng i in. 2023: 14/20 → 3/20 błędów oceny na zadaniach matematycznych), a model faworyzuje własne odpowiedzi (Panickssery i in. 2024). Projekt ma tylko klucz OpenAI (`settings.py:49-54`), więc sędzia z innej rodziny modeli to nowy dostawca i nowy sekret. Większość właściwości z p. 4 da się policzyć deterministycznie z wzorca; sędzia zostaje opcją dla naturalności i powtarzania pytań, z wzorcem i z kalibracją na ocenach użytkownika.
9. **Eval zostaje poza CI, jeśli leży poza `tests/`.** CI uruchamia `uv run pytest` (`.github/workflows/ci.yml:30`), a pytest zbiera tylko `testpaths = ["tests"]` i `python_files = ["test_*.py"]` (`pyproject.toml:33-37`); nie ma `addopts` ani markerów, więc marker `@pytest.mark.eval` w `tests/` niczego by nie wyłączył. Skrypt w `scripts/eval/` (precedens: `scripts/mutation/manual_mutants.py`) nie jest zbierany ani przez CI, ani przez mutacje (`manual_mutants.py:58` też polega na `testpaths`). DeepEval odpada jako dev-dependency: rejestruje własną wtyczkę `pytest11`, która ładowałaby się do każdego `uv run pytest`, także w CI, i ma domyślnie włączoną telemetrię.
10. **Najtańsza użyteczna warstwa:** lokalny skrypt na prawdziwym modelu, który woła `llm.generate_turn` / `llm.analyze_mistakes` na ręcznie opisanym zestawie (wzorzec ze źródłem), liczy metryki deterministycznie, zapisuje wynik przebiegu do pliku i porównuje dwa przebiegi. Sam kod oceniania (dopasowanie, metryki, porównanie) jest deterministyczny, więc dostaje zwykłe testy w `tests/` (CI, bez klucza) z potwierdzeniem mutacją wg §6.1.
11. **Dowód hot-spot jest mylący dla #5.** Wiersz ryzyka #5 nie cytuje hot-spotu (`test-plan.md:48`); przekazany w poleceniu `conversations/ (30 zmian plików/30 dni)` to dowód dla #1 i #3. Ze wszystkich 8 commitów zmieniających `llm.py` / `memory.py` tylko 4 zmieniły tekst promptu i każdy z nich go tworzył lub rozszerzał przy budowie funkcji (2026-10-06/07); żaden nie był strojeniem. Lepszy dowód prawdopodobieństwa jest w archiwum: zmiana samego `reasoning effort` analizy (`high`) zaczęła zgłaszać literówki (`settings.py:69-72`, S-02 `change.md:14`).
12. **Przeżyty mutant odłożony do tej fazy nie pasuje do evalu.** `memory._mistakes__mutmut_47` (wyjaśnienie → `None`, w bloku pamięci „: None”) ma w rejestrze przekierowanie „ryzyko #5 (eval, test-plan Phase 5)” (`scripts/mutation/accepted_survivors.md:79`). Eval nie zabija mutantów (nie jest częścią przebiegu mutmut), a wpływ „: None” na model jest niemierzalny przy tym szumie. To decyzja dla zwykłego testu jednostkowego albo pozostawienia jako `brak wymagania` z poprawionym wskaźnikiem.

## Detailed Findings

### 1. Ścieżki wywołań modelu i kształt wejścia / wyjścia

**Tura agenta** (`conversations/llm.py:284-354`):

- Wejście: `topic: Topic` (scena), `language: str` (`"de"` / `"en"`, `accounts/models.py:48-50`), `history: Sequence[(role, text)]` od najstarszej, `final_turn: bool`, `memory: str` (blok pamięci albo `""`).
- Prompt: `instructions` = stałe `_INSTRUCTIONS` + `Practice language: …` + `Scene: …` + opcjonalny blok pamięci (`llm.py:259-267`). `input` = historia jako wiadomości `user` / `assistant`; pusta historia → jedna wiadomość `_OPENING_MESSAGE` „Open the scene: speak first…” (`llm.py:60`, `:277-278`); ostatnia tura → wiadomość `developer` z `_FINAL_TURN_MESSAGE` na końcu (`llm.py:62-65`, `:279-280`).
- Reguły korekty w prompcie, cytat (`llm.py:47-51`): „work the correct form of at most the 1-2 most important ones (grammar, vocabulary, word order) naturally into your reply. Do not explain rules and do not list mistakes.” / „Ignore typos and punctuation unless they change the meaning.” / „Never interrupt the conversation with a lecture.”
- Wywołanie: `client.responses.parse(model=settings.LLM_MODEL, …, text_format=AgentTurn, reasoning={"effort": settings.LLM_REASONING_EFFORT}, store=False)` (`llm.py:301-308`). Effort tury domyślnie `none` (`settings.py:61`), timeout 30 s, 1 ponowienie (`settings.py:62-63`).
- Wyjście: `AgentTurn(reply: str, end_conversation: bool)` (`llm.py:104-106`) → `TurnResult` z tokenami (`llm.py:109-116`). Pusta odpowiedź → `LLMError` (`llm.py:336-339`).
- Wywołujący: `services._generate_and_save` (`services.py:223-269`); historia z `conversation.messages.values_list("role", "text")` (`services.py:233`), pamięć z `conversation.memory_prompt` (`services.py:246`).

**Analiza po rozmowie** (`llm.py:374-432`):

- Wejście: `language`, `history` (cała rozmowa). Transkrypt: wiadomości ucznia numerowane od 1 jako `[n] Learner: …`, partnera bez numeru jako `Partner: …` (`llm.py:361-371`).
- Reguły w prompcie, cytaty (`llm.py:73-89`): „Analyse only the learner's messages … never report anything from them.”; „Report only mistakes in these categories: grammar, vocabulary, word_order.”; „Ignore typos, capitalisation and punctuation unless they change the meaning.”; `wrong` = „the shortest fragment”, `sentence` = „the learner's whole original sentence … unchanged”, `explanation` = „one short sentence in English”; „Report every occurrence separately”.
- Notatki do pamięci z tego samego wywołania (`llm.py:91-100`): `learner_facts` „at most 5”, `scene_notes` „at most 8 notes … what questions the partner asked”, „Notes never describe mistakes or the learner's language level.”
- Wywołanie: `responses.parse(…, text_format=MistakeReport, reasoning={"effort": settings.LLM_ANALYSIS_REASONING_EFFORT}, store=False)` (`llm.py:386-393`); effort domyślnie `medium` (`settings.py:73-75`), timeout 150 s, 0 ponowień (`settings.py:81-82`).
- Wyjście: `MistakeReport(mistakes: list[FoundMistake], learner_facts: list[str], scene_notes: list[str])` (`llm.py:128-131`); `FoundMistake(message_number, category: Literal["grammar","vocabulary","word_order"], wrong, correct, sentence, explanation)` (`llm.py:119-125`).
- Po stronie aplikacji (deterministycznie, poza modelem): `_merge_mistakes` sortuje chronologicznie, odrzuca puste i `wrong == correct`, scala identyczne pary (`services.py:532-558`); notatki są przycinane (`services.py:516-518`). Wywołujący: `services.analyze_conversation` (`services.py:390-503`, wywołanie `:438`).

**Blok pamięci** (`llm.py:217-256`, wybór `conversations/memory.py:77-101`):

- Wybór bez LLM: fakty z 10 ostatnich przeanalizowanych rozmów, notatki sceny z 5 ostatnich rozmów tej samej sceny, do 10 błędów z 20 ostatnich rozmów, ranking po liczbie rozmów (`memory.py:33-36`, `:116-149`).
- Tekst bloku zawiera instrukcje dla modelu, m.in. „do not ask again questions that were already asked” (`llm.py:239-241`) i „Pick at most one of them … Never say that this is an exercise or that the learner made this mistake before.” (`llm.py:251-254`).
- Konsekwencja dla evalu: przypadek pamięci można zbudować bez bazy — `format_memory(Memory(scene_notes=[[…]], mistakes=[PastMistake(…)]))` i `generate_turn(history=[], memory=…)` (tura otwierająca, w której agent mówi pierwszy).

### 2. Co dziś sprawdzają testy (teza a)

- Atrapy oddają to, co test zakolejkował: domyślna tura `TurnResult(reply="Guten Tag!", …)` (`tests/test_conversation_views.py:31-40`), domyślny błąd `category="grammar"`, `sentence=f"Sentence {n}."` (`tests/test_analysis.py:24-39`), atrapa transportu buduje ciało odpowiedzi z `json.dumps(payload)` (`tests/fake_provider.py:162-196`).
- Testy tekstu promptu (przypinają brzmienie, nie zachowanie): `test_instructions_start_with_the_same_stable_prefix` sprawdza `"B1-B2"` i `"at most the 1-2 most important"` (`tests/test_llm.py:129-139`); `test_format_memory_lists_every_section_in_order` sprawdza m.in. `"do not ask again questions that were already asked"` i `"Never say that this is an exercise"` (`tests/test_llm.py:192-204`); `test_analysis_instructions_share_a_stable_prefix_across_languages` sprawdza `"word_order"`, `"learner_facts"`, `"scene_notes"` (`tests/test_llm.py:471-487`). Część z nich chroni kontrakt cache (stały prefiks), część to lustro brzmienia — przy strojeniu promptu te drugie trzeba będzie świadomie zaktualizować.
- Kategoria w testach: tylko przekazanie etykiety dalej (`tests/test_analysis.py:553-568`) i wyświetlenie „Word order” (`tests/test_conversation_views.py:1131-1155`).
- Ręczne mutanty na tekście promptu: tylko M13 (etykieta „(the most recent)”, `scripts/mutation/manual_mutants.py:186-191`); żaden nie celuje w reguły korekty, kategorie ani literówki.
- Wniosek: zielone testy dowodzą hydrauliki (schemat, koszt, błędy, izolacja, format pamięci), nie jakości nauki. To jest luka, którą ma zamknąć ta faza.

### 3. Wyrocznia: wymagania i wcześniejsze decyzje

- Korekta: PRD Guardrail „Korekta nie przerywa rozmowy: poprawka jest wpleciona naturalnie, rozmowa nie zamienia się w wykład z gramatyki.” (`prd.md:45`); FR-005 „poprawną wersję swojej błędnej wypowiedzi, wplecioną w rozmowę” (`prd.md:71`); „recast bywa niezauważony” zaakceptowane, bo lukę domyka lista (`prd.md:72`). Decyzja S-01 (ostrzejsza niż PRD): max 1–2 najważniejsze błędy, bez literówek i interpunkcji (`context/archive/2026-10-05-first-corrected-conversation/plan-brief.md:30`).
- Lista błędów: kategorie „gramatyka / słownictwo / szyk zdania” (`prd.md:106`). „Lista błędów jest trafna: użytkownik zgadza się z wykrytymi błędami i ich kategoriami.” (`prd.md:42`) — PRD nie definiuje precyzji ani recall; wyrocznią jest zgoda ucznia.
- Literówki: PRD milczy; wykluczenie to decyzja planu S-02 „Bez literówek, wielkości liter i interpunkcji (chyba że zmieniają sens)” (`context/archive/2026-10-06-post-conversation-error-list/plan-brief.md:29`). Jakość listy oceniana „tylko ręcznie na kilku rozmowach; brak automatycznej ewaluacji” (`plan-brief.md:60`).
- Pamięć: FR-009 (`prd.md:81`), z zawężeniem do wątków pasujących do tematu (`prd.md:82`); powtórzenie pytania w innej scenie albo po oknie 5 rozmów jest dopuszczone przez projekt (okna z `memory.py:33-36`).
- Gotowe przypadki z planu S-02 (napisane przez plan, nie przez native speakera): „Ich habe gestern in die Stadt gegangen”, „Ich weiß, dass er kommt morgen”, złe słowo, powtórzony błąd, literówka (`post-conversation-error-list/plan.md:356`).
- Kto ocenia niemiecki: użytkownicy to uczniowie B1–B2, autor sprawdzał jakość korekty po angielsku (S-01 `plan-brief.md:8`, `:27`). W `context/` nie ma native speakera ani nauczyciela, który mógłby opisać zestaw.
- Jedyny wcześniej zaproponowany eval (nieuruchomiony): „20–30 prawdziwych zdań z błędami autora i żony, 2–3 tanie modele … ocena ręczna” (`first-corrected-conversation/research.md:123`).

### 4. Twarde niezmienniki vs wyniki jakościowe

| Właściwość | Gdzie egzekwowana dziś | Rodzaj | Warstwa |
|---|---|---|---|
| Schemat `AgentTurn` / `MistakeReport` | `text_format` (`llm.py:305`, `:390`), `ValidationError` → `LLMError` (`llm.py:323-329`, `:406-411`) | zagwarantowane kodem | zwykły test (istnieje: `tests/test_llm.py:363`, `:545`) |
| Kategoria ∈ {grammar, vocabulary, word_order} | `Literal` (`llm.py:121`) | zagwarantowane kodem | jw.; eval nie mierzy |
| Pusta odpowiedź agenta = błąd | `llm.py:336-339` | zagwarantowane kodem | zwykły test + M14/M15 |
| Scalanie identycznych par, odrzucanie pustych | `services.py:532-558` | logika deterministyczna | zwykły test |
| Format bloku pamięci | `llm.py:217-256` | logika deterministyczna | zwykły test (`tests/test_llm.py:188-235`) |
| A1: każda pozycja ma `message_number` w `1..N`, a `wrong` występuje w tej wiadomości ucznia (nic z partnera) | tylko prompt (`llm.py:73-74`) | twarde per przypadek, oczekiwane 0 naruszeń | eval, liczone ze wzorca |
| A2: `sentence` jest fragmentem wiadomości ucznia bez zmian | tylko prompt (`llm.py:84-85`) | twarde per przypadek | eval |
| A3: podłożona literówka / wielka litera / interpunkcja nie na liście | tylko prompt (`llm.py:76`); `high` łamał to w pomiarze (`settings.py:69-72`) | twarde per przypadek | eval |
| A4: wiadomość bez błędu nie daje pozycji | tylko prompt | twarde per przypadek | eval |
| A5: `learner_facts` ≤ 5, `scene_notes` ≤ 8 | tylko prompt (`llm.py:92`, `:95`); decyzja „ufamy modelowi … Wrócić, gdy zmieni się `LLM_MODEL`” (S-03 `reviews/impl-review.md:38`) | twarde per przypadek | eval |
| T1: `end_conversation = false` w środku rozmowy bez pożegnania | tylko prompt (`llm.py:56-57`) | twarde per przypadek | eval |
| Q1: recall błędów ze wzorca | — | jakościowe (liczba) | eval |
| Q2: pozycje spoza wzorca (fałszywe albo inne poprawne poprawki) | — | jakościowe + przegląd człowieka | eval |
| Q3: trafność kategorii na dopasowanych pozycjach | — | jakościowe | eval; wzorzec może dopuścić 2 kategorie dla przypadków granicznych |
| Q4: odpowiedź zawiera poprawną formę ze wzorca i nie powtarza błędnej | — | jakościowe | eval, deterministycznie |
| Q5: znaczniki wykładu (terminy gramatyczne, „Es heißt …”, „Richtig wäre …”, długość, liczba pytań) | — | jakościowe (proxy z fałszywymi alarmami, np. „Regel” w rozmowie o zasadach gry) | eval + przegląd trafień |
| Q6: naturalność recastu | — | jakościowe | opcjonalnie sędzia z wzorcem |
| Q7: pytanie z notatek pamięci nie pada ponownie | — | jakościowe | opcjonalnie sędzia z listą wcześniejszych pytań jako wzorcem |
| Koszt i czas na wywołanie | `usage` (`llm.py:346-354`, `:423-432`), cennik `budget.turn_cost` (`budget.py:27-45`) | pomiar | eval (raport, nie ocena) |

Uwagi do projektu przypadków:

- Tura ma poprawić „at most the 1-2 most important” (`llm.py:47-48`). Przypadek tury z kilkoma błędami nie ma jednej poprawnej odpowiedzi, więc Q4 jest dobrze zdefiniowane tylko dla przypadku z **jednym** wyraźnym błędem.
- Analiza widzi cały transkrypt, nie pojedyncze zdania (`llm.py:361-371`). Przypadki analizy jako krótkie rozmowy (kilka wiadomości ucznia z błędami, literówką, zdaniem poprawnym i błędem w wiadomości partnera) odpowiadają kształtowi produkcji i zmniejszają liczbę wywołań.
- `wrong` bywa dłuższy niż „najkrótszy” (S-02 `change.md:14`), więc dopasowanie do wzorca musi być tolerancyjne (ten sam `message_number` + słowo kluczowe błędu w `wrong` i poprawnej formy w `correct`), nie porównaniem całych napisów — zgodnie z antywzorcem „asercja na dokładny tekst”.

### 5. Pamięć: „powtarza pytania”

- Wymaganie jest prawdziwe (FR-009 `prd.md:81`, US-01 `prd.md:54`), mechanizm jest w kodzie (`llm.py:95-97`, `:239-241`). Nie jest więc ryzykiem spekulatywnym.
- Łańcuch ma dwa ogniwa i każde można mierzyć osobno:
  1. analiza zapisuje pytania partnera w `scene_notes` (napisany ręcznie transkrypt z 2–3 pytaniami partnera → czy notatki je wymieniają; ocena przez dopasowanie słów kluczowych albo sędziego);
  2. tura otwierająca z ręcznie zbudowanym blokiem pamięci (`format_memory(Memory(scene_notes=[[…]]))`) nie zadaje tych pytań ponownie — parafraza uniemożliwia czysto deterministyczną ocenę, więc potrzebny jest sędzia z listą pytań jako wzorcem albo przegląd człowieka.
- Wytyczna #5 (`test-plan.md:61`) i `change.md:14` pomijają pamięć. Plan musi zdecydować: mała, opcjonalna seria pamięci w tej fazie albo zawężenie ryzyka #5.

### 6. Koszt jednego przebiegu a logika dziennego budżetu

Dane wejściowe (zmierzone):

- Cennik gpt-5.4: 2,50 / 0,25 / 15,00 USD za 1M tokenów wejścia / wejścia z cache / wyjścia (`settings.py:86-92`).
- Analiza, 20 tur (41 wiadomości), `medium`: 52,2 s, 0,067 USD, 12 pozycji; w aplikacji ta sama rozmowa ok. 60–80 s, 0,08 USD, 18 pozycji; `high`: 164,8 s, 0,21 USD, 19 pozycji z literówkami (S-02 `change.md:14`).
- Tura: 16 tur agenta po angielsku ≈ 0,027 USD łącznie, czyli ok. 0,0017 USD na turę (S-01 `reviews/impl-review-phase-4.md:17`); symulacja 32 tur z pamięcią ok. 1,5 tys. tokenów = 0,117 USD, czyli ok. 0,0037 USD na turę (S-03 `reviews/impl-review.md:48`).

Szacunek przykładowego przebiegu (rachunek, nie pomiar; liczba przypadków to przykład dla planu):

- analiza: 12 krótkich transkryptów × K=3 = 36 wywołań × ≤ 0,08 USD (największy zmierzony koszt analizy `medium`, dla rozmowy 20-turowej) = ≤ 2,88 USD;
- tura: 20 przypadków × K=3 = 60 wywołań × ≈ 0,004 USD (górna z dwóch zmierzonych średnich) ≈ 0,24 USD;
- opcjonalnie pamięć: 5 przypadków × 3 = 15 wywołań × ≈ 0,004 USD ≈ 0,06 USD;
- opcjonalnie sędzia: 60 ocen × ≈ 0,004 USD ≈ 0,24 USD (założenie: krótki prompt, effort `none`; niezmierzone);
- razem ≤ ok. 3,4 USD na przebieg, porównanie dwóch wersji = 2 przebiegi ≤ ok. 6,8 USD. Koszt krótkiej analizy (bez 20 tur) nie był mierzony; pierwszy przebieg go ustali. Czas: 36 analiz po ≤ 52 s to ≤ ok. 31 min sekwencyjnie.

Relacja do budżetu:

- `spent_today` czyta tylko `Message.cost_usd`, `Conversation.analysis_cost_usd` i `LLMCharge.cost_usd` (`budget.py:64-81`). Eval wołający `llm.*` wprost nie zapisuje żadnego z nich, więc `DAILY_BUDGET_USD` (`settings.py:100`) go nie ogranicza i nie zużywa limitu żadnego użytkownika.
- Eval przez `services` wymagałby bazy, użytkownika i zderzyłby się z dachem: `is_exhausted` odmawia startu, gdy suma + 0,03 ≥ 1,00 (`budget.py:102-105`), więc przebieg droższy niż ok. 0,97 USD nie przeszedłby w jeden dzień.
- Wniosek: eval potrzebuje własnego limitu (np. suma `turn_cost` z `usage` każdego wyniku i zatrzymanie po przekroczeniu progu) i musi liczyć też nieudane wywołania: `LLMError.usage` albo `billed_without_usage` (`llm.py:155-196`). Użycie `budget.turn_cost` do raportu wydatku jest w porządku — to cennik, nie wyrocznia oceny.
- Timeout analizy 150 s (`settings.py:81`) działa też w evalu, bo `analyze_mistakes` czyta ustawienia; wywołanie dłuższe kończy się `LLMError` i trzeba je liczyć jako porażkę przypadku.

Sprawa przekazana z Phase 2: „Pomiaru realnego czasu analizy względem limitu 300 s proxy Railway nie da się zrobić atrapą — przechodzi do §3 Phase 5” (`test-plan.md:214`). Krótkie transkrypty evalu tego nie zmierzą; potrzebny jest osobny, jeden przypadek długiej rozmowy (rząd 41 wiadomości jak w S-02, wiadomości do 2000 znaków — `services.py:74`), raportowany jako czas, bez oceny.

### 7. Szum i porównanie dwóch wersji

- Brak sterowania losowością: Responses API nie ma `seed`; `temperature` tylko przy effort `none` (§Zewnętrzne fakty). Produkcja nie ustawia `temperature` (`llm.py:301-308`, `:386-393`), więc eval nie powinien jej ustawiać — mierzy to, co dostaje użytkownik.
- Zmierzona zmienność: 12 vs 18 pozycji dla tej samej rozmowy (S-02 `change.md:14`).
- Rachunek (wzory standardowe, nie źródło): przy n = 50 wyników binarnych i p ≈ 0,7 przedział 95% to ok. ±13 pp; najmniejsza wykrywalna różnica bez parowania przy mocy 80% to ok. 25 pp; wykrycie 70% → 80% wymaga ok. 290 przypadków na wersję. Parowanie per przypadek i K powtórzeń zmniejszają wariancję (Miller 2024, §Zewnętrzne fakty).
- Wniosek dla planu: K=3 na przypadek, różnica sparowana per przypadek z błędem standardowym, różnice poniżej ok. 10 pp traktowane jako szum przy tej wielkości zestawu, a przypadki, które zmieniły wynik, wypisane do przeczytania.
- Identyfikacja wersji: eval uruchamia kod z bieżącego checkoutu (bez podmiany promptu); wersję opisuje commit + skrót (hash) `_INSTRUCTIONS`, `_ANALYSIS_INSTRUCTIONS` + `LLM_MODEL`, `LLM_REASONING_EFFORT`, `LLM_ANALYSIS_REASONING_EFFORT`. Zmiana modelu wymaga wpisu w `LLM_PRICES_USD_PER_MTOK`, inaczej start się nie powiedzie (`settings.py:93-98`) — to dobra bramka, bo koszt przebiegu da się wtedy policzyć.

### 8. Sędzia LLM (teza b)

- Bez wzorca sędzia jest mniej wiarygodny (Zheng i in. 2023), faworyzuje własne odpowiedzi (Panickssery i in. 2024) i ma silne uprzedzenie pozycji przy porównaniu A/B (Zheng i in. 2023). Praktyka: ocena pojedynczej odpowiedzi, kryterium tak/nie z krótkim uzasadnieniem, wzorzec w prompcie, zgodność z ocenami człowieka (TPR/TNR) sprawdzona przed zaufaniem (Husain, §Zewnętrzne fakty).
- W tym projekcie: tylko klucz OpenAI (`settings.py:49-54`); sędzia z tej samej rodziny ma ryzyko faworyzowania, sędzia z innej rodziny to nowa zależność i sekret.
- Przy ≤ 50 przypadkach nie da się wypełnić zalecanych podziałów do kalibracji (30–50 przykładów każdej etykiety na podział) — można najwyżej podać TPR/TNR na tym, co użytkownik sam oceni.
- Wniosek: pierwsza wersja bez sędziego (Q1–Q5 deterministycznie + lektura przypadków przez użytkownika); sędzia z wzorcem tylko dla Q6/Q7 i dopiero po kalibracji.

### 9. Zestaw danych: skąd wzorzec, skoro nie z ocenianego modelu

- Antywzorzec z test-planu: zestaw wygenerowany przez oceniany model (`test-plan.md:61`), a zasada §1 każe brać oczekiwany wynik z wymagań, nie z kodu (`test-plan.md:30`). Wynik analizy aplikacji nie może być wzorcem.
- Opcje (decyzja użytkownika, §Open Questions):
  1. błędy podręcznikowe o jednoznacznej regule (Perfekt z `sein`, czasownik na końcu po `dass`, szyk po przysłówku na początku, rodzajnik / przypadek po przyimku) — wyrocznia = reguła gramatyczna; przykłady z planu S-02 (`post-conversation-error-list/plan.md:356`);
  2. zdania z korpusu MERLIN (B1/B2, poprawki ekspertów, licencja CC BY-SA 4.0) dopasowane do formy czatu — wymaga atrybucji w pliku; repo jest prywatne (`test-plan.md:121`);
  3. prawdziwe błędy autora i żony (`first-corrected-conversation/research.md:123`) — realny rozkład błędów, ale poprawną formę musi potwierdzić źródło z opcji 1 albo 2; dane z produkcji wymagałyby zgody i usunięcia faktów osobistych.
- Ocena formy recastu (wykład vs wpleciona poprawka) nie wymaga native speakera — to definicja typu informacji zwrotnej (Lyster i Ranta 1997: recast vs explicit correction vs metalinguistic feedback), którą użytkownik może ocenić sam. Native speaker byłby potrzebny tylko do niejednoznacznych poprawek, których zestaw powinien unikać.

### 10. Jak eval zostaje poza CI i poza domyślnym `uv run pytest`

- Fakty: CI = `uv sync --locked`, `ruff check`, `ruff format --check`, `uv run pytest` (`.github/workflows/ci.yml:26-30`), bez `env:` i sekretów. pytest: `DJANGO_SETTINGS_MODULE = "talkaitive.settings_test"`, `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, bez `addopts`, `markers`, `-m` (`pyproject.toml:33-37`). Testy Playwright startują serwer z `OPENAI_API_KEY: ''` (`playwright.config.ts:55-56`).
- Plik w `tests/` o nazwie `test_*.py` byłby zebrany zawsze, niezależnie od markera. Katalog poza `tests/` (np. `scripts/eval/` albo `evals/`) nie jest zbierany przez CI, przez domyślny `uv run pytest` ani przez `manual_mutants.py` (`:58`).
- Uruchamianie prawdziwego modelu lokalnie: klucz w `.env` (gitignored), `uv run --env-file .env …` (CLAUDE.md). Skrypt musi ustawić `DJANGO_SETTINGS_MODULE=talkaitive.settings` i wywołać `django.setup()` (`llm.py` importuje `accounts.models.PracticeLanguage`, `llm.py:31`), ale nie potrzebuje bazy. Strażnik na starcie: odmowa przy pustym kluczu albo `"test-key"`, wypisanie maksymalnego kosztu, limit wydatku.
- Zależności: dev-group ma `httpx2`, `mutmut`, `pytest`, `pytest-django`, `ruff` (`pyproject.toml:15-22`); w `uv.lock` brak bibliotek do evali. DeepEval dodany do grupy `dev` trafiłby do CI (`uv sync --locked` instaluje grupę `dev`) z automatycznie ładowaną wtyczką pytest i telemetrią — odradzane.

### 11. Najtańsza użyteczna warstwa

1. **Zwykłe testy (CI, bez klucza)** dla kodu oceniania evalu: dopasowanie pozycji do wzorca, metryki, porównanie przebiegów, limit wydatku. Wejście = ręcznie napisane `AnalysisResult` / `TurnResult`, oczekiwane liczby wpisane ręcznie, potwierdzenie mutacją wg §6.1 test-planu.
2. **Lokalny eval na prawdziwym modelu** (`scripts/eval/`, ręcznie przy zmianie promptu, modelu albo effort): seria analizy (A1–A5, Q1–Q3), seria tury (T1, Q4–Q5), wynik do pliku, porównanie dwóch plików. Wynik to liczby, nie zielony/czerwony test.
3. **Opcjonalnie później:** seria pamięci (Q7) i sędzia z wzorcem (Q6/Q7), po kalibracji na ocenach użytkownika; jeden przypadek długiej rozmowy do pomiaru czasu (sprawa z Phase 2).

Odrzucone: eval przez `services` i bazę (dach $1, zbędne zależności), OpenAI Evals API (buduje prompt po stronie OpenAI, omija `llm.py` i parsowanie Pydantic), promptfoo (Node, drugi zestaw narzędzi w repo opartym na uv), DeepEval (§10), eval na każdym commicie (koszt, niedeterminizm; `test-plan.md:61`).

### 12. Dowody hot-spot i prawdopodobieństwo

- 8 commitów zmieniających `conversations/llm.py` / `conversations/memory.py` (`git log`): `897d81c`, `15fc045`, `a01675b`, `c149bc8`, `334f8df`, `34437b6`, `cf14043`, `d37e240`. Tekst promptu zmieniły 4 z nich (`897d81c` tura, `a01675b` analiza, `c149bc8` notatki, `34437b6` blok pamięci), wszystkie 2026-10-06/07 przy budowie funkcji; pozostałe to obsługa błędów, logika wyboru pamięci i koszt.
- Liczba 30 zmian plików w `conversations/` (2026-09-13…10-13) da się odtworzyć bez `migrations/` i `templates/` (wyłączenie `templates/` to wniosek, nie zapis w test-planie); większość dotyczy `services.py`, `models.py`, `views.py`, `budget.py`.
- Model `gpt-5.4` od `8d8d845`; effort tury `none` bez zmian; effort analizy zmieniony raz (`a01675b` `high` → `dfe3e7d` `medium`) z powodu czasu, nie jakości.
- Wiersz #5 opiera prawdopodobieństwo „High” na wywiadzie Q3 („główne optymalizacje będą w promptach i wyborze modelu”, `test-plan.md:48`) — to zamiar na przyszłość. Faza 5 „opłaca się dopiero przed pierwszą optymalizacją promptu lub modelu” (`test-plan.md:78`) i dziś takiej optymalizacji jeszcze nie było.

## Code References

- `conversations/llm.py:38-58` — `_INSTRUCTIONS` tury (reguły korekty `:46-51`, koniec rozmowy `:53-57`)
- `conversations/llm.py:68-101` — `_ANALYSIS_INSTRUCTIONS` (kategorie `:75`, literówki `:76`, pola `:78-89`, notatki `:91-100`)
- `conversations/llm.py:104-131` — schematy `AgentTurn`, `TurnResult`, `FoundMistake` (kategoria `Literal` `:121`), `MistakeReport`
- `conversations/llm.py:155-196` — `LLMError` z `usage` / `billed_without_usage`
- `conversations/llm.py:217-256` — `format_memory` (pytania `:239-241`, jeden stary błąd `:251-254`)
- `conversations/llm.py:259-281` — budowa `instructions` i `input` tury
- `conversations/llm.py:284-354` — `generate_turn`
- `conversations/llm.py:357-432` — transkrypt i `analyze_mistakes`
- `conversations/services.py:137-139` — pamięć liczona raz przy starcie
- `conversations/services.py:223-269` — `_generate_and_save` (wywołanie tury `:241-247`)
- `conversations/services.py:390-503` — `analyze_conversation` (wywołanie `:438`, zapis `:466-470`)
- `conversations/services.py:532-558` — `_merge_mistakes`
- `conversations/memory.py:33-36`, `:77-101`, `:116-149` — okna i wybór pamięci
- `conversations/budget.py:27-45`, `:64-81`, `:84-105` — `turn_cost`, `spent_today`, `is_exhausted`
- `talkaitive/settings.py:59-107` — model, effort, timeouty, cennik, bramka ceny, budżet, szacunki
- `talkaitive/settings_test.py:15-16` — klucz `"test-key"`
- `pyproject.toml:15-22`, `:33-37` — zależności dev, konfiguracja pytest
- `.github/workflows/ci.yml:26-30` — kroki CI
- `tests/test_llm.py:129-139`, `:192-204`, `:471-487` — testy brzmienia promptu
- `tests/fakes.py:23-56`, `tests/fake_provider.py:85-113`, `:162-196` — atrapy
- `scripts/mutation/manual_mutants.py:58`, `:186-191` — argumenty pytest mutacji, M13
- `scripts/mutation/accepted_survivors.md:79` — `memory._mistakes__mutmut_47` przekierowany do Phase 5

## Architecture Insights

- `llm.py` jest jedynym modułem z `openai` i ma czyste funkcje wejście → wynik; to naturalna granica dla evalu (bez bazy, bez widoków, bez budżetu).
- Analiza ma dwie role naraz: lista błędów dla ucznia i źródło pamięci (`learner_facts`, `scene_notes`). Zmiana promptu analizy zmienia więc też pamięć kolejnych rozmów; eval analizy powinien sprawdzać obie części.
- Twarde gwarancje są rozłożone: schemat (Pydantic + structured output), kod aplikacji (`_merge_mistakes`, pusta odpowiedź) i sam prompt. Eval ma sens tylko dla tej trzeciej grupy.
- Repo ma już wzorzec „lokalnie, okresowo, poza CI, z kodem wyjścia”: `scripts/mutation/manual_mutants.py` + rejestr w `scripts/mutation/accepted_survivors.md`. Eval może iść tą samą drogą (skrypt + plik wyników).

## Historical Context (from prior changes)

- `context/archive/2026-10-05-first-corrected-conversation/plan-brief.md:30` — max 1–2 błędy, bez literówek; `research.md:123` — jedyna wcześniejsza propozycja evalu (ocena ręczna); `reviews/impl-review-phase-4.md:17` — koszt 16 tur. Teza „jakość sprawdzono ręcznie”: potwierdzona, ale po angielsku (`plan-brief.md:8`, `:27`).
- `context/archive/2026-10-06-post-conversation-error-list/change.md:14` — pomiar `high` vs `medium` (czas, koszt, liczba pozycji, literówki) i zmienność 12 vs 18; `plan-brief.md:29`, `:60` — reguła literówek i ocena „tylko ręcznie”; `plan.md:356` — gotowe przypadki niemieckie.
- `context/archive/2026-10-07-cross-session-error-memory/plan.md:336` — punkt „nie powtarza wcześniejszych pytań” odhaczony bez zapisanego dowodu; `reviews/impl-review.md:38` — limity notatek „ufamy modelowi … Wrócić, gdy zmieni się `LLM_MODEL`”; `:48` — symulacja 32 tur prawdziwym `generate_turn` bez bazy. Teza test-planu „archive S-03 (zachowanie pamięci sprawdzane tylko ręcznie)” (`test-plan.md:48`): częściowo — ręcznie tak, ale „tylko ręcznie” to parafraza; w archiwum są odhaczone punkty bez zapisu przebiegu.
- `context/archive/2026-10-15-testing-waiting-path-recovery/` — pomiar czasu analizy wobec 300 s proxy przekazany do tej fazy (`test-plan.md:214`).

## Related Research

- `context/archive/2026-10-16-testing-budget-ceiling/research.md` — ścieżki kosztu i księga `LLMCharge` (koszt nieudanych wywołań w evalu).
- `context/archive/2026-10-15-testing-waiting-path-recovery/research.md` — timeouty SDK i limity czasu analizy.
- `context/archive/2026-10-05-first-corrected-conversation/research.md` — wybór modelu i propozycja ręcznej ewaluacji.

## Zewnętrzne fakty (stan na 2026-10-16)

- DeepEval: najnowsza wersja na PyPI 4.3.0 (strona czytana 2026-10-16, https://pypi.org/project/deepeval/); rejestruje wtyczkę `pytest11` i dociąga m.in. `pytest-xdist`, `pytest-repeat`, `pytest-rerunfailures`, `pytest-asyncio`; telemetria PostHog domyślnie włączona, wyłączenie `DEEPEVAL_TELEMETRY_OPT_OUT=1` (dokumentacja przez Context7). GEval to w praktyce prompt sędziego + parsowanie wyniku.
- promptfoo: wymaga Node ≥ 22.22 (https://www.promptfoo.dev/docs/installation/, bez daty); OpenAI ogłosiło przejęcie 2026-03-09 (https://openai.com/index/openai-to-acquire-promptfoo/).
- OpenAI Evals API / graders: usługa po stronie OpenAI, prompt z szablonu albo gotowe próbki JSONL (https://developers.openai.com/api/docs/guides/graders, bez daty).
- OpenAI, parametry losowości: „When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`” (https://developers.openai.com/api/docs/guides/latest-model, bez daty); Responses API nie ma `seed` (openai-node issue #1613, 2025-08-14). Niezweryfikowane własnym wywołaniem.
- Zheng i in., „Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena”, NeurIPS 2023 (https://arxiv.org/abs/2306.05685): wzorzec w prompcie sędziego zmniejszył błędy oceny na zadaniach matematycznych z 14/20 do 3/20; silne uprzedzenie pozycji.
- Panickssery, Bowman, Feng, „LLM Evaluators Recognize and Favor Their Own Generations”, 2024 (https://arxiv.org/abs/2404.13076): faworyzowanie własnych odpowiedzi rośnie z rozpoznawaniem własnego tekstu.
- Husain, evals FAQ i LLM-judge guide (https://hamel.dev/blog/posts/evals-faq/, 2025-05-28, aktualizowane; https://hamel.dev/blog/posts/llm-judge/): asercje w kodzie dla reguł obiektywnych, sędzia tylko dla subiektywnych, kalibracja TPR/TNR na ocenach człowieka.
- Miller, „Adding Error Bars to Evals”, 2024 (https://arxiv.org/abs/2411.00640): K próbek na pytanie, różnice sparowane, błąd standardowy i przedział ufności, analiza mocy.
- MERLIN: 2286 tekstów (niemiecki, włoski, czeski), A1–C1, poprawki i adnotacja błędów, CC BY-SA 4.0 (https://clarin.eurac.edu/repository/xmlui/handle/20.500.12124/6, rekord 2018-08-24). Falko: CC BY 3.0. Pakiet MultiGEC-2025 ma warunki zabraniające redystrybucji i podawania danych modelom zastrzeżonym (https://spraakbanken.github.io/multigec-2025/terms_of_use.html) — brać z MERLIN wprost.
- Lyster i Ranta 1997, SSLA (doi:10.1017/S0272263197001034): taksonomia informacji zwrotnej — recast, explicit correction, metalinguistic feedback i inne.

## Poprawki do test-planu §2 (do backportu albo `--refresh`)

Stan 2026-10-17: punkty dotyczące §2 (Source ryzyka #5 i Risk Response Guidance #5, w tym pamięć) wniesione do `context/foundation/test-plan.md` przez `/10x-test-plan`. Otwarte zostają: §4 Stack (DeepEval) i wiersz w `scripts/mutation/accepted_survivors.md:79` — do decyzji w `plan.md` (ostatnia podfaza, która aktualizuje test-plan).

- **Ryzyko #5, Source:** hot-spot `conversations/` nie jest dowodem dla #5 (4 z 8 commitów `llm.py` / `memory.py` zmieniły prompt, wszystkie przy tworzeniu funkcji). Mocniejszy dowód: pomiar S-02 — zmiana effort analizy na `high` zgłaszała literówki, a ta sama rozmowa dawała 12 vs 18 pozycji.
- **Risk Response Guidance #5, „What would prove protection”:** dopisać pamięć (FR-009 „nie powtarza pytań”) albo zawęzić brzmienie ryzyka; dziś ryzyko ją wymienia, a wytyczna nie.
- **Risk Response Guidance #5, „trzyma kategorie”:** zbiór etykiet gwarantuje schemat; eval mierzy trafność kategorii względem wzorca.
- **Risk Response Guidance #5, „Must challenge”:** dopisać „dzienny limit $1 ogranicza koszt evalu” — fałsz, eval wołający `llm.*` omija budżet.
- **Risk Response Guidance #5, „Likely cheapest layer”:** deterministyczna ocena ze wzorcem + lektura przypadków; sędzia opcjonalny, z wzorcem; kod oceniania w zwykłych testach CI.
- **§4 Stack, „AI-native eval”:** DeepEval odradzany (wtyczka `pytest11` w każdym `uv run pytest` i w CI, domyślna telemetria); zwykły skrypt w `scripts/eval/`.
- **`scripts/mutation/accepted_survivors.md:79`:** przekierowanie `memory._mistakes__mutmut_47` do Phase 5 jest chybione — eval nie zabija mutantów.

## Open Questions

1. **Źródło wzorca i kto go opisuje:** błędy podręcznikowe, MERLIN, prawdziwe błędy autora i żony, czy mieszanka? W `context/` brak native speakera; od tego zależy, czy przypadki niejednoznaczne wchodzą do zestawu.
2. **Pamięć (FR-009) w tej fazie czy później?** Seria pamięci wymaga sędziego albo lektury człowieka (parafraza pytań).
3. **Sędzia:** brak w pierwszej wersji, sędzia OpenAI z wzorcem i kalibracją, czy inny dostawca (nowy klucz i zależność)?
4. **Limit wydatku i K:** jaki próg na przebieg (rząd 3–4 USD przy przykładowym rozmiarze) i czy K=3 wystarczy przy zmierzonej zmienności 12 vs 18?
5. **Przypadek długiej rozmowy do pomiaru czasu (sprawa z Phase 2):** w tej fazie czy osobno?
6. **`memory._mistakes__mutmut_47`:** zwykły test jednostkowy (wyjaśnienie z jednego wystąpienia zostaje zachowane) czy pozostawienie jako `brak wymagania` z poprawionym wskaźnikiem?
7. **Testy brzmienia promptu** (`tests/test_llm.py:138-139`, `:199-204`): przy strojeniu promptu zostają jako świadome lustro (aktualizowane w diffie) czy zostają zawężone do kontraktu cache (stały prefiks)?
8. **Język:** ryzyko i zestaw dotyczą niemieckiego; angielski (`accounts/models.py:48-50`) zostaje bez evalu — do potwierdzenia.
