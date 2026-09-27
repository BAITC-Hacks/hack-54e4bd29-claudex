import { render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import CommandCenterPage from "@/app/command-center/page";

const meta = {
  date_from: "2025-01-01T00:00:00Z",
  date_to: "2025-03-31T23:59:59Z",
  granularity: "DAY" as const,
  source: ["IS_BG"],
  generated_at: "2025-04-01T10:00:00Z",
  latest_import_id: "import-1",
  latest_import_ids: ["import-1"],
  latest_import_completed_at: "2025-04-01T09:00:00Z",
  limitations: [],
};

const signal = {
  id: "signal-1",
  scope_type: "HOSPITAL" as const,
  region_id: null,
  hospital_id: "hospital-1",
  hospital_name: "Городская больница",
  type: "REFERRAL_SPIKE" as const,
  severity: "CRITICAL" as const,
  status: "NEW" as const,
  source_type: "RULE_BASED" as const,
  title: "Рост числа направлений",
  summary: "Отклонение подтверждено правилом.",
  detected_at: "2025-04-01T08:00:00Z",
  evaluation_period_start: "2025-03-25",
  evaluation_period_end: "2025-03-31",
  assigned_user_id: null,
  version: 1,
};

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) =>
    <a href={href} {...props}>{children}</a>,
}));
vi.mock("@/features/auth/auth-context", () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock("@tanstack/react-query", () => ({ useQueries: () => [] }));
vi.mock("@/features/map/region-map", () => ({ RegionMap: () => <div aria-label="Карта исторических показателей" /> }));
vi.mock("echarts", () => ({ init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }) }));

vi.mock("@/hooks/use-domain", () => ({
  useRegions: () => ({ data: { items: [], page: 1, page_size: 20, total: 0, has_next: false } }),
  useSignals: (_enabled: boolean, query: { status?: string }) => ({
    isPending: false,
    isError: false,
    error: null,
    data: query.status === "NEW"
      ? { items: [], page: 1, page_size: 1, total: 2, has_next: false }
      : query.status === "IN_PROGRESS"
        ? { items: [], page: 1, page_size: 1, total: 1, has_next: false }
        : { items: [signal], page: 1, page_size: 6, total: 1, has_next: false },
  }),
}));

vi.mock("@/features/analytics/hooks", () => ({
  useSituationCenter: () => ({
    overview: { isPending: false, error: null, data: { meta, data: {
      referrals_total: { value: 1248, suppressed: false }, waiting_records: { value: 124, suppressed: false },
      refusals_total: { value: 17, suppressed: false }, hospitalized_total: { value: 0, suppressed: false },
      data_quality_warnings: { value: 0, suppressed: false }, represented_organizations: { value: 8, suppressed: false },
      represented_regions: { value: 3, suppressed: false },
    } } },
    referrals: { isPending: false, error: null, data: { meta, data: { metric: "REFERRALS_TOTAL", points: [
      { period: "2025-03-30", period_end: "2025-03-30", value: { value: 101, suppressed: false } },
      { period: "2025-03-31", period_end: "2025-03-31", value: { value: 118, suppressed: false } },
    ] } } },
    waiting: { isPending: false, error: null, data: { meta, data: {
      snapshot_at: "2025-03-31", snapshot_semantics_confirmed: true, waiting_records: { value: 124, suppressed: false },
      median_days: { value: 4.2, suppressed: false }, p75_days: { value: 6, suppressed: false },
      p90_days: { value: 9, suppressed: false }, oldest_days: { value: 12, suppressed: false },
    } } },
    organizations: { isPending: false, error: null, data: { meta, data: { items: [{
      organization_ref: "org-1", canonical_hospital_id: null, display_name: "Городская больница",
      identity_label: null, mapping_status: "MAPPED", source_system: "TEST_SOURCE", region_id: null,
      referrals_total: { value: 300, suppressed: false }, waiting_records: { value: 24, suppressed: false },
      refusals_total: { value: 3, suppressed: false }, observed_waiting_median_days: { value: 4.2, suppressed: false },
    }], page: 1, page_size: 20, total: 1, has_next: false } } },
  }),
}));

vi.mock("@/features/forecasting/hooks", () => ({ useLatestReferralForecast: () => ({
  isPending: false,
  error: null,
  data: {
    id: "00000000-0000-0000-0000-000000000101", target: "DAILY_REFERRAL_COUNT", scope_type: "GLOBAL", horizon_days: 7,
    input_period_start: "2025-01-01", input_period_end: "2025-03-31", validation_period_start: "2025-02-12",
    validation_period_end: "2025-03-25", forecast_start: "2025-04-01", forecast_end: "2025-04-07",
    generated_at: "2025-04-01T10:00:00Z", model_version: "referrals-v1", selected_model: "weekly_naive",
    baseline_model: "weekly_naive", metrics: { mae: 12.3, wape: 0.04, rmse: 15.1 },
    baseline_metrics: { mae: 14.8, wape: 0.05, rmse: 18.2 }, dataset_watermark: {}, freshness_status: "STALE",
    limitations: ["Демонстрационная выборка."], historical: [{ date: "2025-03-31", value: 100 }],
    forecast: [{ date: "2025-04-01", predicted_value: 101, baseline_value: 100, delta_from_baseline: 1 }],
    disclaimer: "Решение принимает уполномоченный сотрудник.",
  },
}) }));

beforeEach(() => vi.clearAllMocks());

it("prioritizes current operational evidence without overstating synthetic or historical data", () => {
  render(<CommandCenterPage />);

  expect(screen.getByRole("heading", { level: 1, name: "Ситуационный центр" })).toBeInTheDocument();
  expect(screen.getByText("Активные сигналы")).toBeInTheDocument();
  expect(within(screen.getByLabelText("Ключевые показатели")).getByText("3")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Динамика направлений" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Последние сигналы" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Организации в текущей выборке" })).toBeInTheDocument();
  expect(screen.getByText(/Глобальный прогноз/)).toBeInTheDocument();
  expect(screen.getAllByText(/Историческая валидация/).length).toBeGreaterThan(0);
  expect(screen.getByText(/12,3 направления в день/)).toBeInTheDocument();
  expect(screen.queryByText(/Минздрав/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/реальные агрегаты/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/фактической нагрузки/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/реальные строки источников/i)).not.toBeInTheDocument();
});
