"""The tool registry — registration, schema export for the Anthropic API, and dispatch.

This is the extension point: a new tool is registered here and is immediately available to the
agent. ``tool_schemas()`` turns each tool's pydantic ``Input`` into the JSON schema the model sees,
and ``dispatch()`` validates an incoming tool_use block against that same model and runs it.
Dispatch *raises* on any failure (unknown tool, invalid arguments, or a tool that itself raised);
the loop catches and converts these into recoverable ``is_error`` tool results, so a bad call never
crashes the run (architecture §3.1).
"""

from __future__ import annotations

from typing import Any

from .analysis.aggregate import Aggregate
from .analysis.attach import Attach
from .analysis.filter import Filter
from .analysis.normalize import Normalize
from .analysis.rank import Rank
from .analysis.relate import Relate
from .base import Tool, ToolContext, ToolOutcome
from .fetch.boundaries import FetchBoundaries
from .fetch.features import FetchFeatures
from .fetch.statistic import FetchStatistic
from .render import RenderChart, RenderChoropleth


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool_schemas(self) -> list[dict[str, Any]]:
        """The ``tools=[...]`` list for the Anthropic API, one entry per registered tool."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.Input.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def dispatch(self, name: str, raw_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        """Validate and run a tool call. Raises on any failure — the loop makes it recoverable."""
        if name not in self._tools:
            raise KeyError(f"unknown tool {name!r}; available: {sorted(self._tools)}")
        tool = self._tools[name]
        args = tool.Input(**raw_input)  # pydantic ValidationError propagates on bad arguments
        return tool.run(ctx, args)


def build_registry() -> Registry:
    """Instantiate and register every tool: fetch, then analysis, then render."""
    registry = Registry()
    for tool in (
        FetchBoundaries(),
        FetchStatistic(),
        FetchFeatures(),
        Aggregate(),
        Normalize(),
        Rank(),
        Attach(),
        Filter(),
        Relate(),
        RenderChoropleth(),
        RenderChart(),
    ):
        registry.register(tool)
    return registry
