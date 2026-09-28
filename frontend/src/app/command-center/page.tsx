"use client";

import { useQueries } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Ban,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Database,
  MapPinned,
  RadioTower,
  Search,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { TimeSeriesChart } from "@/features/analytics/components/time-series-chart";
import { fetchOverview } from "@/features/analytics/api";
import { useSituationCenter } from "@/features/analytics/hooks";
import type { AnalyticsQuery, Overview } from "@/features/analytics/types";
import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { syntheticDemoLabelEnabled } from "@/features/forecasting/demo-context";
import { useLatestReferralForecast } from "@/features/forecasting/hooks";
import { RegionMap, type MapMetric, type RegionPoint } from "@/features/map/region-map";
import { SEVERITY_LABELS, STATUS_LABELS, formatDateTime } from "@/features/signals/labels";
import { useRegions, useSignals } from "@/hooks/use-domain";
import { cn } from "@/utils/cn";

const BASE_QUERY: AnalyticsQuery = {
  dateFrom: "2025-01-01T00:00:00Z",
  dateTo: "2025-03-31T23:59:59.999Z",
  granularity: "DAY",
};

const metricMeta: Record<MapMetric, { label: string; source: string; icon: LucideIcon }> = {
  waiting: { label: "Ожидающие", source: "Предоставленный снимок", icon: Users },
  referrals: { label: "Направления", source: "ИС БГ", icon: Activity },
  refusals: { label: "Отказы", source: "ИС БГ", icon: Ban },
};

