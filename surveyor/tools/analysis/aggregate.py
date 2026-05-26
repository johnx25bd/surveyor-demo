"""aggregate — assign features to the boundary that contains them, then reduce per boundary.

A geopandas point-in-polygon spatial join: each feature is reduced to its representative point and
matched to the boundary polygon containing it (valid in WGS84 at GB scale — no reprojection). The
result is a table keyed by GSS code, ready to normalise or attach. Every boundary appears, with a
zero where no features fall inside, so the ranking and choropleth are complete rather than sparse.
"""

from __future__ import annotations

import geopandas as gpd
from pydantic import BaseModel, Field

from ...data.geo import to_gdf
from ...data.models import GeoDataset, TableDataset, describe
from ..base import ToolContext, ToolOutcome


class AggregateInput(BaseModel):
    features: str = Field(..., description="Handle of the feature GeoDataset to aggregate.")
    boundaries: str = Field(..., description="Handle of the boundary GeoDataset to aggregate into.")
    op: str = Field(
        "count",
        description="'count', 'sum:<field>', or 'mean:<field>' (field is a feature property).",
    )


class Aggregate:
    name = "aggregate"
    description = (
        "Spatially aggregate features into boundaries by the boundary containing each feature's "
        "representative point. op is 'count', 'sum:<field>', or 'mean:<field>'. Returns a table "
        "keyed by GSS code, one row per boundary (zero-filled where no features fall inside)."
    )
    Input = AggregateInput

    def run(self, ctx: ToolContext, args: AggregateInput) -> ToolOutcome:
        features = ctx.store.get(args.features)
        boundaries = ctx.store.get(args.boundaries)
        if not isinstance(features, GeoDataset) or not isinstance(boundaries, GeoDataset):
            raise ValueError("aggregate needs two geo datasets: features and boundaries")

        key = boundaries.key_property
        name = boundaries.name_property
        if key is None:
            raise ValueError("boundaries dataset has no key_property to aggregate by")

        op, _, field = args.op.partition(":")
        if op not in {"count", "sum", "mean"}:
            raise ValueError(f"unknown op {args.op!r}; use count, sum:<field>, or mean:<field>")
        if op in {"sum", "mean"} and not field:
            raise ValueError(f"op {op!r} needs a field, e.g. '{op}:geometry_area_m2'")

        feats = to_gdf(features)
        bounds = to_gdf(boundaries)
        name = name if (name and name in bounds.columns) else None  # a prior filter may have dropped it
        if op in {"sum", "mean"} and field not in feats.columns:
            raise ValueError(f"field {field!r} not in features; available: {sorted(feats.columns)}")

        ctx.sink.emit(
            "status",
            {"state": f"spatial join: {len(feats)} features into {len(bounds)} boundaries ({args.op})"},
        )

        points = feats.set_geometry(feats.representative_point())
        cols = [key, "geometry"] + ([name] if name else [])
        joined = gpd.sjoin(points, bounds[cols], predicate="within", how="inner")

        if op == "count":
            agg = joined.groupby(key).size()
            value_column = "count"
        elif op == "sum":
            agg = joined.groupby(key)[field].sum()
            value_column = f"sum_{field}"
        else:
            agg = joined.groupby(key)[field].mean()
            value_column = f"mean_{field}"

        names = bounds.set_index(key)[name].to_dict() if name else {}
        rows = []
        for code in bounds[key]:
            raw = agg[code] if code in agg.index else 0  # zero-fill boundaries with no features
            value = int(raw) if op == "count" else float(raw)
            rows.append({"code": code, "name": names.get(code), value_column: value})

        dataset = TableDataset(rows=rows, key_column="code", value_columns=[value_column])
        handle = ctx.store.put(dataset)
        ctx.sink.emit("status", {"state": f"aggregated to {len(rows)} boundaries"})
        return ToolOutcome(descriptor=describe(handle, dataset))
