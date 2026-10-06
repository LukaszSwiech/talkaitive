---
project: "TalkAItive"
version: 1
status: draft
created: 2026-09-29
updated: 2026-10-06
prd_version: 1
main_goal: speed
top_blocker: time
milestone_id: first-corrected-conversation-loop
milestone_seq: 1
milestone_status: open
---

# Roadmap: TalkAItive

> Wygenerowane z `context/foundation/prd.md` + auto-zbadanego baseline'u kodu.
> Edytuj w miejscu; archiwizuj przy pełnej regeneracji.
> Zadania (slices) poniżej są ułożone w kolejności zależności. Tabela "At a glance" to indeks.

## Milestone

**M-1: Pierwsza działająca pętla rozmowy z korektą i pamięcią** — Status: open

- **Intent:** Dowieźć najmniejszy kompletny, realnie używalny rdzeń TalkAItive — rozmowę po niemiecku z korektą wplecioną na bieżąco, listą błędów po sesji i pamięcią między sesjami — tak, żeby autor i jego żona mogli faktycznie zacząć z niego korzystać.
- **Source materials:** `context/foundation/prd.md` (v1)
- **Done when:** każdy F-NN i S-NN poniżej ma status `done`.
- **Scope anchors:** wszystkie must-have FR z PRD (FR-001, FR-003…FR-010, FR-012, FR-013) i US-01.

## Vision recap

Obcokrajowcy mieszkający w Niemczech na poziomie B1–B2 nie mają z kim ćwiczyć mówienia w codziennych sytuacjach (spacer, sklep, sąsiad), a wieczorne okienko na naukę bywa krótkie i nieregularne. Zwykła rozmowa z modelem na czacie tego nie rozwiązuje: model zapomina, co było wcześniej, i nie domyka pętli błędów między sesjami. TalkAItive ma to naprawić przez pamięć rozłożoną na sesje (inspiracja: Observational Memory — technika utrzymywania kontekstu rozmowy między sesjami przez kompresję wniosków, a nie zapis surowej historii) i korektę wplecioną naturalnie w rozmowę, zamiast przerywać ją wykładem z gramatyki.

## North star

**S-01: Pierwsza pełna rozmowa z korektą na bieżąco** — to najmniejszy kompletny fragment produktu, który da się zbudować i pokazać jako pierwszy, zgodnie z wybranym celem sekwencjonowania (`speed`).

> Gwiazda przewodnia (ang. north star) to tu najmniejszy kompletny fragment produktu, którego udane dowiezienie dowodzi, że reszta ma sens — umieszczamy go tak wcześnie, jak pozwalają na to zależności, bo wszystko inne ma znaczenie tylko wtedy, gdy to działa.

## At a glance

| ID   | Change ID                    | Outcome (user can …)                                                                                         | Prerequisites | PRD refs                                | Status   |
| ---- | ----------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------- | -------- |
| F-01 | auth-and-access-scaffold      | (foundation) zaproszony użytkownik loguje się e-mailem i hasłem; każda strona poza logowaniem wymaga logowania; dane każdego użytkownika są odizolowane | —              | FR-001, NFR Prywatność, Access Control  | done |
| S-01 | first-corrected-conversation  | wybrać temat, prowadzić rozmowę po niemiecku z korektą wplecioną na bieżąco i zakończyć ją (przyciskiem albo przez agenta) | F-01           | FR-003, FR-004, FR-005, FR-006, FR-007, FR-012, US-01 | done |
| S-02 | post-conversation-error-list  | zobaczyć po zakończeniu rozmowy uporządkowaną listę błędów (kategoria, wersja błędna → poprawna)                | S-01           | FR-008                                  | proposed |
| S-03 | cross-session-error-memory    | zacząć kolejną rozmowę, w której agent nawiązuje do wcześniejszych wątków i błędów pasujących do tematu, bez powtarzania pytań | S-01, S-02     | FR-009, FR-010, US-01                   | proposed |
| S-04 | account-and-data-deletion     | usunąć swoje konto wraz ze wszystkimi danymi (rozmowy, błędy, pamięć)                                            | F-01           | FR-013, NFR Usuwanie danych             | proposed |

## Streams

