import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemStatusPanel } from "@/features/system-status/system-status-panel";

/**
 * Дымовой тест фундамента: панель отображает состояние, полученное
 * от API, и корректно ведёт себя при его недоступности.
 */

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

function mockJson(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    headers: new Headers(),
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SystemStatusPanel", () => {
  it("показывает состояние приложения и зависимостей", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/health")) {
          return mockJson({
            status: "ok",
            service: "medsignal",
            version: "0.1.0",
            environment: "local",
          });
        }
        return mockJson({
          status: "ready",
          service: "medsignal",
          version: "0.1.0",
          dependencies: [
            {
              name: "postgres",
              status: "up",
              required: true,
              latency_ms: 3.2,
              reason: null,
            },
          ],
        });
      }),
    );

    renderWithClient(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByText("работает")).toBeInTheDocument();
    });
    expect(screen.getByText("готов")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("доступна")).toBeInTheDocument();
  });

  it("сообщает о недоступности API вместо пустого экрана", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );

    renderWithClient(<SystemStatusPanel />);

    await waitFor(() => {
      expect(screen.getByText("API недоступен")).toBeInTheDocument();
    });
  });
});
