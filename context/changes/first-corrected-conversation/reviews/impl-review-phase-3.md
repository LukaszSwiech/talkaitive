<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Pierwsza rozmowa z korektą na bieżąco (S-01)

- **Plan**: context/changes/first-corrected-conversation/plan.md
- **Scope**: Phase 3 of 4
- **Reviewed phases**: 3
- **Date**: 2026-10-06
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical 2 warnings 3 observations

Zakres przeglądu: commit `9594f51` (14 plików) + niezacommitowana zmiana w `plan.md` (tylko dopisane SHA w Progress 3.1–3.8). Kryteria automatyczne 3.1–3.5 uruchomione ponownie — wszystkie przechodzą (35 testów widoków + logowania, 97 w całym zestawie, ruff czysty, `manage.py check` bez uwag). Kroki ręczne 3.6–3.8 odhaczone; z natury nie mają śladu w diffie, a dopisek o Enter/Shift+Enter (decyzja w trakcie fazy) wskazuje, że ekran był faktycznie używany.

Sprawdzone i czyste: brak XSS (bez `|safe`, `linebreaksbr` escapuje), CSRF na wszystkich 5 formularzach POST, każdy widok z `pk` przez `for_user` (testy 404 dla B na GET i każdy POST), brak N+1, poprawne `atomic()` + `IntegrityError`, ponowny odczyt z blokadą przed zapisem odpowiedzi agenta. Wszystkie 14 testów wymienionych w kryterium 3.1 istnieje.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — „Czeka na odpowiedź” wygląda jak błąd; równoległe tury są płatne, ale niepoliczone

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Safety & Quality
- **Location**: conversations/templates/conversations/detail.html:19-20, conversations/services.py:90, :108-111
- **Detail**: Stan „czeka na odpowiedź” (ostatnia wiadomość od użytkownika) jest ten sam, gdy model właśnie odpowiada i gdy wywołanie padło. Szablon w obu przypadkach pisze „The agent could not reply. Please try again.” Scenariusz: odpowiedź trwa ~20 s, użytkownik odświeża stronę albo otwiera ją w drugiej karcie → widzi fałszywy błąd → klika „Try again” → drugie płatne wywołanie. Sprawdzenie w `run_agent_turn:90` jest bez blokady, więc obie tury idą do OpenAI; druga odpowiedź jest odrzucana (`:110`) i jej koszt nie trafia do `spent_today`. Tak samo przy „End” klikniętym w trakcie tury. N równoległych POST-ów na `/retry/` (do 8 wątków gunicorna) = N płatnych wywołań, 1 policzone — dzienny limit $1 da się przekroczyć kilkakrotnie. Plan świadomie przyjął „max jedną” odrzuconą turę, ale nie przewidział, że UI sam zachęca do ponowienia w trakcie oczekiwania. Druga linia obrony (limit w panelu OpenAI) zostaje.
- **Fix A ⭐ Recommended**: Znacznik „tura w toku” na rozmowie
  - Approach: pole `Conversation.agent_turn_started_at` (nowa migracja) ustawiane pod blokadą przed wywołaniem modelu i czyszczone po zapisie/błędzie; `send`/`retry` odmawiają, gdy znacznik jest świeży (np. < 90 s, czyli dłużej niż timeout SDK × próby = 60 s); `detail.html` pokazuje wtedy „Agent is typing…” zamiast błędu.
  - Strength: usuwa fałszywy komunikat i równoległe płatne wywołania u źródła; budżet znów odpowiada realnym kosztom.
  - Tradeoff: nowa migracja i ~30 linii w serwisie + testy; znacznik po zabitym workerze wygasa dopiero po 90 s.
  - Confidence: MED — wzorzec prosty, ale dotyka ścieżki start/send/retry naraz.
  - Blind spot: nie sprawdzone, czy strona w stanie „w toku” powinna sama się odświeżać (bez JS użytkownik musi odświeżyć ręcznie).
