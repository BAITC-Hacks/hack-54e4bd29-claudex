"use client";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef } from "react";

export type MapMetric = "waiting" | "referrals" | "refusals";

export interface RegionPoint {
  id: string;
  name: string;
  code: string;
  value: number | null;
}

const CENTERS: Array<{ keys: string[]; lat: number; lng: number }> = [
  { keys: ["astana", "астана"], lat: 51.17, lng: 71.43 },
  { keys: ["almaty city", "город алматы", "г. алматы"], lat: 43.24, lng: 76.89 },
  { keys: ["shymkent", "шымкент"], lat: 42.32, lng: 69.59 },
  { keys: ["akmola", "акмол"], lat: 52.0, lng: 69.1 },
  { keys: ["aktobe", "актюб"], lat: 50.28, lng: 57.17 },
  { keys: ["almaty", "алматин"], lat: 45.0, lng: 78.3 },
  { keys: ["atyrau", "атырау"], lat: 47.1, lng: 51.92 },
  { keys: ["west kazakhstan", "западно-казахстан"], lat: 50.7, lng: 51.5 },
  { keys: ["zhambyl", "жамбыл"], lat: 44.2, lng: 72.0 },
  { keys: ["karaganda", "караганд"], lat: 49.8, lng: 73.1 },
  { keys: ["kostanay", "костан"], lat: 53.2, lng: 63.6 },
  { keys: ["kyzylorda", "кызылорд"], lat: 45.0, lng: 64.8 },
  { keys: ["mangystau", "мангист"], lat: 43.7, lng: 52.2 },
  { keys: ["pavlodar", "павлодар"], lat: 52.3, lng: 76.95 },
  { keys: ["north kazakhstan", "северо-казахстан"], lat: 54.9, lng: 69.2 },
  { keys: ["turkistan", "туркестан"], lat: 43.4, lng: 68.3 },
  { keys: ["east kazakhstan", "восточно-казахстан"], lat: 49.9, lng: 82.6 },
  { keys: ["abai", "абай"], lat: 49.8, lng: 79.9 },
  { keys: ["zhetisu", "жетісу", "жетысу"], lat: 45.0, lng: 78.4 },
  { keys: ["ulytau", "ұлытау", "улытау"], lat: 48.0, lng: 67.8 },
];

function centerFor(name: string, code: string): [number, number] | null {
  const value = `${name} ${code}`.toLowerCase();
  // Города республиканского значения проверяются до одноимённых областей.
  const center = CENTERS.find((item) => item.keys.some((key) => value.includes(key)));
  return center ? [center.lat, center.lng] : null;
}

function statusFor(value: number | null, thresholds: [number, number]): "empty" | "normal" | "warning" | "critical" {
  if (value === null || value === 0) return "empty";
  if (value >= thresholds[1]) return "critical";
  if (value >= thresholds[0]) return "warning";
  return "normal";
}

export function RegionMap({
  points,
  metric,
  selectedRegionId,
  onSelect,
}: {
  points: RegionPoint[];
  metric: MapMetric;
  selectedRegionId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  useEffect(() => {
    let disposed = false;
    async function render() {
      if (!nodeRef.current) return;
      const L = await import("leaflet");
      if (disposed || !nodeRef.current) return;
      mapRef.current?.remove();

      const map = L.map(nodeRef.current, {
        minZoom: 3,
        maxZoom: 9,
        zoomControl: false,
        scrollWheelZoom: true,
      }).setView([48.3, 67.2], 4);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);

      const values = points.map((point) => point.value ?? 0).filter((value) => value > 0).sort((a, b) => a - b);
      const at = (share: number) => values[Math.min(values.length - 1, Math.floor(values.length * share))] ?? Number.POSITIVE_INFINITY;
      const thresholds: [number, number] = [at(0.5), at(0.8)];

      points.forEach((point) => {
        const center = centerFor(point.name, point.code);
        if (!center) return;
        const status = statusFor(point.value, thresholds);
        const selected = point.id === selectedRegionId ? " selected" : "";
        const label = point.value === null ? "—" : point.value.toLocaleString("ru-RU");
        const icon = L.divIcon({
          className: "region-marker-shell",
          html: `<div class="region-marker ${status}${selected}"><span></span><b>${label}</b></div>`,
          iconSize: [58, 36],
          iconAnchor: [29, 18],
        });
        const marker = L.marker(center, { icon, title: point.name }).addTo(map);
        marker.bindTooltip(`<strong>${point.name}</strong><span>${label}</span>`, {
          className: "region-map-tooltip",
          direction: "top",
          offset: [0, -14],
        });
        marker.on("click", () => onSelect(point.id));
      });

      map.on("click", () => onSelect(null));
      window.setTimeout(() => map.invalidateSize(), 80);
    }
    void render();
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [metric, onSelect, points, selectedRegionId]);

  return <div ref={nodeRef} className="h-full min-h-[520px] w-full" aria-label="Карта региональных показателей Казахстана" />;
}
