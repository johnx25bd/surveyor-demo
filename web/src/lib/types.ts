// The wire contract, typed once. These mirror surveyor/agent/events.py (the SSE events) and
// surveyor/data/models.py (the dataset shapes behind a handle) exactly — keep them in lockstep.

import type { FeatureCollection } from "geojson";

// ---- SSE events (event name + JSON data) ---------------------------------------------------------

export interface StatusEvent {
  event: "status";
  data: { state: string };
}
export interface MessageEvent {
  event: "message";
  data: { text: string };
}
export interface ToolCallEvent {
  event: "tool_call";
  data: { id: string; name: string; input: Record<string, unknown> };
}
export interface ToolResultEvent {
  event: "tool_result";
  data: { id: string; descriptor: DatasetDescriptor };
}
export interface ViewEvent {
  event: "view";
  data: ViewSpec;
}
export interface ErrorEvent {
  event: "error";
  data: { message: string; tool_id?: string };
}
export interface DoneEvent {
  event: "done";
  data: { summary: string };
}

export type SurveyorEvent =
  | StatusEvent
  | MessageEvent
  | ToolCallEvent
  | ToolResultEvent
  | ViewEvent
  | ErrorEvent
  | DoneEvent;

// ---- View instructions (from the render tools) ---------------------------------------------------

export type ViewKind = "choropleth" | "chart" | "points";

export interface ChoroplethEncoding {
  value_column: string;
  title: string;
}
export interface ChartEncoding {
  value_column: string;
  label_column: string;
  kind: string;
  title: string;
}
export interface PointsEncoding {
  label_column: string; // feature property to label each point's popup
  title: string;
}

export interface ViewSpec {
  kind: ViewKind;
  handle: string;
  encoding: ChoroplethEncoding | ChartEncoding | PointsEncoding;
}

// ---- Descriptors (the small object the model sees; we get it in tool_result) ---------------------

export interface DatasetDescriptor {
  handle: string;
  kind: "geo" | "table";
  count: number;
  crs?: string;
  geometry_type?: string;
  bbox?: [number, number, number, number];
  key_column?: string;
  columns?: string[];
  sample?: Record<string, unknown>[];
}

// ---- Full datasets (from GET /api/datasets/{handle}) ---------------------------------------------

export interface GeoDataset {
  kind: "geo";
  features: FeatureCollection;
  crs: string;
  geometry_type: string;
  key_property: string | null;
  name_property: string | null;
}

export interface TableDataset {
  kind: "table";
  rows: Record<string, unknown>[];
  key_column: string;
  value_columns: string[];
}

export type Dataset = GeoDataset | TableDataset;
