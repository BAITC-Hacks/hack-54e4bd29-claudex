import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, apiRequest } from "@/services/api-client";

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
});
