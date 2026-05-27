import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatItem, SurveyorState } from "../state/useSurveyor";
import type { DatasetDescriptor } from "../lib/types";

const SUGGESTIONS = [
  "How many health centres per 10,000 residents by local authority across Greater Manchester?",
  "How many health centres in the West Midlands are within 800m of a library?",
  "Population by local authority in England",
];

interface Props {
  state: SurveyorState;
  onAsk(question: string): void;
}

export function ChatPane({ state, onAsk }: Props) {
  const running = state.status === "running";
  const showThinking = running && !endsWithStreamingText(state.items);
  const streamRef = useRef<HTMLDivElement | null>(null);

  // Follow the trace as it streams — the whole point of this pane is watching the agent work. Keyed
  // on item count + the last item's text so each appended tool call / token scrolls into view.
  const lastText = state.items[state.items.length - 1];
  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.items.length, lastText, showThinking]);

  return (
    <section className="sv-chat" aria-label="Conversation">
      <div className="sv-chat-stream" ref={streamRef} aria-live="polite" aria-busy={running}>
        {state.items.length === 0 ? (
          <EmptyState onPick={onAsk} />
        ) : (
          state.items.map((item, i) => <Item key={i} item={item} />)
        )}
        {showThinking && (
          <div className="sv-msg sv-msg--assistant">
            <div className="sv-msg-head">
              <span className="sv-avatar sv-avatar--sm" aria-hidden="true">
                S
              </span>
              <span className="sv-msg-meta">Surveyor</span>
              <span className="sv-thinking">{state.statusLabel ?? "working"}</span>
            </div>
          </div>
        )}
      </div>
      <Composer onAsk={onAsk} disabled={running} />
    </section>
  );
}

function endsWithStreamingText(items: ChatItem[]): boolean {
  const last = items[items.length - 1];
  return !!last && last.kind === "assistant" && last.streaming;
}

function EmptyState({ onPick }: { onPick(q: string): void }) {
  return (
    <div className="sv-empty">
      <div className="sv-empty-greet">
        <span className="sv-avatar sv-avatar--sm" aria-hidden="true">
          S
        </span>
        <div>
          <p className="sv-empty-lead">Ask a question about Great Britain.</p>
          <p className="sv-empty-sub">
            Surveyor composes live queries against Ordnance Survey and ONS data, and shows every step
            — which dataset, which filter, which spatial join — as it works.
          </p>
        </div>
      </div>
      <div className="sv-empty-sugs">
        <div className="sv-empty-eyebrow">Try</div>
        {SUGGESTIONS.map((q) => (
          <button key={q} className="sv-sug" onClick={() => onPick(q)}>
            <span>{q}</span>
            <svg
              className="sv-sug-arrow"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  );
}

function Item({ item }: { item: ChatItem }) {
  switch (item.kind) {
    case "user":
      return (
        <div className="sv-msg sv-msg--user">
          <div className="sv-msg-bubble">{item.text}</div>
        </div>
      );
    case "assistant":
      return (
        <div className="sv-msg sv-msg--assistant">
          <div className="sv-msg-body sv-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
            {item.streaming && <span className="sv-streaming-cursor" aria-hidden="true" />}
          </div>
        </div>
      );
    case "tool":
      return <ToolEntry item={item} />;
    case "error":
      return (
        <div className="sv-msg sv-msg--assistant">
          <div className="sv-msg-caveat" role="alert">
            {item.message}
          </div>
        </div>
      );
  }
}

function ToolEntry({ item }: { item: Extract<ChatItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(item.input)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  const statusText =
    item.status === "running" ? "running" : item.status === "error" ? "error" : "done";

  return (
    <div
      className={`sv-tool sv-tool--inline${item.status === "running" ? " sv-tool--running" : ""}`}
    >
      <button
        type="button"
        className="sv-tool-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="sv-tool-chevron">{open ? "▾" : "▸"}</span>
        <span className="sv-tool-dot" aria-hidden="true" />
        <span className="sv-tool-name">{item.name}</span>
        <span className="sv-tool-args">({args})</span>
        <span className="sv-tool-status">{statusText}</span>
      </button>
      {open && (
        <div className="sv-tool-body">
          {item.status === "error"
            ? item.error
            : item.descriptor
              ? describe(item.descriptor)
              : "…"}
        </div>
      )}
    </div>
  );
}

function describe(d: DatasetDescriptor): string {
  if (d.kind === "geo") {
    const bits = [d.handle, "geo", d.geometry_type, `${d.count} features`, d.crs].filter(Boolean);
    return bits.join("  ·  ");
  }
  const cols = d.columns?.join(", ");
  return [d.handle, "table", `${d.count} rows`, cols && `[${cols}]`].filter(Boolean).join("  ·  ");
}

function Composer({ onAsk, disabled }: { onAsk(q: string): void; disabled: boolean }) {
  const [text, setText] = useState("");

  function submit() {
    if (!text.trim() || disabled) return;
    onAsk(text);
    setText("");
  }

  return (
    <div className="sv-composer">
      <textarea
        value={text}
        placeholder="Ask about UK geography…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="sv-composer-actions">
        <span className="sv-tool-status">{disabled ? "working…" : ""}</span>
        <button
          type="button"
          className="sv-composer-send"
          onClick={submit}
          disabled={disabled || !text.trim()}
        >
          Ask
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
