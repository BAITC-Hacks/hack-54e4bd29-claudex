"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { useAuth } from "@/features/auth/auth-context";

/**
 * Показывает содержимое только после входа.
 *
 * Это удобство, а не защита: доступ к данным ограничивает сервер.
 * Скрытие раздела на клиенте не является механизмом безопасности
 * (SECURITY.md, раздел 4).
 */
export function AuthGate({ children, returnTo }: { children: ReactNode; returnTo?: () => string }) {
  const { isAuthenticated, login } = useAuth();
  const restoreStarted = useRef(false);

  useEffect(() => {
    if (isAuthenticated || restoreStarted.current) return;
    restoreStarted.current = true;
    const currentRoute = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    void login(returnTo?.() ?? currentRoute);
  }, [isAuthenticated, login, returnTo]);

  if (isAuthenticated) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-[52vh] items-center justify-center px-4 text-center" role="status" aria-live="polite">
      <div>
        <LoaderCircle className="mx-auto h-7 w-7 animate-spin text-cyan-700" aria-hidden="true" />
        <p className="mt-3 text-sm font-semibold text-slate-600">Восстанавливаем защищённую сессию…</p>
      </div>
    </div>
  );
}
