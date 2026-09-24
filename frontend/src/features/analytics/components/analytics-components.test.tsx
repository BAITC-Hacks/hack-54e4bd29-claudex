import { render, screen } from "@testing-library/react";
import { Building2 } from "lucide-react";
import { describe, expect, it } from "vitest";

import { DataFreshnessBadge } from "@/features/analytics/components/data-freshness-badge";
import { DataFreshnessDetails } from "@/features/analytics/components/data-freshness-details";
import { KpiCard } from "@/features/analytics/components/kpi-card";
import { SuppressedValue } from "@/features/analytics/components/suppressed-value";
import { EmptyState, ErrorState, LoadingState } from "@/features/analytics/components/states";

describe("analytics presentation states", () => {
  it("renders loading, empty and backend error states", () => {
    const { rerender } = render(<LoadingState />);
    expect(screen.getByText("Загрузка аналитики…")).toBeInTheDocument();

    rerender(<EmptyState />);
    expect(screen.getByText("За выбранный период данных нет.")).toBeInTheDocument();

    rerender(<ErrorState message="ClickHouse недоступен" />);
    expect(screen.getByRole("alert")).toHaveTextContent("ClickHouse недоступен");
  });

  it("does not render the exact value of a suppressed small cell", () => {
    render(<SuppressedValue cell={{ value: null, suppressed: true }} />);

    expect(screen.getByText("Скрыто")).toBeInTheDocument();
    expect(screen.getByTitle(/Малая группа/)).toBeInTheDocument();
  });

  it("renders KPI context together with its value", () => {
    render(
      <KpiCard
        title="Направления"
        value={{ value: 767130, suppressed: false }}
        period="01.01.2025 — 31.03.2025"
        source="ИС БГ"
        icon={Building2}
      />,
    );

    expect(screen.getByText("Направления")).toBeInTheDocument();
    expect(screen.getByText(/767/)).toBeInTheDocument();
    expect(screen.getByText("01.01.2025 — 31.03.2025")).toBeInTheDocument();
    expect(screen.getByText("ИС БГ")).toBeInTheDocument();
  });

  it("labels incomplete delivery and unavailable mapping explicitly", () => {
    render(<DataFreshnessBadge status="PARTIAL" mappingAvailable={false} />);
    expect(screen.getByText("Поставка неполная")).toBeInTheDocument();
    expect(screen.getByText("Сопоставления недоступны")).toBeInTheDocument();
  });

  it("labels unknown freshness explicitly", () => {
    render(<DataFreshnessBadge status="UNKNOWN" />);
    expect(screen.getByText("Не определено")).toBeInTheDocument();
  });

  it("shows source, import, completeness and cadence as separate evidence", () => {
    render(<DataFreshnessDetails item={{
      dataset_type: "REFERRALS",
      event_period_start: "2025-01-01",
      event_period_end: "2025-03-31",
      source_load_date: "2025-04-01",
      last_successful_import: "2026-09-18T09:01:21Z",
      confirmed_complete_through: null,
      cadence_known: false,
      completeness: "UNKNOWN",
      forecast_available: false,
      status: "UNKNOWN",
      explanation: "Периодичность поставки данных не определена.",
    }} />);
    expect(screen.getByText(/Период событий:/)).toBeInTheDocument();
    expect(screen.getByText(/Загрузка источника:/)).toBeInTheDocument();
    expect(screen.getByText(/Последний успешный импорт:/)).toBeInTheDocument();
    expect(screen.getByText(/Полнота поставки: не подтверждена/)).toBeInTheDocument();
    expect(screen.getByText(/Полнота до: не подтверждена/)).toBeInTheDocument();
    expect(screen.getByText(/Периодичность: не определена/)).toBeInTheDocument();
  });
});
