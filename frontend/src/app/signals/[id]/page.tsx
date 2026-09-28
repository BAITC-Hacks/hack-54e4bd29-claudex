"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/features/auth/auth-context";
import { AuthGate } from "@/features/auth/auth-gate";
import { CopilotEntry } from "@/features/copilot/copilot-entry";
import {
  SEVERITY_LABELS,
  SEVERITY_VARIANTS,
  SOURCE_LABELS,
  STATUS_LABELS,
  TYPE_LABELS,
  formatDateTime,
} from "@/features/signals/labels";
import { SignalEvidence } from "@/features/signals/signal-evidence";
import { useCreateIncident, useSignal, useSignalDecision } from "@/hooks/use-domain";
import { ApiError } from "@/services/api-client";
import type { SignalDetail } from "@/types/domain";

export default function SignalDetailPage() {
  const params = useParams<{ id: string }>();
  const { isAuthenticated } = useAuth();
  const signal = useSignal(isAuthenticated, params.id);

  return (
    <div className="space-y-6">
      <AuthGate>
        {signal.isPending && (
          <p className="text-sm text-muted-foreground">Загрузка…</p>
        )}
        {signal.isError && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-900" role="alert">
            <p className="font-bold">Сигнал временно недоступен.</p>
            <p className="mt-1">Обновите страницу позже или вернитесь к ленте сигналов.</p>
          </div>
        )}
        {signal.data && <SignalCard detail={signal.data} />}
      </AuthGate>
    </div>
  );
}

function SignalCard({ detail }: { detail: SignalDetail }) {
  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={SEVERITY_VARIANTS[detail.severity]}>
            {SEVERITY_LABELS[detail.severity]}
          </Badge>
          <span className="text-sm text-muted-foreground">
            {STATUS_LABELS[detail.status]}
          </span>
          <span className="text-xs text-muted-foreground">
            источник: {SOURCE_LABELS[detail.source_type] ?? detail.source_type}
          </span>
        </div>
        <h1 className="text-xl font-semibold tracking-tight">{detail.title}</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          {detail.summary}
        </p>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Ситуация</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              <Row label="Тип">{TYPE_LABELS[detail.type]}</Row>
              <Row label="Организация">
                {detail.scope_type === "GLOBAL"
                  ? "Вся система"
                  : detail.hospital_name ?? detail.hospital_id ?? "—"}
              </Row>
              <Row label="Обнаружен">{formatDateTime(detail.detected_at)}</Row>
              <Row label="Ответственный">
                {detail.assigned_user_id ? "назначен" : "не назначен"}
              </Row>
              <Row label="Версия карточки">{detail.version}</Row>
              {detail.closed_reason && (
                <Row label="Причина закрытия">{detail.closed_reason}</Row>
              )}
            </dl>
          </CardContent>
        </Card>

        <ExplanationCard detail={detail} />
      </div>

      <SignalEvidence detail={detail} />
      <Card>
        <CardHeader>
          <CardTitle>AI-пояснение</CardTitle>
          <CardDescription>
            Дополнительное пояснение формируется только по запросу и не заменяет алгоритмическое основание сигнала.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CopilotEntry signal={{ id: detail.id, version: detail.version, title: detail.title }} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Расчётный сценарий</CardTitle>
          <CardDescription>
            Проверьте гипотетическое изменение потока отдельно от evidence сигнала.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link
            className="inline-flex h-9 items-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-accent"
            href={`/scenarios?signal_id=${detail.id}`}
          >
            Анализировать сценарий
          </Link>
        </CardContent>
      </Card>
      <TransitionCard detail={detail} />
      <IncidentCard detail={detail} />
      <HistoryCard detail={detail} />
    </div>
  );
}

