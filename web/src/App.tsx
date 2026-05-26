import { useState } from "react";

import { ChatPane } from "./components/ChatPane";
import { ChartRail } from "./components/ChartRail";
import { MapPane } from "./components/MapPane";
import { Topbar } from "./components/Topbar";
import { useSurveyor } from "./state/useSurveyor";

export type Mood = "paper" | "dark";

export default function App() {
  const { state, ask } = useSurveyor();
  const [mood, setMood] = useState<Mood>("paper");

  // Shared interaction state: a GSS code hovered/selected in any pane highlights it in all of them.
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className={`sv-app sv-mood--${mood}`}>
      <Topbar
        queryTitle={state.queryTitle}
        mood={mood}
        onToggleMood={() => setMood((m) => (m === "dark" ? "paper" : "dark"))}
      />
      <main className="sv-grid">
        <ChatPane state={state} onAsk={ask} />
        <MapPane
          choropleth={state.choropleth}
          mood={mood}
          hovered={hovered}
          selected={selected}
          onHover={setHovered}
          onSelect={(code) => setSelected((s) => (s === code ? null : code))}
        />
        <ChartRail
          chart={state.chart}
          status={state.status}
          hovered={hovered}
          selected={selected}
          onHover={setHovered}
          onSelect={(code) => setSelected((s) => (s === code ? null : code))}
        />
      </main>
    </div>
  );
}
