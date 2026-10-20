<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Rollout Phase 5 — warstwa evalu AI

- **Plan**: context/changes/testing-ai-eval-layer/plan.md
- **Scope**: Phase 1 of 3
- **Reviewed phases**: 1
- **Date**: 2026-10-17
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Summary of the requested checks

1. **Expected numbers in tests/test_eval_scoring.py**: all hand-written literals with arithmetic in comments; recomputed independently with `statistics` — recall SE 0.1443376, interval [0.2170984, 0.7829016]; typo_free SE 0.2204793, interval [-0.348806, 0.5154727]; cost 0.0046 + 0.00135 + 0.07 + 0.03 = 0.10595. All correct; manual item 1.6 can be checked.
2. **German**: correct — *gehen* → Perfekt with *sein*; *mögen* + Akkusativ → *den Film*; *…, dass er einen Preis gewonnen hat* (verb-final); *spannend*; M4 correct (inversion after *Danach*); partner's *in Kino* is a deliberate error for the A1 test (*im Kino*). Categories match the named rules (see F6).
3. **LECTURE_MARKERS**: see F2.
4. **Contract**: A1–A5, T1, one-to-one matching, extras/neutral, metrics, aggregation and `compare` implemented as in the plan; M35–M43 cover the plan's minimum list plus M41–M43.

Automated checks run in this review: `uv run pytest tests/test_eval_scoring.py tests/test_memory.py` (48 passed), `uv run pytest` (337 passed), `uv run ruff check .` and `uv run ruff format --check .` (clean). `also_copy` contains `scripts`; the `mutmut_47` row is removed from the register. Manual mutants and mutmut not re-run (see F7).

## Findings

### F1 — Keys, typos and neutral tokens matched as substrings, without word boundaries

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/scoring.py:176-177, :223, :225
- **Detail**: `_matches` and the A3/neutral checks use `x in wrong` (substring), while lecture markers use `contains_phrase` (word boundary). With short Phase 2 tokens this skews numbers: Neutral "das" swallows any extra containing "dass", "dasselbe", "was das" (item drops out of `extras`); key "er hat" matches "der hat" / "oder hat"; a Typo "ich" would give a false A3 for "dich" / "nicht". Also, A3 fires whenever the typo word is anywhere in a wider `wrong`, so an item about another real mistake whose span includes the typo word counts as a "reported typo".
- **Fix**: Use `contains_phrase` in `_matches` and for typo/neutral tokens; add tests ("das" does not match "dass", "er hat" does not match "der hat") and a mutant restoring `in`.
  - Strength: One matching rule in the module; Phase 1 tests still pass ("habe" in "habe gegangen" is a whole word).
  - Tradeoff: Keys must be whole words/phrases — enforce in the Phase 2 golden-set consistency test.
  - Confidence: HIGH — all current keys and tokens are whole words.
  - Blind spot: Keys that are part of a compound (e.g. "Kinokarte") would need a separate decision.
- **Decision**: FIXED — `_matches`, typo and neutral checks use `contains_phrase`; tests `test_gold_keyword_matches_whole_words_only`, `test_neutral_token_matches_whole_words_only`; M36 original updated, new M44, M45 (M35–M45 all killed, 339 passed).

### F2 — LECTURE_MARKERS: false alarms, missing inverted forms, compounds

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/scoring.py:49-75
- **Detail**: Likely false alarms in a natural partner reply: "Sie meinen" / "du meinst" ("Sie meinen das Roggenbrot?" in a formal bakery scene is a clarification request, not a lecture), "man sagt" ("Man sagt, das Café ist sehr gut."), "es heißt" ("Es heißt, morgen regnet es."), "Fehler" (ordinary talk about work). Important gaps: inverted forms typical of explicit correction — "Auf Deutsch sagt man…", "…heißt es…" (not caught by "man sagt" / "es heißt"); "besser wäre", "korrekt", "im Perfekt" / "Perfekt mit" (bare "Perfekt" is out — "Perfekt!" means "great!"); "Nebensatz", "Wortstellung", "Satzstellung", "Präposition", "Endung", "Konjugation", "Plural"; EN "should be", "word order", "tense". Word boundaries on both sides miss compounds: "Grammatikfehler", "Tippfehler", "Dativform", "Akkusativobjekt". This matters because the Phase 2 broken-prompt check (2.8) relies on `lecture_free` dropping.
- **Fix**: Remove or narrow "Sie meinen", "du meinst", "man sagt" (e.g. "du meinst wohl", "man sagt nicht"); add "sagt man", "heißt es" and the missing terms; match grammar terms as prefixes (Dativ\w*) and "fehler" as a suffix (\w*fehler, not "fehlerfrei"); a test case for each added/removed marker.
  - Strength: The plan (step 5) already asks to review marker false alarms; cheaper to fix before the paid run.
  - Tradeoff: Each marker trades sensitivity against precision.
  - Confidence: MED — a linguistic judgement, not measured on real replies.
  - Blind spot: No real gpt-5.4 replies from this app were inspected.
