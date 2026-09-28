import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import SignalDetailPage from "@/app/signals/[id]/page";
import { setTokenProvider } from "@/services/api-client";
import type { SignalDetail } from "@/types/domain";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "11111111-1111-4111-8111-111111111111" }) }));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: true, accessToken: "synthetic-token", login: vi.fn() }),
}));

const detail = {
  id: "11111111-1111-4111-8111-111111111111",
  version: 3,
  title: "Синтетический сигнал",
  summary: "Проверка синтетического показателя",
  scope_type: "GLOBAL",
  region_id: null,
  hospital_id: null,
  hospital_name: null,
  type: "QUEUE_GROWTH",
  severity: "WARNING",
  status: "NEW",
  source_type: "RULE_BASED",
  detected_at: "2025-01-29T00:00:00Z",
  evaluation_period_start: null,
  evaluation_period_end: null,
  reference_period_start: null,
  reference_period_end: null,
  assigned_user_id: null,
  created_at: "2025-01-29T00:00:00Z",
  updated_at: "2025-01-29T00:00:00Z",
  forecast_id: null,
  incident_id: null,
  closed_reason: null,
  closed_at: null,
  closure_disposition: null,
  actual_value: null,
  baseline_value: null,
  delta_absolute: null,
  delta_percent: null,
  rule_code: "QUEUE_GROWTH",
  rule_version: "seed-0.1",
  rule_config: { synthetic: true },
  evidence: { synthetic: true },
  source: "SYNTHETIC_DEV_SEED",
  data_watermark: { synthetic: true },
  data_current: false,
  available_transitions: ["IN_PROGRESS"],
  explanation: {
    summary: "Алгоритмическое объяснение остаётся в карточке.",
    factors: [], caveats: [], generator: "RULE", generator_version: "seed-0.1",
    model_version: null, input_period_start: null, input_period_end: null,
    generated_at: "2025-01-29T00:00:00Z",
  },
  actions: [{
    id: "action-1",
    action_type: "ACKNOWLEDGE",
    description: "Принят в работу после проверки evidence.",
    created_by: "demo-admin",
    created_at: "2025-01-29T01:00:00Z",
  }],
  audit_history: [],
} satisfies SignalDetail;

vi.mock("@/hooks/use-domain", () => ({
  useSignal: () => ({ isPending: false, isError: false, data: detail }),
  useSignalDecision: () => ({ isPending: false, isError: false, error: null, mutate: vi.fn() }),
  useCreateIncident: () => ({ isPending: false, isError: false, isSuccess: false, mutate: vi.fn() }),
}));

afterEach(() => {
  setTokenProvider(() => null);
  vi.unstubAllGlobals();
});

it("keeps the algorithmic explanation visible if optional Copilot fails", async () => {
  setTokenProvider(() => "synthetic-token");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    error: { code: "COPILOT_DISABLED", message: "Copilot отключён", details: {}, request_id: "test" },
  }), { status: 503 })));
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });

  render(<SignalDetailPage />);
  expect(screen.getByRole("heading", { name: "Алгоритмическое объяснение" })).toBeInTheDocument();
  expect(screen.getByText(detail.explanation.summary)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
  expect(await screen.findByText("AI-пояснение временно недоступно. Алгоритмическое объяснение сигнала остаётся доступным.")).toBeInTheDocument();
  expect(screen.getByText(detail.explanation.summary)).toBeInTheDocument();
});

it("separates a signal from forecast evidence and makes the human decision step explicit", () => {
  render(<SignalDetailPage />);

  expect(screen.getByText("Операционный сигнал, не прогноз")).toBeInTheDocument();
  expect(screen.getByText(/Прогноз показывается только как отдельное основание, если связь сохранена сервером/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Основание сигнала" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Алгоритмическое объяснение" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Решение сотрудника" })).toBeInTheDocument();
  expect(screen.getByText(/Решение принимает уполномоченный сотрудник/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Принять в работу" })).toBeDisabled();
  expect(screen.getByText("Сотрудник: demo-admin")).toBeInTheDocument();
  const actionHeading = screen.getByRole("heading", { name: "Решение сотрудника" });
  const copilotHeading = screen.getByRole("heading", { name: "AI-пояснение" });
  expect(Boolean(actionHeading.compareDocumentPosition(copilotHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
});
