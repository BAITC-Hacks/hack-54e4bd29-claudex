import type { SignalSeverity, SignalStatus, SignalType } from "@/types/domain";

/** Подписи предметной области. Вся терминология собрана в одном месте. */

export const SEVERITY_LABELS: Record<SignalSeverity, string> = {
  INFO: "информация",
  WARNING: "внимание",
  HIGH: "высокая",
  CRITICAL: "критическая",
};

export const SEVERITY_VARIANTS: Record<
  SignalSeverity,
  "neutral" | "warning" | "danger"
> = {
  INFO: "neutral",
  WARNING: "warning",
  HIGH: "danger",
  CRITICAL: "danger",
};

export const STATUS_LABELS: Record<SignalStatus, string> = {
  NEW: "новый",
  IN_PROGRESS: "в работе",
  CLOSED: "закрыт",
};

export const TYPE_LABELS: Record<SignalType, string> = {
  QUEUE_GROWTH: "рост очереди",
  HIGH_REFUSAL_RATE: "высокая доля отказов",
  OVERLOAD_FORECAST: "прогноз перегрузки",
  DATA_STALE: "данные устарели",
  ANOMALY_DETECTED: "обнаружена аномалия",
};

export const SOURCE_LABELS: Record<string, string> = {
  RULE_BASED: "правило",
  STATISTICAL: "статистика",
  ML_BASED: "модель",
};

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
