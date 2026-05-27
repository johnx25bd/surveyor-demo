// The single source of UI truth: a reducer that folds the SSE event stream into render state, plus
// an ask() that opens the stream. Each query is independent — the backend /api/query is single-shot
// (no server-side history), so a new question replaces the transcript rather than appending a turn.

import { useCallback, useReducer, useRef } from "react";

import { streamQuery, type StreamHandle } from "../lib/stream";
import type { DatasetDescriptor, SurveyorEvent, ViewSpec } from "../lib/types";

export type RunStatus = "idle" | "running" | "done" | "error";

export type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; streaming: boolean }
  | {
      kind: "tool";
      id: string;
      name: string;
      input: Record<string, unknown>;
      status: "running" | "done" | "error";
      descriptor?: DatasetDescriptor;
      error?: string;
    }
  | { kind: "error"; message: string };

export interface SurveyorState {
  status: RunStatus;
  statusLabel: string | null; // the agent's current status verb ("thinking", …)
  queryTitle: string | null;
  items: ChatItem[];
  choropleth: ViewSpec | null;
  chart: ViewSpec | null;
  points: ViewSpec | null; // a reference point overlay (e.g. libraries), drawn over the choropleth
}

const INITIAL: SurveyorState = {
  status: "idle",
  statusLabel: null,
  queryTitle: null,
  items: [],
  choropleth: null,
  chart: null,
  points: null,
};

type Action = { type: "ask"; question: string } | { type: "event"; event: SurveyorEvent } | { type: "close" };

/** Seal any trailing streaming assistant block so the next text starts a fresh paragraph. */
function seal(items: ChatItem[]): ChatItem[] {
  const last = items[items.length - 1];
  if (last && last.kind === "assistant" && last.streaming) {
    return [...items.slice(0, -1), { ...last, streaming: false }];
  }
  return items;
}

function reducer(state: SurveyorState, action: Action): SurveyorState {
  if (action.type === "ask") {
    return {
      ...INITIAL,
      status: "running",
      statusLabel: "thinking",
      queryTitle: action.question,
      items: [{ kind: "user", text: action.question }],
    };
  }

  if (action.type === "close") {
    // Transport closed; if the loop never sent `done`, settle the status anyway.
    return state.status === "running"
      ? { ...state, status: "done", statusLabel: null, items: seal(state.items) }
      : state;
  }

  const { event, data } = action.event;
  switch (event) {
    case "status":
      return { ...state, statusLabel: data.state };

    case "message": {
      const items = [...state.items];
      const last = items[items.length - 1];
      if (last && last.kind === "assistant" && last.streaming) {
        items[items.length - 1] = { ...last, text: last.text + data.text };
      } else {
        items.push({ kind: "assistant", text: data.text, streaming: true });
      }
      return { ...state, items };
    }

    case "tool_call":
      return {
        ...state,
        items: [
          ...seal(state.items),
          { kind: "tool", id: data.id, name: data.name, input: data.input, status: "running" },
        ],
      };

    case "tool_result":
      return {
        ...state,
        items: state.items.map((it) =>
          it.kind === "tool" && it.id === data.id
            ? { ...it, status: "done", descriptor: data.descriptor }
            : it,
        ),
      };

    case "view":
      if (data.kind === "choropleth") return { ...state, choropleth: data };
      if (data.kind === "chart") return { ...state, chart: data };
      if (data.kind === "points") return { ...state, points: data };
      return state; // unknown view kind: ignore rather than mis-route it to the chart

    case "error": {
      if (data.tool_id) {
        return {
          ...state,
          items: state.items.map((it) =>
            it.kind === "tool" && it.id === data.tool_id
              ? { ...it, status: "error", error: data.message }
              : it,
          ),
        };
      }
      return { ...state, items: [...seal(state.items), { kind: "error", message: data.message }] };
    }

    case "done":
      return { ...state, status: "done", statusLabel: null, items: seal(state.items) };

    default:
      return state;
  }
}

export function useSurveyor() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const handle = useRef<StreamHandle | null>(null);

  const ask = useCallback((question: string) => {
    const q = question.trim();
    if (!q) return;
    handle.current?.cancel();
    dispatch({ type: "ask", question: q });
    handle.current = streamQuery(q, {
      onEvent: (event) => dispatch({ type: "event", event }),
      onClose: () => dispatch({ type: "close" }),
      onError: (message) =>
        dispatch({ type: "event", event: { event: "error", data: { message } } }),
    });
  }, []);

  return { state, ask };
}
