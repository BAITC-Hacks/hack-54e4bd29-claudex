document.addEventListener("DOMContentLoaded", () => {
  const button = document.querySelector(".reveal");
  const password = document.querySelector("#password");
  if (!(button instanceof HTMLButtonElement) || !(password instanceof HTMLInputElement)) return;
  button.addEventListener("click", () => {
    const visible = password.type === "text";
    password.type = visible ? "password" : "text";
    button.setAttribute("aria-pressed", String(!visible));
    button.setAttribute("aria-label", visible ? "Показать пароль" : "Скрыть пароль");
  });
});
