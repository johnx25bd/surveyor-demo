import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";

import type { Mood } from "../App";
import { formatNum } from "../lib/format";
import { colourFor, DEFAULT_RAMP, GDV, quantileBreaks } from "../lib/palettes";
import type { ChoroplethEncoding, GeoDataset, ViewSpec } from "../lib/types";

const CLASSES = 7;
const GB_CENTER: [number, number] = [-2.4, 54.2];
const NODATA = "#c9c2b4";

interface Props {
  choropleth: ViewSpec | null;
  mood: Mood;
  hovered: string | null;
  selected: string | null;
  onHover(code: string | null): void;
  onSelect(code: string): void;
}

interface Overlay {
  fc: FeatureCollection;
  keyProp: string;
  nameProp: string | null;
  valueCol: string;
}

interface Legend {
  title: string;
  ramp: readonly string[];
  min: number;
  max: number;
}

function styleUrl(mood: Mood): string {
  return `/api/basemap/style.json?theme=${mood === "dark" ? "night" : "light"}`;
}

export function MapPane({ choropleth, mood, hovered, selected, onHover, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<Overlay | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const appliedRef = useRef<{ hover: string | null; selected: string | null }>({
    hover: null,
    selected: null,
  });
  const [legend, setLegend] = useState<Legend | null>(null);
  const [loading, setLoading] = useState(false);

  // Callbacks read live values through refs so the once-bound map handlers never go stale.
  const onHoverRef = useRef(onHover);
  const onSelectRef = useRef(onSelect);
  onHoverRef.current = onHover;
  onSelectRef.current = onSelect;

  // ---- Create the map once. Layer event handlers are bound here (they tolerate a not-yet-added
  // layer), so re-adding the overlay after a basemap swap never stacks duplicate listeners. ----
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl(mood),
      center: GB_CENTER,
      zoom: 5.1,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });

    map.on("styledata", addOverlay);
    map.on("mousemove", "choro-fill", handleMove);
    map.on("mouseleave", "choro-fill", handleLeave);
    map.on("click", "choro-fill", handleClick);

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Basemap theme swap. setStyle drops sources/layers; the styledata listener re-adds them. ----
  useEffect(() => {
    mapRef.current?.setStyle(styleUrl(mood));
  }, [mood]);

  // ---- A new choropleth view: fetch the dataset, classify it, paint, fit. ----
  useEffect(() => {
    const map = mapRef.current;
    if (!choropleth || !map) {
      overlayRef.current = null;
      setLegend(null);
      if (map?.getSource("choro")) removeOverlay(map);
      return;
    }
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const ds: GeoDataset = await fetch(`/api/datasets/${choropleth.handle}`).then((r) => r.json());
        if (cancelled || ds.kind !== "geo") return;
        const valueCol = (choropleth.encoding as ChoroplethEncoding).value_column;
        const ramp = GDV.sequential[DEFAULT_RAMP];
        const values = ds.features.features
          .map((f) => Number(f.properties?.[valueCol]))
          .filter(Number.isFinite);
        const breaks = quantileBreaks(values, CLASSES);
        for (const f of ds.features.features) {
          const v = Number(f.properties?.[valueCol]);
          f.properties = f.properties ?? {};
          f.properties.__color = Number.isFinite(v) ? colourFor(v, breaks, ramp) : NODATA;
        }
        overlayRef.current = {
          fc: ds.features,
          keyProp: ds.key_property ?? "code",
          nameProp: ds.name_property,
          valueCol,
        };
        addOverlay();
        fitTo(map, ds.features);
        setLegend({
          title: (choropleth.encoding as ChoroplethEncoding).title,
          ramp,
          min: values.length ? Math.min(...values) : 0,
          max: values.length ? Math.max(...values) : 0,
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [choropleth]);

  // ---- Mirror shared hovered/selected into MapLibre feature-state. ----
  useEffect(applyInteractionState, [hovered, selected]);

  function addOverlay() {
    const map = mapRef.current;
    const o = overlayRef.current;
    if (!map || !o || !map.isStyleLoaded()) return;

    const src = map.getSource("choro") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(o.fc);
    } else {
      map.addSource("choro", { type: "geojson", data: o.fc, promoteId: o.keyProp });
      map.addLayer({
        id: "choro-fill",
        type: "fill",
        source: "choro",
        paint: {
          "fill-color": ["get", "__color"],
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            0.96,
            ["boolean", ["feature-state", "selected"], false],
            0.96,
            0.78,
          ],
        } as never,
      });
      map.addLayer({
        id: "choro-line",
        type: "line",
        source: "choro",
        paint: {
          "line-color": mood === "dark" ? "#0d1117" : "#f4f0ea",
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            2.5,
            ["boolean", ["feature-state", "hover"], false],
            1.2,
            0.4,
          ],
        } as never,
      });
    }
    applyInteractionState();
  }

  function applyInteractionState() {
    const map = mapRef.current;
    const o = overlayRef.current;
    if (!map || !o || !map.getSource("choro")) return;
    const prev = appliedRef.current;
    if (prev.hover && prev.hover !== hovered) {
      map.setFeatureState({ source: "choro", id: prev.hover }, { hover: false });
    }
    if (prev.selected && prev.selected !== selected) {
      map.setFeatureState({ source: "choro", id: prev.selected }, { selected: false });
    }
    if (hovered) map.setFeatureState({ source: "choro", id: hovered }, { hover: true });
    if (selected) map.setFeatureState({ source: "choro", id: selected }, { selected: true });
    appliedRef.current = { hover: hovered, selected };
  }

  function handleMove(e: maplibregl.MapLayerMouseEvent) {
    const map = mapRef.current;
    const o = overlayRef.current;
    const f = e.features?.[0];
    if (!map || !o || !f) return;
    map.getCanvas().style.cursor = "pointer";
    const code = String(f.id);
    onHoverRef.current(code);
    const name = o.nameProp ? f.properties?.[o.nameProp] : code;
    const value = f.properties?.[o.valueCol];
    popupRef.current
      ?.setLngLat(e.lngLat)
      .setHTML(
        `<div class="sv-popup-name">${escapeHtml(String(name ?? code))}</div>` +
          `<div class="sv-popup-stat">${escapeHtml(o.valueCol)}: ${formatNum(value)}</div>`,
      )
      .addTo(map);
  }

  function handleLeave() {
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = "";
    onHoverRef.current(null);
    popupRef.current?.remove();
  }

  function handleClick(e: maplibregl.MapLayerMouseEvent) {
    const f = e.features?.[0];
    if (f) onSelectRef.current(String(f.id));
  }

  const title = legend?.title ?? (choropleth ? "Mapping result" : "Map of Great Britain");

  return (
    <section className="sv-map" aria-label="Map">
      <div className="sv-map-toolbar">
        <div className="sv-map-title">
          <span className="sv-map-eyebrow">{choropleth ? "Choropleth" : "Ordnance Survey"}</span>
          <span className="sv-map-h1">{title}</span>
        </div>
      </div>

      <div className="sv-map-body">
        <div className="sv-map-gl" ref={containerRef} />
        {loading && (
          <div className="sv-map-overlay">
            <div className="sv-map-loading">
              <div className="sv-spinner" aria-hidden="true" />
              <span>Drawing the map…</span>
            </div>
          </div>
        )}
      </div>

      <div className="sv-map-foot">
        {legend && (
          <div className="sv-legend">
            <div className="sv-legend-label">{legend.title}</div>
            <div className="sv-legend-ramp">
              {legend.ramp.map((c) => (
                <span key={c} style={{ background: c }} />
              ))}
            </div>
            <div className="sv-legend-scale">
              <span>{formatNum(legend.min)}</span>
              <span>{formatNum(legend.max)}</span>
            </div>
          </div>
        )}
        <div className="sv-map-attribution">
          Contains OS data © Crown copyright and database rights 2026 · ONS Open Geography © Crown
          copyright 2026
        </div>
      </div>
    </section>
  );
}

function fitTo(map: maplibregl.Map, fc: FeatureCollection) {
  const b = new maplibregl.LngLatBounds();
  for (const f of fc.features) walk(f.geometry, (lng, lat) => b.extend([lng, lat]));
  if (!b.isEmpty()) map.fitBounds(b, { padding: 48, duration: 700, maxZoom: 11 });
}

type Coord = number[] | Coord[];
function walk(geometry: unknown, add: (lng: number, lat: number) => void) {
  const g = geometry as { coordinates?: Coord } | null;
  if (!g?.coordinates) return;
  const recurse = (c: Coord) => {
    if (typeof c[0] === "number") add(c[0] as number, c[1] as number);
    else (c as Coord[]).forEach(recurse);
  };
  recurse(g.coordinates);
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

function removeOverlay(map: maplibregl.Map) {
  for (const id of ["choro-fill", "choro-line"]) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource("choro")) map.removeSource("choro");
}
