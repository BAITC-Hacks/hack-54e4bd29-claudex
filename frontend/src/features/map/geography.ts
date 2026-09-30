import type { RegionPoint } from "./region-map";

const CENTERS: Array<{ keys: string[]; lat: number; lng: number }> = [
  { keys: ["astana", "астана", "город астана", "г. астана"], lat: 51.17, lng: 71.43 },
  { keys: ["almaty city", "алматы", "город алматы", "г. алматы"], lat: 43.24, lng: 76.89 },
  { keys: ["shymkent", "шымкент"], lat: 42.32, lng: 69.59 },
  { keys: ["akmola", "акмолинская область"], lat: 52.0, lng: 69.1 },
  { keys: ["aktobe", "актюбинская область"], lat: 50.28, lng: 57.17 },
  { keys: ["almaty region", "алматинская область"], lat: 45.0, lng: 78.3 },
  { keys: ["atyrau", "атырауская область"], lat: 47.1, lng: 51.92 },
  { keys: ["west kazakhstan", "западно-казахстанская область"], lat: 50.7, lng: 51.5 },
  { keys: ["zhambyl", "жамбылская область"], lat: 44.2, lng: 72.0 },
  { keys: ["karaganda", "карагандинская область"], lat: 49.8, lng: 73.1 },
  { keys: ["kostanay", "костанайская область"], lat: 53.2, lng: 63.6 },
  { keys: ["kyzylorda", "кызылординская область"], lat: 45.0, lng: 64.8 },
  { keys: ["mangystau", "мангистауская область"], lat: 43.7, lng: 52.2 },
  { keys: ["pavlodar", "павлодарская область"], lat: 52.3, lng: 76.95 },
  { keys: ["north kazakhstan", "северо-казахстанская область"], lat: 54.9, lng: 69.2 },
  { keys: ["turkistan", "туркестанская область"], lat: 43.4, lng: 68.3 },
  { keys: ["east kazakhstan", "восточно-казахстанская область"], lat: 49.9, lng: 82.6 },
  { keys: ["abai", "абай", "область абай"], lat: 49.8, lng: 79.9 },
  { keys: ["zhetisu", "жетісу", "жетысу", "область жетісу", "область жетысу"], lat: 45.0, lng: 78.4 },
  { keys: ["ulytau", "ұлытау", "улытау", "область ұлытау", "область улытау"], lat: 48.0, lng: 67.8 },
];

export function centerFor(name: string, code: string): [number, number] | null {
  const values = [name.replace(/ \[синтетические данные\]$/i, ""), code]
    .map((value) => value.trim().toLowerCase());
  const center = CENTERS.find((item) => item.keys.some((key) => values.includes(key)));
  return center ? [center.lat, center.lng] : null;
}

export function volumeClass(value: number | null, maximum: number): string {
  if (value === null) return "empty";
  if (value === 0 || maximum === 0) return "volume-low";
  return value / maximum >= 0.67 ? "volume-high" : value / maximum >= 0.34 ? "volume-medium" : "volume-low";
}

export function pointLabel(point: RegionPoint): string {
  if (point.state === "error") return "Ошибка загрузки";
  if (point.state === "loading") return "Загрузка";
  if (point.state === "suppressed") return "Скрыто";
  return point.value === null ? "Нет данных" : point.value.toLocaleString("ru-RU");
}
