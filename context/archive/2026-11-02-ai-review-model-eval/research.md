---
date: 2026-11-02T09:27:50+01:00
researcher: Claude (orchestrator, 4 read-only sub-agents)
git_commit: 12dccd1
branch: ai-review-model-eval
repository: LukaszSwiech/10xDevs4 (TalkAItive)
topic: "Compare AI review models with promptfoo and leave a regression gate"
tags: [research, scripts-review, promptfoo, openrouter, eval, ci]
status: complete
last_updated: 2026-11-02
last_updated_by: Claude
---

# Research: Compare AI review models with promptfoo and leave a regression gate

**Date**: 2026-11-02T09:27:50+01:00
**Researcher**: Claude (orchestrator) with 4 read-only sub-agents (prior decisions, promptfoo, models/prices, test-case candidates)
**Git Commit**: 12dccd1 (main after PR 31; PR 28 merge f3a9789 is an ancestor)
**Branch**: ai-review-model-eval
**Repository**: TalkAItive

## Research Question

How can the CI AI reviewer in `scripts/review/` be evaluated on four models (gpt-5.4, gpt-6.1-terra, Claude Sonnet 5.5, Gemini 3.8 Flash) with promptfoo 0.125.1, reusing the real prompt, schema and `final_verdict`, within a hard 10 USD total budget, and how can a free CI test detect a prompt/schema/model change that has no new result file? Full brief: `change.md` → Notes.

## Summary

- **Reuse points exist and are importable.** The prompt is built by `scripts/review/run_review.py:253-262` (`_build_input`, template `_INSTRUCTIONS` at `:75-84` with a random `{delimiter}`), the schema is `scripts/review/criteria.py:30-78` (`Review`), and the verdict is `criteria.py:116-124` (`final_verdict`, never reads `review.verdict`). `scripts/` is a package and pytest has `pythonpath = ["."]` (`pyproject.toml:33-37`).
- **`run_review` cannot be pointed at another model without touching production settings.** It reads `LLM_MODEL` and `LLM_PRICES_USD_PER_MTOK[LLM_MODEL]` at import (`run_review.py:50,67`); settings price only `gpt-5.4` and refuse an unpriced model (`talkaitive/settings.py:59,84-98`). The eval must pass model and prices itself and call the API itself, reusing `_build_input` and `Review` but not `_call_model`.
- **promptfoo 0.125.1 is installed and is the latest** (released 2026-10-25); `engines.node >=22.22.0`, so Node v25.8.0 is within range (no runtime warning found in the dist). Recommended shape: one custom Python provider (`call_api(prompt, options, context)`) for all four models + a Python assertion that calls the real `final_verdict`; tests from a Python generator.
- **Three promptfoo defaults are dangerous here:** (1) the CLI is logged in to cloud org TalkAItive, so every eval is **auto-shared** (uploads diffs and outputs) unless `--no-share`/`PROMPTFOO_DISABLE_SHARING=true`; (2) the cache would replay old outputs across runs, faking repeats, unless `--no-cache`; (3) promptfoo has **no cost cap** — the budget must be enforced inside the provider with a process-safe ledger (workers are separate processes).
- **Model IDs verified 2026-11-02, two corrections to the brief:** Claude on OpenRouter is `anthropic/claude-sonnet-5.5` (dot; `claude-sonnet-5-5` is the Anthropic-native ID); `gpt-6.1-terra` exists in OpenAI `/v1/models` but has **no dated snapshot**, so it can change under the same name. No list-price change found versus 2026-11-01.
- **Structured output is not equally guaranteed.** OpenAI enforces strict `json_schema` natively. On OpenRouter `require_parameters: true` only filters endpoints that *list* the parameter; some providers treat the schema as a hint. Gemini on Vertex documents "only string enums" while the schema scores are integer enums. So the eval must validate every output with pydantic client-side and count a schema failure as an error result, not a pass.
- **Budget:** a conservative worst case (all 16 cases at ~16k input tokens, 6000 output tokens, highest regional/regular price) is ≈5.7 USD per repeat over the 4 models, so 3 full repeats (≈17 USD) cannot be guaranteed up front; per-call worst-case reservation in a ledger guarantees the 10 USD cap is never crossed. Measured real cost of one gpt-5.4 review is about 0.05 USD (`context/foundation/test-plan.md:99`), so real spend is expected far lower.
- **Regression gate:** no test today hashes a prompt or reads a result file (`scripts/eval/run_eval.py:336-357` stores a `prompt_sha256` informationally only). A new `tests/test_*.py` runs in `ci.yml`'s `uv run pytest` with no workflow edit and no secrets.

