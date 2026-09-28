import { expect, test } from "@playwright/test";

import { referralForecastSchema } from "../src/features/forecasting/types";
import { login } from "./auth";

// Opt in only after the isolated synthetic project uses the current images.
test.skip(process.env.MEDSIGNAL_FORECAST_DEMO !== "1", "Requires current API/UI images and published synthetic history");

const uiDate = (value: string) => new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium" }).format(new Date(value));
const uiNumber = (value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 1 });

test("ADMIN sees the same persisted historical forecast in API and dashboard", async ({ page }) => {
  const responsePromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/v1/forecasts/referrals/latest" &&
    response.request().method() === "GET",
  );

  await login(page, "admin");
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const forecast = referralForecastSchema.parse(await response.json());
  expect(forecast.target).toBe("DAILY_REFERRAL_COUNT");
  expect(forecast.scope_type).toBe("GLOBAL");
  expect(forecast.freshness_status).toBe("STALE");
  expect(forecast.validation_period_start).toBeTruthy();
  expect(forecast.validation_period_end).toBeTruthy();
  expect(forecast.forecast).toHaveLength(forecast.horizon_days);

  const card = page.getByRole("heading", { name: "Краткосрочный прогноз потока направлений" })
    .locator("..").locator("..").locator("..");
  await expect(card.getByText(`Идентификатор прогноза: ${forecast.id}`)).toBeVisible();
  await expect(card.getByText("Область: вся система (GLOBAL)")).toBeVisible();
  await expect(card.getByText(/Источник: ИС БГ/)).toBeVisible();
  await expect(card.getByText(/Историческая валидация прогноза/)).toBeVisible();
  await expect(card.getByText(/Прогноз на синтетических демонстрационных данных/)).toBeVisible();
  await expect(card.getByText(`MAE модели: ${uiNumber(forecast.metrics.mae)} направлений/день`)).toBeVisible();
  await expect(card.getByText(`MAE baseline: ${uiNumber(forecast.baseline_metrics.mae)} направлений/день`)).toBeVisible();
  await expect(card.getByText(/Период оценки:/)).toContainText(
    uiDate(forecast.validation_period_start!),
  );
  const dates = card.getByText(/Исходные данные:/);
  await expect(dates).toContainText(uiDate(forecast.input_period_start));
  await expect(dates).toContainText(uiDate(forecast.input_period_end));
  await expect(dates).toContainText(uiDate(forecast.forecast_start));
  await expect(dates).toContainText(uiDate(forecast.forecast_end));
  await card.getByText("Табличное представление прогноза").click();
  const rows = card.getByRole("table").locator("tbody tr");
  await expect(rows).toHaveCount(forecast.horizon_days);
  const firstPoint = forecast.forecast[0];
  if (!firstPoint) throw new Error("Persisted forecast contains no points");
  await expect(rows.first()).toContainText(uiDate(firstPoint.date));
  await expect(rows.first()).toContainText(uiNumber(firstPoint.predicted_value));
  await expect(card.getByText(/Текущая занятость коек:/i)).toHaveCount(0);
});
