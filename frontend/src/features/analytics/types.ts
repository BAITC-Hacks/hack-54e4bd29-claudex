import { z } from "zod";

const cellSchema = z.object({
  value: z.number().nullable(),
  suppressed: z.boolean(),
});

export const analyticsMetaSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  granularity: z.enum(["DAY", "WEEK"]).nullable(),
  source: z.array(z.string()),
  generated_at: z.string(),
  latest_import_id: z.string().nullable(),
  latest_import_ids: z.array(z.string()),
  latest_import_completed_at: z.string().nullable(),
  limitations: z.array(z.string()),
  mapping_version: z.string().nullable().optional(),
  mapping_publication_available: z.boolean().optional(),
});

export const overviewSchema = z.object({
  data: z.object({
    referrals_total: cellSchema,
    waiting_records: cellSchema,
    refusals_total: cellSchema,
    hospitalized_total: cellSchema,
    data_quality_warnings: cellSchema,
    represented_organizations: cellSchema,
    represented_regions: cellSchema,
  }),
  meta: analyticsMetaSchema,
});

export const timeSeriesSchema = z.object({
  data: z.object({
    metric: z.enum(["REFERRALS_TOTAL", "REFUSALS_TOTAL"]),
    points: z.array(
      z.object({
        period: z.string(),
        period_end: z.string(),
        value: cellSchema,
      }),
    ),
  }),
  meta: analyticsMetaSchema,
});

export const waitingSummarySchema = z.object({
  data: z.object({
    snapshot_at: z.string().nullable().optional().default(null),
    snapshot_semantics_confirmed: z.boolean().optional().default(false),
    waiting_records: cellSchema,
    median_days: cellSchema,
    p75_days: cellSchema,
    p90_days: cellSchema,
    oldest_days: cellSchema,
  }),
  meta: analyticsMetaSchema,
});

export const observedWaitingSchema = z.object({
  data: z.object({
    observed_records: cellSchema,
    excluded_chronology_conflicts: cellSchema,
    mean_days: cellSchema,
    median_days: cellSchema,
    p75_days: cellSchema,
    p90_days: cellSchema,
  }),
  meta: analyticsMetaSchema,
});

export const organizationSchema = z.object({
  organization_ref: z.string(),
  canonical_hospital_id: z.string().uuid().nullable(),
  display_name: z.string().nullable(),
  identity_label: z.string().nullable(),
  mapping_status: z.enum(["MAPPED", "UNMAPPED"]),
  source_system: z.string().nullable(),
  region_id: z.string().uuid().nullable(),
  referrals_total: cellSchema,
  waiting_records: cellSchema,
  refusals_total: cellSchema,
  observed_waiting_median_days: cellSchema,
});

export const organizationListSchema = z.object({
  data: z.object({
    items: z.array(organizationSchema),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
    total: z.number().int().nonnegative(),
    has_next: z.boolean(),
  }),
  meta: analyticsMetaSchema,
});

export const organizationDetailSchema = z.object({
  data: z.object({
    organization: organizationSchema,
    treated_snapshot: z
      .object({
        label: z.string(),
        snapshot_load_dt: z.string(),
        discharged_total: z.number(),
        discharged_children: z.number(),
        treated_budget: z.number(),
        treated_paid: z.number(),
        discharged_within_day: z.number(),
        deaths_total: z.number(),
        bed_days: z.number(),
        amount_to_pay: z.number(),
      })
      .nullable(),
  }),
  meta: analyticsMetaSchema,
});

export const freshnessSchema = z.object({
  data: z.array(
    z.object({
      dataset_type: z.string(),
      event_period_start: z.string().nullable(),
      event_period_end: z.string().nullable(),
      source_load_date: z.string().nullable(),
      last_successful_import: z.string().nullable(),
      status: z.enum(["CURRENT", "STALE", "UNKNOWN", "PARTIAL"]),
      confirmed_complete_through: z.string().nullable().optional(),
      cadence_known: z.boolean().optional(),
      completeness: z.enum(["COMPLETE", "PARTIAL", "UNKNOWN"]).optional(),
      forecast_available: z.boolean().optional(),
      explanation: z.string().nullable(),
    }),
  ),
  meta: analyticsMetaSchema,
});

export const qualitySchema = z.object({
  data: z.array(
    z.object({
      dataset_type: z.string(),
      status: z.string(),
      rows_loaded: z.number().int().nonnegative(),
      warnings_count: z.number().int().nonnegative(),
      rejected_count: z.number().int().nonnegative(),
      issues: z.array(z.string()),
    }),
  ),
  meta: analyticsMetaSchema,
});

export type AnalyticsCell = z.infer<typeof cellSchema>;
export type AnalyticsMeta = z.infer<typeof analyticsMetaSchema>;
export type Overview = z.infer<typeof overviewSchema>;
export type TimeSeries = z.infer<typeof timeSeriesSchema>;
export type WaitingSummary = z.infer<typeof waitingSummarySchema>;
export type ObservedWaiting = z.infer<typeof observedWaitingSchema>;
export type Organization = z.infer<typeof organizationSchema>;
export type OrganizationList = z.infer<typeof organizationListSchema>;
export type OrganizationDetail = z.infer<typeof organizationDetailSchema>;
export type Freshness = z.infer<typeof freshnessSchema>;
export type Quality = z.infer<typeof qualitySchema>;

export interface AnalyticsQuery {
  dateFrom?: string;
  dateTo?: string;
  granularity?: "DAY" | "WEEK";
  organization?: string;
  region?: string;
  profile?: string;
}
