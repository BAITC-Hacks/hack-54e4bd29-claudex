import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MonitorPage } from "./monitor-page";
import ModelPage from "@/app/monitor/model/page";
import AlertPage from "@/app/monitor/[id]/page";
import { setTokenProvider } from "@/services/api-client";
import type { ReferralForecast } from "@/features/forecasting/types";

const route = vi.hoisted(() => ({ query: "" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(route.query) }));
const auth = vi.hoisted(() => ({ accessToken: "synthetic-session-a" as string | null, isAuthenticated: true, login: vi.fn(), logout: vi.fn(), setToken: vi.fn() }));
vi.mock("@/features/auth/auth-context", () => ({ useAuth: () => auth }));
vi.mock("echarts", () => ({ init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }) }));

// Synthetic aggregates only; deliberately different prediction/baseline/delta
// prove the UI displays persisted values rather than recomputing a model/rule.
const forecast: ReferralForecast = {
  id: "00000000-0000-0000-0000-000000000101", target: "DAILY_REFERRAL_COUNT", scope_type: "GLOBAL",
  horizon_days: 7, input_period_start: "2025-01-01T00:00:00Z", input_period_end: "2025-03-31T00:00:00Z",
  forecast_start: "2025-04-01", forecast_end: "2025-04-07", generated_at: "2025-04-01T10:00:00Z",
  model_version: "synthetic-weekly-v1", selected_model: "weekly_naive", baseline_model: "weekly_naive",
  metrics: { mae: 12.3, wape: 0.04, rmse: 15.1 }, baseline_metrics: { mae: 13, wape: 0.05, rmse: 16 },
  dataset_watermark: { import_ids: ["synthetic-import"] }, freshness_status: "CURRENT",
  limitations: ["Synthetic limitation"], historical: [{ date: "2025-03-31", value: 100 }],
  forecast: [{ date: "2025-04-01", predicted_value: 101, baseline_value: 80, delta_from_baseline: 21 }],
  disclaimer: "Расчётный прогноз. Решение принимает уполномоченный сотрудник.",
};
const signals = { items: [{
  id: "00000000-0000-0000-0000-000000000202", scope_type: "GLOBAL", region_id: null, hospital_id: null, hospital_name: null,
  type: "FORECAST_INFLOW_GROWTH", severity: "WARNING", status: "NEW", source_type: "RULE_BASED", title: "Synthetic persisted signal",
  summary: "Saved evidence", detected_at: "2025-04-01T10:00:00Z", evaluation_period_start: null, evaluation_period_end: null,
  assigned_user_id: null, version: 1,
}], page: 1, page_size: 20, total: 1, has_next: false };
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const errorResponse = (status: number) => response({ error: { code: status === 404 ? "NOT_FOUND" : "DENIED", message: "Do not expose server detail", details: {}, request_id: "synthetic-request" } }, status);
let fetcher: ReturnType<typeof vi.fn>;
let client: QueryClient;
function mount(node = <MonitorPage />) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}
beforeEach(() => {
  route.query = "";
  auth.accessToken = "synthetic-session-a"; auth.isAuthenticated = true; auth.login.mockReset();
  setTokenProvider(() => auth.accessToken);
  fetcher = vi.fn(async (url: string) => url.includes("/forecasts/") ? response(forecast) : url.startsWith("/api/v1/signals?") ? response(signals) : response({}, 500));
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => { cleanup(); client?.clear(); setTokenProvider(() => null); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("authenticated monitoring", () => {
  it("requires AuthGate before making any request", () => {
    auth.isAuthenticated = false; auth.accessToken = null;
    mount();
    expect(screen.getByRole("button", { name: /Войти через Keycloak/ })).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("shows loading without starting pilot requests or replay timers", async () => {
    fetcher.mockImplementation(() => new Promise(() => {}));
    vi.useFakeTimers();
    mount();
    expect(screen.getByText(/Загрузка прогноза/)).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetcher.mock.calls.map(([url]) => url).sort()).toEqual(["/api/v1/forecasts/referrals/latest", "/api/v1/signals?page=1&page_size=20"]);
    expect(screen.queryByRole("button", { name: /Запустить|Следующий день/ })).not.toBeInTheDocument();
  });
  it("renders persisted global evidence and links the human Signal/Incident workflow", async () => {
    mount();
    expect(await screen.findByText(/synthetic-weekly-v1/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "101" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "80" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "21" })).toBeInTheDocument();
    expect(screen.getByText(/Допуск модели недоступен/)).toBeInTheDocument();
    expect(screen.getByText(/Подтверждение сигнала и создание инцидента/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Synthetic persisted signal/ })).toHaveAttribute("href", "/signals/00000000-0000-0000-0000-000000000202");
    expect(fetcher.mock.calls.every(([url, options]) => url.startsWith("/api/v1/") && options.method === "GET" && options.headers.Authorization === "Bearer synthetic-session-a")).toBe(true);
  });
  it("marks STALE evidence historical without offering operational activation", async () => {
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? response({ ...forecast, freshness_status: "STALE" }) : response(signals));
    mount();
    expect(await screen.findByText(/Исторический прогноз: период его действия завершён/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Активировать|Создать инцидент/ })).not.toBeInTheDocument();
  });
  it("treats 404 as missing or out of scope without enumerating global/source objects", async () => {
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? errorResponse(404) : response({ ...signals, items: [], total: 0 }));
    mount();
    expect(await screen.findByText(/Прогноз не найден или недоступен в вашей области данных/)).toBeInTheDocument();
    expect(await screen.findByText(/Доступных сигналов пока нет/)).toBeInTheDocument();
    expect(screen.queryByText(/Do not expose/)).not.toBeInTheDocument();
  });
  it("shows denied forecast access while retaining authorized scoped signals", async () => {
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? errorResponse(403) : response(signals));
    mount();
    expect(await screen.findByText(/Недостаточно прав для просмотра прогноза/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Synthetic persisted signal/ })).toBeInTheDocument();
  });
  it.each(["forecast", "signals"])("hides evidence and offers login when %s reports expired login", async (failed) => {
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? (failed === "forecast" ? errorResponse(401) : response(forecast)) : (failed === "signals" ? errorResponse(401) : response(signals)));
    mount();
    const login = await screen.findByRole("button", { name: /Войти повторно/ });
    fireEvent.click(login);
    expect(auth.login).toHaveBeenCalledOnce();
    expect(screen.queryByText(/synthetic-weekly-v1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic persisted signal/)).not.toBeInTheDocument();
  });
  it("retries service failure only on explicit refresh", async () => {
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? errorResponse(503) : response(signals));
    mount();
    expect(await screen.findByText(/Не удалось загрузить прогноз/)).toBeInTheDocument();
    fetcher.mockImplementation(async (url: string) => url.includes("/forecasts/") ? response(forecast) : response(signals));
    fireEvent.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(await screen.findByText(/synthetic-weekly-v1/)).toBeInTheDocument();
  });
  it("never shows a previous identity's cached forecast after login changes", async () => {
    const view = mount();
    await screen.findByText(/synthetic-weekly-v1/);
    auth.accessToken = "synthetic-restricted-session";
    fetcher.mockImplementation(() => new Promise(() => {}));
    view.rerender(<QueryClientProvider client={client}><MonitorPage /></QueryClientProvider>);
    expect(screen.queryByText(/synthetic-weekly-v1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic persisted signal/)).not.toBeInTheDocument();
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4));
    expect(JSON.stringify(client.getQueryCache().getAll().map(q => q.queryKey))).not.toContain("synthetic-session");
  });
  it("hides previously loaded evidence after a refresh is denied", async () => {
    mount(); await screen.findByText(/synthetic-weekly-v1/);
    fetcher.mockImplementation(async () => errorResponse(404));
    fireEvent.click(screen.getByRole("button", { name: /Обновить/ }));
    await screen.findByText(/Прогноз не найден или недоступен/);
    expect(screen.queryByText(/synthetic-weekly-v1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic persisted signal/)).not.toBeInTheDocument();
  });
  it("protects the model URL using the same authenticated persisted evidence", async () => {
    mount(<ModelPage />);
    expect(await screen.findByText(/synthetic-weekly-v1/)).toBeInTheDocument();
    expect(fetcher.mock.calls.every(([url]) => url.startsWith("/api/v1/"))).toBe(true);
  });
  it("does not resolve legacy research IDs as production hospital or signal IDs", async () => {
    const params = Promise.resolve({ id: "synthetic-source-alias" });
    await act(async () => { mount(<AlertPage params={params} />); });
    expect(await screen.findByText(/Исследовательская карточка недоступна/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть сигналы/ })).toHaveAttribute("href", "/signals");
    expect(fetcher).not.toHaveBeenCalled();
  });
});

