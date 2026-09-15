"use client";

import { Building2 } from "lucide-react";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { KpiCard } from "@/features/analytics/components/kpi-card";
import { TimeSeriesChart } from "@/features/analytics/components/time-series-chart";
import { WaitingAgeSummary } from "@/features/analytics/components/waiting-age-summary";
import { ErrorState, LoadingState } from "@/features/analytics/components/states";
import { useOrganizationAnalytics } from "@/features/analytics/hooks";
import { formatPeriod } from "@/features/analytics/format";

const PERIOD = {
  dateFrom: "2025-01-01T00:00:00Z",
  dateTo: "2025-03-31T23:59:59.999Z",
  granularity: "DAY" as const,
};

export function OrganizationAnalyticsView({ organizationRef }: { organizationRef: string }) {
  const { isAuthenticated } = useAuth();
  const analytics = useOrganizationAnalytics(isAuthenticated, organizationRef, PERIOD);
  const pending = Object.values(analytics).some((query) => query.isPending);
  const error = Object.values(analytics).find((query) => query.isError)?.error;

  return (
    <AuthGate>
      {pending && <LoadingState />}
      {error && <ErrorState message={error.message} />}
      {analytics.detail.data &&
        analytics.referrals.data &&
        analytics.refusals.data &&
        analytics.waiting.data &&
        analytics.observed.data && (
          <div className="space-y-6">
            <section>
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
