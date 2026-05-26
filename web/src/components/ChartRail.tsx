import { useEffect, useMemo, useState } from "react";

import { formatNum } from "../lib/format";
import { colourFor, DEFAULT_RAMP, GDV, quantileBreaks } from "../lib/palettes";
import type { ChartEncoding, TableDataset, ViewSpec } from "../lib/types";
import type { RunStatus } from "../state/useSurveyor";

const MAX_ROWS = 25;

interface Props {
  chart: ViewSpec | null;
  status: RunStatus;
  hovered: string | null;
  selected: string | null;
  onHover(code: string | null): void;
  onSelect(code: string): void;
}

interface Row {
  code: string;
  name: string;
  value: number;
  colour: string;
}

export function ChartRail({ chart, status, hovered, selected, onHover, onSelect }: Props) {
  const [table, setTable] = useState<TableDataset | null>(null);

  useEffect(() => {
    if (!chart) {
      setTable(null);
      return;
    }
    let cancelled = false;
    fetch(`/api/datasets/${chart.handle}`)
      .then((r) => r.json())
      .then((ds: TableDataset) => {
        if (!cancelled && ds.kind === "table") setTable(ds);
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  const rows = useMemo<Row[]>(() => {
    if (!table || !chart) return [];
    const enc = chart.encoding as ChartEncoding;
    const values = table.rows.map((r) => Number(r[enc.value_column])).filter(Number.isFinite);
    const breaks = quantileBreaks(values, 7);
    const ramp = GDV.sequential[DEFAULT_RAMP];
    return table.rows
      .map((r) => {
        const value = Number(r[enc.value_column]);
        return {
          code: String(r[table.key_column]),
          name: String(r[enc.label_column] ?? r[table.key_column]),
          value,
          colour: Number.isFinite(value) ? colourFor(value, breaks, ramp) : "#c9c2b4",
        };
      })
      .filter((r) => Number.isFinite(r.value))
      .sort((a, b) => b.value - a.value);
  }, [table, chart]);

  if (status === "running" && !chart) return <RailSkeleton />;
  if (rows.length === 0) return <RailEmpty />;

  const enc = chart!.encoding as ChartEncoding;
  const max = Math.max(...rows.map((r) => r.value));
  const shown = rows.slice(0, MAX_ROWS);
  const top = rows[0];

  return (
    <aside className="sv-rail" aria-label="Evidence">
      <div className="sv-card">
        <div className="sv-card-eyebrow">Summary</div>
        <div className="sv-stat-grid">
          <Stat n={String(rows.length)} label="areas ranked" />
          <Stat n={formatNum(top.value)} label={`highest · ${top.name}`} />
        </div>
        <div className="sv-card-foot">
          {enc.value_column} ranges {formatNum(rows[rows.length - 1].value)}–{formatNum(top.value)}.
        </div>
      </div>

      <div className="sv-card">
        <div className="sv-card-head">
          <div>
            <div className="sv-card-eyebrow">Ranked</div>
            <h3>{enc.title}</h3>
          </div>
          <span className="sv-chip">{enc.value_column}</span>
        </div>
        <ol className="sv-ranked">
          {shown.map((r, i) => (
            <li
              key={r.code}
              className={`sv-ranked-row${hovered === r.code ? " is-hover" : ""}${
                selected === r.code ? " is-selected" : ""
              }`}
              onMouseEnter={() => onHover(r.code)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onSelect(r.code)}
            >
              <span className="sv-ranked-rank">{i + 1}</span>
              <span className="sv-ranked-name" title={r.name}>
                {r.name}
              </span>
              <span className="sv-ranked-track">
                <span
                  className="sv-bar"
                  style={{ width: `${max > 0 ? (r.value / max) * 100 : 0}%`, background: r.colour }}
                />
              </span>
              <span className="sv-ranked-val">{formatNum(r.value)}</span>
            </li>
          ))}
        </ol>
        {rows.length > MAX_ROWS && (
          <div className="sv-card-foot">+{rows.length - MAX_ROWS} more not shown</div>
        )}
      </div>
    </aside>
  );
}

function Stat({ n, label }: { n: string; label: string }) {
  return (
    <div>
      <div className="sv-stat-n">{n}</div>
      <div className="sv-stat-l">{label}</div>
    </div>
  );
}

function RailEmpty() {
  return (
    <aside className="sv-rail" aria-label="Evidence">
      <div className="sv-rail-empty">
        <svg
          className="sv-rail-empty-icon"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M3 3v18h18M7 16l4-5 3 3 5-7" />
        </svg>
        <p>Charts and rankings from the agent's answer will appear here.</p>
      </div>
    </aside>
  );
}

function RailSkeleton() {
  return (
    <aside className="sv-rail" aria-label="Evidence">
      <div className="sv-card sv-card--skel">
        <div className="sv-skel-line" style={{ width: "40%" }} />
        <div className="sv-skel-bars">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="sv-skel-bar" style={{ width: `${90 - i * 12}%` }} />
          ))}
        </div>
      </div>
    </aside>
  );
}
