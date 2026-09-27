import { render, screen, within } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { describe, expect, it, vi } from "vitest";

import { SignalTable } from "@/features/signals/signal-table";
import type { SignalListItem } from "@/types/domain";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) =>
    <a href={href} {...props}>{children}</a>,
}));

const signal: SignalListItem = {
  id: "signal-1",
  scope_type: "HOSPITAL",
  region_id: null,
  hospital_id: "hospital-7",
  hospital_name: "Больница №7",
  type: "REFERRAL_SPIKE",
  severity: "CRITICAL",
  status: "NEW",
  source_type: "RULE_BASED",
  title: "Рост числа направлений",
  summary: "Отклонение подтверждено правилом.",
  detected_at: "2025-04-01T08:00:00Z",
  evaluation_period_start: "2025-03-25",
  evaluation_period_end: "2025-03-31",
  assigned_user_id: null,
  version: 1,
};

describe("SignalTable", () => {
  it("makes severity, title, organization, change, time and status scan-ready without deriving missing metrics", () => {
    render(<SignalTable items={[signal]} />);

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Важность" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Сигнал" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Организация" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Изменение" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Время" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Статус" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Рост числа направлений" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Больница №7").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Не предоставлено").length).toBeGreaterThan(0);
    expect(screen.getAllByText("критическая").length).toBeGreaterThan(0);
  });

  it("uses a clear empty state for the selected filters", () => {
    render(<SignalTable items={[]} />);
    expect(screen.getByText("По выбранным фильтрам сигналов нет.")).toBeInTheDocument();
  });
});
