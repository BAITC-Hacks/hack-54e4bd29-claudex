import { describe, expect, it } from "vitest";

import { syntheticDemoLabelEnabled } from "@/features/forecasting/demo-context";

describe("syntheticDemoLabelEnabled", () => {
  it("shows the label only when a local or test environment explicitly enables it", () => {
    expect(syntheticDemoLabelEnabled("test", "true")).toBe(true);
    expect(syntheticDemoLabelEnabled("local", "true")).toBe(true);
    expect(syntheticDemoLabelEnabled("test", undefined)).toBe(false);
    expect(syntheticDemoLabelEnabled("production", "true")).toBe(false);
  });
});
