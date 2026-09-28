import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ScenarioResultCard,
  ScenarioWorkbench,
} from "@/features/scenarios/components/scenario-workbench";
import type { ScenarioResult } from "@/features/scenarios/types";

function renderWorkbench() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ScenarioWorkbench />
    </QueryClientProvider>,
  );
}

const result: ScenarioResult = {
  id: null,
  scenario_type: "REFERRAL_INFLOW_CHANGE",
  scope_type: "GLOBAL",
  region_id: null,
  hospital_id: null,
  created_by: null,
  source_signal_id: null,
  source_incident_id: null,
  baseline_type: "FORECAST",
  baseline_value: 100,
  baseline_period_start: "2025-04-01",
  baseline_period_end: "2025-04-07",
  assumption_value: 0.2,
  calculated_value: 120,
  delta_absolute: 20,
  delta_percent: 0.2,
  data_watermark: { import_id: "import-1" },
  forecast_id: "00000000-0000-0000-0000-000000000111",
  model_version: "forecast-v1",
  forecast_status: "VALID",
  baseline_freshness_status: "STALE",
  selected_model: "weekly_naive",
  forecast_generated_at: "2025-04-01T00:00:00Z",
  formula_version: "referral_inflow_change.v1",
  limitations_version: "scenario_limitations.ru.v1",
  limitations: [],
  historical: true,
  status: "COMPLETED",
  created_at: null,
};

describe("ScenarioWorkbench", () => {
  it("offers exactly four approved assumptions and shows the disclaimer", () => {
    renderWorkbench();

    for (const label of ["-20%", "-10%", "+10%", "+20%"] ) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "+15%" })).not.toBeInTheDocument();
    expect(screen.getByText(/Не является прогнозом или рекомендацией/)).toBeInTheDocument();
    expect(screen.queryByText(/дефицит мощности: 20/i)).not.toBeInTheDocument();
  });

  it("labels a stale valid forecast as historical", () => {
    render(<ScenarioResultCard result={result} />);

    expect(screen.getByText(/Исторический сценарный анализ/)).toBeInTheDocument();
    expect(screen.getByText(/baseline устарел/)).toBeInTheDocument();
    expect(screen.getByText(/Forecast: VALID/)).toBeInTheDocument();
    expect(screen.getAllByText("120").length).toBeGreaterThan(0);
  });
});