function cellValue(overview: Overview | undefined, metric: MapMetric): number | null {
  if (!overview) return null;
  const cell = metric === "waiting" ? overview.data.waiting_records : metric === "referrals" ? overview.data.referrals_total : overview.data.refusals_total;
  return cell.suppressed ? null : cell.value;
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "не указана";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export default function CommandCenterPage() {
  const { isAuthenticated } = useAuth();
  const [metric, setMetric] = useState<MapMetric>("waiting");
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const regions = useRegions(isAuthenticated);
  const query = useMemo<AnalyticsQuery>(
    () => ({ ...BASE_QUERY, ...(selectedRegionId ? { region: selectedRegionId } : {}) }),
    [selectedRegionId],
  );
  const analytics = useSituationCenter(isAuthenticated, query);
  const forecast = useLatestReferralForecast(isAuthenticated);
  const recentSignals = useSignals(isAuthenticated, { page: 1, pageSize: 6, regionId: selectedRegionId ?? undefined });
  const newSignals = useSignals(isAuthenticated, { page: 1, pageSize: 1, status: "NEW", regionId: selectedRegionId ?? undefined });
  const inProgressSignals = useSignals(isAuthenticated, { page: 1, pageSize: 1, status: "IN_PROGRESS", regionId: selectedRegionId ?? undefined });

  const regionQueries = useQueries({
    queries: (regions.data?.items ?? []).map((region) => ({
      queryKey: ["command-center", "region-overview", region.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchOverview({ ...BASE_QUERY, region: region.id }, signal),
      enabled: isAuthenticated,
      staleTime: 60_000,
    })),
  });

  const points = useMemo<RegionPoint[]>(
    () => (regions.data?.items ?? []).map((region, index) => {
      const result = regionQueries[index];
      const overview = result?.data;
      const cell = overview ? metric === "waiting" ? overview.data.waiting_records : metric === "referrals" ? overview.data.referrals_total : overview.data.refusals_total : null;
      return {
        id: region.id,
        name: region.name,
        code: region.code,
        value: cellValue(overview, metric),
        state: result?.isError ? "error" as const : result?.isPending ? "loading" as const : cell?.suppressed ? "suppressed" as const : "ready" as const,
      };
    }),
    [metric, regionQueries, regions.data?.items],
  );
  const onSelect = useCallback((id: string | null) => setSelectedRegionId(id), []);
  const selectedRegion = regions.data?.items.find((region) => region.id === selectedRegionId);
  const overview = analytics.overview.data;
  const referrals = analytics.referrals.data;
  const waiting = analytics.waiting.data;
  const organizations = useMemo(
    () => mergeOrganizationItems(analytics.organizations.data?.data.items ?? []),
    [analytics.organizations.data?.data.items],
  );
  const visibleOrganizations = organizations.filter((item) =>
    (item.display_name ?? item.identity_label ?? item.organization_ref).toLowerCase().includes(search.toLowerCase()),
  );
  const pending = analytics.overview.isPending || analytics.referrals.isPending || analytics.waiting.isPending || analytics.organizations.isPending;
  const hasError = Boolean(analytics.overview.error ?? analytics.referrals.error ?? analytics.waiting.error ?? analytics.organizations.error);
  const activeSignals = newSignals.data && inProgressSignals.data ? newSignals.data.total + inProgressSignals.data.total : null;

  return (
    <div className="space-y-6 lg:space-y-8">
      <section className="flex flex-col gap-5 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.15em] text-cyan-700">Обзор операционной ситуации</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-[-0.045em] text-[#102f45]">Ситуационный центр</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Исторические агрегаты направлений, ожидания и отказов. Показатели не измеряют загрузку коек.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[10px] font-bold text-slate-600">
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2"><MapPinned className="h-3.5 w-3.5 text-cyan-700" aria-hidden="true" />{selectedRegion?.name ?? "Все доступные регионы"}</span>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2"><CalendarDays className="h-3.5 w-3.5 text-cyan-700" aria-hidden="true" />Январь — март 2025</span>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2">
            <Database className="h-3.5 w-3.5 text-cyan-700" aria-hidden="true" />
            <span>
              <span className="block">{hasError ? "Источник недоступен" : overview ? "Исторические данные" : "Ожидание данных"}</span>
              {overview?.meta.latest_import_completed_at && <span className="mt-0.5 block font-medium text-slate-400">Обновлено: {formatDate(overview.meta.latest_import_completed_at)}</span>}
            </span>
          </span>
        </div>
      </section>

      <AuthGate>
        {hasError && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-900" role="alert">
            <p className="font-bold">Не удалось получить агрегированные данные.</p>
            <p className="mt-1 text-red-800">Обновите страницу позже или обратитесь к администратору данных.</p>
          </div>
        )}
        {pending && (
          <div className="surface-card rounded-2xl p-8 text-sm text-slate-600" role="status" aria-live="polite">
            Загружаем агрегаты для выбранного периода…
          </div>
        )}
        {overview && waiting && referrals && (
          <div className="space-y-6 lg:space-y-8">
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Ключевые показатели">
              <Kpi icon={Activity} label="Направления" value={formatNumber(overview.data.referrals_total.value)} unit="направлений" note="За выбранный период" tone="teal" />
              <Kpi icon={Users} label="Ожидающие" value={formatNumber(overview.data.waiting_records.value)} unit="записей ожидания" note={`Снимок: ${formatDate(waiting.data.snapshot_at)}`} tone="amber" />
              <Kpi icon={Ban} label="Отказы" value={formatNumber(overview.data.refusals_total.value)} unit="отказов" note="За выбранный период" tone="red" />
              <Kpi icon={RadioTower} label="Активные сигналы" value={formatNumber(activeSignals)} unit="сигналов" note="Новые и в работе" tone="blue" />
            </section>

            <section>
              {referrals.data.points.length > 0 ? (
                <TimeSeriesChart title="Динамика направлений" description="Зарегистрированные направления по выбранному периоду" series={referrals} color="#087b83" />
              ) : (
                <EmptyPanel title="Динамика направлений" message="За выбранный период данных нет." />
              )}
            </section>

            <OrganizationsPanel items={visibleOrganizations} search={search} onSearch={setSearch} />
            <LatestSignals query={recentSignals} />
            <ForecastSummary forecast={forecast} />

            <section className="surface-card overflow-hidden rounded-2xl">
              <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between lg:px-6">
                <div>
                  <p className="eyebrow">Региональный контекст</p>
                  <h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Карта исторических показателей</h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">Цвет показывает сравнительный уровень внутри текущей выгрузки, а не медицинский норматив.</p>
                </div>
                <div className="flex w-full overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1 sm:w-fit">
                  {(Object.keys(metricMeta) as MapMetric[]).map((key) => {
                    const Icon = metricMeta[key].icon;
                    return (
                      <button
                        key={key}
                        type="button"
                        aria-pressed={metric === key}
                        onClick={() => setMetric(key)}
                        className={cn(
                          "flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-3 text-[11px] font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700",
                          metric === key ? "bg-[#087b83] text-white shadow-sm" : "text-slate-600 hover:bg-white hover:text-slate-900",
                        )}
                      >
                        <Icon className="h-3.5 w-3.5" aria-hidden="true" />{metricMeta[key].label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="grid xl:grid-cols-[minmax(0,1fr)_320px]">
                <div className="relative min-h-[420px] overflow-hidden bg-slate-100 sm:min-h-[500px]">
                  <RegionMap points={points} metric={metric} selectedRegionId={selectedRegionId} onSelect={onSelect} />
                  <div className="absolute left-4 top-4 z-[500] rounded-xl border border-white/80 bg-white/95 px-3 py-2 text-[10px] font-bold text-slate-700 shadow-lg">
                    {metricMeta[metric].label} · {metricMeta[metric].source}
                  </div>
                </div>
                <aside className="border-t border-slate-200 bg-[#fbfdfd] p-5 xl:border-l xl:border-t-0 xl:p-6">
                  <div className="flex items-center justify-between gap-3">
                    <span className="rounded-full bg-cyan-50 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-wider text-cyan-800">{selectedRegion ? "Выбран регион" : "Общий контекст"}</span>
                    {selectedRegion && <button type="button" className="text-[11px] font-bold text-slate-500 hover:text-slate-900" onClick={() => setSelectedRegionId(null)}>Сбросить</button>}
                  </div>
                  <h3 className="mt-5 text-xl font-extrabold tracking-[-0.04em] text-[#12334a]">{selectedRegion?.name ?? "Доступная выборка"}</h3>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{selectedRegion ? "Показатели пересчитаны backend в рамках выбранного региона." : "Выберите регион на карте, чтобы сузить аналитику."}</p>
                  <dl className="mt-6 space-y-2.5">
                    <MetricLine label="Направления" value={overview.data.referrals_total.value} />
                    <MetricLine label="Ожидающие" value={overview.data.waiting_records.value} />
                    <MetricLine label="Отказы" value={overview.data.refusals_total.value} />
                    <MetricLine label="Уникальные организации" value={organizations.length} />
                  </dl>
                  <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-[11px] leading-5 text-amber-950">
                    Для расчёта загрузки коек необходим подтверждённый справочник мощностей. Этот экран его не заменяет.
                  </div>
                </aside>
              </div>
            </section>

            <div className="rounded-2xl border border-cyan-100 bg-cyan-50/60 p-5 text-xs leading-6 text-slate-600">
              <p className="flex items-center gap-2 font-bold text-[#12334a]"><CheckCircle2 className="h-4 w-4 text-cyan-700" aria-hidden="true" />Контроль интерпретации</p>
              <p className="mt-1">Интерфейс не создаёт значения мощностей или географии, которых нет в источнике. Несопоставленные идентификаторы остаются видимыми.</p>
            </div>
          </div>
        )}
      </AuthGate>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, unit, note, tone }: { icon: LucideIcon; label: string; value: string; unit: string; note: string; tone: "teal" | "amber" | "red" | "blue" }) {
  const tones = {
    teal: "border-cyan-100 bg-cyan-50 text-cyan-800",
    amber: "border-amber-100 bg-amber-50 text-amber-800",
    red: "border-red-100 bg-red-50 text-red-800",
    blue: "border-blue-100 bg-blue-50 text-blue-800",
  };
  return (
    <article className="surface-card rounded-2xl p-5">
      <div className={cn("grid h-10 w-10 place-items-center rounded-xl border", tones[tone])}><Icon className="h-[18px] w-[18px]" aria-hidden="true" /></div>
      <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.09em] text-slate-500">{label}</p>
      <strong className="mt-1 block text-[28px] font-extrabold tracking-[-0.05em] text-[#102f45]">{value}</strong>
      <p className="text-[10px] font-semibold text-slate-600">{unit}</p>
      <p className="mt-1 text-[10px] font-medium text-slate-500">{note}</p>
    </article>
  );
}

function MetricLine({ label, value }: { label: string; value: number | null }) {
  return <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-xs"><dt className="text-slate-500">{label}</dt><dd className="font-extrabold text-[#12334a]">{formatNumber(value)}</dd></div>;
}

function LatestSignals({ query }: { query: ReturnType<typeof useSignals> }) {
  return (
    <section className="surface-card rounded-2xl p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div><p className="eyebrow">Контроль отклонений</p><h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Последние сигналы</h2></div>
        <Link href="/signals" className="text-xs font-extrabold text-cyan-700 hover:text-cyan-900">Все сигналы</Link>
      </div>
      {query.isPending && <p className="mt-5 text-sm text-slate-500" role="status">Загружаем сигналы…</p>}
      {query.isError && <p className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900" role="alert">Сигналы временно недоступны.</p>}
      {query.data?.items.length === 0 && <p className="mt-5 rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">Для выбранной области сигналов нет.</p>}
      <div className="mt-4 space-y-2.5">
        {query.data?.items.slice(0, 4).map((signal) => (
          <Link key={signal.id} href={`/signals/${signal.id}`} className="block rounded-xl border border-slate-200 p-3.5 transition hover:border-cyan-300 hover:bg-cyan-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[9px] font-extrabold uppercase", signal.severity === "CRITICAL" ? "bg-red-50 text-red-800" : signal.severity === "HIGH" ? "bg-orange-50 text-orange-800" : signal.severity === "WARNING" ? "bg-amber-50 text-amber-800" : "bg-blue-50 text-blue-800")}>
                <AlertTriangle className="h-3 w-3" aria-hidden="true" />{SEVERITY_LABELS[signal.severity]}
              </span>
              <time className="text-[10px] text-slate-500">{formatDateTime(signal.detected_at)}</time>
            </div>
            <h3 className="mt-2 text-sm font-extrabold text-slate-900">{signal.title}</h3>
            <p className="mt-1 text-xs text-slate-500">{signal.hospital_name ?? "Область: вся система"} · {STATUS_LABELS[signal.status]}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

function EmptyPanel({ title, message }: { title: string; message: string }) {
  return <section className="surface-card rounded-2xl p-6"><h2 className="text-lg font-extrabold text-[#12334a]">{title}</h2><p className="mt-8 rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{message}</p></section>;
}

type OrganizationItem = NonNullable<ReturnType<typeof useSituationCenter>["organizations"]["data"]>["data"]["items"][number];

function mergeOrganizationItems(items: OrganizationItem[]): OrganizationItem[] {
  const merged = new Map<string, OrganizationItem>();
  for (const item of items) {
    const current = merged.get(item.organization_ref);
    if (!current) {
      merged.set(item.organization_ref, item);
      continue;
    }
    merged.set(item.organization_ref, {
      ...current,
      display_name: current.display_name ?? item.display_name,
      identity_label: current.identity_label ?? item.identity_label,
      canonical_hospital_id: current.canonical_hospital_id ?? item.canonical_hospital_id,
      region_id: current.region_id ?? item.region_id,
      referrals_total: largerCell(current.referrals_total, item.referrals_total),
      waiting_records: largerCell(current.waiting_records, item.waiting_records),
      refusals_total: largerCell(current.refusals_total, item.refusals_total),
      observed_waiting_median_days: largerCell(current.observed_waiting_median_days, item.observed_waiting_median_days),
    });
  }
  return [...merged.values()];
}

function largerCell<T extends { value: number | null; suppressed: boolean }>(left: T, right: T): T {
  if (left.suppressed && !right.suppressed) return right;
  if (right.suppressed) return left;
  return (right.value ?? Number.NEGATIVE_INFINITY) > (left.value ?? Number.NEGATIVE_INFINITY) ? right : left;
}

function organizationValue(cell: { value: number | null; suppressed: boolean }): number | null {
  return cell.suppressed ? null : cell.value;
}

function OrganizationsPanel({ items, search, onSearch }: { items: OrganizationItem[]; search: string; onSearch: (value: string) => void }) {
  return (
    <section className="surface-card overflow-hidden rounded-2xl">
      <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <p className="eyebrow">Организации</p>
          <h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Организации в текущей выборке</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">API не публикует рейтинг риска, поэтому строки не обозначаются как требующие внимания без подтверждающего правила.</p>
        </div>
        <label className="flex h-10 w-full max-w-sm items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 text-slate-500 focus-within:border-cyan-500 focus-within:bg-white">
          <span className="sr-only">Поиск организации</span><Search className="h-4 w-4" aria-hidden="true" />
          <input className="w-full border-0 bg-transparent text-xs text-slate-900 outline-none" placeholder="Поиск организации" value={search} onChange={(event) => onSearch(event.target.value)} />
        </label>
      </div>
      {items.length === 0 ? (
        <p className="p-8 text-center text-sm text-slate-500">Организации не найдены.</p>
      ) : (
        <>
          <div className="grid gap-3 p-4 lg:hidden">
            {items.slice(0, 12).map((organization) => <OrganizationCard key={organization.organization_ref} organization={organization} />)}
          </div>
          <div className="hidden lg:block">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[9px] font-extrabold uppercase tracking-wider text-slate-500"><tr><th className="px-6 py-3.5">Организация</th><th className="px-5 py-3.5">Направления</th><th className="px-5 py-3.5">Ожидающие</th><th className="px-5 py-3.5">Отказы</th><th className="px-5 py-3.5">Медиана ожидания</th><th className="px-5 py-3.5">Сопоставление</th></tr></thead>
              <tbody className="divide-y divide-slate-100">{items.slice(0, 12).map((organization) => (
                <tr key={organization.organization_ref} className="hover:bg-cyan-50/30">
                  <td className="px-6 py-3.5"><OrganizationIdentity organization={organization} /></td>
                  <td className="px-5 py-3.5 font-bold">{formatNumber(organizationValue(organization.referrals_total))}</td>
                  <td className="px-5 py-3.5 font-bold">{formatNumber(organizationValue(organization.waiting_records))}</td>
                  <td className="px-5 py-3.5 font-bold">{formatNumber(organizationValue(organization.refusals_total))}</td>
                  <td className="px-5 py-3.5">{organizationValue(organization.observed_waiting_median_days) === null ? "—" : `${formatNumber(organizationValue(organization.observed_waiting_median_days))} дн.`}</td>
                  <td className="px-5 py-3.5"><MappingStatus status={organization.mapping_status} /></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function OrganizationCard({ organization }: { organization: OrganizationItem }) {
  return (
    <article className="rounded-xl border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3"><OrganizationIdentity organization={organization} /><MappingStatus status={organization.mapping_status} /></div>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center"><MiniMetric label="Направления" value={organizationValue(organization.referrals_total)} /><MiniMetric label="Ожидающие" value={organizationValue(organization.waiting_records)} /><MiniMetric label="Отказы" value={organizationValue(organization.refusals_total)} /></dl>
    </article>
  );
}

function OrganizationIdentity({ organization }: { organization: OrganizationItem }) {
  return <div className="min-w-0"><Link href={`/organizations/${encodeURIComponent(organization.organization_ref)}`} className="font-bold text-slate-900 hover:text-cyan-800">{organization.display_name ?? organization.identity_label ?? organization.organization_ref}</Link><small className="mt-1 block truncate text-[9px] text-slate-500">{organization.source_system ?? "Источник не указан"}</small></div>;
}

function MappingStatus({ status }: { status: OrganizationItem["mapping_status"] }) {
  return <span className={cn("shrink-0 rounded-full px-2 py-1 text-[8px] font-extrabold", status === "MAPPED" ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-700")}>{status === "MAPPED" ? "Сопоставлено" : "Не сопоставлено"}</span>;
}

function MiniMetric({ label, value }: { label: string; value: number | null }) {
  return <div className="rounded-lg bg-slate-50 px-2 py-2"><dt className="text-[8px] uppercase text-slate-500">{label}</dt><dd className="mt-1 text-sm font-extrabold text-slate-900">{formatNumber(value)}</dd></div>;
}

function ForecastSummary({ forecast }: { forecast: ReturnType<typeof useLatestReferralForecast> }) {
  const data = forecast.data;
  return (
    <section className="surface-card rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="eyebrow">Прогнозирование</p>
          <h2 className="mt-1.5 text-lg font-extrabold tracking-[-0.03em] text-[#12334a]">Глобальный прогноз направлений</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">Область прогноза — вся доступная система. Выбор региона не меняет эти значения.</p>
        </div>
        {data && <span className={cn("w-fit rounded-full px-3 py-1.5 text-[9px] font-extrabold uppercase tracking-wide", data.freshness_status === "STALE" ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800")}>{data.freshness_status === "STALE" ? "Историческая валидация" : "Текущий горизонт"}</span>}
      </div>
      {forecast.isPending && <p className="mt-5 text-sm text-slate-500" role="status">Загружаем опубликованный прогноз…</p>}
      {(forecast.error || !data) && !forecast.isPending && <p className="mt-5 rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-500">Прогноз недоступен для этой области данных.</p>}
      {data && (
        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <ForecastFact icon={CalendarDays} label="Период прогноза" value={`${formatDate(data.forecast_start)} — ${formatDate(data.forecast_end)}`} />
          <ForecastFact icon={Activity} label="Целевой показатель" value="Ежедневное число направлений" />
          <ForecastFact icon={Clock3} label="Модель" value={`${data.selected_model} · ${data.model_version}`} />
          <ForecastFact icon={CheckCircle2} label="MAE модели" value={`${formatNumber(data.metrics.mae)} направления в день`} />
          <div className="md:col-span-2 xl:col-span-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-600">
            <p><b className="text-slate-800">Историческая валидация:</b> {data.validation_period_start && data.validation_period_end ? `${formatDate(data.validation_period_start)} — ${formatDate(data.validation_period_end)}` : "период не указан"}</p>
            <p className="mt-1"><b className="text-slate-800">MAE baseline:</b> {formatNumber(data.baseline_metrics.mae)} направления в день</p>
            {syntheticDemoLabelEnabled(process.env.NEXT_PUBLIC_APP_ENV, process.env.NEXT_PUBLIC_SYNTHETIC_DEMO) && <p className="mt-2 font-bold text-amber-800">Синтетические демонстрационные данные</p>}
            <p className="mt-2">{data.disclaimer}</p>
          </div>
          <div className="md:col-span-2 xl:col-span-4 rounded-xl border border-cyan-100 bg-cyan-50/60 p-4 text-xs leading-5 text-slate-700">
            <h3 className="font-extrabold text-[#12334a]">Как читать прогноз</h3>
            <p className="mt-1">MAE показывает среднюю абсолютную ошибку на исторической временной проверке. Чем меньше значение в направлениях за день, тем ближе расчёт к наблюдаемым данным.</p>
            <p className="mt-2 font-semibold text-slate-800">Прогноз отражает входящий поток направлений и не является прогнозом свободных коек, даты выписки или медицинской рекомендацией.</p>
          </div>
        </div>
      )}
    </section>
  );
}

function ForecastFact({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 p-4"><Icon className="h-4 w-4 text-cyan-700" aria-hidden="true" /><p className="mt-3 text-[9px] font-bold uppercase tracking-[0.08em] text-slate-500">{label}</p><p className="mt-1 text-xs font-extrabold leading-5 text-slate-900">{value}</p></div>;
}
