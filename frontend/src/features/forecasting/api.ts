import { z } from "zod";
import { referralForecastSchema, type ReferralForecast } from "@/features/forecasting/types";
import { ApiError, apiRequest } from "@/services/api-client";

export function fetchLatestReferralForecast(signal?: AbortSignal): Promise<ReferralForecast> {
  return apiRequest("/forecasts/referrals/latest", referralForecastSchema, { signal });
}


/** Read one persisted Forecast UUID; scope authorization remains server-side. */
export function fetchReferralForecast(id: string, signal?: AbortSignal): Promise<ReferralForecast> {
  if (!z.string().uuid().safeParse(id).success) {
    return Promise.reject(new ApiError("INVALID_FORECAST_ID", "Некорректный идентификатор прогноза", 400, null));
  }
  return apiRequest(`/forecasts/${encodeURIComponent(id)}`, referralForecastSchema, { signal });
}
