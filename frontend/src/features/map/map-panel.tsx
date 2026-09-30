"use client";

import { Activity, Ban, Users, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { syntheticDemoLabelEnabled } from "@/features/forecasting/demo-context";
import { cn } from "@/utils/cn";

import { DEMO_MAP_REGIONS, demoMapPoints } from "./demo-regions";
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

export function MapPanel({ metric, onMetricChange, apiPoints, selectedRegionId, selectedRegionName, onSelectRegion, apiValues }: MapPanelProps) {
  const demoEnabled = syntheticDemoLabelEnabled(process.env.NEXT_PUBLIC_APP_ENV, process.env.NEXT_PUBLIC_SYNTHETIC_DEMO);
  const [layer, setLayer] = useState<"demo" | "api">(demoEnabled ? "demo" : "api");
  const [selectedDemoId, setSelectedDemoId] = useState<string | null>(null);
  const isDemo = demoEnabled && layer === "demo";
  const selectedDemo = DEMO_MAP_REGIONS.find((region) => region.id === selectedDemoId);
  const points = isDemo ? demoMapPoints(metric) : apiPoints;
  const apiHasMappedPoint = apiPoints.some((point) => centerFor(point.name, point.code) !== null);

  return (
    <section className="surface-card overflow-hidden rounded-2xl" aria-label="Карта Казахстана">
      <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between lg:px-6">
        <div>
          <p className="eyebrow">Региональный контекст · Қазақстан</p>
          <h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Карта региональных показателей</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">На карте показан только Казахстан. Цвет обозначает сравнительный уровень, а не медицинский норматив.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {demoEnabled && (
            <div className="flex rounded-xl border border-cyan-200 bg-cyan-50 p-1" aria-label="Слой карты">
              <button type="button" aria-pressed={isDemo} onClick={() => setLayer("demo")} className={cn("rounded-lg px-3 py-2 text-[11px] font-bold", isDemo ? "bg-white text-cyan-900 shadow-sm" : "text-slate-600")}>Демо-слой</button>
              <button type="button" aria-pressed={!isDemo} onClick={() => setLayer("api")} className={cn("rounded-lg px-3 py-2 text-[11px] font-bold", !isDemo ? "bg-white text-cyan-900 shadow-sm" : "text-slate-600")}>Данные системы</button>
            </div>
          )}
          <div className="flex overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1">
            {(Object.keys(metricMeta) as MapMetric[]).map((key) => {
              const Icon = metricMeta[key].icon;
              return <button key={key} type="button" aria-pressed={metric === key} onClick={() => onMetricChange(key)} className={cn("flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-[11px] font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700", metric === key ? "bg-[#087b83] text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-900")}><Icon className="h-3.5 w-3.5" aria-hidden="true" />{metricMeta[key].label}</button>;
            })}
          </div>
        </div>
      </div>
      {isDemo && <p className="border-b border-cyan-100 bg-cyan-50/70 px-5 py-2.5 text-[11px] font-semibold text-cyan-950 lg:px-6">Условные демонстрационные значения — только для карты; они не получены из API и не входят в KPI.</p>}
      <div className="grid xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="relative h-[380px] overflow-hidden bg-[#eaf5f4] sm:h-[440px]">
          <RegionMap points={points} metric={metric} selectedRegionId={isDemo ? selectedDemoId : selectedRegionId} onSelect={isDemo ? setSelectedDemoId : onSelectRegion} />
          <div className="absolute left-4 top-4 z-[500] rounded-xl border border-white/80 bg-white/95 px-3 py-2 text-[10px] font-bold text-slate-700 shadow-lg">
            {metricMeta[metric].label} · {isDemo ? "демо-пример" : metricMeta[metric].source}
          </div>
          <span className="absolute bottom-3 left-4 z-[500] rounded-md bg-white/80 px-2 py-1 text-[9px] text-slate-600">Граница: Natural Earth · public domain</span>
        </div>
        <aside className="border-t border-slate-200 bg-[#fbfdfd] p-5 xl:border-l xl:border-t-0 xl:p-6">
          <div className="flex items-center justify-between gap-3">
            <span className="rounded-full bg-cyan-50 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-wider text-cyan-800">{isDemo ? "Демонстрационный слой" : selectedRegionId ? "Выбран регион" : "Данные системы"}</span>
            {(isDemo ? selectedDemoId : selectedRegionId) && <button type="button" className="text-[11px] font-bold text-slate-500 hover:text-slate-900" onClick={() => isDemo ? setSelectedDemoId(null) : onSelectRegion(null)}>Сбросить</button>}
          </div>
          <h3 className="mt-5 text-xl font-extrabold tracking-[-0.04em] text-[#12334a]">{isDemo ? selectedDemo?.name ?? "Қазақстан" : selectedRegionName ?? "Доступная выборка"}</h3>
          <p className="mt-2 text-xs leading-5 text-slate-500">{isDemo ? "Выберите маркер. Значения ниже — иллюстрация, не официальная статистика и не результат API." : selectedRegionId ? "Показатели пересчитаны backend в рамках выбранного региона." : apiHasMappedPoint ? "Выберите регион на карте, чтобы сузить аналитику." : `В этом слое нет регионов с сопоставленной географией. Получено записей API: ${apiPoints.length}. Координаты не назначаются произвольно.`}</p>
          {isDemo ? (
            selectedDemo ? <dl className="mt-6 space-y-2.5"><MetricLine label="Направления" value={selectedDemo.referrals} /><MetricLine label="Ожидающие" value={selectedDemo.waiting} /><MetricLine label="Отказы" value={selectedDemo.refusals} /></dl> : <p className="mt-6 rounded-xl border border-dashed border-cyan-200 p-5 text-xs text-slate-600">Выберите одну из демонстрационных точек на карте.</p>
          ) : (
            <dl className="mt-6 space-y-2.5"><MetricLine label="Направления" value={apiValues.referrals} /><MetricLine label="Ожидающие" value={apiValues.waiting} /><MetricLine label="Отказы" value={apiValues.refusals} /><MetricLine label="Уникальные организации" value={apiValues.organizations} /></dl>
          )}
          <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-[11px] leading-5 text-amber-950">Карта не показывает загрузку коек и не заменяет подтверждённые медицинские данные.</div>
        </aside>
      </div>
    </section>
  );
}