Pomoc nawigacyjna — grupuje zadania wg wspólnego łańcucha zależności. Kanoniczna kolejność nadal wynika z grafu zależności poniżej; ta tabela to zaproponowana kolejność czytania po równoległych ścieżkach.

| Stream | Temat                    | Łańcuch                              | Notatka                                                                                   |
| ------ | ------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------- |
| A      | Pętla rozmowy i pamięć    | `F-01` → `S-01` → `S-02` → `S-03`     | Realizuje gwiazdę przewodnią i główną hipotezę produktu; cel `speed` stawia tę ścieżkę na pierwszym miejscu. |
| B      | Zarządzanie kontem        | `S-04`                                | Gałąź równoległa do Stream A — jedyny prerequisite to `F-01` (patrz Stream A); można budować w dowolnym momencie po nim. |

## Baseline

Co już jest w kodzie na dzień `2026-09-29` (auto-zbadane przez podagentów + potwierdzone przez użytkownika).
Foundations poniżej zakładają ten stan i NIE odtwarzają go od nowa.

- **Frontend:** absent — brak własnych szablonów/statyków; jedyny UI to domyślny `/admin/` (`talkaitive/settings.py:62-69`).
- **Backend / API:** absent — tylko `/admin/` i `/healthz/` w `urls.py`; brak własnej aplikacji Django, brak `views.py`/`models.py`.
- **Data:** absent — brak własnych modeli i migracji; obecnie skonfigurowane SQLite jako fallback (`talkaitive/settings.py:107-112`), Postgres podpięty w produkcji przez `DATABASE_URL`.
- **Auth:** absent — tylko domyślne logowanie do `/admin/`; brak własnego logowania e-mail+hasło i mechanizmu zaproszeń dla użytkowników produktu.
- **Deploy / infra:** present — Railway, auto-deploy z `main` działa, `/healthz/` zweryfikowany (`context/deployment/deploy-plan.md`).
- **Observability:** absent — brak logowania strukturalnego i integracji APM/Sentry; jedyny sygnał to `/healthz/`.

## Foundations

### F-01: Auth i izolacja danych między użytkownikami

- **Outcome:** (foundation) zaproszony użytkownik może zalogować się e-mailem i hasłem; każda strona poza logowaniem przekierowuje do logowania; każde zapytanie o rozmowy/błędy/pamięć jest ograniczone do zalogowanego użytkownika.
- **Change ID:** auth-and-access-scaffold
- **PRD refs:** FR-001, NFR Prywatność, sekcja Access Control
- **Unlocks:** S-01, S-02, S-03, S-04 — każdy z nich wymaga zalogowanego, odizolowanego użytkownika; redukuje ryzyko złamania gwarancji prywatności (rozmowy/błędy/pamięć jednej osoby nigdy widoczne dla innej, w tym dla właściciela).
- **Prerequisites:** —
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** wszystko poniżej potrzebuje logowania i izolacji danych per użytkownik; zrobienie tego jako pierwsze unika domieszania kontroli prywatności do już napisanego kodu rozmów, co byłoby ryzykowniejsze dla tej gwarancji.
- **Status:** done

## Slices

### S-01: Pierwsza pełna rozmowa z korektą na bieżąco

- **Outcome:** zalogowany użytkownik może wybrać jeden z 20 tematów, prowadzić tekstową rozmowę po niemiecku, otrzymywać korektę błędnych wypowiedzi wplecioną w odpowiedź agenta (recast) bez przerywania rozmowy, i zakończyć rozmowę przyciskiem „Zakończ” albo przez agenta (pożegnanie / wyczerpany dzienny limit, z komunikatem o limicie).
- **Change ID:** first-corrected-conversation
- **PRD refs:** FR-003, FR-004, FR-005, FR-006, FR-007, FR-012, US-01
- **Prerequisites:** F-01
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:**
  - Jaka jest dokładna wartość dziennego limitu (minuty / liczba wypowiedzi) i od której godziny liczy się nowy dzień? — Owner: user. Block: no (można ruszyć z rozsądną wartością domyślną i dopracować na etapie `/10x-plan`).
  - Czy tekstowa rozmowa w MVP przenosi się na umiejętność mówienia? — Owner: user. Block: no (ryzyko świadomie zaakceptowane w PRD jako scope-down; do zweryfikowania po realnym użyciu, nie blokuje budowy).
