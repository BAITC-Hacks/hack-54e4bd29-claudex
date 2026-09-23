"use client";

import Link from "next/link";
import { useState } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { AuthGate } from "@/features/auth/auth-gate";
import { useAuth } from "@/features/auth/auth-context";
import { fetchLatestReferralForecast, fetchReferralForecast } from "@/features/forecasting/api";
import { ReferralForecastCard } from "@/features/forecasting/components/referral-forecast-card";
import { SCOPE_LABELS, SEVERITY_LABELS, STATUS_LABELS } from "@/features/signals/labels";
import { fetchSignals } from "@/services/domain";
import { ApiError } from "@/services/api-client";
import { forecastLoginReturnTo } from "./forecast-login-return";
import { useLocalResearch } from "./local-research";
import { MonitorPage as ResearchMonitorPage } from "./research-monitor-page";

const button = "inline-flex items-center rounded-lg border px-4 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-40";

export function MonitorPage({ forecastId }: { forecastId?: string } = {}) {
  const research = useLocalResearch();
  const { accessToken } = useAuth();
  if (research && forecastId === undefined) return <ResearchMonitorPage />;
  return <AuthGate returnTo={forecastId === undefined ? undefined : () => forecastLoginReturnTo(forecastId)}><MonitoringSession key={accessToken} forecastId={forecastId} /></AuthGate>;
}

function MonitoringSession({ forecastId }: { forecastId?: string }) {
  // An identity change remounts this boundary. Neither credentials nor a
  // previous user's aggregates enter shared query keys/caches.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: {
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false,
  } } }));
  return <QueryClientProvider client={client}><PersistedMonitoring forecastId={forecastId} /></QueryClientProvider>;
}

function ReadError({ error, subject }: { error: Error; subject: "forecast" | "signals" }) {
  let message = subject === "forecast" ? "Не удалось загрузить прогноз. Повторите запрос." : "Не удалось загрузить сигналы. Повторите запрос.";
  if (error instanceof ApiError) {
    if (error.code === "INVALID_FORECAST_ID") message = "Некорректный идентификатор прогноза. Используйте UUID из карточки сигнала.";
    if (error.httpStatus === 404) message = subject === "forecast"
      ? "Прогноз не найден или недоступен в вашей области данных."
      : "Сигналы не найдены или недоступны в вашей области данных.";
    if (error.httpStatus === 403) message = subject === "forecast"
      ? "Недостаточно прав для просмотра прогноза."
      : "Недостаточно прав для просмотра сигналов.";
  }
  return <p role="alert" className="rounded-lg border p-4 text-sm">{message}</p>;
}

async function afterAuthEffects<T>(signal: AbortSignal, read: (signal: AbortSignal) => Promise<T>): Promise<T> {
  // AuthProvider installs the API token in its parent effect. Query observers
  // mount first, so defer transport until those effects have finished. Consume
  // and check the signal to cancel an obsolete identity before sending anything.
  await Promise.resolve();
  signal.throwIfAborted();
  return read(signal);
}

