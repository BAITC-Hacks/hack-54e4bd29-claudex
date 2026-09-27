import type { CopilotFact } from "@/features/copilot/types";

const numberFormatter = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric",
});
const timestampFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", timeZoneName: "short",
});

export function formatOptionalDate(value: string | null): string {
  if (value === null) return "Неизвестно";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Неизвестно" : dateFormatter.format(date);
}

export function formatOptionalPeriod(start: string | null, end: string | null): string {
  if (start === null && end === null) return "Неизвестно";
  return `${formatOptionalDate(start)} — ${formatOptionalDate(end)}`;
}

export function formatTimestamp(value: string | null): string {
  if (value === null) return "Неизвестно";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Неизвестно" : timestampFormatter.format(date);
}

export function formatFactValue(fact: Pick<CopilotFact, "value" | "unit" | "direction">): string {
  const direction = fact.direction === "INCREASE" ? "Увеличение" : "Уменьшение";
  const number = numberFormatter.format(fact.value);
  const units: Record<string, string> = {
    percent_change: "% изменения",
    percentage_points: "п. п.",
    count_records: "записей",
  };
  return `${direction} · ${number} ${units[fact.unit] ?? "(единица неизвестна)"}`;
}
