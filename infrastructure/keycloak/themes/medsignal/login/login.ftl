<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>Вход в MedSignal</title>
  <link rel="icon" href="${url.resourcesPath}/img/medsignal-icon.png">
  <#if properties.styles?has_content>
    <#list properties.styles?split(' ') as style>
      <link href="${url.resourcesPath}/${style}" rel="stylesheet">
    </#list>
  </#if>
  <#if properties.scripts?has_content>
    <#list properties.scripts?split(' ') as script>
      <script src="${url.resourcesPath}/${script}" defer></script>
    </#list>
  </#if>
</head>
<body>
  <main class="login-shell">
    <section class="brand-panel" aria-label="MedSignal">
      <img class="cityscape" src="${url.resourcesPath}/img/astana-expo.jpg" alt="Современная архитектура Астаны">
      <div class="brand-shade"></div>
      <div class="brand-lockup">
        <img src="${url.resourcesPath}/img/medsignal-icon.png" alt="" width="52" height="52">
        <div><strong>MedSignal</strong><span>HEALTH INTELLIGENCE</span></div>
      </div>
      <div class="brand-copy">
        <h2>Здоровые<br>регионы —<br>сильнее страна</h2>
        <p>Данные. Люди. Будущее.</p>
        <span class="accent-line"></span>
      </div>
    </section>

    <section class="form-panel">
      <div class="locale" role="group" aria-label="Язык интерфейса">
        <button type="button" data-language="ru" aria-pressed="true">РУС</button>
        <button type="button" data-language="kk" aria-pressed="false">ҚАЗ</button>
      </div>
      <div class="form-content">
        <p class="eyebrow">Добро пожаловать</p>
        <h1>Войдите в MedSignal</h1>
        <p class="intro">Доступ к ситуационному центру через защищённую систему идентификации.</p>

        <#if message?has_content>
          <div class="alert alert-${message.type}" role="alert">${message.summary}</div>
        </#if>

        <form id="kc-form-login" action="${url.loginAction}" method="post">
          <label for="username">Email или имя пользователя</label>
          <div class="input-wrap">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h16v12H4zM4 7l8 6 8-6"/></svg>
            <input id="username" name="username" type="text" value="${(login.username!'')}" autocomplete="username" placeholder="name@organization.kz" autofocus>
          </div>

          <label for="password">Пароль</label>
          <div class="input-wrap">
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 10V8a5 5 0 0110 0v2M5 10h14v10H5z"/></svg>
            <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Введите пароль">
            <button class="reveal" type="button" aria-label="Показать пароль" aria-pressed="false">
              <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>

          <div class="form-options">
            <#if realm.rememberMe>
              <label class="remember"><input id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>> Запомнить меня</label>
            <#else><span></span></#if>
            <#if realm.resetPasswordAllowed><a href="${url.loginResetCredentialsUrl}">Забыли пароль?</a></#if>
          </div>

          <input type="hidden" name="credentialId" value="${auth.selectedCredential!''}">
          <button class="submit" id="kc-login" name="login" type="submit">Войти</button>
        </form>

        <div class="security-note">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5zM9 12l2 2 4-5"/></svg>
          <p><strong>Безопасный доступ</strong><span>Ваши данные не хранятся в MedSignal.</span></p>
        </div>
        <p class="demo-note">Исследовательская демонстрационная среда · только искусственные данные</p>
      </div>
    </section>
  </main>
</body>
</html>
