import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { buildForecastChartOption, ReferralForecastCard } from "@/features/forecasting/components/referral-forecast-card";
import { ApiError } from "@/services/api-client";
import type { ReferralForecast } from "@/features/forecasting/types";

vi.mock("echarts", () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
}));

const forecast: ReferralForecast = {
  id: "00000000-0000-0000-0000-000000000101",
  target: "DAILY_REFERRAL_COUNT",
  scope_type: "GLOBAL",
  horizon_days: 7,
  input_period_start: "2025-01-01T00:00:00Z",
  input_period_end: "2025-03-31T00:00:00Z",
  validation_period_start: "2025-02-12",
  validation_period_end: "2025-03-25",
  forecast_start: "2025-04-01",
  forecast_end: "2025-04-07",
  generated_at: "2025-04-01T10:00:00Z",
  model_version: "referrals-v1",
  selected_model: "weekly_naive",
  baseline_model: "weekly_naive",
  metrics: { mae: 12.3, wape: 0.04, rmse: 15.1 },
  baseline_metrics: { mae: 12.3, wape: 0.04, rmse: 15.1 },
  dataset_watermark: { import_ids: ["import-1"] },
  freshness_status: "STALE",
  limitations: ["Годовая сезонность не подтверждена."],
  historical: [{ date: "2025-03-31", value: 100 }],
  forecast: [{ date: "2025-04-01", predicted_value: 101, baseline_value: 100, delta_from_baseline: 1 }],
  disclaimer: "Расчётный прогноз. Решение принимает уполномоченный сотрудник.",
};

describe("ReferralForecastCard", () => {
  it("uses Kazakh legend and date labels in the forecast chart", () => {
    const labels: Record<string, string> = { "История": "Тарих", "Прогноз": "Болжам", "Простое сравнение": "Қарапайым салыстыру" };
    const option = buildForecastChartOption(forecast, "kk", (text) => labels[text] ?? text);
    expect(option).toEqual(expect.objectContaining({
      legend: { data: ["Тарих", "Болжам", "Қарапайым салыстыру"] },
      xAxis: expect.objectContaining({ data: expect.arrayContaining([expect.stringMatching(/нау/), expect.stringMatching(/сәу/)]) }),
    }));
  });

  it("shows persisted forecast provenance, baseline and limitation", () => {
    render(<ReferralForecastCard forecast={forecast} isLoading={false} error={null} isSyntheticDemo />);

    expect(screen.getByText("Краткосрочный прогноз потока направлений")).toBeInTheDocument();
    expect(screen.getByText(/weekly_naive/)).toBeInTheDocument();
    expect(screen.getByText(/Годовая сезонность не подтверждена\./)).toBeInTheDocument();
    expect(screen.getByText(forecast.disclaimer)).toBeInTheDocument();
    expect(screen.getByText(/Историческая валидация прогноза/)).toBeInTheDocument();
    expect(screen.getByText(/Прогноз на синтетических демонстрационных данных/)).toBeInTheDocument();
    expect(screen.getByText(/Историческая валидация модели/)).toBeInTheDocument();
    expect(screen.getByText(/MAE модели: 12,3 направлений\/день/)).toBeInTheDocument();
    expect(screen.getByText(/MAE baseline: 12,3 направлений\/день/)).toBeInTheDocument();
    expect(screen.getByText(/Идентификатор прогноза:/)).toBeInTheDocument();
    expect(screen.getByText(/Источник: ИС БГ/)).toBeInTheDocument();
    expect(screen.getByText(/Исходные данные:/)).toBeInTheDocument();
    expect(screen.getByText(/Период оценки:/)).toBeInTheDocument();
    expect(screen.getByText(/Целевой показатель: ежедневное число направлений/i)).toBeInTheDocument();
    expect(screen.getByText(/Область: вся система \(GLOBAL\)/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Как читать прогноз" })).toBeInTheDocument();
    expect(screen.getByText(/MAE показывает среднюю абсолютную ошибку на исторической временной проверке/i)).toBeInTheDocument();
    expect(screen.getByText(/не является прогнозом свободных коек, даты выписки или медицинской рекомендацией/i)).toBeInTheDocument();
    expect(screen.queryByText(/перегрузк/i)).not.toBeInTheDocument();
  });

  it("shows an explicit unavailable state instead of a zero forecast", () => {
    render(<ReferralForecastCard forecast={undefined} isLoading={false} error={new ApiError("NOT_FOUND", "Not found", 404, null)} />);

    expect(screen.getByText(/Прогноз пока недоступен/)).toBeInTheDocument();
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });

  it("distinguishes a transport error from an unpublished forecast", () => {
    render(<ReferralForecastCard forecast={undefined} isLoading={false} error={new Error("Network failed")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось загрузить прогноз");
    expect(screen.queryByText(/Прогноз пока недоступен/)).not.toBeInTheDocument();
  });

  it("shows a loading state", () => {
    render(<ReferralForecastCard forecast={undefined} isLoading error={null} />);
    expect(screen.getByText("Загрузка сохранённого прогноза…")).toBeInTheDocument();
  });
});
