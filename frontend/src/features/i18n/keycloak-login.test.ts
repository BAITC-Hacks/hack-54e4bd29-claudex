import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, expect, it } from "vitest";

const loginScript = readFileSync(
  resolve(process.cwd(), "../infrastructure/keycloak/themes/medsignal/login/resources/js/login.js"),
  "utf8",
);

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.lang = "ru";
  document.body.innerHTML = `
    <div class="locale" role="group" aria-label="Язык интерфейса">
      <button type="button" data-language="ru" aria-pressed="true">РУС</button>
      <button type="button" data-language="kk" aria-pressed="false">ҚАЗ</button>
    </div>
    <h1>Войдите в MedSignal</h1>
    <input id="password" type="password" placeholder="Введите пароль">
    <button class="reveal" type="button" aria-label="Показать пароль"></button>
  `;
});

it("switches Keycloak login copy to Kazakh while keeping password reveal functional", () => {
  new Function(loginScript)();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  document.querySelector<HTMLButtonElement>('[data-language="kk"]')?.click();
  expect(document.documentElement.lang).toBe("kk");
  expect(window.localStorage.getItem("medsignal-language")).toBe("kk");
  expect(document.querySelector("h1")).toHaveTextContent("MedSignal жүйесіне кіріңіз");
  expect(document.querySelector<HTMLInputElement>("#password")?.placeholder).toBe("Құпиясөзді енгізіңіз");

  document.querySelector<HTMLButtonElement>(".reveal")?.click();
  expect(document.querySelector<HTMLInputElement>("#password")?.type).toBe("text");

  document.querySelector<HTMLButtonElement>('[data-language="ru"]')?.click();
  expect(document.querySelector("h1")).toHaveTextContent("Войдите в MedSignal");
  expect(window.localStorage.getItem("medsignal-language")).toBe("ru");
  expect(document.querySelector<HTMLInputElement>("#password")?.type).toBe("text");
});
