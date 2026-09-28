import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { expect, it, vi } from "vitest";

import { OrganizationAnalyticsView } from "@/features/analytics/components/organization-analytics-view";

const captured = vi.hoisted(() => ({ query: undefined as object | undefined }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("date_from=2025-02-01&date_to=2025-02-28&granularity=WEEK&region=11111111-1111-4111-8111-111111111111"),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));
vi.mock("@/features/auth/auth-context", () => ({ useAuth: () => ({ isAuthenticated: true, login: vi.fn() }) }));
vi.mock("@/features/analytics/components/kpi-card", () => ({ KpiCard: ({ title }: { title: string }) => <div>{title}</div> }));
vi.mock("@/features/analytics/components/time-series-chart", () => ({ TimeSeriesChart: ({ title }: { title: string }) => <div>{title}</div> }));
vi.mock("@/features/analytics/components/waiting-age-summary", () => ({ WaitingAgeSummary: () => <div>Возраст очереди</div> }));

const meta = {
  date_from: "2025-02-01T00:00:00Z",
  date_to: "2025-02-28T23:59:59.999Z",
  granularity: "WEEK" as const,
  source: ["IS_BG"],
  generated_at: "2025-03-01T10:00:00Z",
  latest_import_id: "import-1",
  latest_import_ids: ["import-1"],
  latest_import_completed_at: "2025-03-01T09:00:00Z",
  limitations: [],
};
const cell = { value: 1, suppressed: false };
const organization = {
  organization_ref: "source:clinic-1",
  canonical_hospital_id: "22222222-2222-4222-8222-222222222222",
  display_name: "Городская больница",
  identity_label: null,
  mapping_status: "MAPPED" as const,
  source_system: "IS_BG",
  region_id: "11111111-1111-4111-8111-111111111111",
  referrals_total: cell,
  waiting_records: cell,
  refusals_total: cell,
  observed_waiting_median_days: cell,
};

vi.mock("@/features/analytics/hooks", () => ({
  useOrganizationAnalytics: (_enabled: boolean, _ref: string, query: object) => {
    captured.query = query;
    return {
      detail: { isPending: false, isError: false, data: { meta, data: { organization, treated_snapshot: null } } },
      referrals: { isPending: false, isError: false, data: { meta, data: { metric: "REFERRALS_TOTAL", points: [] } } },
      refusals: { isPending: false, isError: false, data: { meta, data: { metric: "REFUSALS_TOTAL", points: [] } } },
      waiting: { isPending: false, isError: false, data: { meta, data: { snapshot_at: "2025-02-28", waiting_records: cell } } },
      observed: { isPending: false, isError: false, data: { meta, data: { median_days: cell, mean_days: cell, p75_days: cell, p90_days: cell } } },
    };
  },
}));
vi.mock("@/hooks/use-domain", () => ({
  useRegions: () => ({ data: { items: [{ id: organization.region_id, code: "ALA", name: "Алматинская область", is_active: true }] } }),
  useSignals: () => ({ isPending: false, isError: false, data: { items: [{
    id: "33333333-3333-4333-8333-333333333333",
    title: "Рост числа направлений",
    status: "NEW",
    detected_at: "2025-02-27T10:00:00Z",
  }] } }),
}));

it("uses the URL analytics context and provides a contextual return with related organization signals", () => {
  render(<OrganizationAnalyticsView organizationRef="canonical:22222222-2222-4222-8222-222222222222" />);

  expect(captured.query).toEqual({
    dateFrom: "2025-02-01T00:00:00Z",
    dateTo: "2025-02-28T23:59:59.999Z",
    granularity: "WEEK",
    region: "11111111-1111-4111-8111-111111111111",
  });
  expect(screen.getByRole("link", { name: "Вернуться к аналитике" })).toHaveAttribute(
    "href",
    "/dashboard?date_from=2025-02-01&date_to=2025-02-28&granularity=WEEK&region=11111111-1111-4111-8111-111111111111",
  );
  expect(screen.getByText("Регион: Алматинская область")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Связанные сигналы" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Рост числа направлений" })).toHaveAttribute("href", "/signals/33333333-3333-4333-8333-333333333333");
});
