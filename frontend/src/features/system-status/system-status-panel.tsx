"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { DependencyList } from "@/features/system-status/dependency-list";
import { useHealth, useReadiness } from "@/hooks/use-system-status";

/**
 * Служебная панель состояния фундамента.
 *
 * Единственный экран PHASE 1. Прикладных представлений — дашборда,
 * организаций, сигналов — здесь нет: они появляются вместе с доменом
 * в PHASE 2. Показывать вымышленные медицинские данные ради вида
 * интерфейса недопустимо.
 */
export function SystemStatusPanel() {
  const health = useHealth();
  const readiness = useReadiness();

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Приложение</CardTitle>
          <CardDescription>
            Проверка живости процесса. Зависимости не опрашиваются.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {health.isPending && <Skeleton />}

          {health.isError && (
            <Badge variant="danger">API недоступен</Badge>
          )}

          {health.data && (
            <dl className="space-y-2 text-sm">
              <Row label="Состояние">
                <Badge variant="success">работает</Badge>
              </Row>
              <Row label="Сервис">{health.data.service}</Row>
              <Row label="Версия">{health.data.version}</Row>
              <Row label="Среда">{health.data.environment}</Row>
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Готовность</CardTitle>
          <CardDescription>
            Обязательные зависимости определяют готовность принимать трафик.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {readiness.isPending && <Skeleton />}

          {readiness.isError && (
            <Badge variant="danger">Состояние неизвестно</Badge>
          )}

          {readiness.data && (
            <>
              <Badge
                variant={readiness.data.status === "ready" ? "success" : "warning"}
              >
                {readiness.data.status === "ready" ? "готов" : "не готов"}
              </Badge>
              <DependencyList dependencies={readiness.data.dependencies} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2" aria-hidden>
      <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
      <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
    </div>
  );
}
