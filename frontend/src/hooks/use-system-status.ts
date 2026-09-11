"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchHealth, fetchReadiness } from "@/services/system";
import type { HealthResponse, ReadinessResponse } from "@/types/api";

/**
 * Состояние системы для служебной страницы.
 *
 * Работа с серверным состоянием — через TanStack Query: кэш,
 * повторные попытки и обновление не пишутся вручную.
 */

export const systemQueryKeys = {
  health: ["system", "health"] as const,
  readiness: ["system", "readiness"] as const,
};

export function useHealth(): UseQueryResult<HealthResponse, Error> {
  return useQuery({
    queryKey: systemQueryKeys.health,
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: 30_000,
  });
}

export function useReadiness(): UseQueryResult<ReadinessResponse, Error> {
  return useQuery({
    queryKey: systemQueryKeys.readiness,
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: 15_000,
  });
}
