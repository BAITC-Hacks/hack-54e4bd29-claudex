import { z } from "zod";

/**
 * Контракты ответов API.
 *
 * Описаны схемами, а не только типами: ответ сервера проверяется
 * во время выполнения. Расхождение контракта обнаруживается сразу
 * и с понятным сообщением, а не превращается в ошибку доступа
 * к свойству где-то в компоненте.
 */

export const errorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.unknown()).default({}),
    request_id: z.string().nullable(),
  }),
});

export type ErrorResponse = z.infer<typeof errorResponseSchema>;

export const healthResponseSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;

export const dependencyStatusSchema = z.object({
  name: z.string(),
  status: z.enum(["up", "down", "skipped"]),
  required: z.boolean(),
  latency_ms: z.number().nullable(),
  reason: z.string().nullable(),
});

export type DependencyStatus = z.infer<typeof dependencyStatusSchema>;

export const readinessResponseSchema = z.object({
  status: z.enum(["ready", "not_ready"]),
  service: z.string(),
  version: z.string(),
  dependencies: z.array(dependencyStatusSchema),
});

export type ReadinessResponse = z.infer<typeof readinessResponseSchema>;

export const operationStatusSchema = z.enum([
  "PENDING",
  "RUNNING",
  "COMPLETED",
  "FAILED",
]);

export type OperationStatus = z.infer<typeof operationStatusSchema>;

export const securityContextSchema = z.object({
  user_id: z.string(),
  username: z.string().nullable(),
  roles: z.array(z.string()),
  region_ids: z.array(z.string()),
  hospital_ids: z.array(z.string()),
  has_global_scope: z.boolean(),
  scope_resolved: z.boolean(),
});

export type SecurityContext = z.infer<typeof securityContextSchema>;
