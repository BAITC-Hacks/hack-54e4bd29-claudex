import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { AnalyticsCell } from "@/features/analytics/types";
import { SuppressedValue } from "@/features/analytics/components/suppressed-value";

export function KpiCard({ title, value, period, source, icon: Icon }: { title: string; value: AnalyticsCell; period: string; source: string; icon: LucideIcon }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight"><SuppressedValue cell={value} /></p>
          </div>
          <div className="rounded-lg bg-primary/10 p-2.5 text-primary"><Icon className="h-5 w-5" aria-hidden="true" /></div>
        </div>
        <div className="mt-4 space-y-1 border-t pt-3 text-xs text-muted-foreground">
          <p>{period}</p><p>{source}</p>
        </div>
      </CardContent>
    </Card>
  );
}