- **Risk:** to jest gwiazda przewodnia. FR-003/004/005/006/007/012 zostały celowo utrzymane w jednym zadaniu (nie rozbite na mniejsze), bo opisują jedną, niepodzielną czynność użytkownika — „odbyć rozmowę od początku do końca” — a każdy mniejszy podział (np. „rozmowa bez korekty” albo „rozmowa bez możliwości zakończenia”) dawałby fragment niemożliwy do sensownego pokazania czy przetestowania. PRD samo ma tu tylko jedną historyjkę użytkownika (US-01) obejmującą ten sam zakres.
- **Status:** done

### S-02: Lista błędów po zakończeniu rozmowy

- **Outcome:** użytkownik może po zakończeniu rozmowy zobaczyć uporządkowaną listę błędów z tej rozmowy: kategoria (gramatyka / słownictwo / szyk zdania), wersja błędna → poprawna.
- **Change ID:** post-conversation-error-list
- **PRD refs:** FR-008
- **Prerequisites:** S-01
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:** —
- **Risk:** zależy od istnienia danych z realnej rozmowy (S-01), dlatego jest zaraz po niej — dzięki temu logika wykrywania błędów użytej w korekcie na żywo (S-01) i w liście końcowej nie jest budowana dwa razy od zera.
- **Status:** proposed

### S-03: Pamięć między rozmowami i domykanie pętli błędów

- **Outcome:** użytkownik może rozpocząć kolejną rozmowę, w której agent uwzględnia wcześniej omawiane wątki pasujące do wybranego tematu, nie powtarza wcześniej zadanych pytań i naturalnie stwarza okazje do użycia konstrukcji, w których użytkownik wcześniej się mylił — bez informowania wprost, że to poprawka.
- **Change ID:** cross-session-error-memory
- **PRD refs:** FR-009, FR-010, US-01
- **Prerequisites:** S-01, S-02
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:** —
- **Risk:** to jest dokładnie ta różnica, którą Wizja w PRD nazywa wprost jako przewagę nad zwykłym czatem („nie pamięta, co już było omawiane”) — mocniej testuje główną hipotezę produktu niż sam S-01, ale wymaga najpierw danych z S-01 i S-02, więc nie może być wcześniej; mimo to nie powinno być odkładane bez powodu, bo to druga po S-01 najważniejsza rzecz do zweryfikowania.
- **Status:** proposed

### S-04: Usunięcie konta wraz z danymi

