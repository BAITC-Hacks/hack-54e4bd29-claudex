"use client";

import type { AnalyticsQuery } from "@/features/analytics/types";

export function FilterBar({ value, onChange }: { value: AnalyticsQuery; onChange: (next: AnalyticsQuery) => void }) {
  return <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-4"><label className="space-y-1 text-xs text-muted-foreground">Начало<input className="block h-9 rounded-md border bg-background px-3 text-sm text-foreground" type="date" value={value.dateFrom?.slice(0, 10) ?? ""} onChange={(event) => onChange({ ...value, dateFrom: `${event.target.value}T00:00:00Z` })} /></label><label className="space-y-1 text-xs text-muted-foreground">Конец<input className="block h-9 rounded-md border bg-background px-3 text-sm text-foreground" type="date" value={value.dateTo?.slice(0, 10) ?? ""} onChange={(event) => onChange({ ...value, dateTo: `${event.target.value}T23:59:59.999Z` })} /></label><label className="space-y-1 text-xs text-muted-foreground">Группировка<select className="block h-9 rounded-md border bg-background px-3 text-sm text-foreground" value={value.granularity ?? "DAY"} onChange={(event) => onChange({ ...value, granularity: event.target.value as "DAY" | "WEEK" })}><option value="DAY">По дням</option><option value="WEEK">По неделям</option></select></label></div>;
}
