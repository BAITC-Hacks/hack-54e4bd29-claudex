import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignalEvidence } from "@/features/signals/signal-evidence";
import type { SignalDetail } from "@/types/domain";

const detail = {
  id: "11111111-1111-1111-1111-111111111111",
  scope_type: "GLOBAL",
  region_id: null,
  hospital_id: null,
  hospital_name: null,
  type: "REFUSAL_SPIKE",
  severity: "HIGH",
  status: "NEW",
  source_type: "STATISTICAL",
  title: "Всплеск отказов",
  summary: "Текущий уровень выше исторического ориентира.",
  detected_at: "2026-09-17T10:00:00Z",
  evaluation_period_start: "2025-03-25",
  evaluation_period_end: "2025-03-31",
  assigned_user_id: null,
  version: 1,
  created_at: "2026-09-17T10:00:00Z",
  updated_at: "2026-09-17T10:00:00Z",
  forecast_id: null,
  incident_id: null,
  closed_reason: null,
  closed_at: null,
  closure_disposition: null,
  reference_period_start: "2025-01-28",
  reference_period_end: "2025-03-24",
  actual_value: 140,
  baseline_value: 100,
  delta_absolute: 40,
  delta_percent: 40,
  rule_code: "REFUSAL_SPIKE",
  rule_version: "v1",
  rule_config: { warning_pct: 20, high_pct: 35, critical_pct: 50 },
  evidence: { complete_days_only: true },
  source: "REFUSALS",
  data_watermark: { latest_import_id: "import-1" },
  data_current: true,
  available_transitions: ["IN_PROGRESS", "CLOSED"],
  explanation: null,
  actions: [],
  audit_history: [],
} satisfies SignalDetail;

describe("SignalEvidence", () => {
  it("shows global scope, rule provenance and analytical-policy caveat", () => {
    render(<SignalEvidence detail={detail} />);

    expect(screen.getByText("Вся система")).toBeInTheDocument();
    expect(screen.getByText("REFUSAL_SPIKE / v1")).toBeInTheDocument();
    expect(screen.getByText("40%", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/аналитическ/i)).toBeInTheDocument();
  });

  it("marks stale evidence explicitly", () => {
    render(<SignalEvidence detail={{ ...detail, data_current: false }} />);
    expect(screen.getByText(/данные неактуальны/i)).toBeInTheDocument();
  });
});
