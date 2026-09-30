"use client";

import { Activity, Ban, Users, type LucideIcon } from "lucide-react";

import { syntheticDemoLabelEnabled } from "@/features/forecasting/demo-context";
import { cn } from "@/utils/cn";

import { centerFor } from "./geography";
import { RegionMap, type MapMetric, type RegionPoint } from "./region-map";

const metricMeta: Record<MapMetric, { label: string; source: string; icon: LucideIcon }> = {
  waiting: { label: "Ожидающие", source: "Предоставленный снимок", icon: Users },
  referrals: { label: "Направления", source: "ИС БГ", icon: Activity },
  refusals: { label: "Отказы", source: "ИС БГ", icon: Ban },
};

interface MapPanelProps {
  metric: MapMetric;
  onMetricChange: (metric: MapMetric) => void;
  apiPoints: RegionPoint[];
  apiLoading: boolean;
  apiError: boolean;
  selectedRegionId: string | null;
  selectedRegionName?: string;
  onSelectRegion: (id: string | null) => void;
  apiValues: { referrals: number | null; waiting: number | null; refusals: number | null; organizations: number };
}

function display(value: number | null): string {
  return value === null ? "—" : value.toLocaleString("ru-RU");
}

function MetricLine({ label, value }: { label: string; value: number | null }) {
  return <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-xs"><dt className="text-slate-500">{label}</dt><dd className="font-extrabold text-[#12334a]">{display(value)}</dd></div>;
}

export function MapPanel({ metric, onMetricChange, apiPoints, apiLoading, apiError, selectedRegionId, selectedRegionName, onSelectRegion, apiValues }: MapPanelProps) {
  const demoEnabled = syntheticDemoLabelEnabled(process.env.NEXT_PUBLIC_APP_ENV, process.env.NEXT_PUBLIC_SYNTHETIC_DEMO);
  const apiHasMappedPoint = apiPoints.some((point) => centerFor(point.name, point.code) !== null);
  const context = apiError
    ? "Данные карты временно недоступны"
    : apiLoading
      ? "Загружаем регионы…"
      : selectedRegionId
        ? "Показатели пересчитаны backend в рамках выбранного региона."
        : apiPoints.length === 0
          ? "Для выбранного периода регионы не найдены."
          : apiHasMappedPoint
            ? "Выберите регион на карте, чтобы сузить аналитику."
            : `Нет регионов с сопоставленной географией. Получено записей API: ${apiPoints.length}. Координаты не назначаются произвольно.`;

  return (
    <section className="surface-card overflow-hidden rounded-2xl" aria-label="Карта Казахстана">
      <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between lg:px-6">
        <div>
          <p className="eyebrow">Региональный контекст · Қазақстан</p>
          <h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Карта региональных показателей</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="flex overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1">
            {(Object.keys(metricMeta) as MapMetric[]).map((key) => {
              const Icon = metricMeta[key].icon;
              return <button key={key} type="button" aria-pressed={metric === key} onClick={() => onMetricChange(key)} className={cn("flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-[11px] font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700", metric === key ? "bg-[#087b83] text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-900")}><Icon className="h-3.5 w-3.5" aria-hidden="true" />{metricMeta[key].label}</button>;
            })}
          </div>
        </div>
      </div>
      {demoEnabled && <p className="border-b border-cyan-100 bg-cyan-50/70 px-5 py-2.5 text-[11px] font-semibold text-cyan-950 lg:px-6">Синтетические данные · исторический период · значения из API</p>}
      <div className="grid xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="relative h-[380px] overflow-hidden bg-[#eaf5f4] sm:h-[440px]">
          <RegionMap points={apiError ? [] : apiPoints} metric={metric} selectedRegionId={selectedRegionId} onSelect={onSelectRegion} />
          <div className="absolute left-4 top-4 z-[500] rounded-xl border border-white/80 bg-white/95 px-3 py-2 text-[10px] font-bold text-slate-700 shadow-lg">
            {metricMeta[metric].label} · {metricMeta[metric].source}
          </div>
          <span className="absolute bottom-3 left-4 z-[500] rounded-md bg-white/80 px-2 py-1 text-[9px] text-slate-600">Граница: Natural Earth · public domain</span>
        </div>
        <aside className="border-t border-slate-200 bg-[#fbfdfd] p-5 xl:border-l xl:border-t-0 xl:p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="rounded-full bg-cyan-50 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-wider text-cyan-800">{selectedRegionId ? "Выбран регион" : "Данные системы"}</span>
            {selectedRegionId && <button type="button" className="text-[11px] font-bold text-slate-500 hover:text-slate-900" onClick={() => onSelectRegion(null)}>Сбросить</button>}
          </div>
          <h3 className="mt-5 text-xl font-extrabold tracking-[-0.04em] text-[#12334a]">{selectedRegionName ?? "Доступная выборка"}</h3>
          <p className="mt-2 text-xs leading-5 text-slate-500">{context}</p>
          {!apiError && !apiLoading && <dl className="mt-6 space-y-2.5"><MetricLine label="Направления" value={apiValues.referrals} /><MetricLine label="Ожидающие" value={apiValues.waiting} /><MetricLine label="Отказы" value={apiValues.refusals} /><MetricLine label="Уникальные организации" value={apiValues.organizations} /></dl>}
        </aside>
      </div>
    </section>
  );
}
