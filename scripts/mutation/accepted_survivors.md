# Zaakceptowane przeżycia mutantów

Jedno miejsce dla każdego mutanta, który przeżywa testy i którego **świadomie** nie zabijamy. Dotyczy obu źródeł:

- ręcznej listy w `scripts/mutation/manual_mutants.py` (id `C1`, `C2`, `M1`–`M13`); wpis tutaj idzie w parze z `expected="accepted"` przy tym mutancie w skrypcie,
- przebiegów mutmut (nazwa mutanta z raportu, np. `conversations.budget.x_is_exhausted__mutmut_3`).

Mutant, którego nie ma w tej tabeli, a przeżywa, to luka w testach do naprawienia, nie wynik do przyjęcia.

## Klasyfikacja

| Klasyfikacja | Kiedy |
| --- | --- |
| `równoważny` | Zmiana bez skutku obserwowalnego: żaden użytkownik ani proces nie zobaczy innego zachowania. |
| `brak wymagania` | Brak źródła wymagania w PRD, `test-plan.md` ani w zapisanych decyzjach — nie ma wyroczni, więc test przypiąłby tylko obecną implementację. |
| `przekazany do fazy N` | Zachowanie należy do zakresu innej fazy planu testów (`context/foundation/test-plan.md` §3); tam zostanie zabite albo przeklasyfikowane. |

## Rejestr

| id / nazwa mutmut | plik i funkcja | klasyfikacja | uzasadnienie | data |
| --- | --- | --- | --- | --- |
