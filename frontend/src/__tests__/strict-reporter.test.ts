import { describe, expect, it } from "vitest";
import type { FullConfig, FullResult, Suite, TestCase, TestResult } from "@playwright/test/reporter";

import StrictReporter from "../../e2e/strict-reporter";

const config = {} as FullConfig;
const result = { status: "passed" } as FullResult;

function suite(expectedStatuses: Array<"passed" | "skipped">): Suite {
  return {
    allTests: () => expectedStatuses.map((expectedStatus) => ({ expectedStatus } as TestCase)),
  } as Suite;
}

describe("strict browser reporter", () => {
  it("rejects a zero-test run", async () => {
    const reporter = new StrictReporter();
    reporter.onBegin(config, suite([]));
    expect((await reporter.onEnd(result)).status).toBe("failed");
  });

  it("rejects a skipped test even if Playwright reports passed", async () => {
    const reporter = new StrictReporter();
    reporter.onBegin(config, suite(["skipped"]));
    expect((await reporter.onEnd(result)).status).toBe("failed");
  });

  it("accepts a completed test", async () => {
    const reporter = new StrictReporter();
    reporter.onBegin(config, suite(["passed"]));
    reporter.onTestEnd({ expectedStatus: "passed" } as TestCase, { status: "passed" } as TestResult);
    expect((await reporter.onEnd(result)).status).toBe("passed");
  });
});
