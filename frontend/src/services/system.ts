import { apiRequest } from "@/services/api-client";
import {
  healthResponseSchema,
  readinessResponseSchema,
  type HealthResponse,
  type ReadinessResponse,
} from "@/types/api";

/** Служебные обращения к API. Домен появляется в PHASE 2. */

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest("/health", healthResponseSchema, { signal });
}

export function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiRequest("/ready", readinessResponseSchema, { signal });
}
