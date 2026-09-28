import type { AnalyticsQuery } from "@/features/analytics/types";

export const DEFAULT_ANALYTICS_QUERY: AnalyticsQuery = {
  dateFrom: "2025-01-01T00:00:00Z",
  dateTo: "2025-03-31T23:59:59.999Z",
  granularity: "DAY",
};

const DATE_PARAM = /^\d{4}-\d{2}-\d{2}$/;

function queryBoundary(value: string | null, endOfDay = false): string | undefined {
  if (!value) return undefined;
  if (DATE_PARAM.test(value)) return `${value}${endOfDay ? "T23:59:59.999Z" : "T00:00:00Z"}`;
  return Number.isFinite(Date.parse(value)) ? value : undefined;
}

export function analyticsQueryFromSearch(search: Pick<URLSearchParams, "get">): AnalyticsQuery {
  const dateFrom = queryBoundary(search.get("date_from") ?? search.get("from"));
  const dateTo = queryBoundary(search.get("date_to") ?? search.get("to"), true);
  const validPeriod = Boolean(dateFrom && dateTo && Date.parse(dateFrom) <= Date.parse(dateTo));
  const region = search.get("region");
  return {
    ...(validPeriod ? { dateFrom, dateTo } : DEFAULT_ANALYTICS_QUERY),
    granularity: search.get("granularity") === "WEEK" ? "WEEK" : "DAY",
    ...(region ? { region } : {}),
  };
}

export function analyticsContextParams(query: AnalyticsQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.dateFrom) params.set("date_from", query.dateFrom.slice(0, 10));
  if (query.dateTo) params.set("date_to", query.dateTo.slice(0, 10));
  if (query.granularity) params.set("granularity", query.granularity);
  if (query.region) params.set("region", query.region);
  return params;
}

export function withAnalyticsContext(path: string, query?: AnalyticsQuery): string {
  if (!query) return path;
  const params = analyticsContextParams(query).toString();
  return params ? `${path}?${params}` : path;
}
