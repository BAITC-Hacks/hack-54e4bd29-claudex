import { apiRequest } from "@/services/api-client";
import { copilotResponseSchema, type CopilotResponse } from "@/features/copilot/types";

/** One user-initiated request; no query cache, polling or automatic retry. */
export function fetchCopilotExplanation(signalId: string, signal?: AbortSignal): Promise<CopilotResponse> {
  return apiRequest("/copilot/explain-signal", copilotResponseSchema, {
    method: "POST",
    body: { signal_id: signalId },
    signal,
  });
}
