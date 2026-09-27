"use client";

import { useEffect, useRef } from "react";

import { Card, CardContent } from "@/components/ui/card";
import type { TimeSeries } from "@/features/analytics/types";
import { formatCell, formatDate } from "@/features/analytics/format";

export function TimeSeriesChart({ title, description, series, color }: { title: string; description: string; series: TimeSeries; color: string }) {
  const chartRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!chartRef.current) return;
    let disposed = false;
    let cleanup = () => undefined;
    void import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;
      const chart = echarts.init(chartRef.current);
      chart.setOption({
        animationDuration: 300,
        grid: { left: 48, right: 20, top: 24, bottom: 42 },
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", boundaryGap: false, data: series.data.points.map((item) => formatDate(item.period)), axisLabel: { hideOverlap: true } },
        yAxis: { type: "value", min: 0 },
        series: [{ type: "line", smooth: true, showSymbol: false, lineStyle: { width: 3, color }, areaStyle: { color, opacity: 0.08 }, data: series.data.points.map((item) => item.value.suppressed ? null : item.value.value) }],
      });
      const resize = () => chart.resize();
      window.addEventListener("resize", resize);
      cleanup = () => { window.removeEventListener("resize", resize); chart.dispose(); };
    });
    return () => { disposed = true; cleanup(); };
  }, [color, series]);

  return (
    <Card>
      <CardContent className="p-5">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        <div ref={chartRef} className="mt-4 h-72 w-full" role="img" aria-label={`${title}. ${series.data.points.length} агрегированных периодов.`} />
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-primary">Табличное представление</summary>
          <div className="mt-3 max-h-64 overflow-auto rounded-md border">
            <table className="w-full text-left text-xs"><thead className="sticky top-0 bg-muted"><tr><th className="px-3 py-2">Период</th><th className="px-3 py-2 text-right">Значение</th></tr></thead><tbody>{series.data.points.map((item) => <tr key={item.period} className="border-t"><td className="px-3 py-2">{formatDate(item.period)}</td><td className="px-3 py-2 text-right">{formatCell(item.value)}</td></tr>)}</tbody></table>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}
