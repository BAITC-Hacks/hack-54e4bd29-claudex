/** Synthetic-only UI fixture. Its UUID is not a guaranteed live signal. */
export const syntheticCopilotResponse = {
  signal_id: "11111111-1111-4111-8111-111111111111",
  signal_version: 3,
  title: "Пояснение сигнала: рост очереди",
  explanation:
    "Сработало правило роста очереди. Наблюдаемое изменение требует проверки сотрудника и не устанавливает причину.",
  fact_ids: ["F1"],
  facts: [
    {
      id: "F1",
      metric_code: "queue_size",
      label: "Размер очереди",
      value: 21,
      unit: "percent_change",
      direction: "INCREASE",
      period_start: "2025-01-01T00:00:00Z",
      period_end: "2025-01-28T23:59:59Z",
      source: "signal_explanation",
    },
  ],
  evaluation_period_start: null,
  evaluation_period_end: null,
  reference_period_start: null,
  reference_period_end: null,
  data_current: false,
  data_watermark_at: null,
  limitations: [
    "Синтетические данные не отражают реальную нагрузку.",
    "Исторические данные не являются текущей очередью.",
  ],
  generated_at: "2026-09-27T10:00:00Z",
  request_id: "synthetic-request-id",
  llm_generated: true,
  provider: "openai",
  model: "gpt-4.1-mini-2025-04-14",
} as const;
