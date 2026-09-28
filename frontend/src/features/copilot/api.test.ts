import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCopilotExplanation } from "@/features/copilot/api";
import { formatFactValue, formatOptionalPeriod } from "@/features/copilot/format";
import { syntheticCopilotResponse } from "@/features/copilot/test-fixtures";
import { copilotResponseSchema } from "@/features/copilot/types";
import { ApiError, setTokenProvider } from "@/services/api-client";

afterEach(() => {
  setTokenProvider(() => null);
  vi.unstubAllGlobals();
});

describe("Copilot API contract", () => {
  it("uses the existing OIDC API client for exactly one POST with the open signal ID", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(syntheticCopilotResponse), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    setTokenProvider(() => "synthetic-test-token");

    const result = await fetchCopilotExplanation(syntheticCopilotResponse.signal_id);

    expect(result.signal_version).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/copilot/explain-signal");
    const options = fetchMock.mock.calls[0]?.[1];
    expect(options?.method).toBe("POST");
    expect(options?.body).toBe(JSON.stringify({ signal_id: syntheticCopilotResponse.signal_id }));
    expect((options?.headers as Record<string, string>).Authorization).toBe("Bearer synthetic-test-token");
    expect(options?.cache).toBe("no-store");
  });

  it("rejects unknown fact IDs and does not treat them as verified evidence", () => {
    const bad = { ...syntheticCopilotResponse, fact_ids: ["F9"] };
    expect(copilotResponseSchema.safeParse(bad).success).toBe(false);
  });

  it("preserves null dates and numeric backend facts", () => {
    const result = copilotResponseSchema.parse(syntheticCopilotResponse);
    expect(result.data_watermark_at).toBeNull();
    expect(result.evaluation_period_start).toBeNull();
    expect(result.facts[0]?.value).toBe(21);
    expect(formatOptionalPeriod(result.evaluation_period_start, result.evaluation_period_end)).toBe("Неизвестно");
  });

  it("distinguishes percent change, percentage points, record count and unknown units", () => {
    const fact = syntheticCopilotResponse.facts[0];
    expect(formatFactValue(fact)).toContain("21 % изменения");
    expect(formatFactValue({ ...fact, unit: "percentage_points", value: 2 })).toContain("2 п. п.");
    expect(formatFactValue({ ...fact, unit: "count_records", value: 12 })).toContain("12 записей");
    expect(formatFactValue({ ...fact, unit: "unrecognized", value: 12 })).toContain("единица неизвестна");
    expect(formatFactValue({ ...fact, unit: "percent_change", value: 0 })).toContain("0 % изменения");
    expect(formatFactValue({ ...fact, direction: "DECREASE", value: -21 })).toContain("Уменьшение");
  });

  it("keeps a Copilot 503 distinct from readiness and exposes its error code", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: {
        code: "COPILOT_DISABLED", message: "Copilot отключён", details: {}, request_id: "test-rid",
      } }), { status: 503 }),
    ));
    await expect(fetchCopilotExplanation(syntheticCopilotResponse.signal_id)).rejects.toMatchObject({
      code: "COPILOT_DISABLED", httpStatus: 503,
    } satisfies Partial<ApiError>);
  });
});
