import { formatDate, formatPeriod } from "@/features/analytics/format";
import type { Freshness } from "@/features/analytics/types";

type DatasetFreshness = Freshness["data"][number];
const COMPLETENESS = {
  COMPLETE: "подтверждена",
  PARTIAL: "неполная",
  UNKNOWN: "не подтверждена",
} as const;

export function DataFreshnessDetails({ item }: { item: DatasetFreshness }) {
  const period = item.last_successful_import && item.event_period_start && item.event_period_end
    ? formatPeriod(item.event_period_start, item.event_period_end)
    : "Не определён";

  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <p className="text-sm font-medium text-foreground">{item.dataset_type}</p>
      <p>Период событий: {period}</p>
      <p>Загрузка источника: {formatDate(item.last_successful_import ? item.source_load_date : null)}</p>
      <p>Последний успешный импорт: {formatDate(item.last_successful_import)}</p>
      <p>Полнота поставки: {COMPLETENESS[item.completeness ?? "UNKNOWN"]}</p>
      <p>Полнота до: {item.confirmed_complete_through
        ? formatDate(item.confirmed_complete_through)
        : "не подтверждена"}</p>
      <p>Периодичность: {item.cadence_known ? "определена" : "не определена"}</p>
      {item.explanation && <p>{item.explanation}</p>}
    </div>
  );
}
