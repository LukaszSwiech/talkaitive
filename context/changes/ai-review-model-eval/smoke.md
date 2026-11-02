# Smoke run notes (Phase 3)

- Date: 2026-11-02 (run id `2026-11-02T094915`, HEAD `2d434d1`, fingerprint `7e46f68e…63b6c`)
- Command: `uv run --env-file .env python -m scripts.review.eval.run --smoke --out <scratchpad>/smoke-1` (exit 0, `complete: true`)
- Case: `pass-settings-env` (expected `pass`), one call per model, default ledger `~/.cache/talkaitive-review-eval/ledger.json`
- Ledger: **0.0000 → 0.0278 USD** (0.0278455; 4 settled, 0 open; cap left 9.4722 of 9.50). Worst case reserved for the smoke: 0.2511 USD.
- Run count: one paid smoke, no re-run. No code fix needed.

## Per model

| Model | Result | Served provider | ZDR | Completion tokens (cap 6000) | Reasoning tokens | Cost reported / computed (USD) | Latency ms |
|---|---|---|---|---|---|---|---|
| gpt-5.4 | parsed, verdict `pass` (scores 10/10/9/10/6/10) | OpenAI direct | n/a (`store=False`) | 431 | 112 | — / 0.010165 | 9436 |
| gpt-6.1-terra | parsed, verdict `fail` (correctness 5, tests 1) | OpenAI direct | n/a (`store=False`) | 322 | 41 | — / 0.003470 (input at cache-write 1.25, upper bound) | 7239 |
| claude-sonnet-5.5 | parsed, verdict `pass` (scores 10/10/9/10/8/10) | `Google` = google-vertex, inside `only` | routed (no fallback) | 528 | 0 | 0.011566 / 0.011566 | 7790 |
| gemini-3.8-flash | parsed, verdict `pass` (all 10) | `Google` = google-vertex, inside `only` | routed (no fallback) | 314 | 0 | 0.0026445 / 0.0026445 (regular 0.005289) | 4244 |

Scores order: data_isolation, no_secrets, correctness, migrations, tests, openai_boundary.

- No row errored: no schema failure, refusal, `incomplete` or API error. Every route stayed far below the 6000 completion-token cap.
- Both OpenRouter requests carried `provider: {data_collection: "deny", require_parameters: true, zdr: true, only: [...]}` and were **accepted** (HTTP 200, finish reason `stop`).
- OpenRouter's billed `usage.cost` equals tokens × the **global** list price for both models (Claude 2.00/10.00, Gemini intro 0.75/3.75), so both calls went to `google-vertex/global`, not a +10% regional endpoint.
- The `served` field is OpenRouter's display name (`Google`), not the slug. Among `only` it can only mean `google-vertex` (AI Studio shows as `Google AI Studio`, Azure as `Azure`). Nothing in the runner compares `served` with `only`; the Phase 4 report must read `Google` as google-vertex.
- Claude and Gemini report 0 reasoning tokens with `reasoning.effort: low`; either they did not reason on this small case or the route does not report it. Their completion tokens are still billed as output.
- gpt-6.1-terra failed a clean case (tests 1). That is a measurement for Phase 4, not a defect.

## `/endpoints` check (free, 2026-11-02)

| Model | Endpoint (tag) | structured_outputs | response_format / reasoning / max_tokens | On ZDR list |
|---|---|---|---|---|
| Claude | google-vertex/global, /us, /europe | yes | yes | yes |
| Claude | azure/global, azure/us | yes | yes | no |
| Claude | anthropic | yes | yes | no |
| Claude | amazon-bedrock (+ eu-west-1, us-east-1), claude-on-aws | **no** | yes | Bedrock yes |
| Gemini | google-vertex/global, /us, /global/priority | yes | yes | yes |
| Gemini | google-vertex/global/flex | yes (status −2, down) | yes | yes |
| Gemini | google-ai-studio (+ /flex, /priority) | yes | yes | no |

- The `only` slugs in `models.py` (`google-vertex`, `azure` for Claude; `google-vertex` for Gemini) match OpenRouter's tag prefixes; **no change made**.
- With `zdr: true`, Azure drops out for Claude, so in practice both OpenRouter models route only to google-vertex. Bedrock is ZDR but lacks `structured_outputs`, so it stays excluded on purpose.
- Gemini `google-vertex/global/priority` (1.35/6.75) and regional `us` (0.825/4.125) stay below the worst-case prices (1.65/8.25), so the reservation still covers them.
