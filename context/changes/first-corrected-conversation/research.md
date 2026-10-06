---
date: 2026-10-05T20:11:04+0200
researcher: Claude (Opus 5.5) dla LukaszSwiech
git_commit: 4448ed1c38ba7b8ab70bcaa3a4fe2ce2ad211928
branch: main
repository: 10xDevs4 (TalkAItive)
topic: "Wybór modelu/dostawcy LLM + STT/TTS do płynnej rozmowy po niemiecku (czat teraz, głos po MVP)"
tags: [research, llm, voice, stt, tts, openai, gemini, elevenlabs, s-01]
status: complete
last_updated: 2026-10-05
last_updated_by: Claude (Opus 5.5)
---

# Research: dostawca LLM + głos (STT/TTS) dla TalkAItive

**Date**: 2026-10-05T20:11:04+0200
**Researcher**: Claude (Opus 5.5) dla LukaszSwiech
**Git Commit**: 4448ed1c38ba7b8ab70bcaa3a4fe2ce2ad211928
**Branch**: main
**Repository**: 10xDevs4 (TalkAItive)

## Research Question

Jaki model / dostawca najlepiej sprawdzi się w aplikacji do nauki rozmowy po niemiecku (B1–B2): płynna rozmowa po niemiecku/angielsku bez przestojów, dobre rozumienie, wysoka dostępność, i jednocześnie zwykły czat tekstowy. Czy dedykowana platforma (np. ElevenLabs Agents) jest lepsza niż OpenAI / Gemini, które poleca model planujący?

## Summary

