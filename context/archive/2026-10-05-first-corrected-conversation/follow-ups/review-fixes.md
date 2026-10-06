# Follow-ups z przeglądu implementacji

Źródło: `reviews/impl-review-phase-1.md` (2026-10-06). Pozycje odroczone do kolejnych faz.

## Faza 3 — F2: wiadomości tylko przez rozmowę właściciela

- `Message` nie ma własnego `user` ani `for_user` (`conversations/models.py`).
- W widokach fazy 3 nie pobierać `Message` po `pk` (`Message.objects.get(pk=...)` to IDOR). Wiadomości czytać przez `conversation.messages`, gdzie `conversation` pochodzi z `get_object_or_404(Conversation.objects.for_user(request.user), pk=pk)`.
- Sprawdzić to w `/10x-impl-review` fazy 3. Jeśli kiedyś potrzebny będzie widok z `Message` po `pk`, wtedy dodać `MessageQuerySet.for_user`.

## Faza 3/4 — F4: `LLM_REASONING_EFFORT="none"`

- Wartość `none` nie jest potwierdzona dla `gpt-5.4` na prawdziwym API (`talkaitive/settings.py`).
- Przy pierwszym prawdziwym wywołaniu (ręczny test fazy 3) sprawdzić, czy API ją przyjmuje. Jeśli odrzuci: ustawić `LLM_REASONING_EFFORT=minimal` (lub `low`) w env albo zmienić domyślną wartość w `settings.py`.
