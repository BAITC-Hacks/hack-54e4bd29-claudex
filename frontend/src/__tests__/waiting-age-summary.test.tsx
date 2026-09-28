import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WaitingAgeSummary } from "@/features/analytics/components/waiting-age-summary";
import { waitingSummarySchema } from "@/features/analytics/types";

const cell = (value: number | null) => ({ value, suppressed: false });

function summary(snapshotAt: string | null, confirmed: boolean) {
  return waitingSummarySchema.parse({
    data: {
      snapshot_at: snapshotAt,
      snapshot_semantics_confirmed: confirmed,
      waiting_records: cell(12),
      median_days: cell(5),
      p75_days: cell(7),
      p90_days: cell(9),
      oldest_days: cell(11),
    },
    meta: {
      date_from: "2025-01-01T00:00:00Z",
      date_to: "2025-03-31T23:59:59Z",
      granularity: null,
      source: ["ИС БГ:WAITING"],
      generated_at: "2026-09-26T00:00:00Z",
      latest_import_id: null,
      latest_import_ids: [],
      latest_import_completed_at: null,
      limitations: [],
    },
  });
}

describe("waiting snapshot label", () => {
  it("shows the source date supplied by the API without deriving it", () => {
    render(<WaitingAgeSummary summary={summary("2025-03-01T00:00:00", true)} />);
    expect(screen.getByText(/Снимок:/)).toBeInTheDocument();
    expect(screen.getByText("2025-03-01T00:00:00")).toHaveAttribute(
      "dateTime",
      "2025-03-01T00:00:00",
    );
    expect(screen.queryByText(/текущей очереди/)).not.toBeInTheDocument();
  });

  it("states that the snapshot is unconfirmed when provenance is absent", () => {
    render(<WaitingAgeSummary summary={summary(null, false)} />);
    expect(screen.getByText(/Семантика снимка не подтверждена/)).toBeInTheDocument();
  });
});
