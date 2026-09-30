import { fireEvent, render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import CommandCenterPage from "@/app/command-center/page";
import { LanguageProvider, LanguageSwitch } from "@/features/i18n/i18n-context";

const { situationSpy } = vi.hoisted(() => ({ situationSpy: vi.fn() }));
const REGIONS = [
  { id: "00000000-0000-0000-0000-000000000201", code: "KZ-ASTANA", name: "Астана [синтетические данные]" },
  { id: "00000000-0000-0000-0000-000000000202", code: "KZ-ALMATY", name: "Алматы [синтетические данные]" },
];

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
vi.mock("@tanstack/react-query", () => ({ useQueries: () => [
  { isPending: false, isError: false, data: { data: {
    waiting_records: { value: 5, suppressed: false }, referrals_total: { value: 100, suppressed: false }, refusals_total: { value: 2, suppressed: false },
  } } },
  { isPending: false, isError: false, data: { data: {
    waiting_records: { value: 7, suppressed: false }, referrals_total: { value: 120, suppressed: false }, refusals_total: { value: 3, suppressed: false },
  } } },
] }));
vi.mock("@/features/map/region-map", () => ({
  RegionMap: ({ points, onSelect }: { points: Array<{ id: string; name: string; value: number | null }>; onSelect: (id: string) => void }) => (
    <div aria-label="Карта региональных показателей Казахстана">
      {points.map((point) => <button key={point.id} type="button" data-testid={`map-point-${point.id}`} onClick={() => onSelect(point.id)}>{point.name}: {point.value}</button>)}
    </div>
  ),
}));
vi.mock("echarts", () => ({ init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }) }));

vi.mock("@/hooks/use-domain", () => ({
  useRegions: () => ({ isPending: false, isError: false, data: { items: REGIONS, page: 1, page_size: 20, total: 2, has_next: false } }),
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
  useSituationCenter: (enabled: boolean, query: { region?: string }) => {
    situationSpy(enabled, query);
    return {
    overview: { isPending: false, error: null, data: { meta, data: {
      referrals_total: { value: query.region ? 100 : 1248, suppressed: false }, waiting_records: { value: query.region ? 5 : 124, suppressed: false },
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
    }, {
      organization_ref: "org-1", canonical_hospital_id: null, display_name: "Городская больница",
      identity_label: null, mapping_status: "MAPPED", source_system: "TEST_SOURCE", region_id: null,
      referrals_total: { value: 0, suppressed: false }, waiting_records: { value: 0, suppressed: false },
      refusals_total: { value: 8, suppressed: false }, observed_waiting_median_days: { value: null, suppressed: false },
    }], page: 1, page_size: 20, total: 1, has_next: false } } },
    };
  },
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
afterEach(() => vi.unstubAllEnvs());

it("uses only canonical API map points and applies the selected region to backend scope", () => {
  vi.stubEnv("NEXT_PUBLIC_APP_ENV", "test");
  vi.stubEnv("NEXT_PUBLIC_SYNTHETIC_DEMO", "true");
  render(<CommandCenterPage />);

  const mapHeading = screen.getByRole("heading", { name: "Карта региональных показателей" });
  const kpis = screen.getByLabelText("Ключевые показатели");
  expect(Boolean(mapHeading.compareDocumentPosition(kpis) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  expect(screen.queryByRole("button", { name: "Демо-слой" })).not.toBeInTheDocument();
  expect(screen.getByTestId(`map-point-${REGIONS[0]!.id}`)).toHaveTextContent("5");
  expect(screen.getByTestId(`map-point-${REGIONS[1]!.id}`)).toHaveTextContent("7");
  fireEvent.click(screen.getByTestId(`map-point-${REGIONS[0]!.id}`));
  expect(situationSpy).toHaveBeenLastCalledWith(true, expect.objectContaining({ region: REGIONS[0]!.id }));
  expect(screen.getByText("Астана [синтетические данные]", { selector: "h3" })).toBeInTheDocument();
  expect(screen.getByText("Показатели пересчитаны backend в рамках выбранного региона.")).toBeInTheDocument();
});

it("prioritizes current operational evidence without overstating synthetic or historical data", () => {
  render(<CommandCenterPage />);

  expect(screen.getByRole("heading", { level: 1, name: "Ситуационный центр" })).toBeInTheDocument();
  expect(screen.getByText("Исторические агрегаты направлений, ожидания и отказов за выбранный период.")).toBeInTheDocument();
  expect(screen.queryByText(/Показатели не измеряют загрузку коек/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Интерфейс не создаёт значения мощностей коек/)).not.toBeInTheDocument();
  expect(screen.getByText("Исторические данные")).toBeInTheDocument();
  expect(screen.getByText(/Обновлено:.*1 апр/i)).toBeInTheDocument();
  expect(screen.getByText("Активные сигналы")).toBeInTheDocument();
  const kpis = within(screen.getByLabelText("Ключевые показатели"));
  expect(kpis.getByText("3")).toBeInTheDocument();
  expect(kpis.getByText("направлений")).toBeInTheDocument();
  expect(kpis.getByText("записей ожидания")).toBeInTheDocument();
  expect(kpis.getByText("отказов")).toBeInTheDocument();
  expect(kpis.getByText("сигналов")).toBeInTheDocument();

  const journeyHeadings = [
    screen.getByRole("heading", { name: "Динамика направлений" }),
    screen.getByRole("heading", { name: "Организации в текущей выборке" }),
    screen.getByRole("heading", { name: "Последние сигналы" }),
    screen.getByRole("heading", { name: "Глобальный прогноз направлений" }),
  ];
  for (let index = 0; index < journeyHeadings.length - 1; index += 1) {
    expect(Boolean(journeyHeadings[index]!.compareDocumentPosition(journeyHeadings[index + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
  }
  expect(screen.getAllByRole("link", { name: "Городская больница" })).toHaveLength(2);
  expect(screen.getByText(/Глобальный прогноз/)).toBeInTheDocument();
  expect(screen.getAllByText(/Историческая валидация/).length).toBeGreaterThan(0);
  expect(screen.getByText(/12,3 направления в день/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Как читать прогноз" })).toBeInTheDocument();
  expect(screen.getByText(/MAE показывает среднюю абсолютную ошибку на исторической временной проверке/i)).toBeInTheDocument();
  expect(screen.getByText(/не является прогнозом свободных коек, даты выписки или медицинской рекомендацией/i)).toBeInTheDocument();
  expect(screen.queryByText(/Минздрав/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/реальные агрегаты/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/фактической нагрузки/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/реальные строки источников/i)).not.toBeInTheDocument();
});

it("formats visible dates in Kazakh after switching language", () => {
  render(<LanguageProvider><LanguageSwitch /><CommandCenterPage /></LanguageProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Қаз" }));

  const localizedDate = new Intl.DateTimeFormat("kk-KZ", { day: "numeric", month: "short", year: "numeric" }).format(new Date(meta.latest_import_completed_at));
  expect(screen.getByText(new RegExp(localizedDate), { selector: "span" })).toBeInTheDocument();
});
