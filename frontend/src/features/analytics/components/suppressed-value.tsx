import { ShieldCheck } from "lucide-react";

import type { AnalyticsCell } from "@/features/analytics/types";
import { formatCell } from "@/features/analytics/format";

export function SuppressedValue({ cell }: { cell: AnalyticsCell }) {
  if (!cell.suppressed) return <>{formatCell(cell)}</>;
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground" title="Малая группа скрыта для защиты конфиденциальности">
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      Скрыто
    </span>
  );
}
