import { z } from "zod";

/**
 * Контракты доменного API.
 *
 * Ответ сервера проверяется во время выполнения: расхождение контракта
 * обнаруживается сразу и с понятным сообщением, а не превращается
 * в ошибку доступа к свойству где-то в компоненте.
 */

export const signalStatusSchema = z.enum(["NEW", "IN_PROGRESS", "CLOSED"]);
export type SignalStatus = z.infer<typeof signalStatusSchema>;

export const signalSeveritySchema = z.enum([
  "INFO",
  "WARNING",
  "HIGH",
  "CRITICAL",
]);
export type SignalSeverity = z.infer<typeof signalSeveritySchema>;

export const signalTypeSchema = z.enum([
  "QUEUE_GROWTH",
  "HIGH_REFUSAL_RATE",
  "OVERLOAD_FORECAST",
  "DATA_STALE",
  "ANOMALY_DETECTED",
  "DATA_QUALITY_DEGRADED",
  "REFERRAL_SPIKE",
  "REFUSAL_SPIKE",
  "FORECAST_INFLOW_GROWTH",
]);
export type SignalType = z.infer<typeof signalTypeSchema>;

export const signalSourceTypeSchema = z.enum([
  "RULE_BASED",
  "STATISTICAL",
  "ML_BASED",
]);

export const dataScopeTypeSchema = z.enum(["GLOBAL", "REGION", "HOSPITAL"]);
export type DataScopeType = z.infer<typeof dataScopeTypeSchema>;

export const signalClosureDispositionSchema = z.enum(["RESOLVED", "DISMISSED"]);
export type SignalClosureDisposition = z.infer<
  typeof signalClosureDispositionSchema
>;

/** Постраничный ответ. Форма общая для всех списков. */
export function pageSchema<ItemT extends z.ZodTypeAny>(item: ItemT) {
  return z.object({
    items: z.array(item),
    page: z.number(),
    page_size: z.number(),
    total: z.number(),
    has_next: z.boolean(),
  });
}

export interface Page<ItemT> {
  items: ItemT[];
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
}

export const regionSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  is_active: z.boolean(),
});
export type Region = z.infer<typeof regionSchema>;

export const hospitalSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  region_id: z.string(),
  is_active: z.boolean(),
});
export type Hospital = z.infer<typeof hospitalSchema>;

export const signalListItemSchema = z.object({
  id: z.string(),
  scope_type: dataScopeTypeSchema,
  region_id: z.string().nullable(),
  hospital_id: z.string().nullable(),
  hospital_name: z.string().nullable(),
  type: signalTypeSchema,
  severity: signalSeveritySchema,
  status: signalStatusSchema,
  source_type: signalSourceTypeSchema,
  title: z.string(),
  summary: z.string(),
  detected_at: z.string(),
  evaluation_period_start: z.string().nullable(),
  evaluation_period_end: z.string().nullable(),
  assigned_user_id: z.string().nullable(),
  version: z.number(),
});
export type SignalListItem = z.infer<typeof signalListItemSchema>;

export const explanationFactorSchema = z.object({
  metric_code: z.string(),
  direction: z.string(),
  change_pct: z.number().nullable(),
  comparison_period: z.string().nullable(),
  rule_code: z.string().nullable(),
  actual_value: z.number().nullable(),
  baseline_value: z.number().nullable(),
  delta_absolute: z.number().nullable(),
  delta_percent: z.number().nullable(),
});

export const signalExplanationSchema = z.object({
  summary: z.string(),
  factors: z.array(explanationFactorSchema),
  caveats: z.array(z.string()),
  generator: z.string(),
  generator_version: z.string(),
  model_version: z.string().nullable(),
  input_period_start: z.string().nullable(),
  input_period_end: z.string().nullable(),
  generated_at: z.string(),
});

export const actionSchema = z.object({
  id: z.string(),
  action_type: z.string(),
  description: z.string(),
  created_by: z.string(),
  created_at: z.string(),
});

export const auditEventSchema = z.object({
  id: z.string(),
  actor_user_id: z.string().nullable(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  request_id: z.string().nullable(),
  metadata: z.record(z.unknown()),
  created_at: z.string(),
});

export const signalDetailSchema = signalListItemSchema.extend({
  created_at: z.string(),
  updated_at: z.string(),
  forecast_id: z.string().nullable(),
  incident_id: z.string().nullable(),
  closed_reason: z.string().nullable(),
  closed_at: z.string().nullable(),
  closure_disposition: signalClosureDispositionSchema.nullable(),
  reference_period_start: z.string().nullable(),
  reference_period_end: z.string().nullable(),
  actual_value: z.number().nullable(),
  baseline_value: z.number().nullable(),
  delta_absolute: z.number().nullable(),
  delta_percent: z.number().nullable(),
  rule_code: z.string(),
  rule_version: z.string(),
  rule_config: z.record(z.unknown()),
  evidence: z.record(z.unknown()),
  source: z.string(),
  data_watermark: z.record(z.unknown()),
  data_current: z.boolean(),
  // Перечень переходов приходит с сервера: клиент не решает,
  // что доступно этой роли.
  available_transitions: z.array(signalStatusSchema),
  explanation: signalExplanationSchema.nullable(),
  actions: z.array(actionSchema),
  audit_history: z.array(auditEventSchema),
});
export type SignalDetail = z.infer<typeof signalDetailSchema>;

export const incidentStatusSchema = z.enum(["OPEN", "CLOSED"]);
export type IncidentStatus = z.infer<typeof incidentStatusSchema>;

export const incidentSchema = z.object({
  id: z.string(),
  scope_type: dataScopeTypeSchema,
  region_id: z.string().nullable(),
  hospital_id: z.string().nullable(),
  title: z.string(),
  status: incidentStatusSchema,
  assigned_user_id: z.string().nullable(),
  version: z.number(),
  created_at: z.string(),
  description: z.string().nullable(),
  updated_at: z.string(),
  signals: z.array(signalListItemSchema),
  actions: z.array(actionSchema),
});
export type Incident = z.infer<typeof incidentSchema>;

export const regionPageSchema = pageSchema(regionSchema);
export const hospitalPageSchema = pageSchema(hospitalSchema);
export const signalPageSchema = pageSchema(signalListItemSchema);
