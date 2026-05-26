"""render_choropleth and render_chart — turn a dataset handle into a view instruction (§8).

Render tools do not return data to the model: they return a minimal acknowledgement descriptor
(the Anthropic API requires a tool_result for every tool_use) and carry the actual draw instruction
on the ToolOutcome's ``view``, which the loop forwards to the event sink. The CLI sink (phase 1) or
the browser (phase 2) then fetches the named handle to draw it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..data.models import GeoDataset, TableDataset
from .base import ToolContext, ToolOutcome, ViewEvent


class RenderChoroplethInput(BaseModel):
    geo_dataset: str = Field(
        ..., description="Handle of a GeoDataset with the value joined on (from attach/aggregate)."
    )
    value_column: str = Field(..., description="The feature property to colour by, e.g. 'rate'.")
    title: str = Field(..., description="Map title for display.")


class RenderChoropleth:
    name = "render_choropleth"
    description = (
        "Render a choropleth map from a GeoDataset whose features carry the value to colour by "
        "(produced by attach). Returns an acknowledgement; the map instruction is emitted to the "
        "trace for the client to draw."
    )
    Input = RenderChoroplethInput

    def run(self, ctx: ToolContext, args: RenderChoroplethInput) -> ToolOutcome:
        ds = ctx.store.get(args.geo_dataset)
        if not isinstance(ds, GeoDataset):
            raise ValueError("render_choropleth needs a geo dataset (use attach to build one)")
        feats = ds.features.get("features", [])
        if feats and args.value_column not in feats[0].get("properties", {}):
            cols = sorted(feats[0].get("properties", {}))
            raise ValueError(
                f"value_column {args.value_column!r} not on the features; available: {cols}"
            )
        return ToolOutcome(
            descriptor={"rendered": True, "handle": args.geo_dataset, "kind": "choropleth"},
            view=ViewEvent(
                kind="choropleth",
                handle=args.geo_dataset,
                encoding={"value_column": args.value_column, "title": args.title},
            ),
        )


class RenderChartInput(BaseModel):
    table: str = Field(..., description="Handle of the table to chart.")
    value_column: str = Field(..., description="Column for the bar lengths, e.g. 'rate'.")
    label_column: str = Field("name", description="Column for the bar labels, e.g. 'name'.")
    kind: str = Field("bar", description="Chart kind; 'bar' (default, ranked).")
    title: str = Field(..., description="Chart title for display.")


class RenderChart:
    name = "render_chart"
    description = (
        "Render a chart (default: a ranked bar) from a table — value_column drives the bars, "
        "label_column the labels. Returns an acknowledgement; the chart instruction is emitted to "
        "the trace for the client to draw."
    )
    Input = RenderChartInput

    def run(self, ctx: ToolContext, args: RenderChartInput) -> ToolOutcome:
        ds = ctx.store.get(args.table)
        if not isinstance(ds, TableDataset):
            raise ValueError("render_chart needs a table")
        if ds.rows and args.value_column not in ds.rows[0]:
            raise ValueError(
                f"value_column {args.value_column!r} not in the table; available: {sorted(ds.rows[0])}"
            )
        return ToolOutcome(
            descriptor={"rendered": True, "handle": args.table, "kind": "chart"},
            view=ViewEvent(
                kind="chart",
                handle=args.table,
                encoding={
                    "value_column": args.value_column,
                    "label_column": args.label_column,
                    "kind": args.kind,
                    "title": args.title,
                },
            ),
        )