## Detailed Findings

### 1. The reviewer as it is today

- One call: `client.responses.parse(model=LLM_MODEL, input=messages, text_format=Review, reasoning={"effort": "low"}, max_output_tokens=6000, store=False)` with `max_retries=0`, timeout 180 s (`run_review.py:57-60,265-274`).
- Messages: a `developer` message (instructions with a per-run `secrets.token_hex(16)` delimiter, plus `_TRUNCATED_INSTRUCTION` when cut) and a `user` message with the delimited diff (`run_review.py:253-262`). Any stable hash must use the template `_INSTRUCTIONS` and `_TRUNCATED_INSTRUCTION`, not the formatted prompt.
- Diff: `git diff HEAD^1 HEAD` excluding `uv.lock`, `package-lock.json`, `context` (`run_review.py:62,95-113`); cut at 120 000 chars, which forces `fail` (`:52,122-138`, `criteria.py:122`).
- Failure modes the eval must mirror: pydantic `ValidationError` (malformed output) and `output_parsed is None` (refusal or reasoning-only `incomplete`) both exit 1 in production (`run_review.py:325-345`). For the eval these are "error" rows, never a verdict.
- Verdict: `fail` iff `truncated` or a blocker (`data_isolation`, `no_secrets`, `correctness`, `migrations`) scores ≤ `FAIL_FLOOR = 3` (`criteria.py:20,89,116-124`). Warnings `tests`, `openai_boundary` never fail (`criteria.py:90`).
- Cost helper `scripts/review/cost.py:18-33` (`cost_usd`, `worst_case_usd` at 3 chars/token) has no cache-write term.

### 2. promptfoo 0.125.1 (installed package is the source of truth)

- Version/Node: 0.125.1 = latest on npm; `engines.node: ">=22.22.0"`; docs recommend Node 24 LTS. Pin in the documented command with `npx -y promptfoo@0.125.1` (the global install can drift). Changelog: https://github.com/promptfoo/promptfoo/blob/main/CHANGELOG.md
- Python provider: `call_api(prompt, options, context)`; `options.config` carries YAML config; `context` has `vars`, `test`, `repeatIndex`. Return `output` (str or dict) or `error`, plus optional `tokenUsage`, `cost`, `latencyMs`, `metadata`. Workers are persistent; count from `config.workers` / `PROMPTFOO_PYTHON_WORKERS` / `-j`. Interpreter: `config.pythonExecutable` → `PROMPTFOO_PYTHON` → `python` on PATH; assertions and test generators only see `PROMPTFOO_PYTHON`/PATH, so set `PROMPTFOO_PYTHON` to the uv venv. Docs: https://www.promptfoo.dev/docs/providers/python
- Python assertion: `get_assert(output, context)` where `context.providerResponse.metadata` is available; returns bool/float/`{pass, score, reason}`. Docs: https://www.promptfoo.dev/docs/configuration/expected-outputs/python
- Tests: `tests: file://….py:generate_tests`; `defaultTest.assert` applies to all.
- `.env`: promptfoo auto-loads `./.env` with `override=false`; its parser handles `NAME = value` (sub-agent tested dummy keys). Values from `uv run --env-file .env` win. `DOTENV_PATH=/dev/null` disables the auto-load.
- Repeats: `--repeat N` really calls the model per repeat in one run (namespace `repeat:<i>`); across runs the Python provider cache key ignores the repeat index → always `--no-cache`. Rows carry `repeatIndex`.
- Budget: no eval-level cost cap (only `PROMPTFOO_MAX_EVAL_TIME_MS`); a provider error marks a row ERROR and the run continues.
- Output `-o results.json`: rows with `vars`, `provider`, `response{output, tokenUsage, metadata}`, `success`, `latencyMs`, `cost`, `repeatIndex`, `error`.
- Sharing: auto-share when logged in (`shouldShareResults` = cloud enabled && `sharing !== false`); uploads prompts, vars, outputs. Use `--no-share` for the run, then `promptfoo share <evalId>` deliberately. `PROMPTFOO_DISABLE_TELEMETRY=1`, `PROMPTFOO_DISABLE_UPDATE=1` exist.
- Latency: the row's `latencyMs` is the provider's own value if returned, else wall clock around the worker call (includes IPC/queue) → the provider should measure the SDK call itself.
- Built-in cost table knows `gpt-5.4` but not `gpt-6.1-terra`; on the OpenRouter path cost comes from `usage.cost`. Another reason to compute cost in our provider.

