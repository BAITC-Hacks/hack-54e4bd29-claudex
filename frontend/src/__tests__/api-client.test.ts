import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, apiRequest } from "@/services/api-client";
import { fetchReadiness } from "@/services/system";

/**
 * Клиент API разбирает контракт ошибки и проверяет ответ схемой.
 * Второе важно: расхождение контракта должно обнаруживаться сразу.
 */

afterEach(() => {
  vi.restoreAllMocks();
});

const schema = z.object({ value: z.string() });

function mockResponse(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    headers: new Headers({ "X-Request-ID": "abc123def456" }),
    json: async () => body,
  } as Response;
}

describe("apiRequest", () => {
  it("возвращает разобранный ответ", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => mockResponse({ value: "ok" })));
    await expect(apiRequest("/x", schema)).resolves.toEqual({ value: "ok" });
  });

  it("преобразует ответ об ошибке в ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(
          {
            error: {
              code: "NOT_FOUND",
              message: "Объект не найден",
              details: {},
              request_id: "abc123def456",
            },
          },
          404,
        ),
      ),
    );

    await expect(apiRequest("/x", schema)).rejects.toMatchObject({
      code: "NOT_FOUND",
      httpStatus: 404,
      requestId: "abc123def456",
    });
  });

  it("отклоняет ответ, не соответствующий контракту", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => mockResponse({ unexpected: true })),
    );

    await expect(apiRequest("/x", schema)).rejects.toBeInstanceOf(ApiError);
    await expect(apiRequest("/x", schema)).rejects.toMatchObject({
      code: "CONTRACT_MISMATCH",
    });
  });

  it("распознаёт отказ аутентификации", async () => {
    const error = new ApiError("UNAUTHENTICATED", "нет доступа", 401, null);
    expect(error.isUnauthenticated).toBe(true);
  });

  it("сохраняет контракт ошибки аналитики при HTTP 503", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse(
          {
            error: {
              code: "DEPENDENCY_UNAVAILABLE",
              message: "Аналитическое хранилище недоступно",
              details: {},
              request_id: "abc123def456",
            },
          },
          503,
        ),
      ),
    );

    await expect(apiRequest("/analytics/overview", schema)).rejects.toMatchObject({
      code: "DEPENDENCY_UNAVAILABLE",
      httpStatus: 503,
      requestId: "abc123def456",
    });
  });

  it("не выдаёт HTML 503 от прокси за ошибку API-контракта", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ...mockResponse(null, 503),
        json: async () => { throw new SyntaxError("Unexpected token '<'"); },
      })),
    );

    await expect(apiRequest("/analytics/overview", schema)).rejects.toMatchObject({
      code: "UNEXPECTED_RESPONSE",
      httpStatus: 503,
      requestId: "abc123def456",
    });
  });

  it("читает ответ о неготовности только у /ready", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        mockResponse({
          status: "not_ready",
          service: "MedSignal",
          version: "test",
          dependencies: [{
            name: "postgres",
            status: "down",
            required: true,
            latency_ms: null,
            reason: "unavailable",
          }],
        }, 503),
      ),
    );

    await expect(fetchReadiness()).resolves.toMatchObject({
      status: "not_ready",
      dependencies: [{ name: "postgres", status: "down" }],
    });
  });
});
