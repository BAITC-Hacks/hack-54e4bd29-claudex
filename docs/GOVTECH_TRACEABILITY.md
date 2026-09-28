# GovTech Case 1 — traceability matrix

| Требование | Реализация | Evidence |
|---|---|---|
| Воспроизводимый запуск | Compose, one-shot migrations | Clean project; PostgreSQL `0001–0006`, ClickHouse `001–005` |
| Исторические данные | Allowlisted streaming pipeline | Exact counts; repeat import `SKIP_IDEMPOTENT` |
| Вход и RBAC | Keycloak OIDC, permission/scope | Real HEALTH_AUTHORITY/REGION/HOSPITAL tokens |
| Situation Center | Aggregate-only API + Next.js | `/dashboard`, full-Q1 validation |
| Прогноз | 7-day referral-flow experiment | Historical forecast; validity/freshness separated |
| Предупреждения | Rule/statistical/forecast evaluators | `DATA_STALE`; spike/stale-forecast suppression |
| Explainability | Versioned evidence/rule snapshot | Signal detail and evaluator report |
| Human decision | Acknowledge, explicit Incident, assignment | Authenticated E2E and Audit |
| Расчётный сценарий | Immutable inflow change | Preview/save, authoritative baseline, Audit |
| Privacy | HMAC before ClickHouse, suppression | Privacy-at-rest and security tests |
| Recovery | PostgreSQL/ClickHouse/MinIO restore | Exact counts in isolated namespace |

MedSignal — Decision Support System. Данные не позволяют заявлять bed
occupancy, индивидуальную дату выписки, точное освобождение койки или
медицинскую рекомендацию. Текущий forecast относится к глобальному потоку
направлений и не является overload classifier. Решение принимает человек.