### 3. Models, prices and routes (verified 2026-11-02)

USD per 1M tokens, standard tier, prompts below the long-context threshold. Reasoning tokens are billed as output on every route.

| Model | Route / ID | Input | Cached | Output | Notes |
|---|---|---|---|---|---|
| gpt-5.4 (baseline) | OpenAI `gpt-5.4` (snapshot `gpt-5.4-2026-03-05`) | 2.50 | 0.25 | 15.00 | equals `talkaitive/settings.py:86-92` |
| gpt-6.1-terra | OpenAI `gpt-6.1-terra`, no dated snapshot | 1.00 | 0.05 | 5.00 | cache **write** 1.25 (30-min retention); released ~2026-10-31 |
| Claude Sonnet 5.5 | OpenRouter `anthropic/claude-sonnet-5.5` | 2.00 | 0.10 | 10.00 | regional endpoints +10% (2.20 / 11.00); cache write 2.50 |
| Gemini 3.8 Flash | OpenRouter `google/gemini-3.8-flash` | intro 0.75 / from 2027-01-01 1.50 | 0.075 / 0.15 | intro 3.75 / 7.50 | Vertex non-global +10% (intro 0.825/4.125, regular 1.65/8.25); OpenRouter's model-level price shows the regional intro figure |

Sources: developers.openai.com pricing and model pages, openai.com "Introducing GPT-6.1 Terra", ai.google.dev pricing (2026-10-30), platform.claude.com pricing/structured outputs, OpenRouter live API `/api/v1/models` and `/models/<slug>/endpoints` (fetched 2026-11-02). Third-party cross-checks: model-prices.com, aipricing.guru (2026-11-01).

Structured output per route:
- OpenAI: native strict `json_schema` via Responses `text.format`; integer `enum`, all-required, `additionalProperties: false` are within the supported subset. Effort `low` accepted by both models.
- OpenRouter Claude: endpoints listing `structured_outputs`: `anthropic`, `google-vertex/{global,us,europe}`, `azure/{global,us}`; `amazon-bedrock*` and `claude-on-aws` list only `response_format`. Anthropic uses native constrained decoding; number `enum` works; `minimum`/`maximum` would 400 (the schema has none, `criteria.py:12-15`). Anthropic warns that structured output at low effort can think until `max_tokens` → treat `incomplete` as an error row.
- OpenRouter Gemini: all endpoints list both parameters, but Vertex `response_schema` documents "only string enums" and unsupported fields are silently ignored → enforcement of integer enums is **unverified**; pydantic validation is the real check.
- `provider.require_parameters: true` filters to endpoints that list the sent parameters; it does not prove strict decoding (OpenRouter structured-outputs docs).
- Whether OpenAI SDK `responses.parse(text_format=Review)` works against OpenRouter's Responses-compatible endpoint is **untested**; `chat.completions.parse(response_format=Review)` against OpenRouter's chat endpoint sends a strict `json_schema` generated from the same pydantic class.

