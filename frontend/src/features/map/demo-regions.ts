import type { MapMetric, RegionPoint } from "./region-map";

/** Illustrative map-only values. Never use these as API results or dashboard KPIs. */
export const DEMO_MAP_REGIONS = [
  { id: "demo-astana", name: "Астана", code: "astana", waiting: 38, referrals: 94, refusals: 7 },
  { id: "demo-almaty", name: "Алматы", code: "almaty city", waiting: 52, referrals: 121, refusals: 9 },
  { id: "demo-shymkent", name: "Шымкент", code: "shymkent", waiting: 25, referrals: 72, refusals: 6 },
  { id: "demo-atyrau", name: "Атырауская область", code: "atyrau", waiting: 16, referrals: 43, refusals: 4 },
  { id: "demo-aktobe", name: "Актюбинская область", code: "aktobe", waiting: 22, referrals: 58, refusals: 5 },
  { id: "demo-karaganda", name: "Карагандинская область", code: "karaganda", waiting: 31, referrals: 81, refusals: 6 },
  { id: "demo-kostanay", name: "Костанайская область", code: "kostanay", waiting: 19, referrals: 47, refusals: 3 },
  { id: "demo-kyzylorda", name: "Кызылординская область", code: "kyzylorda", waiting: 14, referrals: 39, refusals: 4 },
  { id: "demo-pavlodar", name: "Павлодарская область", code: "pavlodar", waiting: 17, referrals: 44, refusals: 3 },
  { id: "demo-east", name: "Восточно-Казахстанская область", code: "east kazakhstan", waiting: 23, referrals: 61, refusals: 5 },
  { id: "demo-west", name: "Западно-Казахстанская область", code: "west kazakhstan", waiting: 15, referrals: 42, refusals: 3 },
  { id: "demo-mangystau", name: "Мангистауская область", code: "mangystau", waiting: 21, referrals: 55, refusals: 4 },
] as const;

export function demoMapPoints(metric: MapMetric): RegionPoint[] {
  return DEMO_MAP_REGIONS.map((region) => ({
    id: region.id,
    name: region.name,
    code: region.code,
    value: region[metric],
    state: "ready",
  }));
}