- **Outcome:** użytkownik może usunąć swoje konto wraz ze wszystkimi danymi (rozmowy, błędy, pamięć), z trwałym usunięciem w ciągu 24 godzin.
- **Change ID:** account-and-data-deletion
- **PRD refs:** FR-013, NFR Usuwanie danych
- **Prerequisites:** F-01
- **Parallel with:** S-01, S-02, S-03
- **Blockers:** —
- **Unknowns:** —
- **Risk:** utrzymane niezależnie od zadań rozmowy/pamięci, żeby dało się je zbudować równolegle zaraz po F-01; warto wracać do niego przy każdym nowym modelu danych (S-02, S-03), żeby usuwanie konta dalej obejmowało wszystko.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                   | Suggested issue title                                         | Ready for `/10x-plan` | GitHub Issue | Linear Issue | Notes                                   |
| ---------- | ----------------------------- | ---------------------------------------------------------------- | ---------------------- | ------------- | ------------- | ------------------------------------------ |
| F-01       | auth-and-access-scaffold      | Auth i izolacja danych między użytkownikami                     | yes                    | [#1](https://github.com/LukaszSwiech/talkaitive/issues/1) | [LUK-16](https://linear.app/lukaszswiech/issue/LUK-16/f-01-auth-i-izolacja-danych-miedzy-uzytkownikami) | Fundament pod wszystkie zadania poniżej |
| S-01       | first-corrected-conversation  | Pierwsza rozmowa po niemiecku z korektą na bieżąco (gwiazda przewodnia) | yes                    | [#2](https://github.com/LukaszSwiech/talkaitive/issues/2) | [LUK-17](https://linear.app/lukaszswiech/issue/LUK-17/s-01-pierwsza-rozmowa-po-niemiecku-z-korekta-na-biezaco-gwiazda) | F-01 `done` (2026-10-03). Następny krok: `/10x-plan first-corrected-conversation`. |
| S-02       | post-conversation-error-list  | Lista błędów po zakończonej rozmowie                             | no                     | [#3](https://github.com/LukaszSwiech/talkaitive/issues/3) | [LUK-18](https://linear.app/lukaszswiech/issue/LUK-18/s-02-lista-bledow-po-zakonczonej-rozmowie) | Czeka na S-01                            |
| S-03       | cross-session-error-memory    | Pamięć między rozmowami i domykanie pętli błędów                | no                     | [#4](https://github.com/LukaszSwiech/talkaitive/issues/4) | [LUK-19](https://linear.app/lukaszswiech/issue/LUK-19/s-03-pamiec-miedzy-rozmowami-i-domykanie-petli-bledow) | Czeka na S-01, S-02                      |
| S-04       | account-and-data-deletion     | Usunięcie konta wraz z danymi                                   | no                     | [#5](https://github.com/LukaszSwiech/talkaitive/issues/5) | [LUK-20](https://linear.app/lukaszswiech/issue/LUK-20/s-04-usuniecie-konta-wraz-z-danymi) | Czeka na F-01; może ruszyć równolegle z S-01 |

**Dozwolone wartości `Status:`:** `proposed`, `ready`, `planning`, `in-progress`, `blocked`, `done`. (`planning` = jest `plan.md` z `/10x-plan`, implementacja jeszcze nie ruszyła.)

**Synchronizacja statusów (bez integracji, wykonywana przez agenta):** Pole `Status:` przy każdym F-NN/S-NN w sekcjach `## Foundations` / `## Slices` powyżej jest jedynym źródłem prawdy (single source of truth). GitHub Issues i Linear to dwa **niezależne** lustra roadmapy — żadna integracja nie synchronizuje ich ani z roadmapą, ani między sobą (świadoma decyzja: brak cross-linków/integracji Linear↔GitHub). Dlatego agent, który zmienia `Status:` pozycji (na prośbę użytkownika albo w ramach skilla, np. `/10x-plan`, `/10x-implement`, `/10x-archive`), w tej samej turze i bez osobnej prośby: zaktualizuje odpowiedni GitHub Issue z tej tabeli (`gh issue edit/close`), osobno przestawi stan w Linear (`mcp__linear__save_issue`, pole `state`) i poprawi tabele mapowania w `tasks-github.md` i `tasks-linear.md`. Pełna mechanika: `context/foundation/tasks-github.md` (GitHub), `context/foundation/tasks-linear.md` (Linear).

## Open Roadmap Questions

| ID | Question | Owner | Block | GitHub Issue | Linear Issue |
| ---- | ---------- | ------ | ------- | -------------- | -------------- |
| Q-01 | Jak Praktika rozwiązuje pamięć między sesjami, kontrolę poziomu CEFR i informację zwrotną o błędach? | user | — (informacyjne; wpływa na to, jak mocno wgląd odróżnia produkt, ale nie blokuje żadnego etapu) | [#6](https://github.com/LukaszSwiech/talkaitive/issues/6) | [LUK-21](https://linear.app/lukaszswiech/issue/LUK-21/q-01-jak-praktika-rozwiazuje-pamiec-miedzy-sesjami-kontrole-poziomu) |
| Q-02 | Czy MVP zdąży przed terminem miękkim (2026-11-04)? | user | — (kwestia tempa całego milestone'a, nie konkretnego zadania) | [#7](https://github.com/LukaszSwiech/talkaitive/issues/7) | [LUK-22](https://linear.app/lukaszswiech/issue/LUK-22/q-02-czy-mvp-zdazy-przed-terminem-miekkim-2026-11-04) |
| Q-03 | Ile razy w tygodniu oznacza „regularne używanie” w Primary Success Criterion? | user | — (potrzebne, żeby ocenić, czy milestone spełnił swój warunek „Done when”, ale nie blokuje samego budowania) | [#8](https://github.com/LukaszSwiech/talkaitive/issues/8) | [LUK-23](https://linear.app/lukaszswiech/issue/LUK-23/q-03-ile-razy-w-tygodniu-oznacza-regularne-uzywanie-w-primary-success) |
| Q-04 | Jak ma wyglądać zakładanie kont po MVP? | user | — (dotyczy kolejnego milestone'a; F-01 w pełni pokrywa zakres MVP) | [#9](https://github.com/LukaszSwiech/talkaitive/issues/9) | [LUK-24](https://linear.app/lukaszswiech/issue/LUK-24/q-04-jak-ma-wygladac-zakladanie-kont-po-mvp) |
| Q-05 | Jakie są niefunkcjonalne non-goals MVP? | user | no | [#10](https://github.com/LukaszSwiech/talkaitive/issues/10) | [LUK-25](https://linear.app/lukaszswiech/issue/LUK-25/q-05-jakie-sa-niefunkcjonalne-non-goals-mvp) |
| Q-06 | Jaki jest ballpark `target_scale.qps` i `target_scale.data_volume`? | user | no | [#11](https://github.com/LukaszSwiech/talkaitive/issues/11) | [LUK-26](https://linear.app/lukaszswiech/issue/LUK-26/q-06-jaki-jest-ballpark-target-scaleqps-i-target-scaledata-volume) |

**Synchronizacja statusów (bez integracji, wykonywana przez agenta, GitHub i Linear niezależnie od siebie):** tak jak w `Backlog Handoff` — gdy pytanie zostaje rozstrzygnięte, agent w tej samej turze i bez osobnej prośby zamyka odpowiedni GitHub Issue (`gh issue close`), osobno przestawia Linear issue na `Done` (`mcp__linear__save_issue`, pole `state`), usuwa lub oznacza jako rozwiązany odpowiedni wiersz w tej tabeli i poprawia tabele mapowania w `tasks-github.md` i `tasks-linear.md`. Pełna mechanika: `context/foundation/tasks-github.md`, `context/foundation/tasks-linear.md`.

## Parked

- **Wylogowanie (FR-002)** — Why parked: zdegradowane z must-have do nice-to-have w rundzie sokratejskiej; PRD Non-Goals: poza zakresem wiążącym MVP.
- **Oznaczanie zagadnienia jako opanowanego po N poprawnych użyciach (FR-011)** — Why parked: nice-to-have, jawnie „po MVP” zarówno w rundzie sokratejskiej, jak i w Non-Goals (statystyki postępu).
- **Rozmowa głosowa (naciśnij i mów, odpowiedź głosem)** — Why parked: PRD Non-Goals — scope-down z fazy 3; głos dopiero po MVP.
- **Historia rozmów i edycja błędów/pamięci** — Why parked: PRD Non-Goals — celem MVP jest rozmawianie, nie analiza.
- **Przygotowanie do egzaminu Goethe-Institut** — Why parked: persona drugorzędna, poza zakresem MVP (PRD Non-Goals).
- **Wybór poziomu CEFR** — Why parked: PRD Non-Goals — stały poziom B1–B2.
- **Samoobsługa konta (rejestracja, reset hasła)** — Why parked: PRD Non-Goals — obsługuje wyłącznie właściciel poza produktem.
- **Inne języki niż niemiecki** — Why parked: PRD Non-Goals.
- **Ćwiczenia i testy (fiszki, quizy)** — Why parked: PRD Non-Goals — jedyną formą ćwiczenia jest rozmowa.
- **Statystyki postępu (wykresy, panel)** — Why parked: PRD Non-Goals.

## Milestone History

(Puste — to pierwszy milestone.)

## Done

- **F-01: (foundation) zaproszony użytkownik może zalogować się e-mailem i hasłem; każda strona poza logowaniem przekierowuje do logowania; każde zapytanie o rozmowy/błędy/pamięć jest ograniczone do zalogowanego użytkownika.** — Archived 2026-10-03 → `context/archive/2026-10-01-auth-and-access-scaffold/`. Lesson: —.
- **S-01: zalogowany użytkownik może wybrać jeden z 20 tematów, prowadzić tekstową rozmowę po niemiecku, otrzymywać korektę błędnych wypowiedzi wplecioną w odpowiedź agenta (recast) bez przerywania rozmowy, i zakończyć rozmowę przyciskiem „Zakończ” albo przez agenta (pożegnanie / wyczerpany dzienny limit, z komunikatem o limicie).** — Archived 2026-10-06 → `context/archive/2026-10-05-first-corrected-conversation/`. Lesson: —.
