import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SCOPE_LABELS } from "@/features/signals/labels";
import type { SignalDetail } from "@/types/domain";

export function SignalEvidence({ detail }: { detail: SignalDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Основание сигнала</CardTitle>
        <CardDescription>
          Воспроизводимые значения, версия правила и период оценки.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge variant="neutral">{SCOPE_LABELS[detail.scope_type]}</Badge>
          <Badge variant={detail.data_current ? "neutral" : "warning"}>
            {detail.data_current ? "Данные актуальны для правила" : "Данные неактуальны"}
          </Badge>
        </div>
        <dl className="space-y-2">
          <EvidenceRow label="Правило">
            <span className="font-mono text-xs">
              {detail.rule_code} / {detail.rule_version}
            </span>
          </EvidenceRow>
          <EvidenceRow label="Источник">{detail.source}</EvidenceRow>
          <EvidenceRow label="Период оценки">
            {formatRange(detail.evaluation_period_start, detail.evaluation_period_end)}
          </EvidenceRow>
          <EvidenceRow label="Эталонный период">
            {formatRange(detail.reference_period_start, detail.reference_period_end)}
          </EvidenceRow>
          <EvidenceRow label="Фактическое значение">
            {formatNumber(detail.actual_value)}
          </EvidenceRow>
          <EvidenceRow label="Базовый уровень">
            {formatNumber(detail.baseline_value)}
          </EvidenceRow>
          <EvidenceRow label="Отклонение">
            {detail.delta_percent === null
              ? "—"
              : `${formatNumber(detail.delta_percent)}%`}
          </EvidenceRow>
        </dl>
        <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
          Пороги являются конфигурируемой первоначальной аналитической
          политикой. Они не являются медицинскими нормативами или SLA.
        </p>
      </CardContent>
    </Card>
  );
}

function EvidenceRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

function formatNumber(value: number | null): string {
  return value === null ? "—" : value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function formatRange(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  return `${start} — ${end}`;
}
