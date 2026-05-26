"""The hand-rolled Anthropic tool-use loop — the heart of Surveyor, kept fully legible (§3).

The loop is the lesson: we send the conversation plus the tool schemas, stream the model's reply
(emitting text as it arrives), dispatch any tool_use blocks ourselves, append the tool results, and
loop — stopping on a final text answer or a step ceiling. Because we wrote the dispatch, *we* decide
what the trace shows. Tool errors are recoverable: a tool that raises becomes an ``is_error``
tool_result the model can adapt to on the next turn, bounded by ``MAX_STEPS`` so there are no
infinite loops (§3.1).
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from ..config import anthropic_api_key, model
from ..data.store import DatasetStore
from ..manifest import capabilities
from ..tools.base import EventSink, ToolContext
from ..tools.registry import build_registry
from . import events as ev
from .prompt import build_system_prompt

MAX_STEPS = 12  # model turns; the headline chain is ~6, leaving room for self-correction
MAX_TOKENS = 4096


def _to_input_block(block) -> dict:
    """Reduce a streamed response content block to the minimal shape valid as message *input*."""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.model_dump()  # any other block kind: best effort


def run(question: str, sink: EventSink, store: DatasetStore | None = None) -> None:
    """Answer a question by composing tools, emitting the whole trace to ``sink``."""
    store = store or DatasetStore()
    registry = build_registry()
    ctx = ToolContext(store=store, manifest=capabilities, sink=sink)

    # Two static cache breakpoints — the system prompt and the tool list — so every turn after the
    # first reads them from cache rather than re-billing the full prefix.
    system = [
        {"type": "text", "text": build_system_prompt(), "cache_control": {"type": "ephemeral"}}
    ]
    tools = registry.tool_schemas()
    if tools:
        # One breakpoint on the last tool caches the whole tool block above it — which tool is last
        # doesn't matter, only that the breakpoint sits at the end of the static prefix.
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    client = Anthropic(api_key=anthropic_api_key())
    messages: list[dict] = [{"role": "user", "content": question}]
    sink.emit(ev.STATUS, {"state": "thinking"})

    for _ in range(MAX_STEPS):
        text_parts: list[str] = []
        with client.messages.stream(
            model=model(),
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:  # the SDK's text-delta iterator drives the live trace
                sink.emit(ev.MESSAGE, {"text": text})
                text_parts.append(text)
            final = stream.get_final_message()

        if final.stop_reason != "tool_use":
            if final.stop_reason not in ("end_turn", "stop_sequence"):
                sink.emit(ev.ERROR, {"message": f"model stopped early: {final.stop_reason}"})
            sink.emit(ev.DONE, {"summary": "".join(text_parts)})
            return

        tool_uses = [b for b in final.content if b.type == "tool_use"]
        if not tool_uses:  # defensive: a tool_use stop with no blocks should not happen
            sink.emit(ev.ERROR, {"message": "model signalled a tool call but produced none"})
            sink.emit(ev.DONE, {"summary": "".join(text_parts)})
            return

        # Echo the assistant turn back (text + tool_use blocks) so the next call has context.
        # Re-serialise to the minimal *input* shape: the streamed blocks carry response-only fields
        # (e.g. a text block's parsed_output) the API rejects if sent back.
        messages.append({"role": "assistant", "content": [_to_input_block(b) for b in final.content]})

        results: list[dict] = []
        for block in tool_uses:
            sink.emit(ev.TOOL_CALL, {"id": block.id, "name": block.name, "input": block.input})
            try:
                outcome = registry.dispatch(block.name, block.input, ctx)
            except Exception as exc:  # noqa: BLE001 — recoverable by design; returned to the model
                message = f"{type(exc).__name__}: {exc}"
                sink.emit(ev.ERROR, {"message": message, "tool_id": block.id})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": message,
                        "is_error": True,
                    }
                )
                continue
            sink.emit(ev.TOOL_RESULT, {"id": block.id, "descriptor": outcome.descriptor})
            if outcome.view is not None:
                sink.emit(
                    ev.VIEW,
                    {
                        "kind": outcome.view.kind,
                        "handle": outcome.view.handle,
                        "encoding": outcome.view.encoding,
                    },
                )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(outcome.descriptor),
                }
            )

        messages.append({"role": "user", "content": results})

    # Step ceiling reached without a final answer (§3.1) — surface it, do not loop forever.
    sink.emit(ev.ERROR, {"message": f"reached the step ceiling (MAX_STEPS={MAX_STEPS})"})
    sink.emit(ev.DONE, {"summary": "I couldn't complete the question within the step budget."})
