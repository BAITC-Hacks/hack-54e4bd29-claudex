"use client";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";

import { centerFor, pointLabel, volumeClass } from "./geography";
import { KAZAKHSTAN_BORDER } from "./kazakhstan-boundary";

export type MapMetric = "waiting" | "referrals" | "refusals";

export interface RegionPoint {
  id: string;
  name: string;
  code: string;
  value: number | null;
  state?: "ready" | "error" | "loading" | "suppressed";
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
  const [mapError, setMapError] = useState(false);
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
        zoomControl: false,
        attributionControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
        touchZoom: false,
      });
      mapRef.current = map;
      const outline = L.polygon(
        KAZAKHSTAN_BORDER.map(([longitude, latitude]) => [latitude, longitude] as [number, number]),
        { color: "#087c86", fillColor: "#c6e9e6", fillOpacity: 1, weight: 2.5, interactive: false },
      ).addTo(map);
      map.fitBounds(outline.getBounds(), { padding: [24, 24], animate: false });

      const maximum = Math.max(0, ...points.map((point) => point.value ?? 0));
      const compactMarkers = window.innerWidth <= 640;

      points.forEach((point) => {
        const center = centerFor(point.name, point.code);
        if (!center) return;
        const status = volumeClass(point.value, maximum);
        const selected = point.id === selectedRegionId ? " selected" : "";
        const label = pointLabel(point);
        const markerLabel = point.value === null ? point.state === "loading" ? "…" : point.state === "error" ? "!" : "—" : label;
        const icon = L.divIcon({
          className: "region-marker-shell",
          html: `<div class="region-marker ${status}${selected}"><span></span><b>${markerLabel}</b></div>`,
          iconSize: compactMarkers ? [16, 16] : [58, 36],
          iconAnchor: compactMarkers ? [8, 8] : [29, 18],
        });
        const marker = L.marker(center, { icon, title: `${point.name}: ${label}` }).addTo(map);
        const tooltip = document.createElement("div");
        tooltip.textContent = `${point.name}: ${label}`;
        marker.bindTooltip(tooltip, { className: "region-map-tooltip", direction: "top", offset: [0, -14] });
        marker.on("click", () => onSelect(point.id));
      });

      map.on("click", () => onSelect(null));
      window.setTimeout(() => {
        if (disposed) return;
        map.invalidateSize();
        map.fitBounds(outline.getBounds(), { padding: [24, 24], animate: false });
      }, 80);
    }
    void render().catch(() => { if (!disposed) setMapError(true); });
    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [metric, onSelect, points, selectedRegionId]);

  if (mapError) return <p role="alert" className="p-6">Карта недоступна. Выберите регион в списке рядом с картой.</p>;
  return <div ref={nodeRef} className="h-full min-h-[360px] w-full" aria-label="Карта региональных показателей Казахстана" />;
}
