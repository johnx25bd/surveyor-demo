import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";

import type { Mood } from "../App";
import { formatNum } from "../lib/format";
import { classify, DEFAULT_RAMP, GDV } from "../lib/palettes";
import type { ChoroplethEncoding, GeoDataset, PointsEncoding, ViewSpec } from "../lib/types";

const GB_CENTER: [number, number] = [-2.4, 54.2];

interface Props {
  choropleth: ViewSpec | null;
  points: ViewSpec | null;
  mood: Mood;
  hovered: string | null;
  selected: string | null;
  onHover(code: string | null): void;
  onSelect(code: string): void;
}

// A reference point overlay (e.g. libraries) drawn over the choropleth, each footprint reduced to a
// representative point. Held in a ref so the once-bound styledata handler can re-add it after a swap.
interface PointOverlay {
  fc: FeatureCollection; // Point features carrying a `__label` property
  title: string;
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

interface Resolved {
  style: maplibregl.StyleSpecification;
  os: boolean; // true when the real OS vector basemap loaded, false when we fell back to a plain bg
}

function styleUrl(mood: Mood): string {
  return `/api/basemap/style.json?theme=${mood === "dark" ? "night" : "light"}`;
}

// A plain background so the choropleth always draws — even with no OS key, or if the basemap is down.
function fallbackStyle(mood: Mood): maplibregl.StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: "bg",
        type: "background",
        paint: { "background-color": mood === "dark" ? "#0d1117" : "#e9edf0" },
      },
    ],
  };
}

// MapLibre fetches tiles (and glyphs) from a Web Worker, which has no document base URL, so relative
// proxy URLs fail to parse there ("Failed to construct 'Request'"). Make them absolute against the
// page origin. (The style, sprite, etc. load on the main thread, so they tolerate relative URLs.)
function absolutize(style: maplibregl.StyleSpecification): maplibregl.StyleSpecification {
  const origin = window.location.origin;
  const abs = (u: string) => (u.startsWith("/") ? origin + u : u);
  for (const source of Object.values(style.sources ?? {})) {
    const s = source as { tiles?: string[] };
    if (Array.isArray(s.tiles)) s.tiles = s.tiles.map(abs);
  }
  if (typeof style.glyphs === "string") style.glyphs = abs(style.glyphs);
  return style;
}

async function resolveStyle(mood: Mood): Promise<Resolved> {
  // The style document serves without a key; the *tiles* don't. Probe the keyed tile endpoint so a
  // missing/invalid key falls back to a plain background (over which the choropleth still draws)
  // rather than loading an OS style whose sources 503 and never finish.
  try {
    const probe = await fetch("/api/basemap/vts");
    if (probe.ok) {
      const r = await fetch(styleUrl(mood));
      if (r.ok) return { style: absolutize((await r.json()) as maplibregl.StyleSpecification), os: true };
    }
  } catch {
    /* basemap unreachable — fall through to the plain background */
  }
  return { style: fallbackStyle(mood), os: false };
}

