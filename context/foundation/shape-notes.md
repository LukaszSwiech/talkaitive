---
project: "TalkAItive"
context_type: greenfield
created: 2026-09-17
updated: 2026-09-19
product_type: web-app
target_scale:
  users: small
timeline_budget:
  mvp_weeks: 10
  hard_deadline: 2026-12-06
  after_hours_only: true
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  gray_areas_resolved:
    - topic: "context type"
      decision: "greenfield — nowy projekt od zera"
    - topic: "primary persona"
      decision: "codzienne sytuacje (spacer, sklep, sąsiad); przygotowanie do egzaminu Goethe jako persona drugorzędna poza MVP"
    - topic: "skill focus"
      decision: "mówienie; rozumienie ze słuchu tylko przy okazji (odpowiedzi głosowe), bez osobnych ćwiczeń ze słuchu"
    - topic: "auth"
      decision: "e-mail + hasło; rejestracja tylko na zaproszenie wystawiane przez właściciela poza produktem"
    - topic: "roles"
      decision: "płaskie; każdy widzi tylko własne dane"
    - topic: "model costs"
      decision: "ponosi aplikacja; dzienny limit na użytkownika; po przekroczeniu agent kończy rozmowę"
    - topic: "MVP scope"
      decision: "scope down: rozmowa tekstowa w MVP, głos (naciśnij i mów + odpowiedź głosem) po MVP; jeden sposób zakończenia rozmowy (przycisk „Zakończ” + zamknięcie przez agenta); pamięć w stylu OM i 20 tematów zostają w MVP"
    - topic: "error correction style"
      decision: "hybryda: recast w locie + uporządkowana lista błędów na koniec rozmowy"
    - topic: "conversation history visibility"
      decision: "użytkownik widzi tylko bieżącą rozmowę; brak wglądu w poprzednie — celem jest rozmawianie, nie analiza"
    - topic: "error list / memory editing"
      decision: "użytkownik nie edytuje błędów ani pamięci"
    - topic: "mastery tracking"
      decision: "oznaczanie zagadnienia jako opanowanego po N poprawnych użyciach — nice-to-have, po MVP"
    - topic: "password reset"
      decision: "reset przez właściciela poza produktem; brak samodzielnego resetu w MVP"
    - topic: "data deletion"
      decision: "użytkownik może usunąć konto wraz ze wszystkimi danymi"
    - topic: "CEFR level"
      decision: "stały poziom B1–B2; użytkownik nie wybiera poziomu"
  frs_drafted: 13
  quality_check_status: accepted
---

# Shape notes — TalkAItive

## Seed idea

> Aplikacja webowa do ćwiczenia mówienia po niemiecku dla osób na poziomie B1–B2, które nie mają z kim rozmawiać. Przepływ: logowanie → wybór jednego z 20 tematów → rozmowa z modelem → wykrywanie błędów, korekta wpleciona w odpowiedź, zapis błędu. Aplikacja pamięta wcześniejsze rozmowy i błędy (inspiracja: Observational Memory), żeby nie powtarzać pytań. Rozmowa głosowa (STT/TTS). Preferowany język: Python.
> Otwarte pytania: co dokładnie zapamiętywać między sesjami; głos na żywo czy „naciśnij i mów”; klucz API użytkownika czy serwerowy.

## Vision & Problem Statement

Obcokrajowcy mieszkający w Niemczech na poziomie B1–B2 uczą się języka z aplikacji, które ćwiczą pisanie i czytanie, ale nie mówienie. W codziennych sytuacjach — spacer z psem i rozmowa z właścicielem innego psa, sklep, spotkanie z sąsiadem — nie potrafią nic powiedzieć. Wieczorem po pracy mają chwilę na naukę, ale nie mają z kim ćwiczyć rozmowy, a czas bywa różny: raczej 15 minut codziennie o zmiennej porze niż godzina raz w tygodniu o stałej.

Rozmowa z modelem językowym na czacie nie rozwiązuje problemu: po kilku dniach model pyta o to samo, nie pamięta, co już było omawiane, nie poprawia błędów systematycznie, a ograniczony kontekst i niska skuteczność kompresji historii gubią ciągłość. Wgląd: rozwiązanie wymaga świadomego zarządzania kontekstem między sesjami (inspiracja: Observational Memory), rozmów utrzymanych na stałym poziomie B1–B2 oraz zamkniętej pętli informacji zwrotnej między sesjami — błędy z jednej rozmowy wracają w kolejnych. Rozwiązania z nauczycielem na żywo nie dają dostępności o dowolnej porze.

