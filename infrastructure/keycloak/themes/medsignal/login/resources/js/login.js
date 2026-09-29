document.addEventListener("DOMContentLoaded", () => {
  const revealButton = document.querySelector(".reveal");
  const password = document.querySelector("#password");
  if (revealButton instanceof HTMLButtonElement && password instanceof HTMLInputElement) {
    revealButton.addEventListener("click", () => {
      const showPassword = password.type === "password";
      password.type = showPassword ? "text" : "password";
      revealButton.setAttribute("aria-pressed", String(showPassword));
      revealButton.setAttribute("aria-label", showPassword ? "Скрыть пароль" : "Показать пароль");
      revealButton.classList.toggle("is-active", showPassword);
      password.focus({ preventScroll: true });
    });
  }

  const locale = document.querySelector(".locale");
  const localeToggle = document.querySelector(".locale-toggle");
  const localeMenu = document.querySelector("#locale-menu");
  if (!(locale instanceof HTMLElement) || !(localeToggle instanceof HTMLButtonElement) || !(localeMenu instanceof HTMLElement)) return;

  const setLocaleMenuOpen = (open) => {
    localeMenu.hidden = !open;
    localeToggle.setAttribute("aria-expanded", String(open));
    locale.classList.toggle("is-open", open);
  };

  localeToggle.addEventListener("click", () => {
    setLocaleMenuOpen(localeToggle.getAttribute("aria-expanded") !== "true");
  });
  document.addEventListener("click", (event) => {
    if (event.target instanceof Node && !locale.contains(event.target)) setLocaleMenuOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setLocaleMenuOpen(false);
      localeToggle.focus();
    }
  });
});
