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
      <section className="border-b border-slate-200 pb-6">
        <p className="text-[11px] font-extrabold uppercase tracking-[0.15em] text-cyan-700">Контроль отклонений</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-[-0.045em] text-[#102f45]">
          Сигналы
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Показаны сигналы организаций, доступных вашей учётной записи.
          Ограничение применяет сервер.
        </p>
      </section>

      <AuthGate>
        <div className="space-y-4">
          <div className="surface-card flex flex-wrap items-center gap-3 rounded-2xl p-4">
            <label className="text-xs font-bold text-slate-600" htmlFor="status">
              Статус
            </label>
            <select
              id="status"
              className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700"
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
              <span className="ml-auto rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">
                Всего: {signals.data.total}
              </span>
            )}
          </div>

          {signals.isPending && (
            <p className="surface-card rounded-2xl p-8 text-sm text-slate-500" role="status">Загружаем сигналы…</p>
          )}
          {signals.isError && (
            <p className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-900" role="alert">
              Сигналы временно недоступны. Повторите позже.
            </p>
          )}
          {signals.data && <SignalTable items={signals.data.items} />}

          {signals.data && (signals.data.has_next || page > 1) && (
            <div className="flex items-center justify-end gap-3 text-sm">
              <button
                className="min-h-10 rounded-xl border border-slate-200 bg-white px-4 font-bold text-slate-700 disabled:opacity-40"
                disabled={page === 1}
                onClick={() => setPage((current) => current - 1)}
              >
                Назад
              </button>
              <span className="text-slate-500">Страница {page}</span>
              <button
                className="min-h-10 rounded-xl border border-slate-200 bg-white px-4 font-bold text-slate-700 disabled:opacity-40"
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