Skala (sonda 100x): przy stukrotnie większej liczbie użytkowników reguła biznesowa się nie zmienia; do gry wchodzą wydajność logowania oraz samodzielne zakładanie konta bez kontaktu z właścicielem aplikacji.

## User & Persona

**Persona główna:** osoba mieszkająca w Niemczech, ucząca się niemieckiego na poziomie B1–B2 (np. autor projektu i jego żona). Pracuje w ciągu dnia; wieczorem ma krótkie, nieregularne okienko na naukę. Sięga po produkt, gdy chce przećwiczyć rozmowę z codziennej sytuacji, w której wcześniej zabrakło jej słów. Ćwiczy przede wszystkim mówienie; rozumienie ze słuchu ćwiczy się przy okazji.

### Secondary persona

Osoba przygotowująca się do części ustnej egzaminu Goethe-Institut. Poza zakresem MVP.

## MVP flow

Pierwotny przepływ (przed zmniejszeniem zakresu): logowanie → wybór tematu → naciśnij i mów / stop → odpowiedź głosowa agenta z recastem → powtarzanie → zakończenie (wylogowanie, 5 min ciszy, agent kończy przy pożegnaniu lub limicie) → lista błędów → kompresja wniosków do pamięci → kolejna sesja z wiedzą o poprzednich.

Po zmniejszeniu zakresu (MVP):

1. Użytkownik loguje się, widzi listę 20 tematów i wybiera jeden.
2. Użytkownik pisze wypowiedź po niemiecku.
3. Agent odpowiada tekstem; jeśli wypowiedź zawierała błąd, wplata poprawną wersję w odpowiedź (recast) bez przerywania rozmowy.
4. Kroki 2–3 się powtarzają.
5. Rozmowa kończy się przyciskiem „Zakończ” albo zamyka ją agent (użytkownik się żegna, wyczerpany limit).
6. Użytkownik widzi uporządkowaną listę błędów z rozmowy: kategoria (gramatyka / słownictwo / szyk zdania), wersja błędna → poprawna.
7. Wnioski z sesji trafiają do pamięci po kompresji (nie surowy zapis rozmowy).
8. Kolejna sesja: agent wie, co było omawiane i jakie błędy się pojawiały; tworzy okazje do użycia poprawianych konstrukcji, nie mówiąc wprost, że to poprawka.

## Timeline notes

Informacyjne — uzupełnienie `timeline_budget` z frontmattera.

- **Termin miękki:** 2026-11-04 (pierwszy termin oddania projektu).
- **Termin twardy:** 2026-12-06 (drugi termin oddania projektu) — zapisany jako `hard_deadline`.
- **Dostępny czas:** praca po godzinach, ok. 10 h tygodniowo — łącznie na naukę i budowę produktu.
- **Szacunek MVP:** 10 tygodni (pod termin twardy).

## Timeline acknowledgment

Acknowledged on 2026-09-19: 10-week MVP requires sustained dedication; user accepted. MVP (pamięć w stylu OM, 20 tematów, dzienny limit, usuwanie konta) przekracza typowe 3 tygodnie pracy po godzinach; przy ~10 h tygodniowo dzielonych z nauką termin miękki (2026-11-04) jest zagrożony, a termin twardy (2026-12-06) nie zostawia bufora.

## Success Criteria

### Primary
- Aplikacja jest nadal regularnie używana (przez autora i jego żonę) po miesiącu — w odróżnieniu od zwykłego czatu z modelem, który został porzucony.

### Secondary
- Lista błędów jest trafna: użytkownik zgadza się z wykrytymi błędami i ich kategoriami.

### Guardrails
- Korekta nie przerywa rozmowy: poprawka jest wpleciona naturalnie, rozmowa nie zamienia się w wykład z gramatyki.
- Prywatność rozmów: rozmowy, błędy i pamięć jednej osoby nigdy nie są widoczne dla innej.

## User Stories

### US-01: Rozmowa na wybrany temat z korektą i pamięcią błędów

