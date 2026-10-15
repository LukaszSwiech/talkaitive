# Suite trust and CI floor — Plan Brief

> Full plan: `context/changes/testing-suite-trust-and-ci/plan.md`
> Research: `context/changes/testing-suite-trust-and-ci/research.md`

## What & Why

Rollout Phase 1 planu testów, ryzyko #2: regresja trafia na produkcję niezauważona, bo testy nie uruchamiają się przed wdrożeniem albo przechodzą na zepsutym kodzie (napisało je i sprawdzało to samo AI). Udowadniamy mutacjami, że zepsucie izolacji, budżetu, stanu analizy i pamięci wywraca testy, a CI wstrzymuje wdrożenie z czerwonymi testami.

## Starting Point

Brak CI; każdy push na `main` (54 z 59 commitów bez PR) wdraża produkcję. 198 zielonych testów, ale 12 z 13 celowanych ręcznych mutantów przeżyło — m.in. trzy wycieki danych między użytkownikami w widokach i jeden w budżecie. Ochrona gałęzi niedostępna (prywatne repo, plan Free → 403).

## Desired End State

Każdy PR i push do `main` uruchamia ruff + pytest w GitHub Actions; Railway wdraża commit dopiero po zielonym CI (udowodnione celowo czerwonym commitem). Jedna komenda podkłada stałą listę ręcznych mutantów i kończy się sukcesem, a mutmut na czterech modułach logiki krytycznej nie zostawia żadnego niewyjaśnionego przeżycia. Plan testów §6.1 mówi, jak dodać test i potwierdzić go mutacją.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Wymuszenie bramki | Railway „Wait for CI” + workflow na PR i push do `main` | Darmowe, obejmuje bezpośrednie pushe; przeniesienie repo na darmową organizację nie daje ochrony gałęzi (docs GitHub) | Research + Plan |
| GitHub Pro / transfer | Nie | Pro wymusiłby PR dla każdego commita, a dla ryzyka #2 wystarczy blokada wdrożenia | Plan |
| Baza w CI | SQLite | Ten sam wynik lokalnie i w CI; Postgres wraca z testem współbieżności (faza 2 lub 4) | Plan |
| Zakres zabijania | M1–M7, M10, M12, M13 w tej fazie | change.md obejmuje wszystkie cztery obszary; znane wycieki nie czekają do fazy 3 | Plan |
| Wyrocznia bez PRD | Okno 20 rozmów (M10) i etykieta „najnowsza” (M13) = decyzja użytkownika 2026-10-14; M8, M11 = zaakceptowane jako równoważne | Każda oczekiwana wartość ma źródło poza kodem | Plan |
| Zakres mutmut | `budget.py`, `memory.py`, `services.py`, `ownership.py` | Czysta logika z ryzyka #2; widoki pokrywa ręczna lista (mutmut nie usuwa `for_user`) | Research + Plan |
| Próg „zaufany” | 0 przeżyć bez wpisu w `accepted_survivors.md` | Procent ukrywa pojedyncze ważne przeżycie | Plan |
| Ręczna lista mutantów | Skrypt lokalny na kopii repo, okresowo, nie w CI | Powtarzalny dowód bez blokowania wdrożeń przy refaktoryzacji | Plan |
| Plan awaryjny spike'a | Gdy mutmut nie ruszy — dowodem zostaje skrypt, blokada w §6.6 | Bez trzeciego narzędzia w tej fazie | Plan |

## Scope

**In scope:**
- mutmut jako zależność dev + konfiguracja + baseline
- `.github/workflows/ci.yml`, Railway „Wait for CI”, dowód kanarkiem, kopia w `web-settings.json` i `deploy-plan.md`
- `scripts/mutation/manual_mutants.py` + `accepted_survivors.md`
- Testy zabijające M1–M7, M10, M12, M13 i pozostałe przeżycia mutmut z wymaganiem
- test-plan §4/§5/§6.1/§6.6, poprawki `tech-stack.md` i `CLAUDE.md`

**Out of scope:**
- GitHub Pro, transfer repo, Postgres w CI, mutmut w CI
- Testy nowych zachowań faz 2–4 (zawieszenie dostawcy, pełna lista widoków, koszt prób nieudanych)
- Przepisanie istniejących testów z problemem wyroczni (koszt → faza 4, timeout → faza 2)
- Rozjazd PRD „błąd pasuje do tematu” vs `select_memory`; mypy w CI

## Architecture / Approach

Spike najpierw (mutmut z pytest-django to jedyna duża niewiadoma), potem CI + bramka (najtańszy, najmocniejszy sygnał; każdy kolejny test od razu biegnie w CI). Skrypt ręcznych mutantów odtwarza pomiar z researchu i staje się miernikiem dla testów. Testy izolacji są metamorficzne (wynik A z danymi B = bez danych B), granice czasu wpisane ręcznie w UTC. Każdy nowy test potwierdzony ponownym podłożeniem swojego mutanta.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Spike mutmut | Działający przebieg, czas, baseline przeżyć | pytest-django w `mutants/` (zgłoszenia #504, #545) |
| 2. CI + bramka Railway | Workflow na PR i push, „Wait for CI”, dowód kanarkiem | Przełącznik Railway bywa niezapisywany — odczyt kontrolny |
| 3. Skrypt ręcznych mutantów | Jedna komenda, odtwarza 12 przeżyć | Fragmenty kodu zmienią się przy refaktoryzacji — skrypt zgłasza błąd |
| 4. Izolacja i budżet | Testy zabijające M1–M5 | Fixture'y, w których mutant i oryginał dają ten sam wynik |
| 5. Analiza i pamięć | Testy zabijające M6, M7, M10, M12, M13; M8, M11 zaakceptowane | Atrapa analizy potrzebuje wywołania w trakcie (M7) |
| 6. Triage mutmut | 0 niewyjaśnionych przeżyć | Liczba przeżyć nieznana do spike'a |
| 7. Dokumenty | test-plan §5/§6.1/§6.6, tech-stack, CLAUDE.md | — |

**Prerequisites:** dostęp do ustawień Railway `web` i do pushu na `main` (wykonuje użytkownik; agent nie pushuje).
**Estimated effort:** ~4–6 sesji; faza 6 zależy od liczby przeżyć z fazy 1.

## Open Risks & Assumptions

- mutmut może nie współpracować z pytest-django — plan awaryjny w fazie 1.
- Railway „Wait for CI” jest opisany w docs, ale nie obserwowany w tym projekcie; kanarek go weryfikuje.
- Zakładamy, że dodatkowy klucz `deploymentTrigger` w `web-settings.json` nie przeszkadza komendzie re-apply (GraphQL ignoruje niezadeklarowane zmienne); komendy nie uruchamiamy w tej fazie.
- Bramka blokuje wdrożenie, nie merge — czerwony commit może leżeć na `main` do naprawy.

## Success Criteria (Summary)

- Czerwone CI = brak wdrożenia, także przy bezpośrednim pushu na `main` (udowodnione).
- Każdy znany mutant logiki krytycznej jest zabity albo świadomie opisany; mutmut na czterech modułach nie ma niewyjaśnionych przeżyć.
- Nowy test w projekcie dodaje się wg §6.1: oczekiwana wartość z wymagań, potwierdzenie mutacją.
