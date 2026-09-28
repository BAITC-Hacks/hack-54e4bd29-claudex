"use client";

import { useMutation } from "@tanstack/react-query";

import { previewScenario, saveScenario } from "@/features/scenarios/api";

export function useScenarioPreview() {
  return useMutation({ mutationFn: previewScenario });
}

export function useScenarioSave() {
  return useMutation({ mutationFn: saveScenario });
}
