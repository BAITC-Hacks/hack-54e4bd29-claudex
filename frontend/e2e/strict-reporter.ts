import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult } from "@playwright/test/reporter";

/** Numeric-only browser evidence. Zero or skipped tests fail CI. */
export default class StrictReporter implements Reporter {
  private planned = 0;
  private skipped = 0;
  private passed = 0;
  private failed = 0;

  onBegin(_config: FullConfig, suite: Suite): void {
    const tests = suite.allTests();
    this.planned = tests.length;
    this.skipped = tests.filter((item) => item.expectedStatus === "skipped").length;
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    if (result.status === "passed") this.passed += 1;
    else if (result.status === "skipped") {
      if (test.expectedStatus !== "skipped") this.skipped += 1;
    }
    else this.failed += 1;
  }

  onEnd(result: FullResult): Promise<{ status: FullResult["status"] }> {
    const status = this.planned === 0 || this.skipped > 0 || result.status !== "passed"
      ? "failed"
      : "passed";
    const output = resolve(
      process.cwd(),
      "../tmp",
      process.env.MEDSIGNAL_E2E_DEGRADED === "1"
        ? "playwright-degraded-summary.json"
        : "playwright-summary.json",
    );
    mkdirSync(resolve(process.cwd(), "../tmp"), { recursive: true });
    writeFileSync(
      output,
      JSON.stringify({ planned: this.planned, passed: this.passed, failed: this.failed,
        skipped: this.skipped, status }) + "\n",
      { encoding: "utf8" },
    );
    return Promise.resolve({ status });
  }
}
