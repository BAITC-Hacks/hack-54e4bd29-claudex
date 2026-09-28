"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  changeSignalStatus,
  createIncidentFromSignal,
  decideSignal,
  fetchHospitals,
  fetchRegions,
  fetchSignal,
  fetchSignals,
  type SignalDecision,
  type SignalQuery,
} from "@/services/domain";
import type {
  Hospital,
  Incident,
  Page,
  Region,
  SignalDetail,
  SignalListItem,
  SignalStatus,
} from "@/types/domain";

/** Работа с серверным состоянием через TanStack Query. */

export const domainKeys = {
  regions: ["regions"] as const,
  hospitals: (regionId?: string) => ["hospitals", regionId ?? "all"] as const,
  signals: (query: SignalQuery) => ["signals", query] as const,
  signal: (id: string) => ["signals", id] as const,
};

export function useRegions(
  enabled: boolean,
): UseQueryResult<Page<Region>, Error> {
  return useQuery({
    queryKey: domainKeys.regions,
    queryFn: ({ signal }) => fetchRegions(signal),
    enabled,
  });
}

function refreshSignals(
  queryClient: ReturnType<typeof useQueryClient>,
  id: string,
  detail: SignalDetail,
): void {
  queryClient.setQueryData(domainKeys.signal(id), detail);
  void queryClient.invalidateQueries({ queryKey: ["signals"] });
}

export function useHospitals(
  enabled: boolean,
  regionId?: string,
): UseQueryResult<Page<Hospital>, Error> {
  return useQuery({
    queryKey: domainKeys.hospitals(regionId),
    queryFn: ({ signal }) => fetchHospitals(regionId, signal),
    enabled,
  });
}

export function useSignals(
  enabled: boolean,
  query: SignalQuery,
): UseQueryResult<Page<SignalListItem>, Error> {
  return useQuery({
    queryKey: domainKeys.signals(query),
    queryFn: ({ signal }) => fetchSignals(query, signal),
    enabled,
  });
}

export function useSignal(
  enabled: boolean,
  id: string,
): UseQueryResult<SignalDetail, Error> {
  return useQuery({
    queryKey: domainKeys.signal(id),
    queryFn: ({ signal }) => fetchSignal(id, signal),
    enabled,
  });
}

export function useChangeSignalStatus(
  id: string,
): UseMutationResult<
  SignalDetail,
  Error,
  { status: SignalStatus; version: number; reason: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => changeSignalStatus({ id, ...input }),
    onSuccess: (detail) => {
      // Ответ уже содержит актуальную карточку вместе с новой версией:
      // повторный запрос не нужен.
      refreshSignals(queryClient, id, detail);
    },
  });
}


export function useSignalDecision(
  id: string,
): UseMutationResult<
  SignalDetail,
  Error,
  { decision: SignalDecision; version: number; reason: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => decideSignal({ id, ...input }),
    onSuccess: (detail) => refreshSignals(queryClient, id, detail),
  });
}

export function useCreateIncident(
  signalId: string,
): UseMutationResult<
  Incident,
  Error,
  { signalVersion: number; title: string; description?: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => createIncidentFromSignal({ signalId, ...input }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: domainKeys.signal(signalId) });
      void queryClient.invalidateQueries({ queryKey: ["signals"] });
    },
  });
}
