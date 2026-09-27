import { expect, test } from "@playwright/test";

import { login } from "../auth";

test("analytics requests preserve period context, scope organizations and label forecast state honestly", async ({ page }) => {
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status(), "requires a READY isolated synthetic acceptance project").toBe(200);
  await login(page, "admin", "/dashboard");

  await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
  const overviewResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/v1/analytics/overview"
      && url.searchParams.get("date_to")?.startsWith("2025-03-30") === true
      && url.searchParams.get("granularity") === "WEEK";
  });
  await page.getByLabel("Конец").fill("2025-03-30");
  await page.getByLabel("Группировка").selectOption("WEEK");
  expect((await overviewResponse).status()).toBe(200);

  const forecastHeading = page.getByRole("heading", { name: "Краткосрочный прогноз потока направлений" });
  await expect(forecastHeading).toBeVisible();
  const unavailable = page.getByText(/Прогноз пока недоступен для текущей области данных/);
  const published = page.getByRole("img", { name: /расчётный прогноз/ });
  await expect.poll(async () => (await unavailable.count()) + (await published.count())).toBe(1);

  const organizationTable = page.getByRole("table").filter({
    has: page.getByRole("columnheader", { name: "Организация" }),
  }).last();
  const organizationLinks = organizationTable.locator("tbody a");
  expect(await organizationLinks.count(), "synthetic fixture must expose at least two organizations").toBeGreaterThan(1);
  const firstPath = await organizationLinks.nth(0).getAttribute("href");
  const secondPath = await organizationLinks.nth(1).getAttribute("href");
  expect(firstPath).not.toBe(secondPath);

  await organizationLinks.nth(0).click();
  const firstOrganization = await page.getByRole("heading", { level: 1 }).innerText();
  await expect(page.getByText(/2025/).first()).toBeVisible();

  await page.goBack();
  await expect(page.getByLabel("Конец")).toHaveValue("2025-03-30");
  await expect(page.getByLabel("Группировка")).toHaveValue("WEEK");

  await page.goto(secondPath!);
  const secondHeading = page.getByRole("heading", { level: 1 });
  await expect(secondHeading).toBeVisible();
  await expect(secondHeading).not.toHaveText(firstOrganization);

  await page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("link", { name: "Карта" }).click();
  await expect(page.getByText("Историческая сводка записей о направлениях, ожидании и отказах.")).toBeVisible();
  await expect(page.getByText("Показатели не измеряют загрузку коек.")).toBeVisible();
  const marker = page.locator(".leaflet-marker-icon[title]").first();
  await expect(marker).toBeVisible();
  const regionResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/v1/analytics/overview"
      && url.searchParams.has("region")
      && response.status() === 200;
  });
  await marker.click();
  await regionResponse;
  await expect(page.getByText("Выбран регион")).toBeVisible();
});
