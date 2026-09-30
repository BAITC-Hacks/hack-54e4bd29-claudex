"use client";

import { useEffect, useRef } from "react";

import { Card, CardContent } from "@/components/ui/card";
import type { ReferralForecast } from "@/features/forecasting/types";
import { useI18n, type Language } from "@/features/i18n/i18n-context";
import { ApiError } from "@/services/api-client";

interface Props {
  forecast: ReferralForecast | undefined;
  isLoading: boolean;
  error: Error | null;
  isSyntheticDemo?: boolean;
}

function formatDate(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language === "kk" ? "kk-KZ" : "ru-RU", { dateStyle: "medium" }).format(new Date(value));
}

function formatNumber(value: number, language: Language): string {
  return value.toLocaleString(language === "kk" ? "kk-KZ" : "ru-RU", { maximumFractionDigits: 1 });
}

export function buildForecastChartOption(forecast: ReferralForecast, language: Language, t: (text: string) => string) {
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
  return {
    animationDuration: 300,
    grid: { left: 52, right: 20, top: 32, bottom: 44 },
    tooltip: { trigger: "axis" },
    legend: { data: [t("История"), t("Прогноз"), t("Простое сравнение")] },
    xAxis: { type: "category", boundaryGap: false, data: dates.map((date) => formatDate(date, language)) },
    yAxis: { type: "value", min: 0 },
    series: [
      { name: t("История"), type: "line", showSymbol: false, data: history, lineStyle: { color: "#2563eb", width: 2 } },
      { name: t("Прогноз"), type: "line", showSymbol: true, data: forecastValues, lineStyle: { color: "#7c3aed", width: 3 } },
      { name: t("Простое сравнение"), type: "line", showSymbol: false, data: baselineValues, lineStyle: { color: "#64748b", type: "dashed" } },
    ],
  };
}

export function ReferralForecastCard({ forecast, isLoading, error, isSyntheticDemo = false }: Props) {
  const { language, t } = useI18n();
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!forecast || !chartRef.current) return;
    let disposed = false;
    let cleanup = () => undefined;
    void import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;
      const chart = echarts.init(chartRef.current);
      chart.setOption(buildForecastChartOption(forecast, language, t));
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
  }, [forecast, language, t]);

  if (isLoading) {
    return <p className="rounded-lg border bg-card p-5 text-sm text-muted-foreground">Загрузка сохранённого прогноза…</p>;
  }
  if (error && (!(error instanceof ApiError) || error.httpStatus !== 404)) {
    return <section role="alert" className="rounded-lg border bg-card p-5"><h2 className="font-semibold">Не удалось загрузить прогноз</h2><p className="mt-2 text-sm">Проверьте соединение и повторите запрос. Ошибка загрузки не означает отсутствие прогноза.</p></section>;
  }
  if (!forecast) {
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
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-cyan-700">Прогнозирование</p>
            <h2 className="mt-1 text-base font-extrabold tracking-[-0.02em] text-[#102f45]">Краткосрочный прогноз потока направлений</h2>
          </div>
          <span className="w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[9px] font-extrabold uppercase tracking-wide text-slate-600">{forecast.scope_type === "GLOBAL" ? "Вся система" : forecast.scope_type === "REGION" ? "Регион" : "Организация"}</span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Горизонт: {forecast.horizon_days} дней · период: {formatDate(forecast.forecast_start, language)} — {formatDate(forecast.forecast_end, language)}
        </p>
        {forecast.freshness_status === "STALE" ? (
          <p className="mt-2 text-sm font-medium text-amber-800" role="status">
            Историческая валидация прогноза. Исторический прогноз: период его действия завершён. MAE измерена на предшествующих временных окнах, не на показанных прогнозных датах.
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
              <thead className="bg-muted"><tr><th className="px-3 py-2">Дата</th><th className="px-3 py-2 text-right">Прогноз</th><th className="px-3 py-2 text-right">Простое сравнение</th><th className="px-3 py-2 text-right">Δ</th></tr></thead>
              <tbody>{forecast.forecast.map((item) => <tr key={item.date} className="border-t"><td className="px-3 py-2">{formatDate(item.date, language)}</td><td className="px-3 py-2 text-right">{formatNumber(item.predicted_value, language)}</td><td className="px-3 py-2 text-right">{formatNumber(item.baseline_value, language)}</td><td className="px-3 py-2 text-right">{formatNumber(item.delta_from_baseline, language)}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
        <div className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-950">
          <p className="font-medium">{forecast.disclaimer}</p>
          <ul className="mt-2 space-y-1 text-xs">
            {forecast.limitations.map((item) => <li key={item}>— {item}</li>)}
          </ul>
        </div>
        <section className="mt-4 rounded-xl border border-cyan-100 bg-cyan-50/60 p-4 text-sm leading-6 text-slate-700">
          <h3 className="font-extrabold text-[#12334a]">Как читать прогноз</h3>
          <p className="mt-1">MAE показывает среднюю абсолютную ошибку на исторической временной проверке. Значение приводится в направлениях за день и не является процентом точности.</p>
          <p className="mt-2 font-semibold text-slate-800">Прогноз отражает входящий поток направлений и не является прогнозом свободных коек, даты выписки или медицинской рекомендацией.</p>
        </section>
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          <p>Источник: ИС БГ · Целевой показатель: ежедневное число направлений · Область: {forecast.scope_type === "GLOBAL" ? "вся система (GLOBAL)" : forecast.scope_type === "REGION" ? "регион (REGION)" : "организация (HOSPITAL)"}</p>
          <p>Исходные данные: {formatDate(forecast.input_period_start, language)} — {formatDate(forecast.input_period_end, language)} · горизонт: {formatDate(forecast.forecast_start, language)} — {formatDate(forecast.forecast_end, language)}</p>
          <p>Историческая валидация модели:</p>
          <p>Период оценки: {forecast.validation_period_start && forecast.validation_period_end ? `${formatDate(forecast.validation_period_start, language)} — ${formatDate(forecast.validation_period_end, language)}` : "не указан"}</p>
          <p>MAE модели: {formatNumber(forecast.metrics.mae, language)} направлений/день</p>
          <p>MAE baseline: {formatNumber(forecast.baseline_metrics.mae, language)} направлений/день</p>
          <p>Модель: {forecast.selected_model} · простое сравнение: {forecast.baseline_model}</p>
          <p>Версия модели: {forecast.model_version} · сформирован {formatDate(forecast.generated_at, language)}</p>
          <p>Идентификатор прогноза: {forecast.id}</p>
        </div>
      </CardContent>
    </Card>
  );
}
