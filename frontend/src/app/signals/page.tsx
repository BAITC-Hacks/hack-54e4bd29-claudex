"use client";

import { useState } from "react";

import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { SignalTable } from "@/features/signals/signal-table";
import { useSignals } from "@/hooks/use-domain";
import type { SignalStatus } from "@/types/domain";

const STATUS_OPTIONS: Array<{ value: SignalStatus | ""; label: string }> = [
  { value: "", label: "Все статусы" },
  { value: "NEW", label: "Новые" },
  { value: "IN_PROGRESS", label: "В работе" },
  { value: "CLOSED", label: "Закрытые" },
];

export default function SignalsPage() {
  const { isAuthenticated } = useAuth();
  const [status, setStatus] = useState<SignalStatus | "">("");
  const [page, setPage] = useState(1);

  const signals = useSignals(isAuthenticated, { status, page, pageSize: 20 });

  return (
    <div className="space-y-6">
      <section className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">
          Лента предупреждений
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Показаны сигналы организаций, доступных вашей учётной записи.
          Ограничение применяет сервер.
        </p>
      </section>

      <AuthGate>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm text-muted-foreground" htmlFor="status">
              Статус
            </label>
            <select
              id="status"
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as SignalStatus | "");
                setPage(1);
              }}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {signals.data && (
              <span className="text-sm text-muted-foreground">
                Всего: {signals.data.total}
              </span>
            )}
          </div>

          {signals.isPending && (
            <p className="text-sm text-muted-foreground">Загрузка…</p>
          )}
          {signals.isError && (
            <p className="text-sm text-destructive">
              Не удалось получить сигналы: {signals.error.message}
            </p>
          )}
          {signals.data && <SignalTable items={signals.data.items} />}

          {signals.data && (signals.data.has_next || page > 1) && (
            <div className="flex items-center gap-3 text-sm">
              <button
                className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
                disabled={page === 1}
                onClick={() => setPage((current) => current - 1)}
              >
                Назад
              </button>
              <span className="text-muted-foreground">Страница {page}</span>
              <button
                className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40"
                disabled={!signals.data.has_next}
                onClick={() => setPage((current) => current + 1)}
              >
                Вперёд
              </button>
            </div>
          )}
        </div>
      </AuthGate>
    </div>
  );
}