- **Given** zalogowany użytkownik, który w poprzedniej rozmowie popełnił błąd (np. szyk zdania w zdaniu podrzędnym), ma dostępny dzienny limit
- **When** wybiera jeden z 20 tematów, prowadzi tekstową rozmowę po niemiecku i kończy ją przyciskiem „Zakończ”
- **Then** w trakcie rozmowy agent wplata poprawne wersje błędnych wypowiedzi bez przerywania rozmowy, stwarza okazję do użycia konstrukcji z poprzedniej rozmowy i nie powtarza wcześniej zadanych pytań; po zakończeniu użytkownik widzi listę błędów (kategoria, wersja błędna → poprawna)

## Functional Requirements

### Konto i dostęp
- FR-001: Zaproszony użytkownik może zalogować się e-mailem i hasłem. Priority: must-have
  > Socrates: Rozważono, czy e-mail + hasło to nie za dużo dla dwóch osób. Rozstrzygnięcie: zostaje — to świadome uproszczenie na MVP; w wersji docelowej zakładanie kont ma działać inaczej (zob. Open Questions).
- FR-002: Użytkownik może się wylogować. Priority: nice-to-have
  > Socrates: Kontrargument przyjęty: „nikt nie będzie się wylogowywał”. Rozstrzygnięcie: zdegradowane z must-have do nice-to-have.
- FR-013: Użytkownik może usunąć swoje konto wraz ze wszystkimi danymi (rozmowy, błędy, pamięć). Priority: must-have
  > Socrates: Rozważono (nieużywane przy 2 osobach; nieodwracalne przez pomyłkę). Rozstrzygnięcie: brak kontrargumentu, zostaje bez zmian.

### Rozmowa
- FR-003: Użytkownik może wybrać jeden z 20 tematów rozmowy. Priority: must-have
  > Socrates: Kontrargument rozważony: „wybór tematu to tarcie w krótkim wieczornym okienku”. Rozstrzygnięcie: zostaje bez zmian — użytkownik sam wybiera z 20 tematów.
- FR-004: Użytkownik może prowadzić tekstową rozmowę po niemiecku z agentem na wybrany temat. Priority: must-have
  > Socrates: Kontrargument przyjęty jako ryzyko: „tekst to nie mówienie” — pisanie może nie przenosić się na mowę, więc MVP może nie sprawdzić głównej hipotezy. Rozstrzygnięcie: zostaje (scope down z fazy 3, głos po MVP); ryzyko w Open Questions.
- FR-005: Użytkownik może otrzymać w odpowiedzi agenta poprawną wersję swojej błędnej wypowiedzi, wplecioną w rozmowę. Priority: must-have
  > Socrates: Kontrargument rozważony: „recast bywa niezauważony”. Rozstrzygnięcie: zostaje bez zmian — lista błędów po rozmowie (FR-008) domyka lukę.
- FR-006: Użytkownik może zakończyć rozmowę przyciskiem „Zakończ”. Priority: must-have
  > Socrates: Kontrargument rozważony: „użytkownik po prostu zamknie kartę”. Rozstrzygnięcie: zostaje; akceptowane, że w MVP sesja zamknięta bez „Zakończ” przepada (brak listy błędów i zapisu do pamięci).
- FR-007: Agent może zakończyć rozmowę, gdy użytkownik się żegna lub wyczerpał dzienny limit, i informuje o tym użytkownika. Priority: must-have
  > Socrates: Rozważono (fałszywe pożegnania w scenkach; cięcie w pół zdania po limicie). Rozstrzygnięcie: brak kontrargumentu, zostaje bez zmian.
- FR-008: Użytkownik może po zakończeniu rozmowy zobaczyć listę błędów z tej rozmowy (kategoria, wersja błędna → poprawna). Priority: must-have
  > Socrates: Rozważono (lista demotywuje; znika po zamknięciu; 3 kategorie za mało). Rozstrzygnięcie: brak kontrargumentu, zostaje bez zmian.

### Pamięć i postęp
- FR-009: Użytkownik może rozpocząć kolejną rozmowę, w której agent uwzględnia wcześniej omawiane wątki pasujące do wybranego tematu i nie powtarza pytań. Priority: must-have
  > Socrates: Kontrargument przyjęty: „pamięć wcina się w temat”. Rozstrzygnięcie: doprecyzowane — agent nawiązuje do wcześniejszych wątków tylko wtedy, gdy pasują do wybranego tematu.
