import { apiRequest } from "@/services/api-client";
import {
  hospitalPageSchema,
  incidentSchema,
  regionPageSchema,
  signalDetailSchema,
  signalPageSchema,
  type Hospital,
  type Incident,
  type Page,
  type Region,
  type SignalDetail,
  type SignalListItem,
  type SignalStatus,
} from "@/types/domain";

/** Обращения к доменному API. Бизнес-правил здесь нет. */

export interface SignalQuery {
  page?: number;
  pageSize?: number;
  status?: SignalStatus | "";
  hospitalId?: string;
  regionId?: string;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function fetchRegions(signal?: AbortSignal): Promise<Page<Region>> {
  return apiRequest("/regions?page_size=100", regionPageSchema, { signal });
}

export function fetchHospitals(
  regionId?: string,
  signal?: AbortSignal,
): Promise<Page<Hospital>> {
  const query = buildQuery({ page_size: 100, region_id: regionId });
  return apiRequest(`/hospitals${query}`, hospitalPageSchema, { signal });
}

export function fetchSignals(
  query: SignalQuery,
  signal?: AbortSignal,
): Promise<Page<SignalListItem>> {
  const search = buildQuery({
    page: query.page ?? 1,
    page_size: query.pageSize ?? 20,
    status: query.status,
    hospital_id: query.hospitalId,
    region_id: query.regionId,
  });
  return apiRequest(`/signals${search}`, signalPageSchema, { signal });
}

export function fetchSignal(
  id: string,
  signal?: AbortSignal,
): Promise<SignalDetail> {
  return apiRequest(`/signals/${id}`, signalDetailSchema, { signal });
}

export function changeSignalStatus(params: {
  id: string;
  status: SignalStatus;
  version: number;
  reason: string;
}): Promise<SignalDetail> {
  return apiRequest(`/signals/${params.id}/status`, signalDetailSchema, {
    method: "PATCH",
    body: {
      status: params.status,
      version: params.version,
      reason: params.reason,
    },
  });
}

export type SignalDecision = "acknowledge" | "resolve" | "dismiss";

export function decideSignal(params: {
  id: string;
  decision: SignalDecision;
  version: number;
  reason: string;
}): Promise<SignalDetail> {
  return apiRequest(
    `/signals/${params.id}/${params.decision}`,
    signalDetailSchema,
    {
      method: "POST",
      body: { version: params.version, reason: params.reason },
    },
  );
}

export function createIncidentFromSignal(params: {
  signalId: string;
  signalVersion: number;
  title: string;
  description?: string;
}): Promise<Incident> {
  return apiRequest(`/signals/${params.signalId}/incidents`, incidentSchema, {
    method: "POST",
    body: {
      signal_version: params.signalVersion,
      title: params.title,
      description: params.description || null,
    },
  });
}
