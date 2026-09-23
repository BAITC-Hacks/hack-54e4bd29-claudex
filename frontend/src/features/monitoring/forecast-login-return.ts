import { z } from "zod";

/** Keep only the exact validated Forecast UUID in a fixed local return route. */
export function forecastLoginReturnTo(forecastId?: string): string {
  if (forecastId === undefined) return "/monitor/model";
  // Retain an invalid-ID state without forwarding arbitrary input or loading GLOBAL.
  const id = z.string().uuid().safeParse(forecastId).success ? forecastId : "";
  return `/monitor/model?forecast_id=${encodeURIComponent(id)}`;
}