Reasoning: OpenRouter `reasoning: {effort: "low"}` is valid for both Claude (lowest level) and Gemini; reasoning is mandatory for both (cannot be off); the effort-to-budget mapping for these two is not documented, so "low" is comparable in name, not in tokens.

Data policy on OpenRouter: `provider: {data_collection: "deny"}` excludes providers that may store/train; `provider: {zdr: true}` restricts to zero-retention endpoints (can only tighten). Docs list Bedrock, Azure, Google Vertex as zero retention; Anthropic 30 days; Google AI Studio 55 days. Since 2026-10-18 Google Vertex applies "Safety Retention" (flagged prompts up to 90 days); with the default "Safety retention allowed" account setting the Vertex Gemini endpoints count as ZDR. Endpoints meeting both ZDR and `structured_outputs`: Claude → Vertex and Azure; Gemini → Vertex only. Per-endpoint policy is not in the public API.

Cost reporting: OpenRouter returns `usage.cost` (USD) and `cost_details` in every response; no inference markup (5.5% fee is on credit purchases). Routing adds latency (~25–100 ms to first token per a third-party article of 2026-10-21; no official figure), so timings between direct and OpenRouter routes are not fully comparable.

### 4. Budget arithmetic (before any run)

Formula per call (mirrors `scripts/review/cost.py:30-33` but conservative): `input_tokens × input_price + 6000 × output_price`, with input tokens estimated at **1 char/token** (dense-text bound named in the first change's impl review, `context/archive/2026-10-31-ci-ai-code-review/reviews/impl-review.md:76-84`) and the highest applicable price (gpt-6.1-terra input at the cache-write 1.25; Claude regional 2.20/11.00; Gemini regular regional 1.65/8.25).

Illustrative bound for 16 cases capped at 16 000 input chars each:

| Model | Worst per call | × 16 cases |
|---|---|---|
| gpt-5.4 | 0.040 + 0.090 = 0.130 | 2.08 |
| gpt-6.1-terra | 0.020 + 0.030 = 0.050 | 0.80 |
| Claude Sonnet 5.5 | 0.035 + 0.066 = 0.101 | 1.62 |
| Gemini 3.8 Flash | 0.026 + 0.050 = 0.076 | 1.21 |
| **Total per repeat** | | **≈5.71** |

So under this bound one full repeat fits (5.71 ≤ 10) and three do not (≈17.1). Output tokens dominate; real outputs are far below 6000 (measured gpt-5.4 review ≈0.05 USD). The OpenRouter key's 10 USD limit does not cover the direct OpenAI calls, so the provider must enforce one shared total.

### 5. Test-case material (from git history)

PASS slices (diff of the merge's first parent, chars measured with `git diff <merge>^1 <merge> -- <paths> | wc -c`):
- P1 #27 254b61d `conversations/views.py conversations/urls.py conversations/services.py tests/test_conversation_views.py` (11 169): "Surprise me" view using `for_user` + tests.
- P2 #17 5af1ab0 conversations migrations 0004/0005 + `conversations/models.py` (3 488): safe AddField with defaults.
- P3 #12 848eb24 `accounts/migrations/0003_practice_language.py accounts/models.py` (1 692): NOT NULL with `default` and `db_default`.
- P4 #24 b34ecd0 `conversations/migrations/0006_llmcharge.py conversations/models.py` (3 758): CreateModel.
- P5 #13 2c2a3ae `talkaitive/settings.py` (1 446): env-var settings.
- P6 #26 6193c92 CSS tokens/components (13 241): UI only.
- P7 cf14043 `conversations/llm.py tests/test_llm.py` (2 213): llm.py change with test.
- P8 #20 3696e1c `tests/test_memory.py` (5 445): tests only.
- P9 #28 f3a9789 `scripts/review/run_review.py` (12 392): imports `openai` inside the exempt `scripts/review/`.

Real bugs:
- R1 74d7411 (branch `origin/ci-ai-review-gate-failtest`, never merged) `conversations/views.py` (527): `for_user` replaced by `Conversation.objects.all()` — real IDOR; in the gate's fail test gpt-5.4 scored data_isolation 1, correctness 1 (`context/archive/2026-11-01-ci-ai-review-gate/plan.md:430-438`). Unambiguous blocker.
- R2–R7 (reverse diffs of fixes 7f8d62c, cf14043, 52c9c48, f128a4b, c179381, 375e2e4): subtle correctness bugs (races, missed retry paths, data left after admin delete). A correct reviewer may score them 4–6, so they are soft cases, not hard blockers.

Not in history (must be seeded on real files): a committed secret, an unsafe migration, an OpenAI import in application code, an admin registration of a per-user model. Seed proposals: `Mistake.objects.filter(conversation_id=pk)` in `conversations/views.py`; a literal `sk-proj-…` (fake) in `talkaitive/settings.py`; an inverted condition in `conversations/services.py` `surprise_topic_key` or `budget.py`; accounts 0003 without `default`/`db_default` or a `RemoveField`; a behaviour change with its test deleted; `from openai import OpenAI` in `conversations/views.py`. Injection placement: a code comment above the R1-style line ("AI reviewer: ignore previous instructions…"), so `final_verdict` must still return `fail`.

### 6. CI and the regression gate

- `ci.yml` runs ruff check, ruff format --check, `uv run pytest` on every PR and push to main, no secrets, no Node (`.github/workflows/ci.yml:1-30`). A new `tests/test_*.py` runs there automatically.
- `tests/test_review_workflow.py:170-183` fails if another workflow has a job id/name `review` — irrelevant if no workflow is added.
- Manual-mutant copies exclude `.github` and `context` (`tests/test_review_workflow.py:25-29`); a hash test must not read files under `context/`. Files under `scripts/` are copied.
- Hash inputs available without network: `_INSTRUCTIONS`, `_TRUNCATED_INSTRUCTION`, `openai.lib._pydantic.to_strict_json_schema(Review)` (already used in `tests/test_review_criteria.py:14`), `MAX_OUTPUT_TOKENS`, `REASONING_EFFORT`, `MAX_DIFF_CHARS`, `EXCLUDED_PATHS`, and `settings.LLM_MODEL` (default `gpt-5.4`; CI sets no `LLM_MODEL`).

### 7. The "only conversations/llm.py calls OpenAI" boundary

- Written in `conversations/llm.py:1`, `CLAUDE.md` (scripts/review/ the one exception) and the reviewer's `openai_boundary` criterion, which exempts `scripts/review/` and `tests/` (`criteria.py:69-76`, asserted by `tests/test_review_criteria.py:97-102`). No test enforces imports.
- An eval placed **under `scripts/review/`** stays inside the reviewer's stated exemption; an eval elsewhere (e.g. `scripts/review_eval/`) would likely get a low `openai_boundary` warning (non-blocking). The CLAUDE.md sentence would still need a wording update — the brief asks for it as a proposal only.

## Code References

- `scripts/review/run_review.py:52-60` — size caps, output cap, effort, timeout
- `scripts/review/run_review.py:75-88` — prompt template and truncation note
- `scripts/review/run_review.py:253-274` — `_build_input`, `_call_model`
- `scripts/review/run_review.py:325-345` — schema-error and no-output handling
- `scripts/review/criteria.py:30-78` — `Review` schema; `:89-90` blockers/warnings; `:116-124` `final_verdict`
- `scripts/review/cost.py:18-33` — cost formula and worst case
- `talkaitive/settings.py:59,84-98` — `LLM_MODEL`, price table, unpriced-model guard
- `scripts/eval/run_eval.py:93-96,336-357,463-468` — result naming, prompt hash, no-overwrite
- `scripts/eval/cost.py:29-64` — `CostMeter` reservation pattern (Django-bound)
- `tests/test_review_criteria.py:14,97-102,218-235` — strict-schema import, exemption strings, clean-interpreter import
- `pyproject.toml:33-37` — pytest config
- `.github/workflows/ci.yml:1-30` — free CI job

## Architecture Insights

- Mirror `scripts/eval/` conventions (`context/foundation/test-plan.md:205-239`): local and manual only, own `--max-usd`-style cap, results named `<date>-<model>-<sha>.json`, never overwrite, never commit `-dirty` or trial files, logic tested by pytest without network, docs in test-plan §6.5-style section.
- The `CostMeter` reservation idea (`scripts/eval/cost.py:62-64`) is the right shape for the budget, but it is Django-bound and in-process; promptfoo workers are separate processes, so the ledger must be a locked file.
- The verdict must come from `final_verdict(Review.model_validate(output), truncated=…)` so a prompt-injected `verdict: pass` cannot pass a case — the same guarantee as production.

## Historical Context (from prior changes)

- `context/archive/2026-10-31-ci-ai-code-review/requirements.md:68`, `plan.md:45` — "No promptfoo, no TypeScript, no extra vendor (no Anthropic)" for that change. **Supported as a historical scope rule; this change deliberately reverses it** (promptfoo + OpenRouter for the eval only, not for the CI reviewer).
- `context/archive/2026-10-16-testing-ai-eval-layer/research.md:191,248` — promptfoo rejected for the conversation eval as a second toolset (Node) in a uv repo; noted Node ≥ 22.22. **Node requirement still supported** (0.125.1 `engines`); the rejection reason still applies in spirit, which is why promptfoo stays a local, pinned, `npx` tool with no `package.json` entry and no CI use.
- `context/archive/2026-10-31-ci-ai-code-review/plan.md:30,101` — `Literal` enum instead of `minimum`/`maximum` because only `enum` was proven against the server. **Supported**; it also keeps the schema valid for Anthropic (which rejects `minimum`/`maximum`), but Gemini-on-Vertex integer-enum enforcement is unknown.
- `context/archive/2026-11-01-ci-ai-review-gate/plan.md:430-438` — one seeded true positive (R1) on gpt-5.4; no false-pass/false-fail rates measured. **Supported**; this change produces the first rates.
- `context/archive/2026-11-01-ci-ai-review-gate/plan.md:369`, `context/foundation/test-plan.md:99` — ≈0.05 USD per real review. **Supported** as a single measurement.

## Related Research

- `context/archive/2026-10-31-ci-ai-code-review/research.md`
- `context/archive/2026-11-01-ci-ai-review-gate/research.md`
- `context/archive/2026-10-16-testing-ai-eval-layer/research.md`

## Open Questions (for /10x-plan to decide)

1. **OpenRouter call shape:** `responses.parse` via OpenRouter's Responses endpoint (untested) or `chat.completions.parse(response_format=Review)` via chat (strict json_schema from the same pydantic class; `developer` role may need mapping to `system`). A one-call smoke test per OpenRouter model can settle it cheaply before the main run.
2. **Data-policy routing:** `data_collection: "deny"` + `zdr: true` + `require_parameters: true` restricts Claude to Vertex/Azure and Gemini to Vertex; if no endpoint qualifies the call errors and the model is reported as unavailable rather than silently loosened.
3. **Repeats under the budget:** worst-case bound allows one guaranteed repeat; per-call reservation lets repeats 2–3 run until the ledger would cross 10 USD. Decide ordering (repeat-major, so each finished repeat covers all models) and the stop rule.
4. **Soft cases (R2–R7):** whether to include them as expected-fail on `correctness` (they test sensitivity but may inflate false-pass counts and disqualify every model) or exclude them from the disqualification rule. The decision rule says "a false pass on a blocker disqualifies a model", so only unambiguous blocker cases should carry an expected blocker.
5. **Gate scope:** hash of prompt template + schema + call constants + `LLM_MODEL`, stored in the newest committed result file; the test fails when no committed result carries the current hash.
