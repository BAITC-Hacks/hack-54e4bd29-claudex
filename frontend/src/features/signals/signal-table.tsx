"use client";

import { AlertTriangle, Clock3, Minus } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  SEVERITY_LABELS,
  SEVERITY_VARIANTS,
  SCOPE_LABELS,
  STATUS_LABELS,
  TYPE_LABELS,
  formatDateTime,
} from "@/features/signals/labels";
import type { SignalListItem } from "@/types/domain";

function organizationLabel(signal: SignalListItem): string {
  if (signal.scope_type === "GLOBAL") return SCOPE_LABELS.GLOBAL ?? "Вся система";
  return signal.hospital_name ?? signal.hospital_id ?? SCOPE_LABELS[signal.scope_type] ?? "Область не указана";
}

function SeverityBadge({ signal }: { signal: SignalListItem }) {
  return (
    <Badge className="gap-1.5 whitespace-nowrap" variant={SEVERITY_VARIANTS[signal.severity]}>
      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
      {SEVERITY_LABELS[signal.severity]}
    </Badge>
  );
}

function MissingChange() {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500" title="Список сигналов API не содержит значение изменения">
      <Minus className="h-3.5 w-3.5" aria-hidden="true" /> Не предоставлено
    </span>
  );
}

export function SignalTable({ items }: { items: SignalListItem[] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
        <p className="text-sm font-semibold text-slate-700">По выбранным фильтрам сигналов нет.</p>
        <p className="mt-1 text-xs leading-5 text-slate-500">Измените фильтр статуса или повторите проверку позже.</p>
      </div>
    );
  }

  return (
    <>
      <div className="grid gap-3 lg:hidden" aria-label="Список сигналов">
        {items.map((signal) => (
          <article key={signal.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_32px_-28px_rgba(15,46,68,.45)]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <SeverityBadge signal={signal} />
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-700">{STATUS_LABELS[signal.status]}</span>
            </div>
            <Link href={`/signals/${signal.id}`} className="mt-4 block text-base font-extrabold text-[#102f45] hover:text-cyan-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700">
              {signal.title}
            </Link>
            <p className="mt-1 text-xs text-slate-500">{TYPE_LABELS[signal.type]}</p>
            <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
              <div><dt className="text-[9px] font-bold uppercase tracking-wide text-slate-400">Организация</dt><dd className="mt-1 font-semibold text-slate-700">{organizationLabel(signal)}</dd></div>
              <div><dt className="text-[9px] font-bold uppercase tracking-wide text-slate-400">Изменение</dt><dd className="mt-1"><MissingChange /></dd></div>
              <div><dt className="text-[9px] font-bold uppercase tracking-wide text-slate-400">Время</dt><dd className="mt-1 inline-flex items-center gap-1.5 text-slate-600"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{formatDateTime(signal.detected_at)}</dd></div>
            </dl>
          </article>
        ))}
      </div>

      <div className="hidden overflow-hidden rounded-2xl border border-slate-200 bg-white lg:block">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-left text-[10px] uppercase tracking-[0.08em] text-slate-500">
            <tr>
              <th className="px-4 py-3.5 font-bold">Важность</th>
              <th className="px-4 py-3.5 font-bold">Сигнал</th>
              <th className="px-4 py-3.5 font-bold">Организация</th>
              <th className="px-4 py-3.5 font-bold">Изменение</th>
              <th className="px-4 py-3.5 font-bold">Время</th>
              <th className="px-4 py-3.5 font-bold">Статус</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((signal) => (
              <tr key={signal.id} className="transition hover:bg-cyan-50/30">
                <td className="px-4 py-4 align-top"><SeverityBadge signal={signal} /></td>
                <td className="px-4 py-4 align-top">
                  <Link href={`/signals/${signal.id}`} className="font-bold text-[#102f45] hover:text-cyan-800 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-700">
                    {signal.title}
                  </Link>
                  <p className="mt-1 text-xs text-slate-500">{TYPE_LABELS[signal.type]}</p>
                </td>
                <td className="max-w-48 px-4 py-4 align-top text-xs leading-5 text-slate-600">{organizationLabel(signal)}</td>
                <td className="px-4 py-4 align-top"><MissingChange /></td>
                <td className="whitespace-nowrap px-4 py-4 align-top text-xs text-slate-600">{formatDateTime(signal.detected_at)}</td>
                <td className="px-4 py-4 align-top"><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-700">{STATUS_LABELS[signal.status]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
