import { z } from "zod";

import { env } from "@/config/env";
import { errorResponseSchema } from "@/types/api";

/**
 * Единая точка обращения к API.
 *
 * Компоненты не вызывают fetch напрямую: здесь сосредоточены разбор
 * контракта ошибки, идентификатор запроса и подстановка токена.
 * Бизнес-логики здесь нет — только транспорт.
 */

/** Ошибка, разобранная по контракту API. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly httpStatus: number,
    readonly requestId: string | null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Требуется ли повторная аутентификация. */
  get isUnauthenticated(): boolean {
    return this.httpStatus === 401;
  }
}

export const REQUEST_ID_HEADER = "X-Request-ID";

/**
 * Поставщик токена доступа.
 *
 * В PHASE 1 токена нет: вход через Keycloak реализуется в PHASE 2.
 * Точка подключения объявлена заранее, чтобы появление аутентификации
 * не потребовало переписывать обращения к API.
 */
type TokenProvider = () => string | null;

let tokenProvider: TokenProvider = () => null;

export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  const parsed = errorResponseSchema.safeParse(payload);
  if (parsed.success) {
    const { code, message, details, request_id } = parsed.data.error;
    return new ApiError(code, message, response.status, request_id, details);
  }

  // Ответ не по контракту: чаще всего это прокси или сетевой посредник.
  return new ApiError(
    "UNEXPECTED_RESPONSE",
    "Сервер вернул неожиданный ответ",
    response.status,
    response.headers.get(REQUEST_ID_HEADER),
  );
}

/**
 * Выполнить запрос и проверить ответ схемой.
 *
 * @param path путь относительно базового адреса API
 * @param schema схема ожидаемого ответа
 */
export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const token = tokenProvider();
  const headers: Record<string, string> = { Accept: "application/json" };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    cache: "no-store",
  });

  // Готовность отвечает кодом 503 вместе с телом по контракту:
  // это состояние, а не отказ, поэтому тело разбирается как обычно.
  if (!response.ok && response.status !== 503) {
    throw await parseError(response);
  }

  const payload: unknown = await response.json();
  const parsed = schema.safeParse(payload);

  if (!parsed.success) {
    throw new ApiError(
      "CONTRACT_MISMATCH",
      "Ответ сервера не соответствует ожидаемому контракту",
      response.status,
      response.headers.get(REQUEST_ID_HEADER),
      { issues: parsed.error.issues },
    );
  }

  return parsed.data;
}
