import { describe, expect, it } from "vitest";

import { ApiError } from "@/services/api-client";
import { shouldRetryQuery } from "@/services/query-retry";

describe("query retry policy", () => {
  it.each([401, 403, 404, 422, 429, 500, 503])(
    "does not repeat an HTTP %i response",
    (status) => {
      expect(shouldRetryQuery(0, new ApiError("TEST", "test", status, null))).toBe(false);
    },
  );

  it("retries a transport failure at most twice", () => {
    expect(shouldRetryQuery(0, new Error("network"))).toBe(true);
    expect(shouldRetryQuery(1, new Error("network"))).toBe(true);
    expect(shouldRetryQuery(2, new Error("network"))).toBe(false);
  });
});
