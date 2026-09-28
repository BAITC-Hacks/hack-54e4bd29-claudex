"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchLatestReferralForecast } from "@/features/forecasting/api";

export function useLatestReferralForecast(enabled: boolean) {
  return useQuery({
    queryKey: ["forecasting", "referrals", "latest"],
    queryFn: ({ signal }) => fetchLatestReferralForecast(signal),
    enabled,
    retry: false,
  });
}

