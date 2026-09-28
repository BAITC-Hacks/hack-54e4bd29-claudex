import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopilotEntry } from "@/features/copilot/copilot-entry";
import { syntheticCopilotResponse } from "@/features/copilot/test-fixtures";
import { setTokenProvider } from "@/services/api-client";

const auth = vi.hoisted(() => ({ accessToken: "synthetic-session-A" as string | null, login: vi.fn() }));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ accessToken: auth.accessToken, isAuthenticated: auth.accessToken !== null, login: auth.login }),
}));

const signal = {
  id: syntheticCopilotResponse.signal_id,
  version: syntheticCopilotResponse.signal_version,
  title: "Синтетический сигнал",
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function errorResponse(code: string, status: number): Response {
  return response({ error: { code, message: "private provider detail", details: {}, request_id: "safe-rid" } }, status);
}

beforeEach(() => {
  auth.accessToken = "synthetic-session-A";
  auth.login.mockReset();
  setTokenProvider(() => auth.accessToken);
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute("open");
      this.dispatchEvent(new Event("close"));
    },
  });
});

afterEach(() => {
  setTokenProvider(() => null);
  vi.unstubAllGlobals();
});

describe("CopilotEntry", () => {
  it("does not call the paid endpoint until click; one click makes one request", async () => {
    let finish!: (value: Response) => void;
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CopilotEntry signal={signal} />);
    expect(screen.getByText("Пояснение на основе показателей выбранного сигнала")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(screen.getByRole("dialog", { name: "AI-пояснение" })).toBeInTheDocument();
    expect(screen.getByText("Формируем пояснение…")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const options = fetchMock.mock.calls[0]?.[1];
    expect(options?.body).toBe(JSON.stringify({ signal_id: signal.id }));

    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { finish(response(syntheticCopilotResponse)); });
    expect(screen.getByText(syntheticCopilotResponse.explanation)).toBeInTheDocument();
    expect(screen.getByText("Синтетическая демонстрация")).toBeInTheDocument();
    expect(screen.getByText(/21 % изменения/)).toBeInTheDocument();
    expect(screen.getByText("Источник: показатели сигнала")).toBeInTheDocument();
    expect(screen.getByText(/Исторические данные не являются текущей очередью/)).toBeInTheDocument();
    expect(screen.getByText(/Период наблюдения/)).toBeInTheDocument();
    expect(screen.getAllByText(/Неизвестно/).length).toBeGreaterThanOrEqual(2);
  });

  it("closes on Escape, returns focus and reopens without another paid request", async () => {
    const fetchMock = vi.fn(async () => response(syntheticCopilotResponse));
    vi.stubGlobal("fetch", fetchMock);
    render(<CopilotEntry signal={signal} />);
    const trigger = screen.getByRole("button", { name: "Объяснить сигнал" });
    fireEvent.click(trigger);
    await screen.findByText(syntheticCopilotResponse.explanation);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(syntheticCopilotResponse.explanation)).toBeInTheDocument();
  });

  it("does not render LLM text as HTML", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response({
      ...syntheticCopilotResponse,
      explanation: "<img src=x onerror=alert(1)> Синтетическое пояснение.",
    })));
    render(<CopilotEntry signal={signal} />);
    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(await screen.findByText(/<img src=x/)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("rejects a response for a different version and never regenerates automatically", async () => {
    const fetchMock = vi.fn(async () => response({ ...syntheticCopilotResponse, signal_version: 2 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CopilotEntry signal={signal} />);
    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(await screen.findByText(/Обновите карточку вручную/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(syntheticCopilotResponse.explanation)).not.toBeInTheDocument();
  });

  it("drops a late response after signal or session changes", async () => {
    let finish!: (value: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<CopilotEntry signal={signal} />);
    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    view.rerender(<CopilotEntry signal={{ ...signal, id: "22222222-2222-4222-8222-222222222222" }} />);
    await act(async () => { finish(response(syntheticCopilotResponse)); });
    expect(screen.queryByText(syntheticCopilotResponse.explanation)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    auth.accessToken = "synthetic-session-B";
    view.rerender(<CopilotEntry signal={signal} />);
    expect(screen.queryByText(syntheticCopilotResponse.explanation)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["COPILOT_DISABLED", 503, /AI-пояснение временно недоступно/i, false],
    ["COPILOT_PROVIDER_UNAVAILABLE", 503, /сервис временно недоступен/i, true],
    ["COPILOT_PROVIDER_TIMEOUT", 504, /время ожидания истекло/i, true],
    ["COPILOT_INSUFFICIENT_DATA", 422, /недостаточно данных/i, false],
    ["NOT_FOUND", 404, /сигнал недоступен/i, false],
    ["UNAUTHENTICATED", 401, /требуется вход/i, false],
    ["COPILOT_INVALID_RESPONSE", 502, /не прошёл проверку/i, false],
    ["COPILOT_RATE_LIMITED", 429, /лимит запросов/i, false],
  ])("maps %s to a safe UI state without automatic retry", async (code, status, message, canRetry) => {
    const fetchMock = vi.fn(async () => errorResponse(code as string, status as number));
    vi.stubGlobal("fetch", fetchMock);
    render(<CopilotEntry signal={signal} />);
    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(await screen.findByText(message as RegExp)).toBeInTheDocument();
    expect(screen.queryByText("private provider detail")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(Boolean(screen.queryByRole("button", { name: "Повторить вручную" }))).toBe(canRetry);
  });

  it("shows Retry-After without automatically retrying a paid rate-limited request", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      error: { code: "COPILOT_RATE_LIMITED", message: "private", details: {}, request_id: "rid" },
    }), { status: 429, headers: { "Retry-After": "30" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CopilotEntry signal={signal} />);
    fireEvent.click(screen.getByRole("button", { name: "Объяснить сигнал" }));
    expect(await screen.findByText(/30 секунд/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