- **Decision**: FIXED — markers split into `LECTURE_MARKERS` (whole words), `LECTURE_PREFIXES` (compounds), `LECTURE_SUFFIXES` ("Fehler"); "du meinst", "Sie meinen", "man sagt" removed (deviation from the plan's example list, reason in the code comment), "sagt man", "man sagt nicht", "auf Deutsch heißt es", "besser wäre", grammar terms and EN phrases added; `lecture_markers()`; new hit cases and `test_natural_reply_is_not_a_lecture`; mutants M46–M48 (M35–M48 all killed, 346 passed).

### F3 — z = 1.96 interval too narrow for small n

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (plan flaw — the code does what the plan says)
- **Location**: scripts/eval/scoring.py:43, :336-339
- **Detail**: Memory has ~5 cases, analysis ~12, turn ~20. The t critical value is 2.776 (n=5, ~30% wider), 2.201 (n=12, ~11%), 2.093 (n=20, ~6%); at n=2 the verdict rests on two points (t = 12.7). A "difference" verdict — the one that decides whether a prompt change is accepted — will be falsely reported more often.
- **Fix**: A small table of t critical values for df 1–30 (no scipy), 1.96 above; update the test arithmetic (for n=3, t = 4.303, recall interval 0.5 ± 0.621 contains 0 — the test data need changing to keep a "difference" example).
  - Strength: Statistically correct for small n; a simple table.
  - Tradeoff: Fewer "differences", lower sensitivity to small changes; changes the plan's contract.
  - Confidence: HIGH — standard interval for a paired mean difference.
  - Blind spot: Irrelevant if only a large drop on the broken prompt matters.
- **Decision**: SKIPPED

### F4 — Greedy matching depends on item order

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/scoring.py:181-193
- **Detail**: An item that fits two gold mistakes in one message takes the first; a later item can be left unmatched although a better assignment gives 2/2. Matches the plan's contract ("first unmatched").
- **Fix**: In the Phase 2 golden-set consistency test, require that gold keys within one message do not overlap.
- **Decision**: FIXED — plan.md Faza 2 §4 consistency contract: gold `wrong_key`s of one message must not overlap; also keys and tokens must occur as whole words (follows from F1).

### F5 — A2 requires an exact fragment, punctuation included

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: scripts/eval/scoring.py:214
- **Detail**: If the learner left out a final period and the model adds one, or uses typographic quotes/apostrophes, A2 fires falsely.
- **Fix**: Strip sentence-final punctuation before comparing, or keep as is and review A2 by hand in the baseline run.
- **Decision**: FIXED — `_fragment()` strips final `.!?` from `sentence` before A2; test `test_sentence_with_an_added_final_period_is_not_a2`; M37 original updated, new M49 (M35–M49 all killed, 347 passed). Typographic quotes left as is.

### F6 — Test data: borderline category, scene, `wrong_form`

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: tests/test_eval_scoring.py:72-79, :294-303, :328
- **Detail**: "Verb am Ende im Nebensatz" is pure word order; also allowing `grammar` inflates `category_accuracy` — in Phase 2 give a second category only when truly ambiguous. TURN has `topic_key="bakery"` for a cinema conversation (harmless now; the Phase 2 consistency test should catch it). "Du habe ins Kino gegangen?" is an unnatural echo — the model would rather write "Du hast … gegangen?", which a first-person `wrong_form` misses; consider several wrong forms in Phase 2.
- **Fix**: Take into account when building the Phase 2 golden set.
- **Decision**: FIXED — plan.md Faza 2 §2: second category only for an ambiguous rule; turn scene matches the conversation; `wrong_form` also covers the partner's 2nd-person echo (possibly `wrong_forms`). Phase 1 tests unchanged.

### F7 — Manual mutants and mutmut not re-run in this review

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: plan.md Progress 1.4, 1.5
- **Detail**: The review was read-only; `manual_mutants.py` and `mutmut` temporarily modify files, so they were skipped. Items 1.4 and 1.5 are checked based on the earlier run only.
- **Fix**: Run `uv run python scripts/mutation/manual_mutants.py M35 M36 M37 M38 M39 M40 M41 M42 M43` after any fixes to F1–F3.
- **Decision**: FIXED — during triage `manual_mutants.py M35 … M49` ran after each fix: 15/15 killed, exit 0. Full `mutmut run` not re-run (Phase 3 runs it).

## Triage summary (2026-10-18)

- Fixed: F1, F2, F4, F5, F6, F7 (6)
- Skipped: F3 (1)
- After fixes: `uv run pytest` 347 passed; `ruff check` / `ruff format --check` clean; manual mutants M35–M49 all killed.
