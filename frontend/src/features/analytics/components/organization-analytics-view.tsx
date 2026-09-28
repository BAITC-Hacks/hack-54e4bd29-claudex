"use client";

import { ArrowLeft, Building2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { KpiCard } from "@/features/analytics/components/kpi-card";
import { TimeSeriesChart } from "@/features/analytics/components/time-series-chart";
import { WaitingAgeSummary } from "@/features/analytics/components/waiting-age-summary";
import { ErrorState, LoadingState } from "@/features/analytics/components/states";
import { useOrganizationAnalytics } from "@/features/analytics/hooks";
import { formatPeriod } from "@/features/analytics/format";
import { analyticsQueryFromSearch, withAnalyticsContext } from "@/features/analytics/navigation-context";
import { STATUS_LABELS, formatDateTime } from "@/features/signals/labels";
import { useRegions, useSignals } from "@/hooks/use-domain";

export function OrganizationAnalyticsView({ organizationRef }: { organizationRef: string }) {
  const { isAuthenticated } = useAuth();
  const query = analyticsQueryFromSearch(useSearchParams());
  const analytics = useOrganizationAnalytics(isAuthenticated, organizationRef, query);
  const organization = analytics.detail.data?.data.organization;
  const regions = useRegions(isAuthenticated);
  const signals = useSignals(isAuthenticated && Boolean(organization?.canonical_hospital_id), {
    page: 1,
    pageSize: 5,
    hospitalId: organization?.canonical_hospital_id ?? undefined,
  });
  const pending = Object.values(analytics).some((query) => query.isPending);
  const error = Object.values(analytics).find((query) => query.isError)?.error;
  const regionName = regions.data?.items.find((region) => region.id === organization?.region_id)?.name;

  return (
    <AuthGate>
      {pending && <LoadingState />}
      {error && <ErrorState label="Аналитика организации временно недоступна. Повторите позже." />}
      {analytics.detail.data &&
        analytics.referrals.data &&
        analytics.refusals.data &&
        analytics.waiting.data &&
        analytics.observed.data && (
          <div className="space-y-6">
            <section>
              <Link className="mb-5 inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline" href={withAnalyticsContext("/dashboard", query)}>
                <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Вернуться к аналитике
              </Link>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Building2 className="h-4 w-4" aria-hidden="true" />
                {analytics.detail.data.data.organization.mapping_status === "MAPPED"
                  ? "Каноническая организация"
                  : "Организация не сопоставлена"}
              </div>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight">
                {analytics.detail.data.data.organization.display_name ??
                  "Организация без названия"}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {formatPeriod(
                  analytics.detail.data.meta.date_from,
                  analytics.detail.data.meta.date_to,
                )}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">Регион: {regionName ?? (organization?.region_id ? "название недоступно" : "не указан")}</p>
            </section>
            <div className="grid gap-4 md:grid-cols-3">
              <KpiCard title="Направления" value={analytics.detail.data.data.organization.referrals_total} period={formatPeriod(analytics.detail.data.meta.date_from, analytics.detail.data.meta.date_to)} source="ИС БГ" icon={Building2} />
              <KpiCard title="Ожидающие" value={analytics.detail.data.data.organization.waiting_records} period="Предоставленный срез" source="ИС БГ" icon={Building2} />
              <KpiCard title="Отказы" value={analytics.detail.data.data.organization.refusals_total} period={formatPeriod(analytics.detail.data.meta.date_from, analytics.detail.data.meta.date_to)} source="ИС БГ" icon={Building2} />
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              <TimeSeriesChart title="Динамика направлений" description="События регистрации по дням" series={analytics.referrals.data} color="#2563eb" />
              <TimeSeriesChart title="Динамика отказов" description="События отказов по дням" series={analytics.refusals.data} color="#dc2626" />
            </div>
            <WaitingAgeSummary summary={analytics.waiting.data} />
            <section className="rounded-lg border bg-card p-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="font-semibold">Связанные сигналы</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Сигналы этой организации из отдельного server-side запроса.</p>
                </div>
                <Link className="text-sm text-primary hover:underline" href="/signals">Все сигналы</Link>
              </div>
              {!organization?.canonical_hospital_id && <p className="mt-4 text-sm text-muted-foreground">Связь с сигналами недоступна, пока организация не сопоставлена с каноническим справочником.</p>}
              {organization?.canonical_hospital_id && signals.isPending && <p className="mt-4 text-sm text-muted-foreground" role="status">Загружаем связанные сигналы…</p>}
              {organization?.canonical_hospital_id && signals.isError && <p className="mt-4 text-sm text-destructive" role="alert">Связанные сигналы временно недоступны.</p>}
              {organization?.canonical_hospital_id && signals.data?.items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">Для организации нет активных записей в текущей ленте.</p>}
              {organization?.canonical_hospital_id && signals.data && signals.data.items.length > 0 && (
                <ul className="mt-4 divide-y rounded-lg border">
                  {signals.data.items.map((signal) => (
                    <li key={signal.id} className="flex flex-col gap-1 p-3 sm:flex-row sm:items-center sm:justify-between">
                      <Link className="font-semibold text-primary hover:underline" href={`/signals/${signal.id}`}>{signal.title}</Link>
                      <span className="text-xs text-muted-foreground">{STATUS_LABELS[signal.status]} · {formatDateTime(signal.detected_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="rounded-lg border bg-card p-5">
              <h2 className="font-semibold">Наблюдаемое время ожидания</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Для завершённых госпитализаций с корректной хронологией. Это не прогноз.
              </p>
              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Stat label="Медиана" value={analytics.observed.data.data.median_days.value} />
                <Stat label="Среднее" value={analytics.observed.data.data.mean_days.value} />
                <Stat label="P75" value={analytics.observed.data.data.p75_days.value} />
                <Stat label="P90" value={analytics.observed.data.data.p90_days.value} />
              </dl>
            </section>
            {analytics.detail.data.data.treated_snapshot && (
              <section className="rounded-lg border bg-card p-5">
                <h2 className="font-semibold">
                  {analytics.detail.data.data.treated_snapshot.label}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Дата загрузки среза:{" "}
                  {new Date(
                    analytics.detail.data.data.treated_snapshot.snapshot_load_dt,
                  ).toLocaleDateString("ru-RU")}
                  . Дата не является отчётным периодом.
                </p>
                <p className="mt-4 text-2xl font-semibold">
                  {analytics.detail.data.data.treated_snapshot.discharged_total.toLocaleString(
                    "ru-RU",
                  )}{" "}
                  <span className="text-sm font-normal text-muted-foreground">
                    выписано в предоставленном срезе
                  </span>
                </p>
              </section>
            )}
            <ul className="space-y-1 text-xs text-muted-foreground">
              {analytics.detail.data.meta.limitations.map((item) => (
                <li key={item}>— {item}</li>
              ))}
            </ul>
          </div>
        )}
    </AuthGate>
  );
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">
        {value === null
          ? "—"
          : value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}{" "}
        <span className="text-xs font-normal text-muted-foreground">дней</span>
      </dd>
    </div>
  );
}
