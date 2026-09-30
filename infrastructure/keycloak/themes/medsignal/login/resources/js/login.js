document.addEventListener("DOMContentLoaded", () => {
  const revealButton = document.querySelector(".reveal");
  const password = document.querySelector("#password");
  const translations = {
    "Здоровые": "Дені сау",
    "регионы —": "өңірлер —",
    "сильнее страна": "қуатты ел",
    "Данные. Люди. Будущее.": "Деректер. Адамдар. Болашақ.",
    "Добро пожаловать": "Қош келдіңіз",
    "Войдите в MedSignal": "MedSignal жүйесіне кіріңіз",
    "Доступ к ситуационному центру через защищённую систему идентификации.": "Ситуациялық орталыққа қорғалған сәйкестендіру жүйесі арқылы кіріңіз.",
    "Email или имя пользователя": "Email немесе пайдаланушы аты",
    "Пароль": "Құпиясөз",
    "Запомнить меня": "Мені есте сақтау",
    "Забыли пароль?": "Құпиясөзді ұмыттыңыз ба?",
    "Войти": "Кіру",
    "Безопасный доступ": "Қауіпсіз кіру",
    "Ваши данные не хранятся в MedSignal.": "Деректеріңіз MedSignal жүйесінде сақталмайды.",
    "Исследовательская демонстрационная среда · только искусственные данные": "Зерттеу демонстрациялық ортасы · тек жасанды деректер"
  };
  const originals = new WeakMap();

  const applyLanguage = (language) => {
    document.documentElement.lang = language;
    document.querySelectorAll(".locale button[data-language]").forEach((item) => {
      item.setAttribute("aria-pressed", String(item.dataset.language === language));
    });
    const locale = document.querySelector(".locale");
    if (locale) locale.setAttribute("aria-label", language === "kk" ? "Интерфейс тілі" : "Язык интерфейса");

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.parentElement && node.parentElement.closest("script,style")) continue;
      if (!originals.has(node)) originals.set(node, node.nodeValue);
      const source = (originals.get(node) || "").trim();
      if (!source) continue;
      const replacement = language === "kk" ? translations[source] : source;
      node.nodeValue = node.nodeValue.replace(node.nodeValue.trim(), replacement || source);
    }

    if (password instanceof HTMLInputElement) {
      password.placeholder = language === "kk" ? "Құпиясөзді енгізіңіз" : "Введите пароль";
    }
    if (revealButton instanceof HTMLButtonElement) {
      const visible = password instanceof HTMLInputElement && password.type === "text";
      revealButton.setAttribute("aria-label", language === "kk"
        ? (visible ? "Құпиясөзді жасыру" : "Құпиясөзді көрсету")
        : (visible ? "Скрыть пароль" : "Показать пароль"));
    }
    window.localStorage.setItem("medsignal-language", language);
  };

  document.querySelectorAll(".locale button[data-language]").forEach((item) => {
    item.addEventListener("click", () => applyLanguage(item.dataset.language));
  });
  applyLanguage(window.localStorage.getItem("medsignal-language") === "kk" ? "kk" : "ru");

  if (revealButton instanceof HTMLButtonElement && password instanceof HTMLInputElement) {
    revealButton.addEventListener("click", () => {
      const showPassword = password.type === "password";
      password.type = showPassword ? "text" : "password";
      revealButton.setAttribute("aria-pressed", String(showPassword));
      revealButton.setAttribute("aria-label", document.documentElement.lang === "kk"
        ? (showPassword ? "Құпиясөзді жасыру" : "Құпиясөзді көрсету")
        : (showPassword ? "Скрыть пароль" : "Показать пароль"));
      revealButton.classList.toggle("is-active", showPassword);
      password.focus({ preventScroll: true });
    });
  }
});