function PersistedMonitoring({ forecastId }: { forecastId?: string }) {
  const { login } = useAuth();
  const forecast = useQuery({ queryKey: ["monitoring", "forecast", forecastId ?? "latest"], queryFn: ({ signal }) => afterAuthEffects(signal, currentSignal => forecastId === undefined ? fetchLatestReferralForecast(currentSignal) : fetchReferralForecast(forecastId, currentSignal)) });
  const signals = useQuery({ queryKey: ["monitoring", "signals"], queryFn: ({ signal }) => afterAuthEffects(signal, currentSignal => fetchSignals({ page: 1, pageSize: 20 }, currentSignal)) });
  const expired = [forecast.error, signals.error].some(error => error instanceof ApiError && error.isUnauthenticated);

  if (expired) return <section className="mx-auto max-w-3xl space-y-4 rounded-xl border p-6">
    <h1 className="text-xl font-semibold">Сессия истекла</h1>
    <p role="alert">Войдите повторно, чтобы продолжить просмотр защищённых данных.</p>
    <button className={button} onClick={() => void login(forecastId === undefined ? undefined : forecastLoginReturnTo(forecastId))}>Войти повторно</button>
  </section>;

  return <div className="mx-auto max-w-6xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-3xl font-semibold">Мониторинг направлений</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Сохранённый прогноз и сигналы в вашей области доступа. Решения принимает уполномоченный сотрудник.</p>
      </div>
      <button className={button} disabled={forecast.isFetching || signals.isFetching} onClick={() => { void forecast.refetch(); void signals.refetch(); }}>Обновить</button>
    </header>

    <section aria-label="Сохранённый прогноз" className="space-y-4">
      {forecast.isPending ? <p role="status">Загрузка прогноза…</p> : forecast.error ? <ReadError error={forecast.error} subject="forecast" /> : forecast.data ? <>
        <p className="text-sm font-medium">Область прогноза: {SCOPE_LABELS[forecast.data.scope_type]} ({forecast.data.scope_type}).</p>
        <ReferralForecastCard forecast={forecast.data} isLoading={false} error={null} />
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950" role="status">
          <h2 className="font-semibold">Допуск модели недоступен</h2>
          <p className="mt-2">В этом ответе API нет подтверждения допуска к эксплуатации. Актуальность периода и качество прогноза сами по себе не подтверждают допуск. Этот экран не активирует модель и не создаёт сигналы.</p>
        </div>
        <details className="rounded-xl border p-5 text-sm">
          <summary className="cursor-pointer font-semibold">Основания и происхождение прогноза</summary>
          <dl className="mt-3 space-y-2 break-words">
            <div><dt className="font-medium">Идентификатор сохранённого прогноза</dt><dd>{forecast.data.id}</dd></div>
            {forecast.data.hospital_id && <div><dt className="font-medium">Идентификатор организации</dt><dd>{forecast.data.hospital_id}</dd></div>}
            {forecast.data.region_id && <div><dt className="font-medium">Идентификатор региона</dt><dd>{forecast.data.region_id}</dd></div>}
            <div><dt className="font-medium">Период исходных данных</dt><dd>{forecast.data.input_period_start} — {forecast.data.input_period_end}</dd></div>
            <div><dt className="font-medium">Период прогноза</dt><dd>{forecast.data.forecast_start} — {forecast.data.forecast_end}</dd></div>
            <div><dt className="font-medium">MAE простого сравнения</dt><dd>{forecast.data.baseline_metrics.mae}</dd></div>
          </dl>
        </details>
      </> : null}
    </section>

    <section aria-label="Сигналы и действия человека" className="space-y-4 rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Сигналы в вашей области доступа</h2>
      <p className="text-sm text-muted-foreground">Подтверждение сигнала и создание инцидента доступны в карточке сигнала с учётом ваших прав. Список может включать сигналы из других расчётов; связь с прогнозом проверяйте в основаниях карточки.</p>
      {signals.isPending ? <p role="status">Загрузка сигналов…</p> : signals.error ? <ReadError error={signals.error} subject="signals" /> : signals.data?.items.length ? <ul className="space-y-3">
        {signals.data.items.map(item => <li key={item.id}>
          <Link href={`/signals/${encodeURIComponent(item.id)}`} className="block rounded-lg border p-4 hover:border-teal-600">
            <h3 className="font-semibold">{item.title}</h3>
            <p className="mt-1 text-sm">{item.summary}</p>
            <p className="mt-2 text-xs text-muted-foreground">{SCOPE_LABELS[item.scope_type]}{item.hospital_name ? ` · ${item.hospital_name}` : ""} · {SEVERITY_LABELS[item.severity]} · {STATUS_LABELS[item.status]}</p>
          </Link>
        </li>)}
      </ul> : <p>Доступных сигналов пока нет.</p>}
      {signals.data && !signals.error && signals.data.has_next && <p className="text-sm">Показаны первые {signals.data.items.length} из {signals.data.total}. Остальные доступны в общем списке.</p>}
      <Link href="/signals" className={button}>Открыть все сигналы</Link>
    </section>
  </div>;
}
