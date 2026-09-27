"use client";

import { Activity, AlertTriangle, Ban, Building2, ClipboardList } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { DataFreshnessBadge } from "@/features/analytics/components/data-freshness-badge";
import { DataFreshnessDetails } from "@/features/analytics/components/data-freshness-details";
import { FilterBar } from "@/features/analytics/components/filter-bar";
import { KpiCard } from "@/features/analytics/components/kpi-card";
import { OrganizationTable } from "@/features/analytics/components/organization-table";
import { QualityIndicator } from "@/features/analytics/components/quality-indicator";
import { EmptyState, ErrorState, LoadingState } from "@/features/analytics/components/states";
import { TimeSeriesChart } from "@/features/analytics/components/time-series-chart";
import { WaitingAgeSummary } from "@/features/analytics/components/waiting-age-summary";
import { formatPeriod } from "@/features/analytics/format";
import { useSituationCenter } from "@/features/analytics/hooks";
import type { AnalyticsQuery } from "@/features/analytics/types";
import { ReferralForecastCard } from "@/features/forecasting/components/referral-forecast-card";
import { syntheticDemoLabelEnabled } from "@/features/forecasting/demo-context";
import { useLatestReferralForecast } from "@/features/forecasting/hooks";
import { SignalTable } from "@/features/signals/signal-table";
import { useSignals } from "@/hooks/use-domain";

const INITIAL_QUERY: AnalyticsQuery = {
  dateFrom: "2025-01-01T00:00:00Z",
  dateTo: "2025-03-31T23:59:59.999Z",
  granularity: "DAY",
};

const DATE_PARAM = /^\d{4}-\d{2}-\d{2}$/;

function queryBoundary(value: string | null, endOfDay = false): string | undefined {
  if (!value) return undefined;
  if (DATE_PARAM.test(value)) {
    return `${value}${endOfDay ? "T23:59:59.999Z" : "T00:00:00Z"}`;
  }
  return Number.isFinite(Date.parse(value)) ? value : undefined;
}

function dashboardQuery(search: Pick<URLSearchParams, "get">): AnalyticsQuery {
  const dateFrom = queryBoundary(search.get("date_from") ?? search.get("from"));
  const dateTo = queryBoundary(search.get("date_to") ?? search.get("to"), true);
  const granularity = search.get("granularity");
  const region = search.get("region");
  const validPeriod = Boolean(
    dateFrom
      && dateTo
      && Date.parse(dateFrom) <= Date.parse(dateTo),
  );
  return {
    ...(validPeriod ? { dateFrom, dateTo } : INITIAL_QUERY),
    granularity: granularity === "WEEK" ? "WEEK" : "DAY",
    ...(region ? { region } : {}),
  };
}

