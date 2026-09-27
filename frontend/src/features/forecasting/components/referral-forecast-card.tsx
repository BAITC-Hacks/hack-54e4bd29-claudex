"use client";

import { useEffect, useRef } from "react";

import { Card, CardContent } from "@/components/ui/card";
import type { ReferralForecast } from "@/features/forecasting/types";

interface Props {
  forecast: ReferralForecast | undefined;
  isLoading: boolean;
  error: Error | null;
  isSyntheticDemo?: boolean;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(new Date(value));
}

function formatNumber(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

export function ReferralForecastCard({ forecast, isLoading, error, isSyntheticDemo = false }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!forecast || !chartRef.current) return;
    let disposed = false;
    let cleanup = () => undefined;
    void import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;
      const chart = echarts.init(chartRef.current);
      const historyDates = forecast.historical.map((item) => item.date);
      const forecastDates = forecast.forecast.map((item) => item.date);
      const dates = [...historyDates, ...forecastDates];
      const history = [
        ...forecast.historical.map((item) => item.value),
        ...forecast.forecast.map(() => null),
      ];
      const forecastValues = [
        ...forecast.historical.map(() => null),
        ...forecast.forecast.map((item) => item.predicted_value),
      ];
      const baselineValues = [
        ...forecast.historical.map(() => null),
        ...forecast.forecast.map((item) => item.baseline_value),
      ];
      chart.setOption({
        animationDuration: 300,
        grid: { left: 52, right: 20, top: 32, bottom: 44 },
        tooltip: { trigger: "axis" },
        legend: { data: ["История", "Прогноз", "Baseline"] },
        xAxis: { type: "category", boundaryGap: false, data: dates.map(formatDate) },
        yAxis: { type: "value", min: 0 },
        series: [
          { name: "История", type: "line", showSymbol: false, data: history, lineStyle: { color: "#2563eb", width: 2 } },
          { name: "Прогноз", type: "line", showSymbol: true, data: forecastValues, lineStyle: { color: "#7c3aed", width: 3 } },
          { name: "Baseline", type: "line", showSymbol: false, data: baselineValues, lineStyle: { color: "#64748b", type: "dashed" } },
        ],
      });
      const resize = () => chart.resize();
      window.addEventListener("resize", resize);
      cleanup = () => {
        window.removeEventListener("resize", resize);
        chart.dispose();
      };
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [forecast]);

  if (isLoading) {
    return <p className="rounded-lg border bg-card p-5 text-sm text-muted-foreground">Загрузка сохранённого прогноза…</p>;
  }
  if (error || !forecast) {
    return (
      <section className="rounded-lg border bg-card p-5" aria-live="polite">
        <h2 className="font-semibold">Краткосрочный прогноз потока направлений</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Прогноз пока недоступен для текущей области данных или ещё не сформирован.
        </p>
      </section>
    );
  }

  return (
    <Card>
      <CardContent className="p-5">
        <h2 className="text-base font-semibold">Краткосрочный прогноз потока направлений</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Горизонт: {forecast.horizon_days} дней · модель: {forecast.selected_model} · baseline: {forecast.baseline_model}
        </p>
        {forecast.freshness_status === "STALE" ? (
          <p className="mt-2 text-sm font-medium text-amber-800" role="status">
            Историческая проверка прогноза. Исторический прогноз: период его действия завершён. MAE измерена на предшествующих временных окнах, не на показанных прогнозных датах.
          </p>
        ) : null}
        {isSyntheticDemo ? (
          <p className="mt-2 text-sm font-medium" role="status">
            Прогноз на синтетических демонстрационных данных.
          </p>
        ) : null}
        <div
          ref={chartRef}
          className="mt-4 h-72 w-full"
          role="img"
          aria-label={`История направлений и расчётный прогноз на ${forecast.horizon_days} дней.`}
        />
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-primary">Табличное представление прогноза</summary>
          <div className="mt-3 overflow-auto rounded-md border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted"><tr><th className="px-3 py-2">Дата</th><th className="px-3 py-2 text-right">Прогноз</th><th className="px-3 py-2 text-right">Baseline</th><th className="px-3 py-2 text-right">Δ</th></tr></thead>
              <tbody>{forecast.forecast.map((item) => <tr key={item.date} className="border-t"><td className="px-3 py-2">{formatDate(item.date)}</td><td className="px-3 py-2 text-right">{formatNumber(item.predicted_value)}</td><td className="px-3 py-2 text-right">{formatNumber(item.baseline_value)}</td><td className="px-3 py-2 text-right">{formatNumber(item.delta_from_baseline)}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
        <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-950">
          <p className="font-medium">{forecast.disclaimer}</p>
          <ul className="mt-2 space-y-1 text-xs">
            {forecast.limitations.map((item) => <li key={item}>— {item}</li>)}
          </ul>
        </div>
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          <p>Источник: ИС БГ · показатель: зарегистрированные направления за день · область: {forecast.scope_type === "GLOBAL" ? "глобальная" : forecast.scope_type === "REGION" ? "региональная" : "организация"}</p>
          <p>Исходные данные: {formatDate(forecast.input_period_start)} — {formatDate(forecast.input_period_end)} · горизонт: {formatDate(forecast.forecast_start)} — {formatDate(forecast.forecast_end)}</p>
          <p>Историческая валидация модели:</p>
          <p>Период оценки: {forecast.validation_period_start && forecast.validation_period_end ? `${formatDate(forecast.validation_period_start)} — ${formatDate(forecast.validation_period_end)}` : "не указан"}</p>
          <p>MAE модели: {formatNumber(forecast.metrics.mae)} направлений/день</p>
          <p>MAE baseline: {formatNumber(forecast.baseline_metrics.mae)} направлений/день</p>
          <p>Версия модели: {forecast.model_version} · сформирован {formatDate(forecast.generated_at)}</p>
          <p>Идентификатор прогноза: {forecast.id}</p>
        </div>
      </CardContent>
    </Card>
  );
}
