import { Card, CardContent } from "@/components/ui/card";
import { SuppressedValue } from "@/features/analytics/components/suppressed-value";
import type { WaitingSummary } from "@/features/analytics/types";

export function WaitingAgeSummary({ summary }: { summary: WaitingSummary }) {
  const metrics = [
    ["Медиана", summary.data.median_days],
    ["75-й перцентиль", summary.data.p75_days],
    ["90-й перцентиль", summary.data.p90_days],
    ["Максимум", summary.data.oldest_days],
  ] as const;
  const snapshotAt = summary.data.snapshot_at;
  const confirmed = summary.data.snapshot_semantics_confirmed && snapshotAt !== null;

  return (
    <Card>
      <CardContent className="p-5">
        <h2 className="text-base font-semibold">Возраст очереди в снимке</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Возраст записей на дату предоставленного снимка. Это не историческая
          динамика ожидания.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {confirmed ? (
            <>
              Снимок: <time dateTime={snapshotAt}>{snapshotAt}</time>
            </>
          ) : (
            "Семантика снимка не подтверждена или дата неизвестна."
          )}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {metrics.map(([label, cell]) => (
            <div key={label}>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="mt-1 text-xl font-semibold">
                <SuppressedValue cell={cell} />{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  дней
                </span>
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
