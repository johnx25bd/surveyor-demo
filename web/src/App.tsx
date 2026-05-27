import { lazy, Suspense, useCallback, useState } from "react";

import { ChatPane } from "./components/ChatPane";
import { ChartRail } from "./components/ChartRail";
import { Topbar } from "./components/Topbar";
import { useSurveyor } from "./state/useSurveyor";

// MapLibre is ~800KB — the bulk of the bundle and only needed once a map renders. Lazy-load MapPane
// so it splits into its own chunk and stays off the initial load.
const MapPane = lazy(() => import("./components/MapPane").then((m) => ({ default: m.MapPane })));

export type Mood = "paper" | "dark";

export default function App() {
  const { state, ask } = useSurveyor();
  const [mood, setMood] = useState<Mood>("paper");

  // Shared interaction state: a GSS code hovered/selected in any pane highlights it in all of them.
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // One definition of the select-toggle, shared by map and chart (click a selected area to deselect).
  const toggleSelect = useCallback((code: string) => {
    setSelected((current) => (current === code ? null : code));
  }, []);

  return (
    <div className={`sv-app sv-mood--${mood}`}>
      <Topbar
        queryTitle={state.queryTitle}
        mood={mood}
        onToggleMood={() => setMood((m) => (m === "dark" ? "paper" : "dark"))}
      />
      <main className="sv-grid">
        <ChatPane state={state} onAsk={ask} />
        <Suspense fallback={<section className="sv-map" aria-label="Map" />}>
          <MapPane
            choropleth={state.choropleth}
            mood={mood}
            hovered={hovered}
            selected={selected}
            onHover={setHovered}
            onSelect={toggleSelect}
          />
        </Suspense>
        <ChartRail
          chart={state.chart}
          status={state.status}
          hovered={hovered}
          selected={selected}
          onHover={setHovered}
          onSelect={toggleSelect}
        />
      </main>
    </div>
  );
}
