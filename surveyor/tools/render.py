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
        if not feats:
            raise ValueError(
                "render_choropleth got an empty GeoDataset — the attach/aggregate step produced "
                "nothing to map; revisit the upstream steps"
            )
        if args.value_column not in feats[0].get("properties", {}):
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
        if not ds.rows:
            raise ValueError(
                "render_chart got an empty table — the upstream step produced no rows to chart"
            )
        if args.value_column not in ds.rows[0]:
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


class RenderPointsInput(BaseModel):
    geo_dataset: str = Field(
        ..., description="Handle of a GeoDataset of features to plot as points, e.g. libraries."
    )
    title: str = Field(..., description="Layer title for the legend/popup.")
    label_column: str = Field(
        "name1_text",
        description="Feature property to label each point in its popup (OS NGD name field).",
    )


class RenderPoints:
    name = "render_points"
    description = (
        "Plot a GeoDataset of features as a point overlay on the map (each footprint shown at its "
        "representative point), drawn on top of any choropleth. Use it to show a reference layer — "
        "e.g. the libraries a proximity question relates to. Returns an acknowledgement; the "
        "overlay instruction is emitted to the trace for the client to draw."
    )
    Input = RenderPointsInput

    def run(self, ctx: ToolContext, args: RenderPointsInput) -> ToolOutcome:
        ds = ctx.store.get(args.geo_dataset)
        if not isinstance(ds, GeoDataset):
            raise ValueError("render_points needs a geo dataset (e.g. a fetched feature layer)")
        if not ds.features.get("features"):
            raise ValueError(
                "render_points got an empty GeoDataset — nothing to plot; revisit the fetch step"
            )
        return ToolOutcome(
            descriptor={"rendered": True, "handle": args.geo_dataset, "kind": "points"},
            view=ViewEvent(
                kind="points",
                handle=args.geo_dataset,
                encoding={"label_column": args.label_column, "title": args.title},
            ),
        )
