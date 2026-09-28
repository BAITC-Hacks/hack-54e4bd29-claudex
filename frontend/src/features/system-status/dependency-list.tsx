"use client";

import { Badge } from "@/components/ui/badge";
import type { DependencyStatus } from "@/types/api";

/**
 * Список состояния зависимостей.
 *
 * Компонент только отображает то, что вернул сервер. Решение о том,
 * готова ли система, принимает backend: повторять эту логику здесь
 * значит завести второй источник истины.
 */

const STATUS_LABELS: Record<DependencyStatus["status"], string> = {
  up: "доступна",
  down: "недоступна",
  skipped: "не проверялась",
};

const STATUS_VARIANTS: Record<
  DependencyStatus["status"],
  "success" | "danger" | "neutral"
> = {
  up: "success",
  down: "danger",
  skipped: "neutral",
};

const DEPENDENCY_LABELS: Record<string, string> = {
  postgres: "PostgreSQL",
  clickhouse: "ClickHouse",
  redis: "Redis",
  object_storage: "Объектное хранилище",
};

export function DependencyList({
  dependencies,
}: {
  dependencies: DependencyStatus[];
}) {
  if (dependencies.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Нет данных о зависимостях.</p>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {dependencies.map((dependency) => (
        <li
          key={dependency.name}
          className="flex items-center justify-between gap-4 py-2.5"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              {DEPENDENCY_LABELS[dependency.name] ?? dependency.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {dependency.required ? "обязательная" : "необязательная"}
              {dependency.latency_ms !== null
                ? ` · ${dependency.latency_ms} мс`
                : ""}
            </p>
          </div>
          <Badge variant={STATUS_VARIANTS[dependency.status]}>
            {STATUS_LABELS[dependency.status]}
          </Badge>
        </li>
      ))}
    </ul>
  );
}
