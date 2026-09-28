import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/features/auth/auth-context";
import { MonitorPage } from "./monitor-page";

function LoginHarness() {
  const { setToken } = useAuth();
  return <><button onClick={() => setToken("synthetic-first-user", 300)}>First user</button><button onClick={() => setToken("synthetic-second-user", 300)}>Second user</button><MonitorPage /></>;
}
const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); });

it("uses the current AuthProvider token for the first request after each identity change", async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Unavailable", details: {}, request_id: "synthetic" } }), { status: 404 }));
  vi.stubGlobal("fetch", fetcher);
  render(<QueryClientProvider client={client}><AuthProvider><LoginHarness /></AuthProvider></QueryClientProvider>);
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "First user" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(fetcher).toHaveBeenNthCalledWith(1, "/api/v1/forecasts/referrals/latest", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer synthetic-first-user" }) }));
  fireEvent.click(screen.getByRole("button", { name: "Second user" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(4));
  expect(fetcher).toHaveBeenNthCalledWith(3, "/api/v1/forecasts/referrals/latest", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer synthetic-second-user" }) }));
});
