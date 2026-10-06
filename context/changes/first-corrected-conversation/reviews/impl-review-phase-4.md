<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Pierwsza rozmowa z korektą na bieżąco (S-01)

- **Plan**: context/changes/first-corrected-conversation/plan.md
- **Scope**: Phase 4 of 4
- **Reviewed phases**: 4
- **Date**: 2026-10-06
- **Verdict**: APPROVED
- **Findings**: 0 critical 1 warning 1 observation

Zakres przeglądu: commit `c602ec2` (3 pliki dokumentacji: `CLAUDE.md`, `context/deployment/deploy-plan.md`, `plan.md`) + niezacommitowana zmiana w `plan.md` (tylko dopisane SHA w Progress 4.1–4.7). Faza nie zmienia kodu. Commit nie jest jeszcze na `origin/main` (push robi użytkownik).

Kryteria automatyczne uruchomione ponownie: 4.1 — 101 testów przechodzi, ruff check i format czyste; 4.2 — `check --deploy` zgłasza tylko `mail.E001` (zaakceptowane, Deviation 4 w `deploy-plan.md`), `security.W004` (HSTS, zaakceptowane) i `security.W009` (wynik testowego `SECRET_KEY=x`); 4.3 — bez klucza poza DEBUG start kończy się `KeyError: 'OPENAI_API_KEY'`. 4.4 (healthz po deployu) czeka na push.

Sprawdzone twierdzenia z dokumentacji: `OPENAI_API_KEY` jest ustawiony na serwisie `web` na Railway (sprawdzone `railway variables`, wartość nie była wyświetlana) — część 4.8 „przed pushem” spełniona, „rozmowa działa na produkcji” czeka na push. Opis w `CLAUDE.md` zgadza się z kodem: fail-fast poza DEBUG (`talkaitive/settings.py:54`), `ImproperlyConfigured` dla modelu bez cennika (`settings.py:75`), `LLMError` przy braku klucza w DEBUG (`conversations/llm.py:77`), atrapa klucza w `settings_test.py`. Timeout 30 s × 2 próby = 60 s < 120 s gunicorna.

Ręczne 4.5–4.7 mają ślad w lokalnej bazie: rozmowy `en` zakończone z `agent_goodbye` i z `daily_limit`, łącznie 16 tur agenta, `cost_usd` razem ≈ $0.027 (przyda się do 4.9).

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Findings

### F1 — Dwa ręczne kroki fazy 4 nie mają pozycji w Progress

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/first-corrected-conversation/plan.md:301, plan.md:317 (Progress: plan.md:429-444)
- **Detail**: Plan wymaga (a) ustawienia na produkcji w `/admin/` `practice_language=en` dla autora i `de` dla żony (plan.md:317) oraz (b) projektu OpenAI z regionem EU i miesięcznym limitem wydatków (plan.md:301). Żaden z tych kroków nie ma checkboxa w Progress. (a) Po deployu oba konta mają `de` (domyślna wartość migracji), więc pierwsza rozmowa autora na produkcji będzie po niemiecku, a nic w Progress o tym nie przypomina. (b) `deploy-plan.md` zamyka follow-up „usage alert” właśnie tym limitem, a limit jest też „drugą linią obrony” budżetu (plan.md:233) — jego istnienie nie jest nigdzie potwierdzone.
- **Fix**: Dopisać na końcu Progress fazy 4 nowe pozycje (bez zmiany tytułów istniejących): `4.10 Na produkcji w /admin/: autor practice_language=en, żona de` i `4.11 Projekt OpenAI „talkaitive” w regionie EU ma miesięczny limit/alert wydatków`.
- **Decision**: SKIPPED

### F2 — Komenda „Simulate production” w deploy-plan.md wywala się po dodaniu klucza LLM

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: context/deployment/deploy-plan.md:98
- **Detail**: Krok 5 opisuje `DEBUG=False SECRET_KEY=x ALLOWED_HOSTS=localhost uv run python manage.py check --deploy` i oczekuje tylko ostrzeżenia HSTS. Od S-01 `OPENAI_API_KEY` jest wymagany poza DEBUG, więc ta komenda kończy się teraz `KeyError: 'OPENAI_API_KEY'`. Faza 4 aktualizowała `deploy-plan.md`, ale tej linii nie ruszyła. Plan S-01 (plan.md:324) ma już poprawną wersję z `OPENAI_API_KEY=x`.
- **Fix**: W `deploy-plan.md:98` dodać `OPENAI_API_KEY=x` do komendy z krótkim dopiskiem „(od 2026-10-06, S-01)”.
- **Decision**: FIXED