1. **ElevenLabs Agents nie zastępuje OpenAI/Gemini, tylko je opakowuje.** „Mózg” agenta ElevenLabs to wybrany LLM (GPT-5.x, Gemini, Claude albo hostowany Qwen); ElevenLabs dokłada „uszy” (ASR), „usta” (TTS) i model przejmowania tury (https://elevenlabs.io/docs/agents-platform/customization/llm, strona bez daty, pobrana 2026-10-05). Dlatego model planujący poleca OpenAI/Gemini — wybór LLM i tak trzeba podjąć.
2. **Rekomendacja dla MVP (S-01, tylko tekst):** wywołuj tekstowy LLM bezpośrednio z Django (zwykłe API tekstowe, nie platforma agentów). Prompt, pamięć z Postgresa, narzędzie „zakończ rozmowę” i structured output zostają w kodzie aplikacji. U OpenAI i Google API głosowe (Realtime / Live) nie jest dobrym kanałem czatu: natywne modele Gemini Live zwracają tylko audio, a w OpenAI zwykłe Responses API jest prostsze niż sesja Realtime (szczegóły niżej). ElevenLabs ma tryb tekstowy, ale wtedy prompt i rozmowa przechodzą przez platformę.
3. **Wybór dostawcy LLM pod kątem głosu po MVP:** OpenAI to najbardziej kompletna opcja „jeden dostawca na tekst + głos” na dzień 2026-10-05: Realtime API jest GA, ma WebRTC z tokenem efemerycznym (który Django może wystawić jednym POST-em), function calling i rezydencję danych w UE obejmującą `/v1/realtime`. Gemini jest tańszy w audio, ale strona Live API nadal ma baner „Preview”, nie ma czystego trybu tekst→tekst ani structured output w Live i działa tylko przez WebSocket. ElevenLabs Agents daje tekst + głos w jednym SDK, ale rozmowa i prompt żyją na platformie, a rezydencja UE i SLA są tylko w planie Enterprise.
4. **Najważniejsze ryzyko dla tej aplikacji to nie opóźnienie, tylko transkrypcja.** Badania na mowie uczących się (angielski L2) pokazują, że ASR (zwłaszcza Whisper) „poprawia” błędy morfologiczne w transkrypcie. Rdzeń produktu to lista błędów, więc przy głosie trzeba wybrać dosłowny (verbatim) tryb STT, trzymać audio i zrobić pilotaż na prawdziwych błędach. Nie znaleziono testu dla niemieckiego ani dla obecnych modeli STT.
5. **Wysoka dostępność:** dla planów samoobsługowych żadnego z trzech dostawców nie znaleziono publicznego SLA. Przy 2 użytkownikach rozsądną mitygacją jest retry + zapasowy model / dostawca, a nie płatne SLA.

## Detailed Findings

### Ograniczenia z produktu (lokalnie)

- Głos jest poza MVP: „Brak rozmowy głosowej … głos (naciśnij i mów) dopiero po MVP” (`context/foundation/prd.md:122`; `context/foundation/roadmap.md:169`).
- Wymagania wobec modelu z planu architektury: osobne tanie wywołanie ze **structured output** (JSON z listą błędów) oraz **narzędzie** do zakończenia sesji (`context/foundation/shape-notes.md:215-217`).
- Brak decyzji o dostawcy: klucz API LLM nie jest ustawiony i nie ma kodu LLM (`context/deployment/deploy-plan.md:122`).
- Infrastruktura: Railway ma WebSockety bez limitu czasu, więc ścieżka głosowa jest otwarta, ale niezaprojektowana (`context/foundation/infrastructure.md:72`, `:204`). Jeden synchroniczny worker Gunicorna blokuje inne żądania podczas wywołania LLM (`context/foundation/infrastructure.md:108`, `:153`).
- Prywatność: dane jednej osoby nigdy nie są widoczne dla innej (`context/foundation/prd.md:94`). PRD nie wymaga rezydencji danych w UE — to otwarta decyzja (zob. Open Questions).

### OpenAI (tekst + Realtime)

- Modele głosowe: `gpt-realtime-2.1` i `gpt-realtime-2.1-mini`, ogłoszone 2026-07-06 (https://community.openai.com/t/new-realtime-models-on-the-api-gpt-realtime-2-1-and-gpt-realtime-2-1-mini/1385896). Wersja beta Realtime jest wycofana na rzecz interfejsu GA (https://developers.openai.com/api/docs/guides/realtime).
- Cennik (za 1M tokenów, https://developers.openai.com/api/docs/pricing): 2.1 audio in $32 / out $64; 2.1-mini audio in $10 / out $20. Tanie modele tekstowe: `gpt-5.4-nano` $0.20/$1.25, `gpt-5.4-mini` $0.75/$4.50. Oficjalnego przeliczenia na minutę brak. Szacunek z zewnętrznego źródła (aireiter.com, ~2026-07-09) to ok. $0.04–0.10/min dla 2.1, a mini ok. 3× taniej.
- Tekst w Realtime: technicznie działa (`output_modalities: ["text"]`), ale do czatu praktyczniejsze jest zwykłe Responses API (https://developers.openai.com/api/docs/guides/realtime-conversations).
- Function calling: jest w sesji Realtime. Structured output w Realtime: nie zweryfikowano. Listę błędów i tak robi osobne wywołanie Responses API z JSON schema.
- Transkrypt mowy użytkownika: robi go **osobny model ASR**, asynchronicznie po zakończeniu tury. Cookbook OpenAI mówi o możliwych rozbieżnościach i podaje przykład: ASR „otoo accident”, a model zrozumiał „auto accident” (openai-cookbook, `Realtime_out_of_band_transcription.ipynb`).
- Przeglądarka: WebRTC + token efemeryczny z `POST /v1/realtime/client_secrets`. Limit sesji: 60 min (guides/realtime-webrtc, guides/realtime-conversations).
- UE: `/v1/realtime` (w tym 2.1 i 2.1-mini) jest objęte rezydencją danych EEA+CH przez `eu.api.openai.com`. Wymaga to projektu z regionem EU. Jest ZDR-eligible z 30-dniowym monitoringiem nadużyć (https://developers.openai.com/api/docs/guides/your-data).
- Dostępność: status.openai.com pokazuje 99.96% uptime (agregat wszystkich komponentów, lipiec–październik 2026). Są wpisy o incydentach Realtime (m.in. „High Error Rate in Realtime API (EU)”), ale bez wyciągniętych dat. Publicznego SLA dla zwykłego API nie znaleziono.

### Google Gemini (tekst + Live API)

- Modele: `gemini-3.8-live` (domyślny), `gemini-3.8-live-extended-thinking` oraz `gemini-3.1-flash-live-preview` (legacy). Strona capabilities ma baner „Preview: The Live API is in preview” (zweryfikowane 2026-10-05: https://ai.google.dev/gemini-api/docs/live-api/capabilities). Strona modelu podaje „Stable” — to **sprzeczność**, nierozstrzygnięta.
- Cennik Live (za 1M tokenów, https://ai.google.dev/gemini-api/docs/pricing): audio in $3 (~$0.005/min), audio out $12 (~$0.018/min). To najtańsze audio wśród badanych opcji. Tanie modele tekstowe: `gemini-3.5-flash-lite` $0.30/$2.50. Uwaga: ceny 3.x Flash rosną od 2027-01-01.
- Natywne modele audio zwracają tylko modalność AUDIO, a tekst odpowiedzi jest dostępny jedynie jako transkrypcja audio (live-api/capabilities, wg raportu agenta). Do czatu trzeba więc używać zwykłego `generateContent`. Structured output w 3.8 Live: „Not supported”.
- Transkrypcja: osobny model `gemini-3.5-transcribe-live` ma tryb „smart transcription”, który czyści tekst. Dokumentacja odróżnia go od zwykłej transkrypcji (zweryfikowane 2026-10-05: https://ai.google.dev/gemini-api/docs/live-api/live-transcribe). Według raportu agenta domyślny tryb to `VERBATIM` („exact literal transcript”). Fragment z nazwą parametru nie zmieścił się w moim odczycie strony.
- Połączenie: tylko WebSocket, PCM 16 kHz; tokeny efemeryczne ważne do 30 min (v1beta). Sesja audio bez kompresji kontekstu trwa do 15 min, a z kompresją jest „unlimited”. Potrzebne jest wznawianie sesji (session resumption).
- SLA: jest dla Vertex AI i wyłącza funkcje pre-GA. Dla Gemini Developer API go nie znaleziono. Dostępność `gemini-3.8-live` w regionie UE na Developer API: nie zweryfikowano.

### ElevenLabs Agents („ElevenAgents”)

- Architektura: dostrojony ASR + wybrany LLM (OpenAI GPT-5.x, Gemini do 3.7 Flash, Anthropic Opus 4.8 / Sonnet 5 / Haiku 4.5, hostowany Qwen) albo custom LLM + TTS + własny model przejmowania tury (https://elevenlabs.io/docs/agents-platform/overview, …/customization/llm). TTS do agentów: Flash v2.5 (~75 ms inferencji, wspiera niemiecki) (https://elevenlabs.io/docs/eleven-api/concepts/latency.mdx).
- Tryb tekstowy: jest, przez `conversation.text_only` lub override `textOnly`; wymaga callbacku `agent_response` (zweryfikowane 2026-10-05: https://elevenlabs.io/docs/eleven-agents/guides/chat-mode).
- Cennik (https://elevenlabs.io/pricing/agents): tekst $0.003 za wiadomość + LLM osobno; głos $0.08/min ponad plan (zawiera STT + TTS + turn-taking) + LLM osobno. Plany: Free 15 min, Starter $6 (75 min), Creator $22 (275 min), Pro $99. Szacunek dla 2 osób × 15 min/dzień ≈ 900 min/mies. głosu: ~$72 + LLM (obliczenie agenta: 900 × $0.08).
- Personalizacja: zmienne dynamiczne `{{var}}` i override całego system promptu przy starcie sesji, systemowe narzędzie `end_call`, post-call webhooki i API transkryptu (https://elevenlabs.io/docs/eleven-agents/customization/personalization, …/tools/system-tools/end-call). Webhook inicjalizacji działa tylko dla telefonii/WhatsApp/SMS, więc w aplikacji webowej dane wysyła klient albo backend przed startem.
- Integracja webowa: backend wywołuje `get-signed-url` (WebSocket) albo `/conversation/token` (WebRTC) z kluczem API — pasuje do widoku Django z `login_required`.
- Dane: rezydencja UE tylko w Enterprise. Domyślnie dane są w USA. Retencję można ustawić na 0 dni; jest Zero Retention Mode per agent (https://elevenlabs.io/docs/overview/administration/data-residency.mdx, …/customization/privacy).
- Dostępność: SLA tylko w Enterprise. Incydenty w 2026 m.in.: 28.09 (~30 min, EU Residency Agents), 26.08 (~2,7 h podwyższonego opóźnienia), 14.07 (~9,5 h awarii Speech Engine, bez wpływu na standardowe agenty) (https://status.elevenlabs.io).
- Niezależny pomiar opóźnienia (telefon/Twilio, nie przeglądarka): mediana 1424 ms, p95 1768 ms (https://openbenchmarks.com/voice-agent-latency/voice-agent-end-to-end-latency).
- Lock-in: konfiguracja agenta i historia rozmów są na platformie (łagodzi to CLI `agents pull/push`). Czy ASR ElevenLabs normalizuje gramatykę: nie znaleziono informacji.

### Pułapka: STT „poprawia” błędy uczącego się

- Praca J-STAGE (LET Journal vol. 35, data niepodana, prawdopodobnie 2025): 3 systemy ASR na spontanicznej mowie nie-natywnej (angielski). Wszystkie „tended to correct erroneous morphological forms”, a Whisper najmocniej. Autorzy piszą, że takie transkrypty mogą nie nadawać się do analizy błędów (https://www.jstage.jst.go.jp/article/letcj/35/0/35_15/_pdf). Cytowane tam prace Bear et al. 2023 i Michot et al. 2024 — nie otwierane bezpośrednio.
- Whisper wygładza mowę i pomija wahania (arXiv 2307.09378, 2023).
- Tryby dosłowne u dostawców: Gemini transcribe (verbatim vs smart, j.w.); ElevenLabs Scribe v2 `no_verbatim=false` domyślnie (zachowuje wtrącenia; https://elevenlabs.io/docs/overview/capabilities/speech-to-text.md); Deepgram `filler_words` (tylko wtrącenia, nie gramatyka). Dla `gpt-4o-transcribe` nie znaleziono przełącznika dosłowności.
- Model mowa→mowa (OpenAI Realtime, Gemini Live) też zapisuje transkrypt użytkownika osobnym ASR, więc to samo ryzyko dotyczy listy błędów (cookbook OpenAI j.w.).
- **Luka:** brak testu na niemieckiej mowie uczących się dla któregokolwiek obecnego STT.

### Głos po MVP: „naciśnij i mów” prostym łańcuchem vs realtime

- Prosty łańcuch: przeglądarka nagrywa → upload do Django → STT → LLM → TTS → odtworzenie. Jeden deweloper zmierzył ok. 5–6 s do pierwszego dźwięku, a po optymalizacjach (strumieniowe odtwarzanie, bez dodatkowego wywołania narzędzia) 2,5–3 s; wąskim gardłem był LLM (https://andrzejoblong.pl/posts/voice_coach_03_latency/). Przy „naciśnij i mów” 1,5–3 s jest akceptowalne; poniżej ~0,8 s rozmowa brzmi naturalnie.
- Zaleta prostego łańcucha: transkrypt to prawdziwy tekst z wybranego STT (verbatim), który trafia do tej samej logiki co czat tekstowy. Prompt i pamięć są jedne.
- Frameworki Pipecat / LiveKit Agents: dojrzałe, ale wymagają osobnego serwisu (Pipecat: kontener 512 MB–1 GB, WebRTC, STUN/TURN; https://docs.pipecat.ai/pipecat/deployment/platforms/fly). Dla „naciśnij i mów” to przerost.
- Realtime mowa→mowa: pomiar zewnętrzny (Cekura, symulowane rozmowy) podaje medianę 1,94 s (OpenAI 2.1) i 1,91 s (Gemini 3.8 Live), w tym wykrycie końca tury. Inne źródła podają 0,2–0,5 s — **sprzeczność** zależna od metody pomiaru.

### Jakość niemieckiego (STT, TTS, LLM)

- STT niemiecki — źródła wzajemnie sprzeczne: Novascribe (2026-07-15, 20 plików FLEURS-DE) stawia GPT-4o-transcribe na 3,3% WER, a Nova-3 na 6,3%; benchmark Deepgrama (26 h) stawia Nova-3 na 1. miejscu (8,8% batch). Wniosek: liczby z blogów dostawców nie rozstrzygają.
- TTS — czas do pierwszego dźwięku (Coval przez Gradium, 2026-09-08): ElevenLabs Flash v2.5 185 ms, Cartesia Sonic 3.5 269 ms, OpenAI gpt-4o-mini-tts p95 3 927 ms. Jakości niemieckiego głosu nie oceniono niezależnie.
- LLM do korekty gramatyki / kontroli poziomu CEFR: nie znaleziono wiarygodnego porównania obecnych modeli z 2026. Starsze prace (ACL 2024, ACL 2026) pokazują, że duże modele (GPT-4) są dobre w GEC i kontroli poziomu, ale dotyczą starych modeli.

## Code References

- `context/foundation/prd.md:94` — wymóg prywatności między użytkownikami.
- `context/foundation/prd.md:97` — czas odpowiedzi agenta bez progu liczbowego.
- `context/foundation/prd.md:122` — głos poza MVP.
- `context/foundation/shape-notes.md:215-217` — structured output dla listy błędów, wstrzykiwanie błędów do system prompta, narzędzie do zakończenia sesji.
- `context/foundation/infrastructure.md:72` — WebSockety na Railway bez limitu czasu.
- `context/foundation/infrastructure.md:153` — rekomendowane workery/timeout Gunicorna dla wolnych wywołań LLM.
- `context/deployment/deploy-plan.md:122` — brak klucza API LLM i kodu LLM.

## Architecture Insights

- **Rozdziel „mózg” od „uszu i ust”.** Logika rozmowy (prompt z poziomem B1–B2, recast, pamięć z Postgresa, narzędzie końca rozmowy, osobne wywołanie z listą błędów) powinna być w Django, niezależnie od kanału. Kanał tekstowy (MVP) i głosowy (po MVP) to tylko różne wejścia/wyjścia do tej samej logiki. Platforma agentów (ElevenLabs) albo API mowa→mowa przenosi część tej logiki do zewnętrznej usługi.
- **Cienka warstwa nad dostawcą LLM** (jedna funkcja/serwis „wyślij wiadomości, dostań odpowiedź / wywołanie narzędzia”) ułatwia zapasowego dostawcę i zmianę modelu po ewaluacji jakości niemieckiego.
- **Synchroniczny Django:** wywołanie LLM blokuje worker. Dla 2 osób wystarczy konfiguracja z `infrastructure.md:153`. Odpowiedzi strumieniowe (streaming) i realtime głos to osobna decyzja projektowa.

## Historical Context (from prior changes)

Nie dotyczy — w `context/changes/**` i `context/archive/**` nie ma wcześniejszych decyzji o dostawcy LLM. Przeszukano słowa openai/gemini/elevenlabs/llm/tts/stt/voice/głos we wszystkich `*.md` w `context/`; trafienia tylko w plikach foundation/deployment cytowanych wyżej.

## Related Research

Brak innych dokumentów `research.md`.

## Open Questions

1. **Który model LLM daje najlepsze recasty i listę błędów po niemiecku?** Nie ma aktualnego porównania. Proponowana mała ewaluacja: 20–30 prawdziwych zdań z błędami autora i żony, 2–3 tanie modele (np. `gpt-5.4-mini`, `gemini-3.5-flash-lite` / `3.8-flash`, Claude Haiku), ocena ręczna. Owner: user / `/10x-plan`.
2. **Czy wymagana jest rezydencja danych w UE?** PRD wymaga prywatności między użytkownikami, ale nie lokalizacji danych. Jeśli tak: OpenAI ma rezydencję UE dla tekstu i Realtime, a ElevenLabs tylko w Enterprise. Owner: user.
3. **Głos: „naciśnij i mów” prostym łańcuchem czy realtime?** Decyzja produktowa po MVP. Badanie wskazuje, że prosty łańcuch daje kontrolę nad dosłownym transkryptem kosztem opóźnienia ~2–3 s. Owner: user.
4. **Czy STT zachowuje niemieckie błędy uczącego się?** Wymaga pilotażu na nagraniach autora (verbatim Gemini transcribe vs Scribe v2 vs gpt-4o-transcribe). Owner: user, po MVP.
5. **Gemini Live: GA czy Preview?** Sprzeczne strony dokumentacji (baner Preview vs „Stable”). Sprawdzić przed ewentualnym wyborem.
6. **Fallback przy awarii dostawcy** — czy w S-01 dodać zapasowy model/dostawcę, czy wystarczy komunikat o błędzie i retry? Owner: `/10x-plan`.
