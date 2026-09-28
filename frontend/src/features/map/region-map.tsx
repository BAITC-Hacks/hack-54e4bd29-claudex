"use client";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";

import { centerFor, pointLabel, volumeClass } from "./geography";

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
  const viewRef = useRef<{ center: [number, number]; zoom: number }>({ center: [48.3, 67.2], zoom: 4 });
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
      }).setView(viewRef.current.center, viewRef.current.zoom);
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);

      const maximum = Math.max(0, ...points.map((point) => point.value ?? 0));

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
          iconSize: [58, 36],
          iconAnchor: [29, 18],
        });
        const marker = L.marker(center, { icon, title: `${point.name}: ${label}` }).addTo(map);
        const tooltip = document.createElement("div");
        tooltip.textContent = `${point.name}: ${label}`;
        marker.bindTooltip(tooltip, { className: "region-map-tooltip", direction: "top", offset: [0, -14] });
        marker.on("click", () => onSelect(point.id));
      });

      map.on("click", () => onSelect(null));
      window.setTimeout(() => map.invalidateSize(), 80);
    }
    void render().catch(() => { if (!disposed) setMapError(true); });
    return () => {
      disposed = true;
      if (mapRef.current) {
        const center = mapRef.current.getCenter();
        viewRef.current = { center: [center.lat, center.lng], zoom: mapRef.current.getZoom() };
      }
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [metric, onSelect, points, selectedRegionId]);

  if (mapError) return <p role="alert" className="p-6">Карта недоступна. Выберите регион в списке рядом с картой.</p>;
  return <div ref={nodeRef} className="h-full min-h-[520px] w-full" aria-label="Карта региональных показателей Казахстана" />;
}
