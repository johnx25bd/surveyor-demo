// SSE client for POST /api/query. The contract is a POST that returns text/event-stream, so we read
// the response body as a stream and parse SSE frames by hand — EventSource is GET-only and can't
// carry the question in a body.

import type { SurveyorEvent } from "./types";

export interface StreamHandle {
  cancel(): void;
}

export interface StreamCallbacks {
  onEvent(e: SurveyorEvent): void;
  onClose(): void; // stream ended (after the loop's own `done` event, or on transport close)
  onError(message: string): void;
}

export function streamQuery(question: string, cb: StreamCallbacks): StreamHandle {
  const controller = new AbortController();

  (async () => {
    let res: Response;
    try {
      res = await fetch("/api/query", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
    } catch (err) {
      if (!controller.signal.aborted) cb.onError(transportMessage(err));
      return;
    }

    if (!res.ok || !res.body) {
      cb.onError(`The query request failed (HTTP ${res.status}).`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE frames are separated by a blank line.
        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const frame = parseFrame(buffer.slice(0, sep));
          buffer = buffer.slice(sep + 2);
          if (frame) cb.onEvent(frame);
        }
      }
      cb.onClose();
    } catch (err) {
      if (!controller.signal.aborted) cb.onError(transportMessage(err));
    }
  })();

  return { cancel: () => controller.abort() };
}

export function parseFrame(raw: string): SurveyorEvent | null {
  let name = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  try {
    return { event: name, data: JSON.parse(dataLines.join("\n")) } as SurveyorEvent;
  } catch {
    return null; // a malformed frame is dropped rather than killing the stream
  }
}

function transportMessage(err: unknown): string {
  return err instanceof Error ? `Connection error: ${err.message}` : "Connection error.";
}
