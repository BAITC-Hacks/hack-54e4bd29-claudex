import { render, screen } from "@testing-library/react";
import { Building2 } from "lucide-react";
import { describe, expect, it } from "vitest";

import { DataFreshnessBadge } from "@/features/analytics/components/data-freshness-badge";
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

  it("labels unknown freshness explicitly", () => {
    render(<DataFreshnessBadge status="UNKNOWN" />);
    expect(screen.getByText("Не определено")).toBeInTheDocument();
  });
});
