"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useScenarioPreview, useScenarioSave } from "@/features/scenarios/hooks";
import type {
  ScenarioAssumption,
  ScenarioBaselineType,
  ScenarioRequest,
  ScenarioResult,
} from "@/features/scenarios/types";

const ASSUMPTIONS: ScenarioAssumption[] = [-0.2, -0.1, 0.1, 0.2];
const DISCLAIMER =
  "Расчётный сценарий. Не является прогнозом или рекомендацией. Решение принимает уполномоченный сотрудник.";

interface ScenarioWorkbenchProps {
  sourceSignalId?: string;
  initialForecastId?: string;
  signalContext?: {
    type: string;
    period?: string;
    actual?: number | null;
    baseline?: number | null;
    delta?: number | null;
  };
}

export function ScenarioWorkbench({
  sourceSignalId,
  initialForecastId,
  signalContext,
}: ScenarioWorkbenchProps) {
  const [baselineType, setBaselineType] = useState<ScenarioBaselineType>("OBSERVED");
  const [assumption, setAssumption] = useState<ScenarioAssumption>(0.2);
  const [dateFrom, setDateFrom] = useState("2025-01-01");
  const [dateTo, setDateTo] = useState("2025-03-31");
  const [forecastId, setForecastId] = useState(initialForecastId ?? "");
  const preview = useScenarioPreview();
  const save = useScenarioSave();
  const result = save.data ?? preview.data;

  const request = useMemo<ScenarioRequest>(
    () => ({
      scenario_type: "REFERRAL_INFLOW_CHANGE",
      scope_type: "GLOBAL",
      baseline_type: baselineType,
      assumption_value: assumption,
      historical_analysis: true,
      ...(baselineType === "OBSERVED"
        ? { period_start: dateFrom, period_end: dateTo }
        : { forecast_id: forecastId }),
      ...(sourceSignalId ? { source_signal_id: sourceSignalId } : {}),
    }),
    [assumption, baselineType, dateFrom, dateTo, forecastId, sourceSignalId],
  );

  const canSubmit =
    baselineType === "OBSERVED" ? Boolean(dateFrom && dateTo) : Boolean(forecastId);

  return (
    <div className="space-y-5">
      {signalContext && (
        <Card>
          <CardHeader>
            <CardTitle>Контекст сигнала</CardTitle>
            <CardDescription>
              Обнаруженное событие показано отдельно от нового гипотетического расчёта.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <span>Тип: {signalContext.type}</span>
            <span>Период: {signalContext.period ?? "—"}</span>
            <span>Факт: {formatNumber(signalContext.actual)}</span>
            <span>Baseline сигнала: {formatNumber(signalContext.baseline)}</span>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Расчётный сценарий</CardTitle>
          <CardDescription>
            Выберите подтверждённый baseline и одно фиксированное изменение потока направлений.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Источник baseline</legend>
            <div className="flex gap-2">
              <Button type="button" variant={baselineType === "OBSERVED" ? "default" : "outline"} onClick={() => setBaselineType("OBSERVED")}>Наблюдаемые данные</Button>
              <Button type="button" variant={baselineType === "FORECAST" ? "default" : "outline"} onClick={() => setBaselineType("FORECAST")}>Сохранённый прогноз</Button>
            </div>
          </fieldset>

          {baselineType === "OBSERVED" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm">Начало периода<input aria-label="Начало периода" className="mt-1 h-9 w-full rounded-md border bg-background px-3" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
              <label className="text-sm">Конец периода<input aria-label="Конец периода" className="mt-1 h-9 w-full rounded-md border bg-background px-3" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
            </div>
          ) : (
            <label className="block text-sm">ID сохранённого прогноза<input aria-label="ID сохранённого прогноза" className="mt-1 h-9 w-full rounded-md border bg-background px-3" value={forecastId} onChange={(event) => setForecastId(event.target.value)} placeholder="UUID Forecast" /></label>
          )}

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Гипотетическое изменение входящего потока</legend>
            <div className="flex flex-wrap gap-2">
              {ASSUMPTIONS.map((value) => (
                <Button key={value} type="button" variant={assumption === value ? "default" : "outline"} aria-pressed={assumption === value} onClick={() => setAssumption(value)}>
                  {formatPercent(value)}
                </Button>
              ))}
            </div>
          </fieldset>

          <div className="flex flex-wrap gap-2">
            <Button disabled={!canSubmit || preview.isPending} onClick={() => preview.mutate(request)}>Рассчитать preview</Button>
            <Button variant="outline" disabled={!preview.data || save.isPending} onClick={() => save.mutate({ ...request, client_request_id: crypto.randomUUID() })}>Сохранить сценарий</Button>
          </div>
          {(preview.error || save.error) && <p role="alert" className="text-sm text-destructive">{(preview.error ?? save.error)?.message}</p>}
        </CardContent>
      </Card>

      {result && <ScenarioResultCard result={result} />}

      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
        <p className="font-medium">{DISCLAIMER}</p>
        <p className="mt-1">Расчёт меняет только число направлений и не моделирует койки, госпитализации, выписки, длительность лечения, персонал, занятость или дефицит мощности.</p>
      </div>
    </div>
  );
}

export function ScenarioResultCard({ result }: { result: ScenarioResult }) {
  const max = Math.max(result.baseline_value, result.calculated_value);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{result.id ? "Сохранённый сценарий" : "Preview"}</CardTitle>
        <CardDescription>
          {result.historical ? "Исторический сценарный анализ" : "Сценарный анализ"}
          {result.baseline_freshness_status === "STALE" ? " · baseline устарел" : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Metric label="Baseline" value={result.baseline_value} />
          <Metric label="Допущение" value={formatPercent(result.assumption_value)} />
          <Metric label="Расчётное значение" value={result.calculated_value} />
        </div>
        <div aria-label="Сравнение baseline и сценария" className="space-y-2 text-sm">
          <ComparisonBar label="Baseline" value={result.baseline_value} max={max} />
          <ComparisonBar label="Сценарий" value={result.calculated_value} max={max} />
        </div>
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Табличное сравнение baseline и сценария</caption>
          <tbody><tr><th>Разница</th><td>{formatNumber(result.delta_absolute)} ({formatPercent(result.delta_percent)})</td></tr><tr><th>Период</th><td>{result.baseline_period_start} — {result.baseline_period_end}</td></tr><tr><th>Источник</th><td>{result.baseline_type === "OBSERVED" ? "Наблюдаемые агрегаты" : "Сохранённый Forecast"}</td></tr></tbody>
        </table>
        {result.forecast_id && <p className="text-xs text-muted-foreground">Forecast: {result.forecast_status} · freshness: {result.baseline_freshness_status} · модель: {result.selected_model ?? "—"} / {result.model_version ?? "—"}</p>}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) { return <div className="rounded-md border p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-xl font-semibold">{typeof value === "number" ? formatNumber(value) : value}</p></div>; }
function ComparisonBar({ label, value, max }: { label: string; value: number; max: number }) { return <div><div className="flex justify-between"><span>{label}</span><b>{formatNumber(value)}</b></div><div className="mt-1 h-2 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${max > 0 ? (value / max) * 100 : 0}%` }} /></div></div>; }
function formatNumber(value: number | null | undefined) { return value === null || value === undefined ? "—" : value.toLocaleString("ru-RU", { maximumFractionDigits: 4 }); }
function formatPercent(value: number) { return `${value > 0 ? "+" : ""}${Math.round(value * 100)}%`; }