export function MapPane({ choropleth, points, mood, hovered, selected, onHover, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<Overlay | null>(null);
  const pointsRef = useRef<PointOverlay | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [legend, setLegend] = useState<Legend | null>(null);
  const [pointsTitle, setPointsTitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [basemapOn, setBasemapOn] = useState(true);

  // Live values behind refs so the once-bound map callbacks never read stale props.
  const moodRef = useRef(mood);
  const hoveredRef = useRef(hovered);
  const selectedRef = useRef(selected);
  const onHoverRef = useRef(onHover);
  const onSelectRef = useRef(onSelect);
  moodRef.current = mood;
  hoveredRef.current = hovered;
  selectedRef.current = selected;
  onHoverRef.current = onHover;
  onSelectRef.current = onSelect;

  // ---- Create the map once. Layer handlers are bound here (they tolerate a not-yet-added layer),
  // so re-adding the overlay after a basemap swap never stacks duplicate listeners. ----
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let map: maplibregl.Map | null = null;
    let disposed = false;

    void resolveStyle(moodRef.current).then(({ style, os }) => {
      if (disposed) return;
      setBasemapOn(os);
      map = new maplibregl.Map({
        container,
        style,
        center: GB_CENTER,
        zoom: 5.9,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      popupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
      mapRef.current = map;

      map.on("styledata", addOverlay);
      map.on("styledata", addPoints);
      map.on("mousemove", "choro-fill", handleMove);
      map.on("mouseleave", "choro-fill", handleLeave);
      map.on("click", "choro-fill", handleClick);
      // Registered after the choro handler so, when a point sits over a polygon, the point's popup
      // wins (MapLibre fires same-event layer listeners in registration order).
      map.on("mousemove", "lib-points", handlePointMove);
      map.on("mouseleave", "lib-points", handlePointLeave);
    });

    return () => {
      disposed = true;
      map?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Basemap theme swap. setStyle drops sources/layers; the styledata listener re-adds them. ----
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    void resolveStyle(mood).then(({ style, os }) => {
      if (cancelled) return;
      setBasemapOn(os);
      map.setStyle(style);
    });
    return () => {
      cancelled = true;
    };
  }, [mood]);

  // ---- A new choropleth view: fetch the dataset, classify it, paint, fit. ----
  useEffect(() => {
    const map = mapRef.current;
    if (!choropleth) {
      overlayRef.current = null;
      setLegend(null);
      if (map?.getSource("choro")) removeOverlay(map);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const ds: GeoDataset = await fetch(`/api/datasets/${choropleth.handle}`).then((r) => r.json());
        if (cancelled || ds.kind !== "geo") return;
        const valueCol = (choropleth.encoding as ChoroplethEncoding).value_column;
        const ramp = GDV.sequential[DEFAULT_RAMP];
        const feats = ds.features.features;
        const valueOf = (f: Feature) => Number(f.properties?.[valueCol]);
        const colour = classify(feats, valueOf, ramp);
        for (const f of feats) {
          f.properties = f.properties ?? {};
          (f.properties as Record<string, unknown>).__color = colour(f);
        }
        const values = feats.map(valueOf).filter(Number.isFinite);
        overlayRef.current = {
          fc: ds.features,
          keyProp: ds.key_property ?? "code",
          nameProp: ds.name_property,
          valueCol,
        };
        addOverlay();
        if (mapRef.current) fitTo(mapRef.current, ds.features);
        setLegend({
          title: (choropleth.encoding as ChoroplethEncoding).title,
          ramp,
          min: values.length ? Math.min(...values) : 0,
          max: values.length ? Math.max(...values) : 0,
        });
      } catch {
        /* a failed dataset fetch leaves the prior map in place; the chat shows the error */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [choropleth]);

  // ---- A reference point overlay (e.g. libraries): fetch, reduce each footprint to a point, draw. ----
  useEffect(() => {
    const map = mapRef.current;
    if (!points) {
      pointsRef.current = null;
      setPointsTitle(null);
      if (map?.getSource("points")) removePoints(map);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const ds: GeoDataset = await fetch(`/api/datasets/${points.handle}`).then((r) => r.json());
        if (cancelled || ds.kind !== "geo") return;
        const { label_column, title } = points.encoding as PointsEncoding;
        const pts: Feature[] = [];
        for (const f of ds.features.features) {
          const c = centroidOf(f.geometry);
          if (!c) continue;
          pts.push({
            type: "Feature",
            geometry: { type: "Point", coordinates: c },
            properties: { __label: String(f.properties?.[label_column] ?? title) },
          });
        }
        pointsRef.current = { fc: { type: "FeatureCollection", features: pts }, title };
        setPointsTitle(title);
        addPoints();
      } catch {
        /* a failed fetch leaves the prior overlay in place; the chat shows the error */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [points]);

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
          "line-color": moodRef.current === "dark" ? "#0d1117" : "#f4f0ea",
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
    // Clear all feature-state on the source, then set the current two — no need to track what was
    // set last (which also avoids a stale-id desync when the dataset changes under us).
    map.removeFeatureState({ source: "choro" });
    const h = hoveredRef.current;
    const s = selectedRef.current;
    if (h) map.setFeatureState({ source: "choro", id: h }, { hover: true });
    if (s) map.setFeatureState({ source: "choro", id: s }, { selected: true });
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

  // Add (or refresh) the point overlay above the choropleth. Bound to styledata, so it survives a
  // basemap swap; tolerates being called before the style is ready.
  function addPoints() {
    const map = mapRef.current;
    const p = pointsRef.current;
    if (!map || !p || !map.isStyleLoaded()) return;
    const src = map.getSource("points") as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(p.fc);
      return;
    }
    map.addSource("points", { type: "geojson", data: p.fc });
    map.addLayer({
      id: "lib-points",
      type: "circle",
      source: "points",
      paint: {
        "circle-radius": 5,
        "circle-color": moodRef.current === "dark" ? "#7ee0c8" : "#0b6e4f",
        "circle-stroke-color": moodRef.current === "dark" ? "#0d1117" : "#ffffff",
        "circle-stroke-width": 1.4,
        "circle-opacity": 0.95,
      },
    });
  }

  function handlePointMove(e: maplibregl.MapLayerMouseEvent) {
    const map = mapRef.current;
    const f = e.features?.[0];
    if (!map || !f) return;
    map.getCanvas().style.cursor = "pointer";
    const label = String(f.properties?.__label ?? "");
    popupRef.current
      ?.setLngLat(e.lngLat)
      .setHTML(`<div class="sv-popup-name">${escapeHtml(label)}</div>`)
      .addTo(map);
  }

  function handlePointLeave() {
    const map = mapRef.current;
    if (map) map.getCanvas().style.cursor = "";
    popupRef.current?.remove();
  }

  const title = legend?.title ?? (choropleth ? "Map" : "Map of Great Britain");

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
        {pointsTitle && (
          <div className="sv-legend">
            <div className="sv-legend-label">
              <span
                style={{
                  display: "inline-block",
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: mood === "dark" ? "#7ee0c8" : "#0b6e4f",
                  border: `1.4px solid ${mood === "dark" ? "#0d1117" : "#ffffff"}`,
                  marginRight: 6,
                  verticalAlign: "middle",
                }}
                aria-hidden="true"
              />
              {pointsTitle}
            </div>
          </div>
        )}
        {!basemapOn && (
          <div className="sv-map-note" role="note">
            Basemap unavailable — add an OS Data Hub key to show the OS vector basemap.
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

function removePoints(map: maplibregl.Map) {
  if (map.getLayer("lib-points")) map.removeLayer("lib-points");
  if (map.getSource("points")) map.removeSource("points");
}

// Representative point for a footprint: the centre of its coordinate bounding box. Good enough to
// place a marker at city scale, and cheap — no turf/centroid dependency.
function centroidOf(geometry: unknown): [number, number] | null {
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  walk(geometry, (lng, lat) => {
    minx = Math.min(minx, lng);
    miny = Math.min(miny, lat);
    maxx = Math.max(maxx, lng);
    maxy = Math.max(maxy, lat);
  });
  if (!Number.isFinite(minx)) return null;
  return [(minx + maxx) / 2, (miny + maxy) / 2];
}
