"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";

import { env } from "@/config/env";
import { AUTH_CALLBACK_PATH, useAuth } from "@/features/auth/auth-context";
import { exchangeCodeForToken, readAuthorizationReturnTo } from "@/features/auth/pkce";

function CallbackHandler() {
  const params = useSearchParams();
  const router = useRouter();
  const { setToken } = useAuth();
  const [exchangeError, setExchangeError] = useState<string | null>(null);
  // Обмен кода одноразовый: повторный вызов провайдер отклонит.
  const exchanged = useRef(false);

  const code = params.get("code");
  const state = params.get("state");

  // Ошибки самого ответа видны сразу и выводятся из параметров при
  // отрисовке. Устанавливать их состоянием внутри эффекта не нужно:
  // это вызвало бы лишний цикл отрисовки.
  const responseError = params.get("error")
    ? "Провайдер отклонил вход"
    : !code
      ? "Ответ провайдера не содержит кода авторизации"
      : null;

  useLayoutEffect(() => {
    if (responseError === null && code !== null) {
      window.history.replaceState(null, "", readAuthorizationReturnTo());
    }
  }, [code, responseError]);

  useEffect(() => {
    if (responseError !== null || code === null || exchanged.current) {
      return;
    }
    exchanged.current = true;

    exchangeCodeForToken({
      issuer: env.oidcIssuer,
      clientId: env.oidcClientId,
      redirectUri: `${window.location.origin}${AUTH_CALLBACK_PATH}`,
      code,
      state,
    })
      .then((result) => {
        setToken(result.accessToken, result.expiresInSeconds, result.idToken);
        router.replace(result.returnTo);
      })
      .catch(() => setExchangeError("Не удалось завершить вход. Повторите попытку позже."));
  }, [code, state, responseError, router, setToken]);

  const error = responseError ?? exchangeError;

  if (error !== null) {
    return (
      <div className="rounded-lg border border-border bg-card p-6">
        <h1 className="text-base font-semibold">Вход не выполнен</h1>
        <p className="mt-2 text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  return <p className="text-sm text-muted-foreground">Завершается вход…</p>;
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={<p className="text-sm text-muted-foreground">Загрузка…</p>}
    >
      <CallbackHandler />
    </Suspense>
  );
}
