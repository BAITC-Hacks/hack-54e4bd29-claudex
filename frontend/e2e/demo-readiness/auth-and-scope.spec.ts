import { expect, test } from "@playwright/test";

import { login } from "../auth";

test.beforeEach(async ({ page }) => {
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status(), "requires a READY isolated synthetic acceptance project").toBe(200);
});

test("protected routes require real Keycloak login and return to the requested page", async ({ page }) => {
  const apiResponse = await page.request.get("/api/v1/signals?page=1&page_size=1");
  expect(apiResponse.status()).toBe(401);

  await page.goto("/signals");
  await expect(page.getByRole("heading", { name: "Войдите в ситуационный центр" })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeHidden();

  await login(page, "admin", "/signals");
  await expect(page).toHaveURL(/\/signals$/);
  await expect(page.getByRole("heading", { name: "Сигналы" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
});

test("hospital-scoped identity cannot list or open another synthetic organization", async ({
  baseURL,
  browser,
  page,
}) => {
  expect(baseURL).toBeTruthy();
  await login(page, "admin", "/hospitals");
  const foreignLink = page.getByRole("link", { name: /Медицинская организация B1/ });
  await expect(foreignLink).toBeVisible();
  const foreignPath = await foreignLink.getAttribute("href");
  expect(foreignPath).toMatch(/^\/hospitals\/[0-9a-f-]+$/);

  await new Promise((resolve) => setTimeout(resolve, 2_000));
  const restrictedContext = await browser.newContext({ baseURL });
  const restrictedPage = await restrictedContext.newPage();
  try {
    await login(restrictedPage, "hospital-manager", "/hospitals");
    await expect(restrictedPage.getByRole("link", { name: /Медицинская организация A1/ })).toBeVisible();
    await expect(restrictedPage.getByRole("link", { name: /Медицинская организация B1/ })).toHaveCount(0);

    await restrictedPage.goto(foreignPath!);
    await expect(restrictedPage.getByRole("alert")).toContainText("Не удалось получить агрегированные данные");
    await expect(restrictedPage.getByText(/Медицинская организация B1/)).toHaveCount(0);
  } finally {
    await restrictedContext.close();
  }
});
