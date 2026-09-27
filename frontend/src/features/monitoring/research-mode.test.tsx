import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { MonitorPage } from "./monitor-page";
import { SiteHeader } from "@/components/site-header";

vi.mock("@/config/env", () => ({ env: { pilotModeEnabled: true, appEnv: "local" } }));
vi.mock("@/features/auth/auth-context", () => ({ useAuth: () => ({ isAuthenticated: false, accessToken: null, login: vi.fn() }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/monitor" }));
const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); });

it("preserves explicit localhost historical replay and sends a step only after human input", async () => {
  const monitor = { as_of: "2025-01-01", new_records: 3, hospitals_checked: 1, alerts: [], running: false,
    index: 0, total_steps: 2, finished: false, updated_at: null, interval_seconds: 10, model_id: "synthetic-model", prediction_mode: "historical" };
  const fetcher = vi.fn(async () => new Response(JSON.stringify(monitor)));
  vi.stubGlobal("fetch", fetcher);
  render(<QueryClientProvider client={client}><SiteHeader /><MonitorPage /></QueryClientProvider>);
  expect(await screen.findByText(/Историческое воспроизведение/)).toBeInTheDocument();
  expect(screen.getByText(/тестовые данные/i)).toBeInTheDocument();
  expect(screen.queryByText(/реальные данные/i)).not.toBeInTheDocument();
  const step = await screen.findByRole("button", { name: "Следующий день" });
  await waitFor(() => expect(step).toBeEnabled());
  expect(fetcher.mock.calls).toHaveLength(1);
  expect(screen.getByText("Локальный пилот")).toBeInTheDocument();
  fireEvent.click(step);
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/pilot/replay", expect.objectContaining({ method: "POST", body: '{"action":"step"}' })));
});
