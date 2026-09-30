import { expect, test } from "@playwright/test";

import { login } from "./auth";

test.skip(process.env.MEDSIGNAL_LOCAL_DEMO !== "1", "requires a fresh local synthetic project");

test("one real local dataset powers map, analytics, forecast and human action", async ({ page }) => {
  test.setTimeout(120_000);
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status()).toBe(200);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Войти в ситуационный центр" })).toBeVisible();

  const regionsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/regions" && response.request().method() === "GET");
  const forecastResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/forecasts/referrals/latest");
  await login(page, "admin", "/command-center");
  await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
  const regionsHttp = await regionsResponse;
  expect(regionsHttp.status()).toBe(200);
  const regions = (await regionsHttp.json() as { items: Array<{ id: string; code: string }> }).items;
  expect(regions).toHaveLength(12);
  const astana = regions.find((item) => item.code === "KZ-ASTANA");
  expect(astana).toBeTruthy();
  if (!astana) throw new Error("Canonical Astana region missing");
  await expect(page.locator(".leaflet-marker-icon[title]")).toHaveCount(regions.length);
  await expect(page.getByText(/Синтетические данные · исторический период · значения из API/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Демо-слой" })).toHaveCount(0);

  const selectedOverview = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/v1/analytics/overview" && url.searchParams.get("region") === astana.id;
  });
  await page.locator(".leaflet-marker-icon[title*='Астана']").first().click();
  const selected = await selectedOverview;
  expect(selected.status()).toBe(200);
  const selectedData = await selected.json() as { data: { waiting_records: { value: number } } };
  const waiting = selectedData.data.waiting_records.value;
  await expect(page.getByRole("heading", { name: "Астана [синтетические данные]" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Глобальный прогноз направлений" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Организации в текущей выборке" })).toBeVisible();
  await expect(page.getByLabel("Ключевые показатели").getByText(waiting.toLocaleString("ru-RU"))).toBeVisible();

  const forecastHttp = await forecastResponse;
  expect(forecastHttp.status()).toBe(200);
  const forecast = await forecastHttp.json() as {
    target: string; scope_type: string; forecast: unknown[]; horizon_days: number;
    validation_period_start: string | null; validation_period_end: string | null;
    metrics: { mae: number }; baseline_metrics: { mae: number };
  };
  expect(forecast.target).toBe("DAILY_REFERRAL_COUNT");
  expect(forecast.scope_type).toBe("GLOBAL");
  expect(forecast.forecast).toHaveLength(7);
  expect(forecast.horizon_days).toBe(7);
  expect(forecast.validation_period_start).toBeTruthy();
  expect(forecast.validation_period_end).toBeTruthy();
  await expect(page.getByText(
    `${forecast.metrics.mae.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} направления в день`,
    { exact: true },
  )).toBeVisible();
  await expect(page.getByText(/MAE baseline:/).locator("..")).toContainText(
    forecast.baseline_metrics.mae.toLocaleString("ru-RU", { maximumFractionDigits: 1 }),
  );

  await page.getByRole("link", { name: /Условная клиника Астана/ }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: /Условная клиника Астана/ })).toBeVisible();
  await expect(page.getByText(/Регион: Астана/)).toBeVisible();
  await page.getByRole("link", { name: "Вернуться к аналитике" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Ситуационный центр" })).toBeVisible();

  await page.goto("/signals");
  await page.getByLabel("Статус").selectOption("NEW");
  const signalLink = page.getByRole("table").getByRole("link", { name: /Исторический источник данных/ }).first();
  await expect(signalLink).toBeVisible();
  await signalLink.click();
  const algorithmicCard = page.getByText("Алгоритмическое объяснение", { exact: true })
    .locator("..").locator("..");
  const originalExplanation = await algorithmicCard.innerText();
  expect(originalExplanation).toContain("31 марта 2025");
  await expect(page.getByText("SYNTHETIC_LOCAL_DEMO", { exact: true })).toBeVisible();
  const accepted = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/acknowledge"));
  await page.getByLabel("Причина").fill("Проверка локального синтетического сценария");
  await page.getByRole("button", { name: "Принять в работу" }).click();
  expect((await accepted).status()).toBe(200);
  await expect(page.getByRole("button", { name: "Закрыть как обработанный" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Закрыть как обработанный" })).toBeVisible();
  await expect(page.getByText("Проверка локального синтетического сценария")).toBeVisible();
  expect(await algorithmicCard.innerText()).toBe(originalExplanation);

  const disabled = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/copilot/explain-signal");
  await page.getByRole("button", { name: "Объяснить сигнал" }).click();
  const disabledHttp = await disabled;
  expect(disabledHttp.status()).toBe(503);
  expect((await disabledHttp.json()).error.code).toBe("COPILOT_DISABLED");
  await expect(page.getByRole("dialog").getByText(/AI-пояснение временно недоступно/)).toBeVisible();
  expect(await algorithmicCard.innerText()).toBe(originalExplanation);
});
