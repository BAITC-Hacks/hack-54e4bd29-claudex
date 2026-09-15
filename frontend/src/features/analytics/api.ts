import { apiRequest } from "@/services/api-client";
import {
  freshnessSchema,
  observedWaitingSchema,
  organizationDetailSchema,
  organizationListSchema,
  overviewSchema,
  qualitySchema,
  timeSeriesSchema,
  waitingSummarySchema,
  type AnalyticsQuery,
  type Freshness,
  type ObservedWaiting,
  type OrganizationDetail,
  type OrganizationList,
  type Overview,
  type Quality,
  type TimeSeries,
  type WaitingSummary,
} from "@/features/analytics/types";

function queryString(query: AnalyticsQuery & { page?: number }): string {
  const params = new URLSearchParams();
  if (query.dateFrom) params.set("date_from", query.dateFrom);
  if (query.dateTo) params.set("date_to", query.dateTo);
  if (query.granularity) params.set("granularity", query.granularity);
  if (query.organization) params.set("organization", query.organization);
  if (query.region) params.set("region", query.region);
  if (query.profile) params.set("profile", query.profile);
  if (query.page) params.set("page", String(query.page));
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export function fetchOverview(query: AnalyticsQuery, signal?: AbortSignal): Promise<Overview> {
  return apiRequest(`/analytics/overview${queryString(query)}`, overviewSchema, { signal });
}

export function fetchReferralSeries(query: AnalyticsQuery, signal?: AbortSignal): Promise<TimeSeries> {
  return apiRequest(`/analytics/referrals/timeseries${queryString(query)}`, timeSeriesSchema, { signal });
}

export function fetchRefusalSeries(query: AnalyticsQuery, signal?: AbortSignal): Promise<TimeSeries> {
  return apiRequest(`/analytics/refusals/timeseries${queryString(query)}`, timeSeriesSchema, { signal });
}

export function fetchWaitingSummary(query: AnalyticsQuery, signal?: AbortSignal): Promise<WaitingSummary> {
  return apiRequest(`/analytics/waiting/summary${queryString(query)}`, waitingSummarySchema, { signal });
}

export function fetchObservedWaiting(query: AnalyticsQuery, signal?: AbortSignal): Promise<ObservedWaiting> {
  return apiRequest(`/analytics/observed-waiting/summary${queryString(query)}`, observedWaitingSchema, { signal });
}

export function fetchOrganizations(query: AnalyticsQuery & { page?: number }, signal?: AbortSignal): Promise<OrganizationList> {
  return apiRequest(`/analytics/organizations${queryString(query)}`, organizationListSchema, { signal });
}

export function fetchOrganization(ref: string, query: AnalyticsQuery, signal?: AbortSignal): Promise<OrganizationDetail> {
  return apiRequest(`/analytics/organizations/${encodeURIComponent(ref)}${queryString(query)}`, organizationDetailSchema, { signal });
}

export function fetchFreshness(signal?: AbortSignal): Promise<Freshness> {
  return apiRequest("/analytics/data-freshness", freshnessSchema, { signal });
}

export function fetchQuality(signal?: AbortSignal): Promise<Quality> {
  return apiRequest("/analytics/data-quality", qualitySchema, { signal });
}
