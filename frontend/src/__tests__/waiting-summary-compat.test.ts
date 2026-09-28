import { describe, expect, it } from "vitest";

import { waitingSummarySchema } from "@/features/analytics/types";

describe("existing waiting summary client contract", () => {
  it("accepts additive snapshot provenance without losing old fields", () => {
    const cell = (value: number | null) => ({ value, suppressed: false });
    const response = {
      data: {
        snapshot_at: "2025-03-01T00:00:00",
        snapshot_semantics_confirmed: true,
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
    };

    const parsed = waitingSummarySchema.parse(response);

    expect(parsed.data.waiting_records).toEqual(cell(12));
    expect(parsed.data.median_days).toEqual(cell(5));
    expect(parsed.data.snapshot_at).toBe("2025-03-01T00:00:00");
    expect(parsed.data.snapshot_semantics_confirmed).toBe(true);
  });

  it("defaults provenance to unknown for a response from an older backend", () => {
    const cell = { value: null, suppressed: false };
    const parsed = waitingSummarySchema.parse({
      data: {
        waiting_records: cell,
        median_days: cell,
        p75_days: cell,
        p90_days: cell,
        oldest_days: cell,
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

    expect(parsed.data.snapshot_at).toBeNull();
    expect(parsed.data.snapshot_semantics_confirmed).toBe(false);
  });
});
