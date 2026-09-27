import type { AnalyticsCell } from "@/features/analytics/types";

export function formatNumber(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
}

export function formatCell(cell: AnalyticsCell): string {
  return cell.suppressed ? "Скрыто" : formatNumber(cell.value);
}

export function formatDate(value: string | null): string {
  if (!value) return "Не определено";
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(value));
}

export function formatPeriod(from: string, to: string): string {
  return `${formatDate(from)} — ${formatDate(to)}`;
}
