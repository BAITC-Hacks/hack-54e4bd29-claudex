"use client";

import { useQueries } from "@tanstack/react-query";
import {
  Activity, Ban, CalendarClock, CircleHelp, Database, MapPinned, Search,
  ShieldCheck, Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { fetchOverview } from "@/features/analytics/api";
import { useSituationCenter } from "@/features/analytics/hooks";
import type { AnalyticsQuery, Overview } from "@/features/analytics/types";
import { useLatestReferralForecast } from "@/features/forecasting/hooks";
import { RegionMap, type MapMetric, type RegionPoint } from "@/features/map/region-map";
import { useRegions, useSignals } from "@/hooks/use-domain";

const BASE_QUERY: AnalyticsQuery = {
  dateFrom: "2025-01-01T00:00:00Z",
  dateTo: "2025-03-31T23:59:59.999Z",
  granularity: "DAY",
};

const metricMeta = {
  waiting: { label: "Ожидающие", source: "ИС БГ", icon: Users },
  referrals: { label: "Направления", source: "ИС БГ", icon: Activity },
  refusals: { label: "Отказы", source: "ИС БГ", icon: Ban },
};

function cellValue(overview: Overview | undefined, metric: MapMetric): number | null {
  if (!overview) return null;
  if (metric === "waiting") return overview.data.waiting_records.value;
  if (metric === "referrals") return overview.data.referrals_total.value;
  return overview.data.refusals_total.value;
}

function number(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

export default function CommandCenterPage() {
  const { isAuthenticated } = useAuth();
  const [metric, setMetric] = useState<MapMetric>("waiting");
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const regions = useRegions(isAuthenticated);
  const query = useMemo<AnalyticsQuery>(() => ({ ...BASE_QUERY, ...(selectedRegionId ? { region: selectedRegionId } : {}) }), [selectedRegionId]);
  const analytics = useSituationCenter(isAuthenticated, query);
  const forecast = useLatestReferralForecast(isAuthenticated);
  const signals = useSignals(isAuthenticated, { page: 1, pageSize: 6, regionId: selectedRegionId ?? undefined });

  const regionQueries = useQueries({
    queries: (regions.data?.items ?? []).map((region) => ({
      queryKey: ["command-center", "region-overview", region.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchOverview({ ...BASE_QUERY, region: region.id }, signal),
      enabled: isAuthenticated,
      staleTime: 60_000,
    })),
  });

  const points = useMemo<RegionPoint[]>(() => (regions.data?.items ?? []).map((region, index) => ({
    id: region.id,
    name: region.name,
    code: region.code,
    value: cellValue(regionQueries[index]?.data, metric),
  })), [metric, regionQueries, regions.data?.items]);
  const onSelect = useCallback((id: string | null) => setSelectedRegionId(id), []);
  const selectedRegion = regions.data?.items.find((region) => region.id === selectedRegionId);
  const overview = analytics.overview.data;
  const waiting = analytics.waiting.data;
  const organizations = analytics.organizations.data?.data.items ?? [];
  const visibleOrganizations = organizations.filter((item) => (item.display_name ?? item.identity_label ?? item.organization_ref).toLowerCase().includes(search.toLowerCase()));
  const pending = analytics.overview.isPending || analytics.waiting.isPending || analytics.organizations.isPending;
  const error = analytics.overview.error ?? analytics.waiting.error ?? analytics.organizations.error;

  return <div className="space-y-5">
    <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[.14em] text-teal-700"><MapPinned size={15}/>Национальный ситуационный центр</div><h1 className="mt-2 text-3xl font-semibold tracking-[-.035em]">Медицинская нагрузка Казахстана</h1><p className="mt-2 max-w-3xl text-sm text-slate-500">Фактические агрегаты загруженных выгрузок ИС БГ, ЭРСБ и ЕИП. Период: январь—март 2025.</p></div>
      <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800"><Database size={15}/><span>Источник: backend API</span><i className="h-2 w-2 rounded-full bg-emerald-500"/></div>
    </section>

    <AuthGate>
      {error && <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">Backend недоступен: {error.message}</div>}
      {pending && <div className="rounded-xl border bg-white p-8 text-sm text-slate-500">Загружаем реальные агрегаты…</div>}
      {overview && waiting && <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi icon={Activity} label="Направления" value={number(overview.data.referrals_total.value)} note="ИС БГ · фактические записи" tone="teal"/>
          <Kpi icon={Users} label="Ожидающие" value={number(overview.data.waiting_records.value)} note="Последний доступный снимок" tone="amber"/>
          <Kpi icon={Ban} label="Отказы" value={number(overview.data.refusals_total.value)} note="ИС БГ · фактические события" tone="red"/>
          <Kpi icon={CalendarClock} label="Медиана ожидания" value={waiting.data.median_days.value === null ? "—" : `${number(waiting.data.median_days.value)} дн.`} note={`P90: ${waiting.data.p90_days.value === null ? "—" : `${number(waiting.data.p90_days.value)} дн.`}`} tone="slate"/>
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-4 lg:flex-row lg:items-center lg:justify-between">
            <div><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">Регионы Казахстана</p><h2 className="mt-1 font-semibold">Сравнительная карта фактической нагрузки</h2></div>
            <div className="flex rounded-lg bg-slate-100 p-1">{(Object.keys(metricMeta) as MapMetric[]).map((key)=>{const Icon=metricMeta[key].icon;return <button key={key} onClick={()=>setMetric(key)} className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold transition ${metric===key?"bg-white text-teal-700 shadow-sm":"text-slate-500"}`}><Icon size={14}/>{metricMeta[key].label}</button>})}</div>
          </div>
          <div className="grid min-h-[560px] lg:grid-cols-[1fr_300px]">
            <div className="relative min-h-[520px] overflow-hidden bg-slate-100"><RegionMap points={points} metric={metric} selectedRegionId={selectedRegionId} onSelect={onSelect}/><div className="absolute left-3 top-3 z-[500] rounded-lg bg-slate-900/90 px-3 py-2 text-[10px] font-semibold text-white shadow-lg">{metricMeta[metric].label} · {metricMeta[metric].source}</div><div className="absolute bottom-3 left-3 z-[500] flex flex-wrap gap-3 rounded-lg border bg-white/95 px-3 py-2 text-[9px] text-slate-600 shadow-lg"><b>Относительно регионов:</b><span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-emerald-500"/>ниже</span><span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-amber-400"/>средне</span><span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-red-500"/>выше</span><span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-slate-400"/>нет сопоставления</span></div></div>
            <aside className="border-l border-slate-200 p-5"><div className="flex items-center justify-between"><span className="rounded-full bg-teal-50 px-2 py-1 text-[9px] font-bold uppercase text-teal-700">{selectedRegion ? "Выбран регион" : "Весь Казахстан"}</span>{selectedRegion&&<button className="text-xs text-slate-400 hover:text-slate-700" onClick={()=>setSelectedRegionId(null)}>Сбросить</button>}</div><h3 className="mt-4 text-lg font-semibold">{selectedRegion?.name ?? "Национальная сводка"}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{selectedRegion ? "Все показатели ниже пересчитаны backend в рамках выбранного региона." : "Выберите регион на карте, чтобы сузить аналитику."}</p><div className="mt-5 space-y-2"><MetricLine label="Направления" value={overview.data.referrals_total.value}/><MetricLine label="Ожидающие" value={overview.data.waiting_records.value}/><MetricLine label="Отказы" value={overview.data.refusals_total.value}/><MetricLine label="Организации в данных" value={overview.data.represented_organizations.value}/></div><div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[10px] leading-5 text-amber-900"><b className="flex items-center gap-1.5"><CircleHelp size={14}/>Как читать цвет</b><p className="mt-1">Это сравнительный уровень внутри текущей выгрузки, а не медицинский норматив перегрузки. Для расчёта загрузки коек backend должен получить официальный справочник мощностей.</p></div></aside>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">ML-прогноз</p><h2 className="mt-1 font-semibold">Поток направлений на 7 дней</h2></div><span className={`rounded-full px-2.5 py-1 text-[9px] font-bold ${forecast.data?.freshness_status==="CURRENT"?"bg-emerald-50 text-emerald-700":"bg-amber-50 text-amber-700"}`}>{forecast.data?.freshness_status ?? "Загрузка"}</span></div>{forecast.data ? <><div className="mt-6 flex h-48 items-end gap-2 border-b border-slate-200">{forecast.data.forecast.map((point)=><div key={point.date} className="group relative flex-1 rounded-t bg-teal-600 transition hover:bg-teal-700" style={{height:`${Math.max(12,(point.predicted_value/Math.max(...forecast.data!.forecast.map(p=>p.predicted_value)))*100)}%`}}><span className="absolute -top-6 left-1/2 hidden -translate-x-1/2 rounded bg-slate-900 px-1.5 py-1 text-[8px] text-white group-hover:block">{number(point.predicted_value)}</span></div>)}</div><div className="mt-3 flex items-center justify-between text-[10px] text-slate-500"><span>{new Date(forecast.data.forecast_start).toLocaleDateString("ru-RU")}</span><span>MAE: {number(forecast.data.metrics.mae)}</span><span>{new Date(forecast.data.forecast_end).toLocaleDateString("ru-RU")}</span></div><p className="mt-4 text-[10px] leading-5 text-slate-500">{forecast.data.disclaimer}</p></> : <p className="mt-6 text-sm text-slate-500">Прогноз пока не опубликован backend.</p>}</div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-start justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">Signal Engine</p><h2 className="mt-1 font-semibold">Сигналы, требующие внимания</h2></div><Link href="/signals" className="text-xs font-semibold text-teal-700">Все сигналы →</Link></div><div className="mt-4 space-y-2">{signals.data?.items.slice(0,4).map(signal=><Link href={`/signals/${signal.id}`} key={signal.id} className="block rounded-xl border border-slate-200 p-3 transition hover:border-teal-300 hover:bg-teal-50/30"><div className="flex items-center justify-between gap-2"><span className={`rounded-full px-2 py-1 text-[8px] font-bold uppercase ${signal.severity==="CRITICAL"?"bg-red-50 text-red-700":signal.severity==="HIGH"?"bg-orange-50 text-orange-700":"bg-amber-50 text-amber-700"}`}>{signal.severity}</span><span className="text-[9px] text-slate-400">{new Date(signal.detected_at).toLocaleDateString("ru-RU")}</span></div><h3 className="mt-2 text-xs font-semibold">{signal.title}</h3><p className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500">{signal.summary}</p></Link>)}{signals.data?.items.length===0&&<p className="rounded-xl border border-dashed p-6 text-center text-xs text-slate-500">Активных сигналов нет.</p>}</div></div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[.13em] text-slate-400">Реальные строки источников</p><h2 className="mt-1 font-semibold">Медицинские организации</h2></div><label className="flex h-9 w-full max-w-sm items-center gap-2 rounded-lg border border-slate-200 px-3 text-slate-400"><Search size={15}/><input className="w-full border-0 bg-transparent text-xs text-slate-800 outline-none" placeholder="Поиск организации" value={search} onChange={event=>setSearch(event.target.value)}/></label></div><div className="overflow-x-auto"><table className="w-full min-w-[800px] text-left text-xs"><thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Организация</th><th className="px-5 py-3">Направления</th><th className="px-5 py-3">Ожидающие</th><th className="px-5 py-3">Отказы</th><th className="px-5 py-3">Медиана ожидания</th><th className="px-5 py-3">Сопоставление</th></tr></thead><tbody className="divide-y divide-slate-100">{visibleOrganizations.slice(0,12).map(org=><tr key={org.organization_ref} className="hover:bg-slate-50"><td className="px-5 py-3"><Link href={`/organizations/${encodeURIComponent(org.organization_ref)}`} className="font-semibold text-slate-800 hover:text-teal-700">{org.display_name ?? org.identity_label ?? org.organization_ref}</Link><small className="mt-1 block text-[9px] text-slate-400">{org.source_system ?? "Источник не указан"}</small></td><td className="px-5 py-3 font-medium">{number(org.referrals_total.value)}</td><td className="px-5 py-3 font-medium">{number(org.waiting_records.value)}</td><td className="px-5 py-3 font-medium">{number(org.refusals_total.value)}</td><td className="px-5 py-3">{org.observed_waiting_median_days.value===null?"—":`${number(org.observed_waiting_median_days.value)} дн.`}</td><td className="px-5 py-3"><span className={`rounded-full px-2 py-1 text-[8px] font-bold ${org.mapping_status==="MAPPED"?"bg-emerald-50 text-emerald-700":"bg-slate-100 text-slate-600"}`}>{org.mapping_status}</span></td></tr>)}</tbody></table></div></section>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-[10px] leading-5 text-slate-600"><b className="flex items-center gap-2 text-slate-800"><ShieldCheck size={15} className="text-teal-700"/>Контроль достоверности</b><p className="mt-1">Интерфейс не создаёт значения коечного фонда, реагентов или географии организаций, которых нет в предоставленных данных. Несопоставленные идентификаторы остаются видимыми как UNMAPPED. После загрузки официального справочника backend автоматически даст карте точный региональный и организационный разрез.</p></div>
      </>}
    </AuthGate>
  </div>;
}

function Kpi({icon:Icon,label,value,note,tone}:{icon:typeof Activity;label:string;value:string;note:string;tone:"teal"|"amber"|"red"|"slate"}){
  const tones={teal:"bg-teal-50 text-teal-700",amber:"bg-amber-50 text-amber-700",red:"bg-red-50 text-red-700",slate:"bg-slate-100 text-slate-600"};
  return <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><div className="flex items-start justify-between"><span className={`grid h-9 w-9 place-items-center rounded-lg ${tones[tone]}`}><Icon size={17}/></span><CircleHelp size={14} className="text-slate-300"/></div><p className="mt-4 text-[10px] font-medium text-slate-500">{label}</p><strong className="mt-1 block text-2xl tracking-tight text-slate-900">{value}</strong><small className="mt-1 block text-[9px] text-slate-400">{note}</small></article>;
}

function MetricLine({label,value}:{label:string;value:number|null}){
  return <div className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5"><span className="text-[10px] text-slate-500">{label}</span><b className="text-xs text-slate-800">{number(value)}</b></div>;
}
