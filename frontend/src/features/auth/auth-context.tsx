"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { env } from "@/config/env";
import { buildAuthorizationRequest } from "@/features/auth/pkce";
import { setTokenProvider } from "@/services/api-client";

/**
 * Состояние входа.
 *
 * Токен хранится только в памяти приложения: ни localStorage,
 * ни sessionStorage (SECURITY.md, раздел 3). Плата — потеря сессии
 * при перезагрузке страницы. Повторный вход при действующей сессии
 * провайдера проходит без ввода пароля, одним переходом.
 */

interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (returnTo?: string) => Promise<void>;
  logout: () => void;
  setToken: (token: string, expiresInSeconds: number) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export const AUTH_CALLBACK_PATH = "/auth/callback";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Клиент API получает токен через функцию, а не через параметр:
  // обращения к API разбросаны по приложению, и передавать его
  // в каждое было бы источником пропусков.
  useEffect(() => {
    setTokenProvider(() => accessToken);
    return () => setTokenProvider(() => null);
  }, [accessToken]);

  const setToken = useCallback((token: string, expiresInSeconds: number) => {
    setAccessToken(token);
    // Токен убирается из памяти до истечения срока: просроченный токен
    // даёт 401 на каждом запросе, и лучше показать вход заранее.
    const safetyMarginMs = 15_000;
    const timeout = Math.max(expiresInSeconds * 1000 - safetyMarginMs, 5_000);
    window.setTimeout(() => setAccessToken(null), timeout);
  }, []);

  const login = useCallback(async (returnTo?: string) => {
    const request = await buildAuthorizationRequest({
      issuer: env.oidcIssuer,
      clientId: env.oidcClientId,
      redirectUri: `${window.location.origin}${AUTH_CALLBACK_PATH}`,
      returnTo: returnTo ?? window.location.pathname,
    });
    // Адрес провайдера внешний, поэтому используется полный переход.
    window.location.assign(request.url);
  }, []);

  const logout = useCallback(() => {
    setAccessToken(null);
    const query = new URLSearchParams({
      client_id: env.oidcClientId,
      post_logout_redirect_uri: window.location.origin,
    });
    // Переход на внешний адрес провайдера, а не на страницу приложения:
    // маршрутизатор Next.js здесь неприменим.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(
      `${env.oidcIssuer}/protocol/openid-connect/logout?${query.toString()}`,
    );
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      accessToken,
      isAuthenticated: accessToken !== null,
      login,
      logout,
      setToken,
    }),
    [accessToken, login, logout, setToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth вызван вне AuthProvider");
  }
  return context;
}
