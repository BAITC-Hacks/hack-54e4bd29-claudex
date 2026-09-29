"use client";

import { LogOut, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button, type ButtonProps } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";

interface LogoutButtonProps extends Omit<ButtonProps, "onClick"> {
  children: ReactNode;
}

export function LogoutButton({ children, ...buttonProps }: LogoutButtonProps) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();

    function closeOnEscape(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        window.setTimeout(() => triggerRef.current?.focus(), 0);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  function close(): void {
    setOpen(false);
    window.setTimeout(() => triggerRef.current?.focus(), 0);
  }

  return (
    <>
      <Button ref={triggerRef} type="button" {...buttonProps} onClick={() => setOpen(true)}>
        {children}
      </Button>

      {open && createPortal(
        <div className="fixed inset-0 z-[100] grid place-items-center p-4">
          <button type="button" className="absolute inset-0 bg-slate-950/45 backdrop-blur-[2px]" aria-label="Отменить выход" onClick={close} />
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-title"
            aria-describedby="logout-description"
            className="relative w-full max-w-sm rounded-[24px] border border-white/80 bg-white p-6 shadow-[0_30px_90px_-30px_rgba(15,46,68,.65)]"
          >
            <button type="button" className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900" aria-label="Закрыть окно" onClick={close}>
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-cyan-50 text-cyan-800">
              <LogOut className="h-5 w-5" aria-hidden="true" />
            </div>
            <h2 id="logout-title" className="mt-5 text-xl font-extrabold tracking-[-0.035em] text-[#102f45]">Выйти из MedSignal?</h2>
            <p id="logout-description" className="mt-2 text-sm leading-6 text-slate-600">Для продолжения работы потребуется снова войти через защищённую систему идентификации.</p>
            <div className="mt-6 flex justify-end gap-3">
              <Button ref={cancelRef} type="button" variant="outline" onClick={close}>Остаться</Button>
              <Button type="button" className="bg-[#087b83] hover:bg-[#066a71]" onClick={logout}>Выйти</Button>
            </div>
          </section>
        </div>,
        document.body,
      )}
    </>
  );
}
