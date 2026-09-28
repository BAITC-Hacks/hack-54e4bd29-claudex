import { Badge } from "@/components/ui/badge";

const LABELS = { CURRENT: "Актуально", STALE: "Устарело", UNKNOWN: "Не определено", PARTIAL: "Поставка неполная" } as const;

export function DataFreshnessBadge({ status, mappingAvailable }: { status: keyof typeof LABELS; mappingAvailable?: boolean }) {
  const variant = status === "CURRENT" ? "success" : status === "STALE" || status === "PARTIAL" ? "danger" : "neutral";
  return <span className="inline-flex flex-wrap gap-2"><Badge variant={variant}>{LABELS[status]}</Badge>
    {mappingAvailable === false && <Badge variant="neutral">Сопоставления недоступны</Badge>}
  </span>;
}
