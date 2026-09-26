import { expect, test } from "@playwright/test";

import { login } from "./auth";

// The browser tests share one loopback edge IP and its real OIDC rate limit.
// One admin session covers the end-to-end journey without repeated logins.
test.beforeEach(async () => {
  await new Promise((resolve) => setTimeout(resolve, 2_000));
});

test("admin journey through analytics, signal, scenario and logout", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });

  await test.step("OIDC callback and historical waiting snapshot", async () => {
    await login(page, "admin");
    await expect(page.getByRole("link", { name: "MedSignal — главная" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ситуационный центр" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Возраст очереди в снимке" })).toBeVisible();
    await expect(page.getByText("2025-01-03T03:00:00", { exact: true })).toBeVisible();
    await expect(page.getByText("Периодичность: не определена").first()).toBeVisible();
  });

  await test.step("empty event period remains distinct from the supplied waiting snapshot", async () => {
    await page.getByLabel("Конец").fill("2025-02-02");
    await page.getByLabel("Начало").fill("2025-02-01");
    await expect(page.getByText("За выбранный период данных нет.").first()).toBeVisible();
    await page.getByLabel("Начало").fill("2025-01-01");
    await page.getByLabel("Конец").fill("2025-03-31");
    await expect(page.getByRole("heading", { name: "Возраст очереди в снимке" })).toBeVisible();
  });

  await test.step("desktop navigation and mapped hospital analytics", async () => {
    const navigation = page.getByRole("navigation", { name: "Основная навигация" });
    await expect(navigation).toBeVisible();
    await navigation.getByRole("link", { name: "Организации" }).click();
    await expect(page.getByRole("heading", { name: "Медицинские организации" })).toBeVisible();
    await page.getByRole("link", { name: /Медицинская организация A1/ }).click();
    await expect(page.getByText("Каноническая организация")).toBeVisible();
  });

  await test.step("390px and 768px navigation", async () => {
    await page.setViewportSize({ width: 390, height: 820 });
    await page.getByRole("button", { name: "Открыть меню" }).click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("navigation", { name: "Мобильная навигация" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Открыть меню" })).toBeFocused();
    await page.getByRole("button", { name: "Открыть меню" }).click();
    await page.getByRole("navigation", { name: "Мобильная навигация" })
      .getByRole("link", { name: "Регионы" }).click();
    await expect(page.getByRole("heading", { name: "Регионы" })).toBeVisible();

    await page.setViewportSize({ width: 768, height: 820 });
    await page.getByRole("button", { name: "Открыть меню" }).click();
    await page.getByRole("navigation", { name: "Мобильная навигация" })
      .getByRole("link", { name: "Сигналы" }).click();
    await expect(page.getByRole("heading", { name: "Лента предупреждений" })).toBeVisible();
  });

  await test.step("human acknowledges a synthetic signal", async () => {
    await page.getByLabel("Статус").selectOption("NEW");
    await page.getByRole("table").getByRole("link").first().click();
    await page.getByLabel("Причина").fill("Синтетический acceptance test");
    await page.getByRole("button", { name: "Принять в работу" }).click();
    await expect(page.getByRole("button", { name: "Закрыть как обработанный" })).toBeVisible();
    await expect(page.getByText("Синтетический acceptance test").first()).toBeVisible();
  });

  await test.step("scenario preview and immutable save", async () => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.getByRole("navigation", { name: "Основная навигация" })
      .getByRole("link", { name: "Сценарии" }).click();
    await page.getByRole("button", { name: "Рассчитать preview" }).click();
    await expect(page.getByRole("heading", { name: "Preview" })).toBeVisible();
    await page.getByRole("button", { name: "Сохранить сценарий" }).click();
    await expect(page.getByRole("heading", { name: "Сохранённый сценарий" })).toBeVisible();
    await expect(page.getByText("Не является прогнозом или рекомендацией", { exact: false })).toBeVisible();
  });

  await test.step("Keycloak logout returns to unauthenticated UI", async () => {
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(page.getByRole("heading", { name: "Logging out" })).toBeVisible();
    await page.getByRole("button", { name: "Logout" }).click();
    await expect(page.getByRole("button", { name: "Войти", exact: true })).toBeVisible();
  });
});

test("restricted identity sees only its scoped synthetic hospital", async ({ page }) => {
  await login(page, "hospital-manager", "/hospitals");
  await expect(page.getByRole("heading", { name: "Медицинские организации" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Медицинская организация A1/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Медицинская организация B1/ })).toHaveCount(0);
});