- FR-010: Użytkownik może w kolejnych rozmowach ćwiczyć konstrukcje, w których wcześniej się mylił, bez informacji wprost, że to poprawka; agent stwarza takie okazje tylko wtedy, gdy naturalnie pasują do tematu rozmowy. Priority: must-have
  > Socrates: Kontrargument przyjęty: „wymuszone okazje brzmią sztucznie”. Rozstrzygnięcie: doprecyzowane — okazje tylko, gdy pasują do tematu.
- FR-011: Aplikacja oznacza zagadnienie jako opanowane po N poprawnych użyciach (np. 3). Priority: nice-to-have
  > Socrates: Rozważono (N użyć ≠ opanowanie; niewidoczne dla użytkownika). Rozstrzygnięcie: brak kontrargumentu, zostaje jako nice-to-have po MVP.

### Limit
- FR-012: Użytkownik może zobaczyć komunikat o wyczerpanym limicie i o tym, od kiedy może rozmawiać ponownie. Priority: must-have
  > Socrates: Rozważono (limit bez podglądu zaskakuje; limit zbyteczny dla 2 osób). Rozstrzygnięcie: brak kontrargumentu, zostaje bez zmian.

## Non-Functional Requirements

- **Prywatność:** rozmowy, błędy i pamięć jednej osoby nigdy nie są widoczne dla innej osoby — w tym dla właściciela w produkcie.
- **Usuwanie danych:** po usunięciu konta wszystkie dane użytkownika (rozmowy, błędy, pamięć) są trwale usunięte w ciągu 24 godzin.
- **Informacja zwrotna podczas czekania:** użytkownik przez cały czas oczekiwania na odpowiedź agenta widzi, że odpowiedź jest przygotowywana.
- **Czas odpowiedzi agenta:** świadomie bez progu liczbowego — zależy od dostawcy modelu i jest poza kontrolą produktu.

## Business Logic

Aplikacja ocenia poprawność każdego zdania użytkownika, a do kolejnych rozmów wybiera wcześniejsze błędy, które pasują do wybranego tematu, z pierwszeństwem dla błędów częstych i świeżych.

**Wejścia:** tekst wypowiedzi użytkownika w bieżącej rozmowie; wybrany temat rozmowy; błędy zapamiętane z wcześniejszych rozmów tego użytkownika.

**Wyjście:** w trakcie rozmowy — poprawna wersja błędnej wypowiedzi wpleciona w odpowiedź (recast); po rozmowie — lista błędów (kategoria: gramatyka / słownictwo / szyk zdania, wersja błędna → poprawna); w kolejnej rozmowie — okazje do użycia konstrukcji z wybranych wcześniejszych błędów, bez informacji wprost, że to poprawka.

**Kryterium wyboru błędów na kolejną rozmowę:** warunek konieczny — błąd pasuje do wybranego tematu. Wśród pasujących pierwszeństwo ma częstość błędu (błąd powtarzany w wielu rozmowach), w drugiej kolejności świeżość (błąd z ostatnich rozmów).

## Access Control

- **Logowanie:** e-mail + hasło.
- **Rejestracja:** wyłącznie na zaproszenie. Brak publicznego formularza rejestracji. Zaproszenia / konta tworzy właściciel aplikacji poza produktem (bez roli administratora w produkcie).
- **Role:** płaskie — jeden typ użytkownika. Każdy użytkownik widzi i modyfikuje wyłącznie własne rozmowy, błędy i pamięć. Nikt, w tym właściciel, nie ma w produkcie wglądu w dane innych użytkowników.
- **Koszty modeli:** ponosi aplikacja. Każdy użytkownik ma dzienny limit. Gdy limit zostanie przekroczony w trakcie rozmowy, agent komunikuje, że musi zakończyć rozmowę, i rozmowa się kończy (bez otwartego „dokończenia”). Po wyczerpaniu limitu użytkownik widzi komunikat, od kiedy może rozmawiać ponownie.
- **Niezalogowany użytkownik:** każda strona poza logowaniem przekierowuje do logowania.
- **Zapomniane hasło:** reset wykonuje właściciel poza produktem; brak samodzielnego resetu w MVP.
- **Widoczność danych we własnym koncie:** użytkownik widzi tylko bieżącą rozmowę i listę błędów po jej zakończeniu; nie ma wglądu w poprzednie rozmowy ani w pamięć i nie może ich edytować. Może usunąć konto wraz ze wszystkimi danymi.

