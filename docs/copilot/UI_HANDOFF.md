# Copilot UI handoff — synthetic explain-signal only

The backend contract and response example are in [API_V1.md](API_V1.md). The local live smoke evidence is in [LIVE_VERIFICATION_RESULT.md](LIVE_VERIFICATION_RESULT.md): three HTTP 200 responses from the agreed model through the real OIDC → FastAPI path; all eight server-response checks passed. The full generated text was not retained. This is not approval to send real medical data to the model.

## Success response

`POST /api/v1/copilot/explain-signal` accepts only `{"signal_id":"<UUID>"}`. The validated HTTP 200 response has:

- `explanation`: qualitative LLM text, without numeric, date or source-reference assertions;
- `fact_ids`: model-selected references, checked by backend against the same response's `facts`;
- `facts`: backend-generated `id`, `metric_code`, `label`, `value`, `unit`, `direction`, `period_start`, `period_end`, `source`;
- provenance: `signal_id`, `signal_version`, `provider`, `model`, `llm_generated`, `generated_at`, `request_id`;
- temporal context and limits: `evaluation_period_start/end`, `reference_period_start/end`, `data_current`, `data_watermark_at`, `limitations`.

Render numbers, units and periods **only from `facts` and temporal fields**, never by parsing `explanation`. Match `fact_ids` to `facts[].id`; do not display an unknown fact ID. `null` means unknown, not zero or today's date. Show the synthetic and historical limitations alongside the explanation. Preserve the original algorithmic signal explanation if Copilot is unavailable. Label the Copilot section as a synthetic demonstration, not a medical recommendation or current queue assessment.

## UI states and errors

| State | HTTP / code | Expected UI behavior |
| --- | --- | --- |
| Loading | request pending | Show an accessible progress state; keep the signal detail visible. |
| Success | 200 | Show qualitative explanation, backend facts, periods and limitations. |
| Disabled | 503 `COPILOT_DISABLED` | Hide or disable Copilot action; keep algorithmic explanation. |
| Provider unavailable | 503 `COPILOT_PROVIDER_UNAVAILABLE` | Show a retryable service error; do not synthesize an AI response. |
| Timeout | 504 `COPILOT_PROVIDER_TIMEOUT` | Show timeout state; no automatic paid retry. |
| Insufficient synthetic facts | 422 `COPILOT_INSUFFICIENT_DATA` | Show an unavailable-for-this-signal state. |
| Inaccessible/nonexistent signal | 404 `NOT_FOUND` | Use existing signal not-found handling. |
| Authentication failure | 401 `UNAUTHENTICATED` | Use existing sign-in flow. |
| Invalid model response | 502 `COPILOT_INVALID_RESPONSE` | Show a safe error; do not display unvalidated model text. |
| Demo rate limit | 429 `COPILOT_RATE_LIMITED` | Show rate-limit state; do not automatically retry. |

Use the existing synthetic API fixtures in `backend/tests/integration/test_copilot_api.py` and unit fixtures in `backend/tests/unit/test_copilot.py` for UI fixture design. Do not copy their example UUID as though it were a guaranteed live signal. The frontend implementation and design remain untouched in this work.
