import { expect, test } from "@playwright/test";

import { login } from "../auth";

test("fresh synthetic signal persists one action, rejects stale card and keeps explanation when Copilot is disabled", async ({
  baseURL,
  browser,
  page,
}) => {
  expect(baseURL).toBeTruthy();
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status(), "requires a READY isolated synthetic acceptance project").toBe(200);
  await login(page, "admin", "/signals");
  await page.getByLabel("Статус").selectOption("NEW");
  const signalLink = page.getByRole("table").getByRole("link").first();
  await expect(signalLink).toBeVisible();
  await signalLink.click();

  await expect(page.getByText("SYNTHETIC_DEV_SEED", { exact: true })).toBeVisible();
  await expect(page.getByText("Новый", { exact: true })).toBeVisible();
  const acknowledge = page.getByRole("button", { name: "Принять в работу" });
  await expect(acknowledge, "state-changing test requires a fresh NEW synthetic signal").toBeVisible();
  const signalPath = new URL(page.url()).pathname;

  await new Promise((resolve) => setTimeout(resolve, 2_000));
  const staleContext = await browser.newContext({ baseURL });
  const stalePage = await staleContext.newPage();
  await login(stalePage, "admin", signalPath);
  await expect(stalePage.getByRole("button", { name: "Принять в работу" })).toBeVisible();

  let acknowledgeRequests = 0;
  page.context().on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/acknowledge")) acknowledgeRequests += 1;
  });
  const accepted = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/acknowledge"));
  await page.getByLabel("Причина").fill("Demo readiness isolated synthetic check");
  await acknowledge.click();
  expect((await accepted).status()).toBe(200);
  expect(acknowledgeRequests).toBe(1);
  await expect(page.getByRole("button", { name: "Закрыть как обработанный" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Принять в работу" })).toHaveCount(0);

  const conflict = stalePage.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/acknowledge"));
  await stalePage.getByLabel("Причина").fill("Stale synthetic card check");
  await stalePage.getByRole("button", { name: "Принять в работу" }).click();
  expect((await conflict).status()).toBe(409);
  await expect(stalePage.getByText(/Карточку изменил другой сотрудник/)).toBeVisible();
  await staleContext.close();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Войдите в ситуационный центр" })).toBeVisible();
  await page.getByRole("button", { name: "Войти через Keycloak" }).click();
  await page.waitForURL((url) => url.pathname === signalPath);
  await expect(page.getByRole("button", { name: "Закрыть как обработанный" })).toBeVisible();
  await expect(page.getByText("Demo readiness isolated synthetic check")).toBeVisible();

  let copilotRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/v1/copilot/explain-signal") copilotRequests += 1;
  });
  const disabled = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/copilot/explain-signal");
  await page.getByRole("button", { name: "Объяснить сигнал" }).click();
  const disabledResponse = await disabled;
  expect(disabledResponse.status()).toBe(503);
  expect((await disabledResponse.json()).error.code).toBe("COPILOT_DISABLED");
  await expect(page.getByRole("dialog").getByText(/Функция отключена/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Объяснение", exact: true })).toBeVisible();
  expect(copilotRequests).toBe(1);

  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Объяснить сигнал" }).click();
  await expect(page.getByRole("dialog").getByText(/Функция отключена/)).toBeVisible();
  expect(copilotRequests).toBe(1);
});
