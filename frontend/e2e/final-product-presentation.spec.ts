import { expect, test } from "@playwright/test";

import { login } from "./auth";

const presentationWidths = [1440, 1280, 768, 390] as const;

test("landing leads to real login and the situation center remains usable at presentation widths", async ({ page }) => {
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status(), "requires a READY isolated synthetic acceptance project").toBe(200);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Ситуационный центр здравоохранения" })).toBeVisible();
  await expect(page.getByText("Демонстрационный исследовательский контур")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Основная навигация" })).toHaveCount(0);
  await page.getByRole("button", { name: "Войти в ситуационный центр" }).click();
  await expect(page.locator("#username")).toBeVisible();

  await login(page, "admin", "/command-center");
  await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Как читать прогноз" })).toBeVisible();

  for (const width of presentationWidths) {
    await test.step(`${width}px layout has no page-level horizontal overflow`, async () => {
      await page.setViewportSize({ width, height: 900 });
      await expect.poll(() => page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      if (width >= 1024) {
        await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
      } else {
        await expect(page.getByRole("button", { name: "Открыть меню" })).toBeVisible();
      }
    });
  }
});