- **Fix B**: Tylko neutralny komunikat, ryzyko kosztu zaakceptowane
  - Approach: zmienić tekst na neutralny (np. „The agent hasn't replied yet.” + „Try again”) i dopisać w planie, że koszt odrzuconych tur nie jest liczony (2 zaufanych użytkowników, limit w panelu OpenAI).
  - Strength: jedna linia w szablonie, zero zmian w modelu danych.
  - Tradeoff: podwójne wywołania i niepoliczony koszt zostają.
  - Confidence: HIGH — trywialna zmiana.
  - Blind spot: nie wiadomo, jak często żona na telefonie odświeża stronę w trakcie czekania.
- **Decision**: FIXED (Fix A) — `Conversation.agent_turn_started_at` + migracja `conversations/0002`; znacznik ustawiany pod blokadą w start/send/retry, czyszczony po zapisie lub błędzie (tylko własny), ważny `LLM_TIMEOUT_SECONDS × (LLM_MAX_RETRIES + 1) + 30` s; strona w toku pokazuje spinner i odświeża się co 5 s (`{% block head %}` w `base.html`); 2 nowe testy. Blind spot rozstrzygnięty: auto-odświeżanie przez `<meta refresh>`.

### F2 — Brak limitu długości wiadomości

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/services.py:70-72, conversations/templates/conversations/detail.html:35
- **Detail**: Jedyna walidacja to `text.strip()`; `<textarea>` nie ma `maxlength`, a Django przyjmuje ciało POST do 2.5 MB. Wklejony długi tekst może jedną turą przekroczyć dzienny budżet (`is_final_turn` szacuje z kosztu *poprzedniej* tury, więc tego nie zatrzyma). Tekst dłuższy niż okno kontekstu modelu daje 400 → `LLMError`, a ta wiadomość zostaje ostatnia na zawsze — każde „Try again” padnie tak samo, wyjście tylko przez „End”.
- **Fix**: Limit np. 2000 znaków w `send_message` (`ConversationError`), ten sam `maxlength` na `<textarea>` i test.
- **Decision**: FIXED — `services.MAX_MESSAGE_LENGTH = 2000` sprawdzany po `strip()`, `maxlength` w `<textarea>` z kontekstu widoku, test `test_too_long_message_does_not_call_the_model_and_shows_a_notice`.

### F3 — Zły JSON z modelu daje stronę 500 zamiast „Try again”

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: conversations/llm.py:134 (kod z fazy 2, objawia się w widokach fazy 3: conversations/views.py:58-61, :102-105, :114-117)
- **Detail**: `generate_turn` łapie tylko `openai.APIError`. Przy uciętej lub niepoprawnej odpowiedzi `responses.parse` rzuca `pydantic.ValidationError` (`openai/lib/_parsing/_responses.py:160`, `model_parse_json`), który przelatuje przez widoki → 500. Stan da się odzyskać (wiadomość użytkownika zapisana, po odświeżeniu jest „Try again”), ale użytkownik widzi błąd serwera. Rzadkie przy structured outputs, możliwe przy niekompletnej odpowiedzi.
- **Fix**: W `llm.py` złapać też `pydantic.ValidationError` i zamienić na `LLMError` (z logiem bez treści rozmowy) + test z atrapą.
- **Decision**: FIXED — `except ValidationError` → `LLMError(...) from None` (tekst błędu cytuje odpowiedź modelu, więc nie jest łańcuchowany ani logowany), test `test_malformed_structured_output_becomes_llm_error`. Wyjaśnione z użytkownikiem: błąd nigdy nie trafia do historii wysyłanej do modelu (historia = tylko zapisane `Message`, `store=False`), retry wysyła tę samą historię, więc recovery hint nie jest potrzebny.

### F4 — Niespójny typ użytkownika między widokami, serwisem i budżetem

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: conversations/views.py:55-56, conversations/services.py:34, conversations/budget.py:57, :65
- **Detail**: `request.user` ma typ `AbstractBaseUser | AnonymousUser`, `start_conversation` oczekuje `User` (czyta `practice_language`), a `budget.py` typuje ten sam parametr jako `AbstractBaseUser`. Działa dzięki `LoginRequiredMiddleware`, ale po dodaniu `mypy` + `django-stubs` (planowane w CLAUDE.md) to będą pierwsze błędy.
- **Fix**: Jedna konwencja: alias `AuthenticatedHttpRequest` z `user: User` dla widoków za `LoginRequiredMiddleware` i `User` wszędzie w serwisie i budżecie (albo odłożyć do zmiany wprowadzającej mypy).
- **Decision**: FIXED — `AuthenticatedHttpRequest(HttpRequest)` z `user: User` w `conversations/views.py` (wszystkie widoki i `_get_conversation`; do przeniesienia do `accounts`, gdy druga aplikacja będzie go potrzebować), `budget.py` typuje `user: User`. `accounts/ownership.for_user` bez zmian (celowo przyjmuje też `AnonymousUser`).

### F5 — Drobne dodatki poza planem

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: conversations/templates/conversations/_reset_notice.html, accounts/templates/base.html:48-58, :69-75
- **Detail**: (1) Wspólny fragment szablonu `_reset_notice.html` — nie ma go na liście plików. (2) Skrypt jest w `base.html`, więc działa na każdej stronie (także logowania), a nie „w szablonie” formularza; blokuje wszystkie przyciski na stronie, nie tylko kliknięty. (3) Odblokowanie strony po powrocie z pamięci podręcznej przeglądarki (back/forward cache). (4) 4 dodatkowe testy. Wszystko sensowne i nieszkodliwe.
- **Fix**: Dopisać jedną linię-addendum w planie (Faza 3, pkt 3), żeby plan zgadzał się z kodem.
- **Decision**: FIXED — addendum „Dodane 2026-10-06 (po przeglądzie fazy 3)” w `plan.md` (Faza 3, pkt 3) opisuje dodatki z implementacji i poprawki F1–F4 (w tym migrację `conversations/0002`).

## Triage summary

- Fixed: F1 (Fix A), F2, F3, F4, F5 (5)
- Po poprawkach: `uv run pytest` — 101 passed; `ruff check` / `ruff format --check` czyste; `makemigrations --check` bez zmian; `manage.py check` bez uwag.
- Poprawki nie są jeszcze zacommitowane. Ręcznie warto sprawdzić z prawdziwym kluczem: odświeżenie strony w trakcie odpowiedzi pokazuje spinner i strona sama się odświeża, aż przyjdzie odpowiedź.
