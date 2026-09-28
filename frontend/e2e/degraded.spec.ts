import { expect, test } from "@playwright/test";

import { login } from "./auth";

test("dependency outage returns HTTP 503 and dashboard explains unavailability", async ({ page }) => {
  const ready = await page.request.get("/api/v1/ready");
  expect(ready.status()).toBe(503);
  const live = await page.request.get("/api/v1/health");
  expect(live.status()).toBe(200);

  await login(page, "admin");
  await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "Не удалось получить агрегированные данные" }),
  ).toBeVisible({ timeout: 25_000 });
});
