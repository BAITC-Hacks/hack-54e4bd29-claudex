"use client";

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

/**
 * Лента предупреждений.
 *
 * Компонент только отображает то, что вернул сервер. Ни фильтрация
 * по области данных, ни расчёт доступных действий здесь не выполняются:
 * это решения сервера.
 */
export function SignalTable({ items }: { items: SignalListItem[] }) {
  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
        Сигналов не найдено. Это может означать как отсутствие
        предупреждений, так и то, что область данных не настроена.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full min-w-[56rem] text-sm">
        <thead className="border-b border-border text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">Важность</th>
            <th className="px-4 py-3 font-medium">Тип</th>
            <th className="px-4 py-3 font-medium">Организация</th>
            <th className="px-4 py-3 font-medium">Обнаружен</th>
            <th className="px-4 py-3 font-medium">Статус</th>
            <th className="px-4 py-3 font-medium">Ответственный</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((signal) => (
            <tr key={signal.id} className="hover:bg-accent/40">
              <td className="px-4 py-3">
                <Badge variant={SEVERITY_VARIANTS[signal.severity]}>
                  {SEVERITY_LABELS[signal.severity]}
                </Badge>
              </td>
              <td className="px-4 py-3">
                <Link
                  href={`/signals/${signal.id}`}
                  className="font-medium text-primary hover:underline"
                >
                  {TYPE_LABELS[signal.type]}
                </Link>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {signal.scope_type === "GLOBAL"
                  ? SCOPE_LABELS.GLOBAL
                  : signal.hospital_name ?? signal.hospital_id ?? SCOPE_LABELS[signal.scope_type]}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {formatDateTime(signal.detected_at)}
              </td>
              <td className="px-4 py-3">{STATUS_LABELS[signal.status]}</td>
              <td className="px-4 py-3 text-muted-foreground">
                {signal.assigned_user_id ? "назначен" : "не назначен"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
