"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchCopilotExplanation } from "@/features/copilot/api";
import { formatFactValue, formatOptionalPeriod, formatTimestamp } from "@/features/copilot/format";
import type { CopilotResponse } from "@/features/copilot/types";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/services/api-client";

type SignalIdentity = { id: string; version: number; title: string };
type ResultState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; result: CopilotResponse }
  | { kind: "error"; code: string; retryAfterSeconds: number | null };

const ERROR_STATES: Record<string, string> = {
  COPILOT_DISABLED: "Функция отключена. Обычное объяснение сигнала остаётся доступным.",
  COPILOT_PROVIDER_UNAVAILABLE: "Сервис временно недоступен. Попробуйте позже вручную.",
  COPILOT_PROVIDER_TIMEOUT: "Время ожидания истекло. При необходимости повторите вручную.",
  COPILOT_INSUFFICIENT_DATA: "Недостаточно данных для пояснения этого сигнала.",
  NOT_FOUND: "Сигнал недоступен или не найден.",
  UNAUTHENTICATED: "Требуется вход в систему.",
  COPILOT_INVALID_RESPONSE: "Результат не прошёл проверку. Непроверенный текст не отображается.",
  COPILOT_RATE_LIMITED: "Достигнут лимит запросов. Попробуйте позже.",
  CONTEXT_MISMATCH: "Карточка изменилась. Обновите карточку вручную перед новым запросом.",
};

const RETRYABLE = new Set(["COPILOT_PROVIDER_UNAVAILABLE", "COPILOT_PROVIDER_TIMEOUT"]);

/** Remounts private result state whenever signal, version or OIDC session changes. */
export function CopilotEntry({ signal }: { signal: SignalIdentity }) {
  const { accessToken, isAuthenticated, login } = useAuth();
  // The key is only in React memory (never DOM, storage or logs). A changed
  // OIDC session remounts this private request/result state.
  const contextKey = JSON.stringify([signal.id, signal.version, accessToken]);
  return (
    <CopilotExperience
      key={contextKey}
      signal={signal}
      isAuthenticated={isAuthenticated}
      login={login}
    />
  );
}

function CopilotExperience({
  signal,
  isAuthenticated,
  login,
}: {
  signal: SignalIdentity;
  isAuthenticated: boolean;
  login: (returnTo?: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ResultState>({ kind: "idle" });
  const request = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  // On context change or unmount, the response must never enter the next card.
  // Aborting the browser request does not guarantee provider billing is cancelled.
  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (open && dialog.current && !dialog.current.open) {
      dialog.current.showModal();
      closeButton.current?.focus();
    }
  }, [open]);

  async function generate(): Promise<void> {
    if (!isAuthenticated || request.current !== null) return;
    const controller = new AbortController();
    request.current = controller;
    setState({ kind: "loading" });
    try {
      const result = await fetchCopilotExplanation(signal.id, controller.signal);
      if (controller.signal.aborted) return;
      if (result.signal_id !== signal.id || result.signal_version !== signal.version) {
        setState({ kind: "error", code: "CONTEXT_MISMATCH", retryAfterSeconds: null });
      } else {
        setState({ kind: "success", result });
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({
          kind: "error",
          code: error instanceof ApiError ? error.code : "UNEXPECTED_RESPONSE",
          retryAfterSeconds: error instanceof ApiError ? error.retryAfterSeconds : null,
        });
      }
    } finally {
      if (request.current === controller) request.current = null;
    }
  }

  function openPanel(): void {
    setOpen(true);
    if (state.kind === "idle") void generate();
  }

  function closePanel(): void {
    if (dialog.current?.open) dialog.current.close();
    setOpen(false);
    if (trigger.current?.isConnected) trigger.current.focus();
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-sm leading-6 text-slate-600">
        Пояснение на основе показателей выбранного сигнала
      </p>
      <Button ref={trigger} type="button" className="border-cyan-200 bg-white text-cyan-900 hover:bg-cyan-50" variant="outline" onClick={openPanel} disabled={!isAuthenticated}>
        Объяснить сигнал
      </Button>
      {open && (
        <dialog
          ref={dialog}
          aria-labelledby="copilot-panel-title"
          aria-modal="true"
          onCancel={(event) => { event.preventDefault(); closePanel(); }}
          onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); closePanel(); } }}
          onClose={() => { setOpen(false); if (trigger.current?.isConnected) trigger.current.focus(); }}
          className="fixed inset-y-0 right-0 m-0 ml-auto h-dvh max-h-dvh w-full max-w-[520px] overflow-y-auto border-l border-slate-200 bg-[#f5f8fa] p-0 text-foreground shadow-2xl backdrop:bg-slate-950/40"
        >
          <div className="space-y-6 p-5 sm:p-7">
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
              <div><p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-cyan-700">Дополнительный контекст</p><h2 id="copilot-panel-title" className="mt-1 text-xl font-extrabold tracking-[-0.03em] text-[#102f45]">AI-пояснение</h2></div>
              <Button ref={closeButton} type="button" variant="ghost" size="sm" aria-label="Закрыть пояснение" onClick={closePanel}>
                <X aria-hidden="true" className="h-4 w-4" />
              </Button>
            </header>

            <Badge variant="warning">Синтетическая демонстрация</Badge>
            <p className="text-base font-medium">{signal.title}</p>

            {state.kind === "loading" && (
              <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
                Формируем пояснение…
              </p>
            )}
            {state.kind === "error" && (
              <div role="alert" className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
                <p>{ERROR_STATES[state.code] ?? "Пояснение сейчас недоступно."}</p>
                {state.code === "COPILOT_RATE_LIMITED" && state.retryAfterSeconds !== null && (
                  <p>Повторить не ранее чем через {state.retryAfterSeconds} секунд.</p>
                )}
                {RETRYABLE.has(state.code) && (
                  <Button type="button" variant="outline" onClick={() => void generate()}>
                    Повторить вручную
                  </Button>
                )}
                {state.code === "UNAUTHENTICATED" && (
                  <Button type="button" variant="outline" onClick={() => void login(window.location.pathname)}>
                    Войти
                  </Button>
                )}
              </div>
            )}
            {state.kind === "success" && <CopilotResult result={state.result} />}
          </div>
        </dialog>
      )}
    </div>
  );
}