function ExplanationCard({ detail }: { detail: SignalDetail }) {
  const explanation = detail.explanation;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Алгоритмическое объяснение</CardTitle>
        <CardDescription>
          Показывает, что повлияло на расчёт, а не установленную причину.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!explanation && (
          <p className="text-sm text-muted-foreground">
            Объяснение не построено. Сигнал не считается готовым к разбору.
          </p>
        )}
        {explanation && (
          <>
            <p className="text-sm">{explanation.summary}</p>
            <ul className="space-y-1.5 text-sm">
              {explanation.factors.map((factor) => (
                <li key={factor.metric_code} className="flex justify-between gap-4">
                  <span className="text-muted-foreground">
                    {factor.metric_code}
                  </span>
                  <span className="font-medium">
                    {factor.direction === "INCREASE" ? "↑" : "↓"}
                    {factor.change_pct !== null
                      ? ` ${factor.change_pct}%`
                      : " изменение"}
                  </span>
                </li>
              ))}
            </ul>
            {explanation.caveats.length > 0 && (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {explanation.caveats.map((caveat) => (
                  <li key={caveat}>— {caveat}</li>
                ))}
              </ul>
            )}
            {/* Происхождение обязательно: утверждение без источника
                невозможно перепроверить. */}
            <p className="border-t border-border pt-2 text-xs text-muted-foreground">
              Построено: {explanation.generator} {explanation.generator_version}
              {explanation.model_version
                ? `, модель ${explanation.model_version}`
                : ""}
              , {formatDateTime(explanation.generated_at)}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TransitionCard({ detail }: { detail: SignalDetail }) {
  const [reason, setReason] = useState("");
  const mutation = useSignalDecision(detail.id);

  const conflict =
    mutation.error instanceof ApiError && mutation.error.code === "CONFLICT";

  if (detail.available_transitions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Действия</CardTitle>
          <CardDescription>
            У вашей роли нет права изменять статус этого сигнала. Перечень
            доступных переходов определяет сервер.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Действия</CardTitle>
        <CardDescription>
          Решение принимает уполномоченный сотрудник. Каждое изменение
          попадает в журнал аудита.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="block text-sm" htmlFor="reason">
          Причина
        </label>
        <input
          id="reason"
          className="h-9 w-full max-w-lg rounded-md border border-border bg-background px-3 text-sm"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Кратко опишите основание решения"
        />
        <div className="flex flex-wrap gap-2">
          {detail.status === "NEW" && detail.available_transitions.includes("IN_PROGRESS") && (
            <Button
              variant="outline"
              disabled={mutation.isPending || reason.trim().length < 3}
              onClick={() => mutation.mutate({ decision: "acknowledge", version: detail.version, reason: reason.trim() })}
            >
              Принять в работу
            </Button>
          )}
          {detail.available_transitions.includes("CLOSED") && (
            <>
              <Button
                variant="outline"
                disabled={mutation.isPending || reason.trim().length < 3}
                onClick={() => mutation.mutate({ decision: "resolve", version: detail.version, reason: reason.trim() })}
              >
                Закрыть как обработанный
              </Button>
              <Button
                variant="outline"
                disabled={mutation.isPending || reason.trim().length < 3}
                onClick={() => mutation.mutate({ decision: "dismiss", version: detail.version, reason: reason.trim() })}
              >
                Отклонить
              </Button>
            </>
          )}
        </div>
        {conflict && (
          <p className="text-sm text-destructive">
            Карточку изменил другой сотрудник. Обновите страницу и повторите.
          </p>
        )}
        {mutation.isError && !conflict && (
          <p className="text-sm text-destructive">Не удалось сохранить действие. Повторите позже.</p>
        )}
      </CardContent>
    </Card>
  );
}

function IncidentCard({ detail }: { detail: SignalDetail }) {
  const [title, setTitle] = useState(detail.title);
  const [description, setDescription] = useState("");
  const mutation = useCreateIncident(detail.id);

  if (detail.incident_id) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Инцидент</CardTitle>
          <CardDescription>
            Сигнал связан с инцидентом {detail.incident_id}.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Создать инцидент</CardTitle>
        <CardDescription>
          Инцидент создаёт сотрудник после анализа сигнала. Автоматическое
          управленческое решение не принимается.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="block text-sm" htmlFor="incident-title">Название</label>
        <input
          id="incident-title"
          className="h-9 w-full max-w-xl rounded-md border border-border bg-background px-3 text-sm"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label className="block text-sm" htmlFor="incident-description">Описание</label>
        <textarea
          id="incident-description"
          className="min-h-20 w-full max-w-xl rounded-md border border-border bg-background p-3 text-sm"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <Button
          variant="outline"
          disabled={mutation.isPending || title.trim().length < 1}
          onClick={() => mutation.mutate({ signalVersion: detail.version, title: title.trim(), description: description.trim() })}
        >
          Создать инцидент
        </Button>
        {mutation.isSuccess && (
          <p className="text-sm text-muted-foreground">
            Инцидент создан: {mutation.data.id}
          </p>
        )}
        {mutation.isError && (
          <p className="text-sm text-destructive">Не удалось создать инцидент. Повторите позже.</p>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryCard({ detail }: { detail: SignalDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>История</CardTitle>
        <CardDescription>
          Действия людей и записи журнала аудита.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-medium">Действия</h3>
          {detail.actions.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">
              Действий пока нет.
            </p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {detail.actions.map((action) => (
                <li key={action.id} className="flex justify-between gap-4">
                  <span>{action.description}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(action.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="text-sm font-medium">Журнал аудита</h3>
          {detail.audit_history.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">Записей нет.</p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {detail.audit_history.map((event) => (
                <li key={event.id} className="flex justify-between gap-4">
                  <span className="font-mono text-xs">{event.action}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(event.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}
