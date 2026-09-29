/**
 * Код авторизации с PKCE.
 *
 * Публичный клиент в браузере не может хранить секрет, поэтому подлинность
 * обмена кода на токен подтверждается парой «верификатор — вызов»:
 * перехваченный код бесполезен без верификатора, который остался
 * в исходной вкладке.
 */

const VERIFIER_KEY = "medsignal.pkce.verifier";
const RETURN_KEY = "medsignal.pkce.return_to";
const STATE_KEY = "medsignal.pkce.state";

function randomString(bytes = 32): string {
  const buffer = new Uint8Array(bytes);
  crypto.getRandomValues(buffer);
  return base64UrlEncode(buffer);
}

function base64UrlEncode(buffer: Uint8Array | ArrayBuffer): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(verifier),
  );
  return base64UrlEncode(digest);
}

export interface AuthorizationRequest {
  url: string;
}

/**
 * Подготовить переход к провайдеру.
 *
 * Верификатор и состояние живут в sessionStorage: они нужны только
 * до возврата из провайдера в этой же вкладке и не являются учётными
 * данными. Токен доступа там не хранится никогда.
 */
export async function buildAuthorizationRequest(params: {
  issuer: string;
  clientId: string;
  redirectUri: string;
  returnTo: string;
}): Promise<AuthorizationRequest> {
  const verifier = randomString();
  const state = randomString(16);

  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(RETURN_KEY, params.returnTo);

  const query = new URLSearchParams({
    client_id: params.clientId,
    redirect_uri: params.redirectUri,
    response_type: "code",
    scope: "openid profile email",
    state,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: "S256",
  });

  return {
    url: `${params.issuer}/protocol/openid-connect/auth?${query.toString()}`,
  };
}

export interface TokenExchangeResult {
  accessToken: string;
  idToken: string;
  expiresInSeconds: number;
  returnTo: string;
}

/** Обменять код на токен и убрать одноразовые значения. */
export async function exchangeCodeForToken(params: {
  issuer: string;
  clientId: string;
  redirectUri: string;
  code: string;
  state: string | null;
}): Promise<TokenExchangeResult> {
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const returnTo = sessionStorage.getItem(RETURN_KEY) ?? "/signals";

  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(RETURN_KEY);

  if (!verifier) {
    throw new Error("Не найден верификатор обмена. Повторите вход.");
  }
  // Проверка состояния защищает от подмены ответа провайдера.
  if (!params.state || params.state !== expectedState) {
    throw new Error("Состояние ответа не совпадает. Повторите вход.");
  }

  const response = await fetch(
    `${params.issuer}/protocol/openid-connect/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: params.clientId,
        redirect_uri: params.redirectUri,
        code: params.code,
        code_verifier: verifier,
      }),
    },
  );

  if (!response.ok) {
    throw new Error("Провайдер отклонил обмен кода на токен");
  }

  const payload: unknown = await response.json();
  const token = (payload as { access_token?: unknown }).access_token;
  const idToken = (payload as { id_token?: unknown }).id_token;
  const expiresIn = (payload as { expires_in?: unknown }).expires_in;

  if (typeof token !== "string" || token.length === 0) {
    throw new Error("Ответ провайдера не содержит токена доступа");
  }
  if (typeof idToken !== "string" || idToken.length === 0) {
    throw new Error("Ответ провайдера не содержит токена идентификации");
  }

  return {
    accessToken: token,
    idToken,
    expiresInSeconds: typeof expiresIn === "number" ? expiresIn : 300,
    returnTo,
  };
}
