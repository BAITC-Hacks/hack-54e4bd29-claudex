import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { MapPanel } from "./map-panel";
import { pointLabel } from "./geography";
import type { RegionPoint } from "./region-map";

vi.mock("./region-map", () => ({
  RegionMap: ({ points }: { points: RegionPoint[] }) => (
    <div>{points.map((point) => <span key={point.id}>{pointLabel(point)}</span>)}</div>
  ),
}));

const base = {
  metric: "waiting" as const,
  onMetricChange: vi.fn(),
  apiPoints: [] as RegionPoint[],
  selectedRegionId: null,
  onSelectRegion: vi.fn(),
  apiValues: { referrals: null, waiting: null, refusals: null, organizations: 0 },
};

afterEach(() => vi.unstubAllEnvs());

it("shows synthetic provenance without a duplicate warning below the map", () => {
  vi.stubEnv("NEXT_PUBLIC_APP_ENV", "test");
  vi.stubEnv("NEXT_PUBLIC_SYNTHETIC_DEMO", "true");
  render(<MapPanel {...base} apiError={false} apiLoading={false} />);

  expect(screen.getByText(/Синтетические данные · исторический период · значения из API/)).toBeInTheDocument();
  expect(screen.queryByText(/Карта не показывает загрузку коек/)).not.toBeInTheDocument();
  expect(screen.queryByText(/не медицинский норматив/)).not.toBeInTheDocument();
});

it("reports API errors and loading without substituting invented values", () => {
  const { rerender } = render(<MapPanel {...base} apiError apiLoading={false} />);
  expect(screen.getByText("Данные карты временно недоступны")).toBeInTheDocument();
  expect(screen.queryByText("38")).not.toBeInTheDocument();
  rerender(<MapPanel {...base} apiError={false} apiLoading />);
  expect(screen.getByText("Загружаем регионы…")).toBeInTheDocument();
});

it("shows suppressed API points without replacing them with demo numbers", () => {
  render(<MapPanel {...base} apiError={false} apiLoading={false} apiPoints={[
    { id: "canonical-astana", name: "Астана", code: "KZ-ASTANA", value: null, state: "suppressed" },
  ]} />);
  expect(screen.getByText("Скрыто")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Демо-слой" })).not.toBeInTheDocument();
});
