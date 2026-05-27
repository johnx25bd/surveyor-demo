"""The contract every tool implements — fetch, analysis, and render alike.

A tool declares a Pydantic ``Input`` model (its ``model_json_schema()`` is the schema the model
sees) and a ``run`` that reads inputs from / writes outputs to the store via the ``ToolContext``.
Fetch and analysis tools return a ``ToolOutcome`` whose ``descriptor`` goes to the model; render
tools additionally set ``view``, which the loop forwards to the event sink.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from ..data.store import DatasetStore


class EventSink(Protocol):
    def emit(self, event: str, data: dict[str, Any]) -> None: ...


@dataclass
class ViewEvent:
    kind: str  # "choropleth" | "chart" | "points"
    handle: str
    encoding: dict[str, Any]


@dataclass
class ToolContext:
    store: DatasetStore
    manifest: Any  # the capabilities module
    sink: EventSink


@dataclass
class ToolOutcome:
    descriptor: dict[str, Any]  # returned to the model as the tool_result content
    view: ViewEvent | None = None  # set by render tools; forwarded to the sink by the loop


class Tool(Protocol):
    name: str
    description: str
    Input: type[BaseModel]

    def run(self, ctx: ToolContext, args: Any) -> ToolOutcome: ...