// Parent-defined contract: IDs are persisted Forecast UUIDs, never source aliases.
describe("specific persisted forecast evidence", () => {
  it.each(["GLOBAL", "REGION", "HOSPITAL"])("reads only the requested UUID and displays its %s scope", async (scope) => {
    route.query = `forecast_id=${forecast.id}`;
    fetcher.mockImplementation(async (url: string) => url === `/api/v1/forecasts/${forecast.id}` ? response({
      ...forecast, scope_type: scope, hospital_id: scope === "HOSPITAL" ? "00000000-0000-0000-0000-000000000303" : null,
      region_id: scope === "REGION" ? "00000000-0000-0000-0000-000000000404" : null, historical: [],
    }) : url.startsWith("/api/v1/signals?") ? response(signals) : errorResponse(404));
    mount(<ModelPage />);
    expect(await screen.findByText(/synthetic-weekly-v1/)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Область прогноза:.*${scope}`))).toBeInTheDocument();
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([`/api/v1/forecasts/${forecast.id}`, "/api/v1/signals?page=1&page_size=20"]);
    expect(screen.getByText(/Допуск модели недоступен/)).toBeInTheDocument();
  });
  it.each(["synthetic-source-alias", "", "../../pilot/model"])("rejects non-UUID forecast IDs (%s) without guessing or falling back to global", async (id) => {
    route.query = `forecast_id=${encodeURIComponent(id)}`;
    mount(<ModelPage />);
    expect(await screen.findByText(/Некорректный идентификатор прогноза/)).toBeInTheDocument();
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(["/api/v1/signals?page=1&page_size=20"]);
  });
  it("does not retry a denied forecast UUID through the latest global endpoint", async () => {
    route.query = `forecast_id=${forecast.id}`;
    fetcher.mockImplementation(async (url: string) => url.startsWith("/api/v1/forecasts/") ? errorResponse(404) : response(signals));
    mount(<ModelPage />);
    await screen.findByText(/Прогноз не найден или недоступен/);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([`/api/v1/forecasts/${forecast.id}`, "/api/v1/signals?page=1&page_size=20"]);
  });
});

describe("forecast login return target", () => {
  const id = "ABCDEFAB-1234-4ABC-8DEF-ABCDEFABCDEF";
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("preserves the exact UUID through initial login and resumes only that forecast", async () => {
    route.query = `forecast_id=${id}&returnTo=https://untrusted.invalid`;
    window.history.replaceState(null, "", `/monitor/model?${route.query}`);
    auth.isAuthenticated = false; auth.accessToken = null;
    const view = mount(<ModelPage />);
    fireEvent.click(screen.getByRole("button", { name: /Войти через Keycloak/ }));
    expect(auth.login).toHaveBeenCalledWith(`/monitor/model?forecast_id=${id}`);
    expect(fetcher).not.toHaveBeenCalled();

    const returnTo = auth.login.mock.calls[0]?.[0];
    if (typeof returnTo !== "string") throw new Error("Login must save a return target");
    route.query = new URL(returnTo, "https://synthetic.invalid").search.slice(1);
    auth.isAuthenticated = true; auth.accessToken = "synthetic-restored-session";
    view.rerender(<QueryClientProvider client={client}><ModelPage /></QueryClientProvider>);
    await screen.findByText(/synthetic-weekly-v1/);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([`/api/v1/forecasts/${id}`, "/api/v1/signals?page=1&page_size=20"]);
  });

  it("preserves the selected UUID when a protected request requires repeat login", async () => {
    route.query = `forecast_id=${id}`;
    window.history.replaceState(null, "", `/monitor/model?${route.query}`);
    fetcher.mockImplementation(async () => errorResponse(401));
    mount(<ModelPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Войти повторно/ }));
    expect(auth.login).toHaveBeenCalledWith(`/monitor/model?forecast_id=${id}`);
  });

  it.each(["", "../../pilot/model", "https://untrusted.invalid", " " + id])("never forwards an invalid forecast value (%s) through login or falls back to global", async value => {
    route.query = `forecast_id=${encodeURIComponent(value)}`;
    window.history.replaceState(null, "", `/monitor/model?${route.query}`);
    auth.isAuthenticated = false; auth.accessToken = null;
    const view = mount(<ModelPage />);
    fireEvent.click(screen.getByRole("button", { name: /Войти через Keycloak/ }));
    expect(auth.login).toHaveBeenCalledWith("/monitor/model?forecast_id=");
    route.query = "forecast_id=";
    auth.isAuthenticated = true; auth.accessToken = "synthetic-restored-session";
    view.rerender(<QueryClientProvider client={client}><ModelPage /></QueryClientProvider>);
    await screen.findByText(/Некорректный идентификатор прогноза/);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(["/api/v1/signals?page=1&page_size=20"]);
  });

  it("retains latest-model navigation when no forecast ID is supplied", () => {
    window.history.replaceState(null, "", "/monitor/model?returnTo=https://untrusted.invalid");
    auth.isAuthenticated = false; auth.accessToken = null;
    mount(<ModelPage />);
    fireEvent.click(screen.getByRole("button", { name: /Войти через Keycloak/ }));
    expect(auth.login).toHaveBeenCalledWith("/monitor/model");
  });
});