## Non-Goals

### Funkcjonalne
- **Brak rozmowy głosowej** — ani mowy na wejściu, ani odpowiedzi głosem; głos (naciśnij i mów) dopiero po MVP, zgodnie ze scope down z fazy 3.
- **Brak historii rozmów i edycji** — użytkownik nie przegląda poprzednich rozmów i nie edytuje błędów ani pamięci; celem jest rozmawianie, nie analiza.
- **Brak przygotowania do egzaminu Goethe** — persona drugorzędna poza MVP.
- **Brak wyboru poziomu** — stały poziom B1–B2; brak innych poziomów CEFR.
- **Brak samoobsługi konta** — brak samodzielnej rejestracji i resetu hasła; konta i reset obsługuje właściciel poza produktem.
- **Tylko niemiecki** — brak innych języków do nauki.
- **Brak ćwiczeń i testów** — brak osobnych ćwiczeń gramatycznych, fiszek, quizów; jedyną formą ćwiczenia jest rozmowa.
- **Brak statystyk postępu** — brak wykresów, podsumowań i panelu postępu; oznaczanie zagadnień jako opanowanych (FR-011) jest nice-to-have po MVP.
- **Wylogowanie poza zakresem wiążącym MVP** — FR-002 zdegradowany do nice-to-have w rundzie sokratejskiej.

## Open Questions

1. **Jak Praktika rozwiązuje pamięć między sesjami, kontrolę poziomu CEFR i informację zwrotną o błędach?** — Autor nie znalazł dokładnych informacji; od odpowiedzi zależy, na ile wgląd odróżnia produkt. Owner: user.
2. **Jaka jest wartość dziennego limitu (minuty / liczba wypowiedzi) i od której godziny liczy się nowy dzień?** — Owner: user.
3. **Czy MVP zdąży przed terminem miękkim (2026-11-04)?** — Przyjęty szacunek to 10 tygodni (pod termin twardy 2026-12-06); termin miękki wypada po ok. 6,5 tygodnia przy ~10 h tygodniowo dzielonych z nauką. Owner: user.
4. **Ile razy w tygodniu oznacza „regularne używanie” w kryterium Primary?** — Kryterium nie ma jeszcze progu liczbowego. Owner: user.
5. **Czy tekstowa rozmowa w MVP przenosi się na umiejętność mówienia?** — Ryzyko z rundy sokratejskiej (FR-004): pisanie może nie przenosić się na mowę, więc MVP może nie sprawdzić głównej hipotezy produktu. Owner: user.
6. **Jak ma wyglądać zakładanie kont po MVP?** — Logowanie na zaproszenie (FR-001) to świadome uproszczenie na MVP; docelowo ma być inny sposób tworzenia kont. Owner: user.

## Forward: tech-stack

Informacyjne — nie jest częścią PRD. Dla kroku wyboru stacku:

- Preferowany język: Python (z pomysłu wyjściowego).

## Forward: technical-roadmap

Informacyjne — nie jest częścią PRD. Pomysły autora dotyczące sposobu realizacji, do wykorzystania przy planowaniu implementacji:

- Zbieranie błędów: po zakończeniu lekcji (albo co N wymian — progressive logging) osobne, tanie wywołanie LLM z całym transkryptem, structured output (JSON): lista błędów z kategorią (gramatyka / słownictwo / szyk zdania), przykładem błędnym i poprawnym. W architekturze OM to rola Observera.
- Start kolejnej lekcji: skrócona lista błędów wstrzykiwana do system prompta głównego modelu z instrukcją w stylu „subtelnie stwórz okazje do użycia tych konstrukcji w rozmowie, nie wspominaj explicite, że to poprawka”.
- Zakończenie rozmowy przez agenta: model dostaje narzędzie (function tool / MCP) do zakończenia sesji — używa go, gdy użytkownik się żegna lub wyczerpał limit.
- Dane z sesji trafiają do bazy po kompresji w stylu OM (nie automatycznie, nie surowo); agent na wejściu ładuje to, co już wie.
- Po MVP: zakończenie rozmowy także przez wylogowanie i po 5 minutach bez wypowiedzi; głos w trybie naciśnij i mów.
