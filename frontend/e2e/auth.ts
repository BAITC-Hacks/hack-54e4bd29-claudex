import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";

interface RealmUser {
  username: string;
  credentials?: Array<{ value: string }>;
}

function testPassword(username: string): string {
  const path = process.env.MEDSIGNAL_E2E_REALM;
  if (!path) throw new Error("Test realm path is required");
  const realm = JSON.parse(readFileSync(path, "utf8")) as { users: RealmUser[] };
  const password = realm.users.find((user) => user.username === username)?.credentials?.[0]?.value;
  if (!password) throw new Error("Test identity unavailable");
  return password;
}

export async function login(page: Page, username: string, returnTo = "/dashboard") {
  await page.goto(returnTo);
  await page.getByRole("button", { name: "Войти через Keycloak" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(testPassword(username));
  await page.locator("#kc-login").click();
  await page.getByRole("button", { name: "Выйти" }).waitFor();
}
