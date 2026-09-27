# Copilot live verification — synthetic acceptance

## Current cycle — PASS (synthetic smoke verification)

On 2026-09-27, after narrowing the provider input to verified qualitative facts and clarifying the prompt, three separately authorized HTTP requests went through `POST /api/v1/copilot/explain-signal`. Each used a real test OIDC session and an existing server-confirmed `SYNTHETIC_DEV_SEED` signal. All returned HTTP 200. No request used real medical data. This is a smoke check on one synthetic signal, not proof of reliability across all signals.

| Request ID | HTTP | Total duration | Input tokens | Output tokens | Validation |
| --- | ---: | ---: | ---: | ---: | --- |
| `735b7c7d25a5e0f0706db89f075b9525` | 200 | 2735 ms | 392 | 65 | 8/8 PASS |
| `12a7601056c7846cb893b112d485c600` | 200 | 1532 ms | 392 | 62 | 8/8 PASS |
| `82d56dbe395ab319882429623528fb1b` | 200 | 1500 ms | 392 | 64 | 8/8 PASS |

The eight checks covered API schema, known `fact_ids`, exact match of numeric backend facts and periods to the synthetic signal, model/provenance, absence of unchecked numeric/temporal/causal text claims, historical/synthetic limitations, and preservation of unknown dates. Token usage came from bounded structured backend log fields; no prompt, response text, key, token or patient data was retained. The synthetic backend was then restored without the Copilot key.

## Earlier cycle — FAIL (historical diagnostic evidence)

Before this correction, three HTTP attempts were made through the same endpoint. OpenAI was called on attempts 2 and 3; attempt 1 failed inside backend before the provider call. No request used real medical data. There was no successful `200` response in that cycle; its agreed limit of three attempts was reached.

| Attempt | HTTP | Duration | Request ID | Finding |
| --- | ---: | ---: | --- | --- |
| 1 | 500 | 204 ms | unavailable | Backend failed before calling OpenAI: PostgreSQL returned signal type as `str`, while the service used `.value`. Fixed and covered by a persisted-string regression test. |
| 2 | 502 | 4359 ms | `c9264ebff338486a1e1dc43d905a26a0` | OpenAI completed, then backend rejected the response as `COPILOT_INVALID_RESPONSE`. The older log did not record which validation rule failed. No model text was retained. |
| 3 | 502 | 3453 ms | `f16229da2458660e3f53a03a51abc3d7` | OpenAI completed; backend rejected the free-text explanation with fixed reason code `NUMERIC_ASSERTION`. Provider duration 3390 ms; usage: 378 input and 150 output tokens. |

The earlier response shape, `fact_ids`, fact values, nullable dates and limitations could not be marked PASS without a successful API response. Numeric claims in generated text remained prohibited; no business validation was disabled. That cycle did not produce a valid response. No model text was retained, so the exact phrase behind `NUMERIC_ASSERTION` is unknown; do not attribute it to a particular digit or number word. No automatic retries or model substitution were made.

No key, OIDC token, prompt or LLM answer was saved in this report. Frontend integration can now use the validated response contract in `API_V1.md`, while retaining disabled, loading, error and historical/synthetic states. No frontend code changed in this task.
