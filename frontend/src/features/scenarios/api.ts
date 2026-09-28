import { apiRequest } from "@/services/api-client";
import {
  scenarioResponseSchema,
  type ScenarioRequest,
  type ScenarioResult,
} from "@/features/scenarios/types";

export function previewScenario(payload: ScenarioRequest): Promise<ScenarioResult> {
  return apiRequest("/scenarios/preview", scenarioResponseSchema, {
    method: "POST",
    body: payload,
  });
}

export function saveScenario(
  payload: ScenarioRequest & { client_request_id: string },
): Promise<ScenarioResult> {
  return apiRequest("/scenarios", scenarioResponseSchema, {
    method: "POST",
    body: payload,
  });
}
