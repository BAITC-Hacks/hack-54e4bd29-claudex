"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchFreshness,
  fetchAllOrganizations,
  fetchObservedWaiting,
  fetchOrganization,
  fetchOverview,
  fetchQuality,
  fetchReferralSeries,
  fetchRefusalSeries,
  fetchWaitingSummary,
} from "@/features/analytics/api";
import type { AnalyticsQuery } from "@/features/analytics/types";

export const analyticsKeys = {
  all: ["analytics"] as const,
  query: (name: string, query?: object) => ["analytics", name, query ?? {}] as const,
};

export function useSituationCenter(enabled: boolean, query: AnalyticsQuery) {
  return {
    overview: useQuery({ queryKey: analyticsKeys.query("overview", query), queryFn: ({ signal }) => fetchOverview(query, signal), enabled }),
    referrals: useQuery({ queryKey: analyticsKeys.query("referrals", query), queryFn: ({ signal }) => fetchReferralSeries(query, signal), enabled }),
    refusals: useQuery({ queryKey: analyticsKeys.query("refusals", query), queryFn: ({ signal }) => fetchRefusalSeries(query, signal), enabled }),
    waiting: useQuery({ queryKey: analyticsKeys.query("waiting", query), queryFn: ({ signal }) => fetchWaitingSummary(query, signal), enabled }),
    observed: useQuery({ queryKey: analyticsKeys.query("observed", query), queryFn: ({ signal }) => fetchObservedWaiting(query, signal), enabled }),
    organizations: useQuery({ queryKey: analyticsKeys.query("organizations", query), queryFn: ({ signal }) => fetchAllOrganizations(query, signal), enabled }),
    freshness: useQuery({ queryKey: analyticsKeys.query("freshness"), queryFn: ({ signal }) => fetchFreshness(signal), enabled }),
    quality: useQuery({ queryKey: analyticsKeys.query("quality"), queryFn: ({ signal }) => fetchQuality(signal), enabled }),
  };
}

export function useOrganizationAnalytics(enabled: boolean, ref: string, query: AnalyticsQuery) {
  const scoped = { ...query, organization: ref };
  return {
    detail: useQuery({ queryKey: analyticsKeys.query("organization-detail", { ref, query }), queryFn: ({ signal }) => fetchOrganization(ref, query, signal), enabled }),
    referrals: useQuery({ queryKey: analyticsKeys.query("organization-referrals", scoped), queryFn: ({ signal }) => fetchReferralSeries(scoped, signal), enabled }),
    refusals: useQuery({ queryKey: analyticsKeys.query("organization-refusals", scoped), queryFn: ({ signal }) => fetchRefusalSeries(scoped, signal), enabled }),
    waiting: useQuery({ queryKey: analyticsKeys.query("organization-waiting", scoped), queryFn: ({ signal }) => fetchWaitingSummary(scoped, signal), enabled }),
    observed: useQuery({ queryKey: analyticsKeys.query("organization-observed", scoped), queryFn: ({ signal }) => fetchObservedWaiting(scoped, signal), enabled }),
  };
}
