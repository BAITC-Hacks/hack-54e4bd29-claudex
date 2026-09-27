"use client";

import { LockKeyhole, ShieldCheck } from "lucide-react";
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
export function AuthGate({ children, returnTo }: { children: ReactNode; returnTo?: () => string }) {
  const { isAuthenticated, login } = useAuth();

  if (isAuthenticated) {
    return <>{children}</>;
  }

  return (
    <div className="surface-card relative overflow-hidden rounded-[24px] p-8 text-center sm:p-12">
      <div className="pointer-events-none absolute -right-10 -top-12 h-44 w-44 rounded-full border-[28px] border-cyan-50" />
      <div className="relative mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#0d7f87] text-white shadow-[0_16px_32px_-16px_rgba(13,127,135,.8)]">
        <LockKeyhole size={22} />
      </div>
      <p className="eyebrow relative mt-5">Защищённый контур</p>
      <h2 className="relative mt-2 text-xl font-extrabold tracking-[-0.035em] text-[#102f45]">Войдите в ситуационный центр</h2>
      <p className="relative mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-500">
        Данные медицинских организаций доступны после входа через провайдера
        идентификации. MedSignal не хранит пароли.
      </p>
      <Button className="relative mt-6 h-11 bg-[#0d7f87] px-6 shadow-[0_12px_24px_-14px_rgba(13,127,135,.9)] hover:bg-[#096b72]" onClick={() => void login(returnTo?.())}>
        <ShieldCheck size={16} /> Войти через Keycloak
      </Button>
    </div>
  );
}
