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
  const firstOrganizationName = (await organizationLinks.nth(0).innerText()).split(/\r?\n/, 1)[0]?.trim();
  const firstPath = await organizationLinks.nth(0).getAttribute("href");
  const secondPath = await organizationLinks.nth(1).getAttribute("href");
  expect(firstOrganizationName).toBeTruthy();
  expect(firstPath).toMatch(/^\/hospitals\/[0-9a-f-]+$/);
  expect(secondPath).toMatch(/^\/hospitals\/[0-9a-f-]+$/);
  expect(firstPath).not.toBe(secondPath);

  await Promise.all([
    page.waitForURL((url) => url.pathname === firstPath),
    organizationLinks.nth(0).click(),
  ]);
  const firstHeading = page.getByRole("heading", { level: 1 });
  await expect(firstHeading).toHaveText(firstOrganizationName!);
  await expect(page.getByText("Каноническая организация")).toBeVisible();
  await expect(page.getByText("Направления", { exact: true })).toBeVisible();
  const firstOrganization = await firstHeading.innerText();

  await Promise.all([
    page.waitForURL((url) => url.pathname === "/dashboard"),
    page.goBack(),
  ]);
  await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible();
  await expect(page.getByLabel("Конец")).toHaveValue("2025-03-30");
  await expect(page.getByLabel("Группировка")).toHaveValue("WEEK");

  const secondLink = page.locator(`a[href="${secondPath}"]`).first();
  await expect(secondLink).toBeVisible();
  await Promise.all([
    page.waitForURL((url) => url.pathname === secondPath),
    secondLink.click(),
  ]);
  const secondHeading = page.getByRole("heading", { level: 1 });
  await expect(secondHeading).toBeVisible();
  await expect(secondHeading).not.toHaveText(firstOrganization);

  const mapLink = page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("link", { name: "Обзор" });
  await Promise.all([
    page.waitForURL((url) => url.pathname === "/command-center"),
    mapLink.click(),
  ]);
  await expect(page.getByText(/Исторические агрегаты направлений, ожидания и отказов/)).toBeVisible();
  await expect(page.getByText("Показатели не измеряют загрузку коек.")).toBeVisible();
  await expect(page.getByLabel("Карта региональных показателей Казахстана")).toBeVisible();
  await expect(page.locator(".leaflet-marker-icon[title]")).toHaveCount(0);
  await expect(page.getByText("Выберите регион на карте, чтобы сузить аналитику.")).toBeVisible();

  const signalsLink = page.getByRole("navigation", { name: "Основная навигация" })
    .getByRole("link", { name: "Сигналы" });
  await Promise.all([
    page.waitForURL((url) => url.pathname === "/signals"),
    signalsLink.click(),
  ]);
  await expect(page.getByRole("heading", { name: "Сигналы" })).toBeVisible();
});