function DashboardContent() {
  const { isAuthenticated } = useAuth();
  const search = useSearchParams();
  const [query, setQueryState] = useState<AnalyticsQuery>(() => dashboardQuery(search));
  const setQuery = useCallback((next: AnalyticsQuery) => {
    const params = new URLSearchParams(window.location.search);
    params.delete("from");
    params.delete("to");
    params.set("date_from", (next.dateFrom ?? INITIAL_QUERY.dateFrom!).slice(0, 10));
    params.set("date_to", (next.dateTo ?? INITIAL_QUERY.dateTo!).slice(0, 10));
    params.set("granularity", next.granularity === "WEEK" ? "WEEK" : "DAY");
    if (next.region) params.set("region", next.region);
    else params.delete("region");
    setQueryState(next);
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}?${params.toString()}`,
    );
  }, []);
  const analytics = useSituationCenter(isAuthenticated, query);
  const referralForecast = useLatestReferralForecast(isAuthenticated);
  const signals = useSignals(isAuthenticated, { page: 1, pageSize: 5, regionId: query.region });
  const overview = analytics.overview.data;
  const referrals = analytics.referrals.data;
  const refusals = analytics.refusals.data;
  const waiting = analytics.waiting.data;
  const observed = analytics.observed.data;
  const organizations = analytics.organizations.data;
  const freshness = analytics.freshness.data;
  const quality = analytics.quality.data;
  const pending = Object.values(analytics).some((item) => item.isPending);
  const error = Object.values(analytics).find((item) => item.isError)?.error;

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-primary">MedSignal</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Ситуационный центр
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Что происходит в системе по данным предоставленных выгрузок
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          Период:{" "}
          {query.dateFrom && query.dateTo
            ? formatPeriod(query.dateFrom, query.dateTo)
            : "—"}
        </p>
      </section>
      <AuthGate>
        <FilterBar value={query} onChange={setQuery} />
        <p className="text-sm text-muted-foreground">{query.region ? "Показатели отфильтрованы по региону, выбранному на карте." : "Показатели для всей доступной области данных."} <Link href="/command-center" className="underline">Выбрать регион на карте</Link></p>
        {pending && <LoadingState />}
        {error && <ErrorState label="Агрегированные показатели временно недоступны. Повторите позже." />}
        {overview &&
          referrals &&
          refusals &&
          waiting &&
          observed &&
          organizations &&
          freshness &&
          quality && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard title="Направления" value={overview.data.referrals_total} period={formatPeriod(overview.meta.date_from, overview.meta.date_to)} source="ИС БГ" icon={Activity} />
              <KpiCard title="Ожидающие" value={overview.data.waiting_records} period="Предоставленный снимок" source="ИС БГ" icon={ClipboardList} />
              <KpiCard title="Отказы" value={overview.data.refusals_total} period={formatPeriod(overview.meta.date_from, overview.meta.date_to)} source="ИС БГ" icon={Ban} />
              <KpiCard title="Организации" value={overview.data.represented_organizations} period="В пространствах источников" source="ИС БГ" icon={Building2} />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              {referrals.data.points.length ? (
                <TimeSeriesChart title="Динамика направлений" description="Количество зарегистрированных направлений по периоду" series={referrals} color="#2563eb" />
              ) : (
                <EmptyState />
              )}
              {refusals.data.points.length ? (
                <TimeSeriesChart title="Динамика отказов" description="Количество событий отказа по периоду" series={refusals} color="#dc2626" />
              ) : (
                <EmptyState />
              )}
            </div>
            <ReferralForecastCard
              forecast={referralForecast.data}
              isLoading={referralForecast.isPending}
              error={referralForecast.error}
              isSyntheticDemo={syntheticDemoLabelEnabled(process.env.NEXT_PUBLIC_APP_ENV, process.env.NEXT_PUBLIC_SYNTHETIC_DEMO)}
            />
            <p className="text-sm text-muted-foreground">Прогноз имеет собственный период и область, указанные в карточке. Фильтры аналитики его не меняют.</p>
            <section className="rounded-lg border bg-card p-5">
              <h2 className="font-semibold">Расчётный сценарий</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Сравните исторический объём направлений с фиксированным гипотетическим изменением потока.
              </p>
              <Link className="mt-3 inline-block text-sm text-primary hover:underline" href="/scenarios">
                Открыть сценарии
              </Link>
            </section>
            <section className="space-y-3">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-primary" aria-hidden="true" />
                    <h2 className="font-semibold">Сигналы контроля</h2>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Предупреждения для выбранной области. У каждого своя дата обнаружения; фильтр периода событий к ним не применяется. Решение принимает сотрудник.
                  </p>
                </div>
                <Link className="text-sm text-primary hover:underline" href="/signals">
                  Все сигналы
                </Link>
              </div>
              {signals.isPending && <LoadingState />}
              {signals.isError && <ErrorState label="Сигналы временно недоступны. Повторите позже." />}
              {signals.data && <SignalTable items={signals.data.items} />}
            </section>
            <WaitingAgeSummary summary={waiting} />
            <section className="rounded-lg border bg-card p-5">
              <h2 className="font-semibold">Наблюдаемое время ожидания</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Завершённые госпитализации; строки с некорректной хронологией
                исключены. Показатель не является прогнозом.
              </p>
              <div className="mt-4 flex flex-wrap gap-6 text-sm">
                <span>
                  Медиана:{" "}
                  <b>{observed.data.median_days.suppressed ? "Скрыто" : formatDays(observed.data.median_days.value)}</b>
                </span>
                <span>
                  P90: <b>{observed.data.p90_days.suppressed ? "Скрыто" : formatDays(observed.data.p90_days.value)}</b>
                </span>
                <span>
                  Исключено:{" "}
                  <b>
                    {observed.data.excluded_chronology_conflicts.suppressed ? "Скрыто" : observed.data.excluded_chronology_conflicts.value?.toLocaleString(
                      "ru-RU",
                    ) ?? "—"}
                  </b>
                </span>
              </div>
            </section>
            <section className="space-y-3">
              <div>
                <h2 className="font-semibold">
                  Организации в выбранной области
                </h2>
                <p className="text-sm text-muted-foreground">
                  Каждая строка остаётся в пространстве идентификаторов своего
                  источника.
                </p>
              </div>
              {organizations.data.items.length ? (
                <><OrganizationTable items={organizations.data.items} /><p className="mt-3 text-sm">Показано {organizations.data.items.length} из {organizations.data.total}. <Link href="/command-center" className="text-primary underline">Полный список и поиск на карте</Link></p></>
              ) : (
                <EmptyState />
              )}
            </section>
            <div className="grid gap-5 lg:grid-cols-2">
              <section className="rounded-lg border bg-card p-5">
                <h2 className="font-semibold">Качество данных</h2>
                <div className="mt-4 space-y-3">
                  {quality.data.map((item) => (
                    <div key={item.dataset_type} className="flex items-center justify-between gap-3 border-b pb-3 last:border-0">
                      <div><p className="text-sm font-medium">{item.dataset_type}</p><p className="text-xs text-muted-foreground">Загружено {item.rows_loaded.toLocaleString("ru-RU")}</p></div>
                      <QualityIndicator status={item.status} warnings={item.warnings_count} />
                    </div>
                  ))}
                </div>
              </section>
              <section className="rounded-lg border bg-card p-5">
                <h2 className="font-semibold">Актуальность данных</h2>
                <div className="mt-4 space-y-3">
                  {freshness.data.map((item) => (
                    <div key={item.dataset_type} className="flex items-start justify-between gap-3 border-b pb-3 last:border-0">
                      <DataFreshnessDetails item={item} />
                      <DataFreshnessBadge status={item.status} mappingAvailable={freshness.meta.mapping_publication_available} />
                    </div>
                  ))}
                </div>
              </section>
            </div>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {overview.meta.limitations.map((item) => (
                <li key={item}>— {item}</li>
              ))}
            </ul>
          </div>
        )}
      </AuthGate>
    </div>
  );
}

export default function DashboardPage() {
  return <Suspense fallback={<p role="status">Загрузка аналитики…</p>}><DashboardContent /></Suspense>;
}

function formatDays(value: number | null): string {
  return value === null
    ? "—"
    : `${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} дн.`;
}