function CopilotResult({ result }: { result: CopilotResponse }) {
  const selected = new Set(result.fact_ids);
  return (
    <div className="space-y-6 text-sm">
      <section className="space-y-2 rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-extrabold text-[#102f45]">Пояснение</h3>
        <p className="whitespace-pre-line leading-relaxed">{result.explanation}</p>
      </section>
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-extrabold text-[#102f45]">На каких данных основано</h3>
        <ul className="space-y-3">
          {result.facts.map((fact) => (
            <li key={fact.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="font-medium">{fact.label}</p>
              <p>{formatFactValue(fact)}</p>
              <p className="text-xs text-muted-foreground">{selected.has(fact.id) ? "Использовано в пояснении" : "Доступный факт"}</p>
              <p className="text-xs text-muted-foreground">Период факта: {formatOptionalPeriod(fact.period_start, fact.period_end)}</p>
              <p className="text-xs text-muted-foreground">Источник: {fact.source === "signal_explanation" ? "показатели сигнала" : fact.source}</p>
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-2 rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-extrabold text-[#102f45]">Периоды</h3>
        <dl className="space-y-2">
          <div><dt className="text-muted-foreground">Период наблюдения</dt><dd>{formatOptionalPeriod(result.evaluation_period_start, result.evaluation_period_end)}</dd></div>
          <div><dt className="text-muted-foreground">Период сравнения</dt><dd>{formatOptionalPeriod(result.reference_period_start, result.reference_period_end)}</dd></div>
        </dl>
      </section>
      <section className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
        <h3 className="font-extrabold">Ограничения и актуальность</h3>
        <p>{result.data_current ? "Данные обозначены как актуальные для правила." : "Данные не обозначены как текущие."}</p>
        <p>Время данных: {formatTimestamp(result.data_watermark_at)}</p>
        <ul className="list-disc space-y-1 pl-5">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer font-medium">Сведения о формировании</summary>
        <dl className="mt-3 space-y-2 text-xs">
          <div><dt>Модель</dt><dd>{result.provider} / {result.model}</dd></div>
          <div><dt>Сформировано</dt><dd>{formatTimestamp(result.generated_at)}</dd></div>
          <div><dt>request_id</dt><dd className="break-all font-mono">{result.request_id ?? "Неизвестно"}</dd></div>
        </dl>
      </details>
    </div>
  );
}
