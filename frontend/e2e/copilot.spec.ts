import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { syntheticCopilotResponse } from "../src/features/copilot/test-fixtures";
import { copilotResponseSchema } from "../src/features/copilot/types";
import { login } from "./auth";

const frontendURL = process.env.MEDSIGNAL_COPILOT_FRONTEND_URL;
const acceptanceURL = process.env.MEDSIGNAL_E2E_BASE_URL;
if (frontendURL && !/^http:\/\/127\.0\.0\.1:\d+$/.test(frontendURL)) {
  throw new Error("Copilot browser proxy requires a loopback-only current frontend");
}
test.skip(!frontendURL || !acceptanceURL, "Requires a local current-branch frontend and isolated synthetic acceptance");

test.beforeEach(async ({ page }) => {
  // Only UI assets come from the current local build. API and Keycloak stay on
  // the unmodified, loopback-only synthetic acceptance origin.
  await page.context().route("**/*", async (route) => {
    const requestURL = new URL(route.request().url());
    if (requestURL.origin !== acceptanceURL ||
        requestURL.pathname.startsWith("/api/") ||
        (requestURL.pathname.startsWith("/auth/") && requestURL.pathname !== "/auth/callback")) {
      await route.continue();
      return;
    }
    const served = await route.fetch({ url: `${frontendURL}${requestURL.pathname}${requestURL.search}` });
    await route.fulfill({ response: served });
  });
});

async function openSyntheticSignal(page: import("@playwright/test").Page) {
  const pendingLogin = login(page, "admin", "/signals");
  // Chromium follows the Keycloak redirect before Playwright's route sees the
  // callback document. Reload it once to serve the same current frontend build
  // used by the rest of the test, preserving in-tab PKCE state.
  await page.waitForURL((url) => url.pathname === "/auth/callback", { timeout: 15_000 });
  await page.reload();
  await pendingLogin;
  await expect(page.getByRole("heading", { name: "Лента предупреждений" })).toBeVisible();
  const row = page.getByRole("table").locator("tbody tr")
    .filter({ has: page.getByRole("link", { name: "рост очереди", exact: true }) }).first();
  const organization = await row.locator("td").nth(2).innerText();
  await row.getByRole("link").click();
  await expect(page.getByText("SYNTHETIC_DEV_SEED", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Объяснить сигнал" })).toBeVisible();
  return organization;
}

test("synthetic fixture: one click, responsive modal, facts, Escape and no repeated request", async ({ page }) => {
  const originalOrganization = await openSyntheticSignal(page);
  const signalID = new URL(page.url()).pathname.split("/").at(-1);
  const versionRow = page.getByText("Версия карточки").locator("..");
  const version = Number(await versionRow.locator("dd").innerText());
  let calls = 0;
  await page.route("**/api/v1/copilot/explain-signal", async (route) => {
    calls += 1;
    expect(route.request().postDataJSON()).toEqual({ signal_id: signalID });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...syntheticCopilotResponse, signal_id: signalID, signal_version: version }),
    });
  });

  const trigger = page.getByRole("button", { name: "Объяснить сигнал" });
  await trigger.click();
  const panel = page.getByRole("dialog", { name: "AI-пояснение" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Синтетическая демонстрация")).toBeVisible();
  await expect(panel.getByText("21 % изменения", { exact: false })).toBeVisible();
  await expect(panel.getByText(/Исторические данные не являются текущей очередью/)).toBeVisible();
  expect(calls).toBe(1);

  const screenshots = path.resolve(process.cwd(), "../tmp/copilot-demo/screenshots");
  mkdirSync(screenshots, { recursive: true });
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 820 });
    await expect(panel).toBeVisible();
    const noHorizontalOverflow = await panel.evaluate((element) =>
      element.scrollWidth <= element.clientWidth + 1);
    expect(noHorizontalOverflow).toBe(true);
    await page.screenshot({ path: path.join(screenshots, `copilot-synthetic-${width}.png`) });
  }
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(panel).toBeVisible();
  expect(calls).toBe(1);

  await page.getByRole("button", { name: "Закрыть пояснение" }).click();
  await page.getByRole("link", { name: "Сигналы", exact: true }).click();
  const rows = page.getByRole("table").locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  let otherOrganizationRow = -1;
  for (let index = 1; index < await rows.count(); index += 1) {
    if (await rows.nth(index).locator("td").nth(2).innerText() !== originalOrganization) {
      otherOrganizationRow = index;
      break;
    }
  }
  expect(otherOrganizationRow).toBeGreaterThan(-1);
  await rows.nth(otherOrganizationRow).getByRole("link").click();
  await expect(page.getByRole("button", { name: "Объяснить сигнал" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "AI-пояснение" })).toHaveCount(0);
  await expect(page.getByText("21 % изменения", { exact: false })).toHaveCount(0);
  expect(calls).toBe(1);
});

test("real OIDC/backend: disabled Copilot leaves algorithmic explanation available", async ({ page }) => {
  await openSyntheticSignal(page);
  await expect(page.getByRole("heading", { name: "Объяснение", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Объяснить сигнал" }).click();
  await expect(page.getByRole("dialog").getByText(/Функция отключена/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Объяснение", exact: true })).toBeVisible();
});

// Explicit, one-request opt-in only. Never part of the default browser/CI run.
if (process.env.MEDSIGNAL_COPILOT_LIVE === "1") {
  test("paid browser → backend → LLM smoke on one synthetic signal", async ({ page }) => {
    test.setTimeout(60_000);
    await openSyntheticSignal(page);
    const signalID = new URL(page.url()).pathname.split("/").at(-1);
    let calls = 0;
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/v1/copilot/explain-signal") calls += 1;
    });
    const responsePromise = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/v1/copilot/explain-signal",
    );
    const started = Date.now();
    await page.getByRole("button", { name: "Объяснить сигнал" }).click();
    const response = await responsePromise;
    const durationMs = Date.now() - started;
    expect(response.status()).toBe(200);
    const parsed = copilotResponseSchema.safeParse(await response.json());
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;
    const result = parsed.data;
    expect(result.signal_id).toBe(signalID);
    expect(result.llm_generated).toBe(true);
    expect(result.data_current).toBe(false);
    expect(result.limitations.some((item) => /синтетическ/i.test(item))).toBe(true);
    expect(/\d|%|процент/i.test(result.explanation)).toBe(false);
    expect(calls).toBe(1);
    const panel = page.getByRole("dialog", { name: "AI-пояснение" });
    await expect(panel.getByText(result.explanation)).toBeVisible();
    await expect(panel.getByRole("heading", { name: "На каких данных основано" })).toBeVisible();
    // Bounded metadata only: no prompt, response text, token, facts or key.
    const metadata = {
      http_status: response.status(), duration_ms: durationMs,
      provider: result.provider, model: result.model, request_id: result.request_id,
      schema_valid: true, fact_ids_valid: true, synthetic_limit_present: true,
      browser_requests: calls,
    };
    const outputDir = path.resolve(process.cwd(), "../tmp/copilot-demo");
    mkdirSync(outputDir, { recursive: true });
    writeFileSync(path.join(outputDir, "live-browser-metadata.json"), JSON.stringify(metadata) + "\n");
  });
}
