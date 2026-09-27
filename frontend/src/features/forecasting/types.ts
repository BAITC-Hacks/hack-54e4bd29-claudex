import { z } from "zod";

const metricSchema = z.object({
  mae: z.number(),
  wape: z.number().nullable(),
  rmse: z.number(),
}).strict();

const historicalPointSchema = z.object({
  date: z.string(),
  value: z.number().int().nonnegative(),
}).strict();

const forecastPointSchema = z.object({
  date: z.string(),
  predicted_value: z.number().nonnegative(),
  baseline_value: z.number().nonnegative(),
  delta_from_baseline: z.number(),
}).strict();

export const referralForecastSchema = z.object({
  id: z.string().uuid(),
  target: z.literal("DAILY_REFERRAL_COUNT"),
  scope_type: z.enum(["GLOBAL", "REGION", "HOSPITAL"]),
  // Optional for compatibility with the existing latest-global response.
  // By-ID responses supply canonical scope IDs (nullable), never aliases.
  hospital_id: z.string().uuid().nullable().optional(),
  region_id: z.string().uuid().nullable().optional(),
  horizon_days: z.number().int().positive(),
  input_period_start: z.string(),
  input_period_end: z.string(),
  validation_period_start: z.string().nullable().optional(),
  validation_period_end: z.string().nullable().optional(),
  forecast_start: z.string(),
  forecast_end: z.string(),
  generated_at: z.string(),
  model_version: z.string(),
  selected_model: z.string(),
  baseline_model: z.string(),
  metrics: metricSchema,
  baseline_metrics: metricSchema,
  dataset_watermark: z.record(z.unknown()),
  freshness_status: z.enum(["CURRENT", "STALE"]),
  limitations: z.array(z.string()),
  historical: z.array(historicalPointSchema),
  forecast: z.array(forecastPointSchema),
  disclaimer: z.string(),
}).strict();

export type ReferralForecast = z.infer<typeof referralForecastSchema>;
