import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { expect, it, vi } from "vitest";

import { OrganizationTable } from "@/features/analytics/components/organization-table";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children: ReactNode }) =>
    <a href={href} {...props}>{children}</a>,
}));

const organization = {
  organization_ref: "source:clinic-1",
  canonical_hospital_id: "22222222-2222-4222-8222-222222222222",
  display_name: "Городская больница",
  identity_label: null,
  mapping_status: "MAPPED" as const,
  source_system: "IS_BG",
  region_id: "11111111-1111-4111-8111-111111111111",
  referrals_total: { value: 42, suppressed: false },
  waiting_records: { value: 7, suppressed: false },
  refusals_total: { value: 2, suppressed: false },
  observed_waiting_median_days: { value: 3.5, suppressed: false },
};

it("carries the selected analytics period, grouping and region into organization detail", () => {
  render(<OrganizationTable items={[organization]} context={{
    dateFrom: "2025-02-01T00:00:00Z",
    dateTo: "2025-02-28T23:59:59.999Z",
    granularity: "WEEK",
    region: "11111111-1111-4111-8111-111111111111",
  }} />);

  expect(screen.getByRole("link", { name: "Городская больница" })).toHaveAttribute(
    "href",
    "/hospitals/22222222-2222-4222-8222-222222222222?date_from=2025-02-01&date_to=2025-02-28&granularity=WEEK&region=11111111-1111-4111-8111-111111111111",
  );
});
