import { referralForecastSchema, type ReferralForecast } from "@/features/forecasting/types";
import { apiRequest } from "@/services/api-client";

export function fetchLatestReferralForecast(signal?: AbortSignal): Promise<ReferralForecast> {
  return apiRequest("/forecasts/referrals/latest", referralForecastSchema, { signal });
}

