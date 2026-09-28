import { z } from "zod";

const decimalSchema = z.union([z.string(), z.number()]).transform(Number);

export const scenarioResponseSchema = z.object({
  id: z.string().uuid().nullable(),
  scenario_type: z.literal("REFERRAL_INFLOW_CHANGE"),
  scope_type: z.enum(["GLOBAL", "REGION", "HOSPITAL"]),
  region_id: z.string().uuid().nullable(),
  hospital_id: z.string().uuid().nullable(),
  created_by: z.string().uuid().nullable(),
  source_signal_id: z.string().uuid().nullable(),
  source_incident_id: z.string().uuid().nullable(),
  baseline_type: z.enum(["OBSERVED", "FORECAST"]),
  baseline_value: decimalSchema,
  baseline_period_start: z.string(),
  baseline_period_end: z.string(),
  assumption_value: decimalSchema,
  calculated_value: decimalSchema,
  delta_absolute: decimalSchema,
  delta_percent: decimalSchema,
  data_watermark: z.record(z.unknown()),
  forecast_id: z.string().uuid().nullable(),
  model_version: z.string().nullable(),
  forecast_status: z.enum(["PENDING", "VALID", "INVALID", "FAILED"]).nullable(),
  baseline_freshness_status: z.enum(["CURRENT", "STALE"]),
  selected_model: z.string().nullable(),
  forecast_generated_at: z.string().nullable(),
  formula_version: z.string(),
  limitations_version: z.string(),
  limitations: z.array(z.string()),
  historical: z.boolean(),
  status: z.literal("COMPLETED").nullable(),
  created_at: z.string().nullable(),
}).strict();

export type ScenarioResult = z.infer<typeof scenarioResponseSchema>;
export type ScenarioAssumption = -0.2 | -0.1 | 0.1 | 0.2;
export type ScenarioBaselineType = "OBSERVED" | "FORECAST";

export interface ScenarioRequest {
  scenario_type: "REFERRAL_INFLOW_CHANGE";
  scope_type: "GLOBAL" | "REGION" | "HOSPITAL";
  region_id?: string;
  hospital_id?: string;
  baseline_type: ScenarioBaselineType;
  assumption_value: ScenarioAssumption;
  period_start?: string;
  period_end?: string;
  forecast_id?: string;
  historical_analysis: boolean;
  source_signal_id?: string;
  source_incident_id?: string;
}
