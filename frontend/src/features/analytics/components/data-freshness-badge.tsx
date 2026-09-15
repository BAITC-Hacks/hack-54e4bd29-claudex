import { Badge } from "@/components/ui/badge";

const LABELS = { CURRENT: "Актуально", STALE: "Устарело", UNKNOWN: "Не определено" } as const;

export function DataFreshnessBadge({ status }: { status: keyof typeof LABELS }) {
  const variant = status === "CURRENT" ? "success" : status === "STALE" ? "danger" : "neutral";
  return <Badge variant={variant}>{LABELS[status]}</Badge>;
}

