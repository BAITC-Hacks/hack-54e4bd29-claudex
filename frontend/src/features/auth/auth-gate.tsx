"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";

/**
 * Показывает содержимое только после входа.
 *
 * Это удобство, а не защита: доступ к данным ограничивает сервер.
 * Скрытие раздела на клиенте не является механизмом безопасности
 * (SECURITY.md, раздел 4).
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { isAuthenticated, login } = useAuth();

  if (isAuthenticated) {
    return <>{children}</>;
  }

  return (
    <div className="rounded-lg border border-border bg-card p-8 text-center">
      <h2 className="text-base font-semibold">Требуется вход</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Данные медицинских организаций доступны после входа через провайдера
        идентификации. MedSignal не хранит пароли.
      </p>
      <Button className="mt-5" onClick={() => void login()}>
        Войти
      </Button>
    </div>
  );
}
