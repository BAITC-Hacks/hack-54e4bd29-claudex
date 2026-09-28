import { defineConfig } from "@playwright/test";

const baseURL = process.env.MEDSIGNAL_E2E_BASE_URL;
if (!baseURL || !/^http:\/\/127\.0\.0\.1:\d+$/.test(baseURL)) {
  throw new Error("E2E requires an isolated loopback MEDSIGNAL_E2E_BASE_URL");
}
if (!process.env.MEDSIGNAL_E2E_REALM) {
  throw new Error("E2E requires the ignored test Keycloak realm path");
}

export default defineConfig({
  testDir: "./e2e",
  testIgnore: [
    ...(process.env.MEDSIGNAL_E2E_DEGRADED === "1" ? [] : ["**/degraded.spec.ts"]),
    ...(process.env.MEDSIGNAL_COPILOT_FRONTEND_URL ? [] : ["**/copilot.spec.ts"]),
    ...(process.env.MEDSIGNAL_FORECAST_DEMO === "1" ? [] : ["**/forecast-demo.spec.ts"]),
  ],
  outputDir: "../tmp/playwright-results",
  preserveOutput: "never",
  reporter: process.env.CI
    ? [["./e2e/strict-reporter.ts"]]
    : [["list"], ["./e2e/strict-reporter.ts"]],
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 12_000 },
  use: {
    baseURL,
    browserName: "chromium",
    channel: process.env.CI ? undefined : "chrome",
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
