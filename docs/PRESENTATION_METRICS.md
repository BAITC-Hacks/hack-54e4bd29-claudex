# MedSignal — проверенные метрики для презентации

Дата acceptance: 18.09.2026. Среда: отдельный Compose project
`phase8-clean`, новые volumes, реальные allowlisted core datasets. Это
инженерные результаты, не SLA и не доказательство медицинской эффективности.

## Данные

| Набор | Загружено |
|---|---:|
| Направления | 767,130 |
| Ожидающие | 765,182 |
| Отказы | 1,508,732 |
| Пролеченные случаи | 2,196 |

Daily referral sum равна 767,130, daily refusal sum — 1,508,732. API вернул
574,444 завершённых госпитализации с валидной хронологией; 104,644 конфликтов
дат исключены из observed waiting и показаны как quality warning. Median
observed waiting — 0.98 дня, mean — 10.97, P75 — 7.49, P90 — 26.55.

Waiting — поставленный snapshot/export, не исторический ряд очереди. Median
возраста snapshot — 454.67 дня, P75 — 474.64, P90 — 484.52. Это не прогноз.

## Performance benchmark

200 запросов на endpoint, concurrency 20, warm cache, error rate 0%.

| Endpoint | p50 | p95 | p99 |
|---|---:|---:|---:|
| Overview | 185 ms | 3,114 ms | 3,138 ms |
| Referral timeseries | 307 ms | 402 ms | 440 ms |
| Organizations page | 2,332 ms | 3,127 ms | 3,428 ms |

Organizations list требует оптимизации до production SLA; SLA не принят.
Nginx burst throttling измерялся отдельно от application benchmark.

## Фоновые операции

| Операция | Время | Результат |
|---|---:|---|
| Core import | 61.614 s | COMPLETED |
| Signal evaluation | 8.349 s | COMPLETED |
| Referral forecast training | 36.992 s | COMPLETED |

Повторный Signal evaluation на том же watermark вернул `SKIP_IDEMPOTENT` для
трёх stale signals. Повторный import 11 файлов также вернул
`SKIP_IDEMPOTENT`; ClickHouse counts не изменились.

## Security и recovery

- Real signed-token scope: HEALTH_AUTHORITY, REGION и HOSPITAL — PASS.
- Public `/metrics`: 404; internal `/metrics/`: 200.
- Raw `hospitalization_code`/`patient_seq_no` отсутствуют в ClickHouse.
- 15 core files, 2,177,380,780 bytes: SHA-256 неизменны после import.
- Gitleaks 8.30.1: history и 537 release-candidate files — no leaks.
- Trivy 0.58.2: 0 CRITICAL и 0 fixable HIGH. Unfixed HIGH: backend 52,
  worker 44, MLflow 44; frontend/nginx 0.
- Restore: PostgreSQL 21 tables, exact ClickHouse counts, 8 MinIO buckets.

## Ограничения

Доступно около трёх месяцев истории. Годовая сезонность, bed capacity,
supervised overload ground truth и reporting period treated cases не
подтверждены. 5,029 source organization values и 42 region representations
остаются unmapped. MedSignal не заявляет точное предсказание перегрузки или
освобождения конкретной койки.
