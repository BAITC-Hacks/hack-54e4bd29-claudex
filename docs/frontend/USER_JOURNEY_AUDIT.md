# MedSignal user journey audit — isolated synthetic acceptance

Date: 2026-09-26. Evidence comes from `phase8-accept-20260926d`, a loopback-only
Compose project with fresh volumes, production Next build, real test Keycloak,
real backend and invented 30 referral, 22 waiting and 24 refusal records. This
is **not** real-data or production acceptance. The Python image HIGH gate is
still FAIL.

| Journey aspect | Status | Evidence / limitation |
|---|---|---|
| OIDC login/callback and logout | PASS | Browser used signed test Keycloak session; logout confirmation and return to unauthenticated page completed. Test realm's post-logout URI was corrected. |
| Desktop and mobile navigation | PASS | Browser at 1280, 768 and 390 px; mobile Escape closes the menu and restores focus. |
| Dashboard and hospital analytics | PASS | Aggregate-only synthetic KPI, mapped hospital page and waiting snapshot timestamp rendered. |
| Empty period | PASS | No referral/refusal events in a selected February period showed empty charts; the supplied waiting snapshot stayed separate. |
| Partial delivery | NOT TESTED in browser | TREATED fixture could not be published because its reporting-period evidence is unavailable; UI must not present it as a time series. |
| Suppressed values | PASS in component tests; NOT TESTED in browser | `SuppressedValue` renders suppression, but the small acceptance fixture did not yield a suppressed group. |
| Freshness and stale wording | PASS for unknown cadence | Browser showed “Периодичность: не определена”. Q1 2025 must never be labelled a live queue. Operational freshness is not an owner-approved SLA. |
| HTTP 429 | PARTIAL | The real nginx rate limit blocked rapid repeated OIDC logins and a 20-concurrent-request benchmark. The edge returns a JSON 429 page during OIDC navigation; a branded recovery page is not implemented. Limits were not raised. |
| HTTP 503 and dependency recovery | PASS | With only disposable ClickHouse stopped, `/ready` returned 503 while `/health` stayed 200. Dashboard showed an accessible aggregate-data error. The helper restored ClickHouse and readiness in `finally`. |
| Signal acknowledge and Scenario preview/save | PASS | A synthetic signal moved to in-progress with an audit reason; scenario was clearly hypothetical and saved by a human. |
| Restricted organization access | PASS on invented facts | A hospital-manager test token saw only its hospital. The signed-token API check also returned 404 for a foreign hospital and an empty region/hospital intersection. |
| Historical forecast wording | NOT TESTED in browser | No suitable current forecast exists in the synthetic fixture. Forecast validity and temporal freshness remain separate; stale output cannot be labelled current. |

The browser suite has no API mocks, trace, screenshots, video, browser storage
state or token artifacts. Its strict reporter saves only test counts and fails
on zero or skipped tests. CI is configured to run the full journey on a fresh
synthetic project, then a separate controlled dependency-outage test and
namespaced teardown. The new CI job has not yet run on GitHub; its runtime
status is **NOT TESTED**.

Visible product-brand inconsistency (`MedFlow` in a MedSignal repository) was
corrected in the header, metadata, footer and sign-in copy, with a unit test.
Transport-level HTTP errors now stop query retries so unavailability is shown
instead of prolonged loading. This does not change rate limits or backend
authorization.
