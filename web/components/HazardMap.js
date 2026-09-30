"use client";
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

const COL = { critical: "#B3261E", high: "#E0781F", medium: "#D9A520", low: "#5E8C6A" };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export default function HazardMap({ layers }) {
  const ref = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled) return;

      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      if (ref.current && ref.current._leaflet_id) {
        ref.current._leaflet_id = null;
      }
      if (!ref.current || cancelled) return;

      const map = L.map(ref.current, { zoomAnimation: false }).setView([19.9, 86], 9);
      mapRef.current = map;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors", maxZoom: 18,
      }).addTo(map);

      const overlays = {}, groups = [];
      const add = (name, fc, opts) => {
        if (!fc?.features?.length) return;
        const g = L.geoJSON(fc, opts).addTo(map);
        overlays[name] = g; groups.push(g);
      };
      add("Storm surge", layers.surge, {
        style: (f) => ({ color: "#1A5FA8", weight: 1, fillColor: f.properties.zone === "coastal-inner" ? "#1A5FA8" : "#6FA8DC", fillOpacity: 0.45 }),
        onEachFeature: (f, l) => l.bindPopup(`Surge zone: ${esc(f.properties.zone)}<br>${esc(f.properties.surge_height_m)} m`),
      });
      add("Rainfall flood", layers.flood, {
        style: () => ({ color: "#1E8C84", weight: 1, fillColor: "#2AA198", fillOpacity: 0.35 }),
        onEachFeature: (f, l) => l.bindPopup(`Flood depth: ${esc(f.properties.flood_depth_m)} m`),
      });
      add("Infrastructure exposure", layers.exposure, {
        style: (f) => ({ color: COL[f.properties.exposure_level] || "#888", weight: 4 }),
        pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 8, color: "#fff", weight: 2, fillColor: COL[f.properties.exposure_level] || "#888", fillOpacity: 1 }),
        onEachFeature: (f, l) => {
          const p = f.properties;
          l.bindPopup(`<b>${esc(p.name)}</b><br>${esc(p.infra_type)} · ${esc(p.exposure_level)} (${esc(p.exposure_score)})`);
        },
      });
      L.control.layers(null, overlays, { collapsed: false }).addTo(map);
      if (groups.length) {
        const b = L.featureGroup(groups).getBounds();
        
        if (b.isValid()) map.fitBounds(b.pad(0.2), { animate: false });
      }
    })();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [layers]);

  return <div ref={ref} className="map" role="application" aria-label="Hazard map" />;
}