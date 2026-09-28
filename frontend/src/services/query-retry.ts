import { ApiError } from "@/services/api-client";

/** HTTP errors are final for this request; only transport failures are retried. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) return false;
  return failureCount < 2;
}
