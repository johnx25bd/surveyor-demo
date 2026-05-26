"""relate — select the features that satisfy a spatial predicate against a reference geometry set.

predicate ∈ {within, intersects, within_distance:<m>}. within/intersects test topology directly in
WGS84; within_distance reprojects both sets to British National Grid (EPSG:27700) for the metric
test — and that reprojection is surfaced in the trace. Returns the matched features (geo), with
their original WGS84 geometry preserved. This is the proximity seed the roadmap builds on.
"""

from __future__ import annotations

import geopandas as gpd
from pydantic import BaseModel, Field

from ...data.geo import BRITISH_NATIONAL_GRID, to_gdf
from ...data.models import GeoDataset, describe
from ..base import ToolContext, ToolOutcome


class RelateInput(BaseModel):
    features: str = Field(..., description="Handle of the candidate feature GeoDataset.")
    reference: str = Field(..., description="Handle of the reference GeoDataset to relate against.")
    predicate: str = Field(
        ..., description="'within', 'intersects', or 'within_distance:<metres>'."
    )


class Relate:
    name = "relate"
    description = (
        "Select features that satisfy a spatial predicate against a reference set: 'within', "
        "'intersects', or 'within_distance:<metres>'. within_distance reprojects to EPSG:27700 "
        "for the metric test. Returns the matched features (geo)."
    )
    Input = RelateInput

    def run(self, ctx: ToolContext, args: RelateInput) -> ToolOutcome:
        features = ctx.store.get(args.features)
        reference = ctx.store.get(args.reference)
        if not isinstance(features, GeoDataset) or not isinstance(reference, GeoDataset):
            raise ValueError("relate needs two geo datasets: features and reference")

        pred, _, dist = args.predicate.partition(":")
        # reset_index makes the 0..n-1 ⇄ source-list-position invariant explicit: the sjoin below
        # preserves the left index, and we map matched rows back to the original WGS84 features by it.
        feats = to_gdf(features).reset_index(drop=True)
        ref = to_gdf(reference)

        if pred in {"within", "intersects"}:
            ctx.sink.emit(
                "status", {"state": f"relating {len(feats)} features {pred} reference set"}
            )
            joined = gpd.sjoin(feats, ref, predicate=pred, how="inner")
            keep_idx = joined.index.unique()
        elif pred == "within_distance":
            if not dist:
                raise ValueError("within_distance needs metres, e.g. 'within_distance:500'")
            metres = float(dist)
            ctx.sink.emit(
                "status",
                {"state": f"reprojected 4326→27700 for within_distance:{int(metres)}m test"},
            )
            near = gpd.sjoin_nearest(
                feats.to_crs(BRITISH_NATIONAL_GRID),
                ref.to_crs(BRITISH_NATIONAL_GRID),
                how="inner",
                max_distance=metres,
            )
            keep_idx = near.index.unique()
        else:
            raise ValueError(
                f"unknown predicate {args.predicate!r}; use within, intersects, or "
                f"within_distance:<m>"
            )

        source = features.features.get("features", [])
        kept = [source[i] for i in keep_idx]  # original WGS84 geometry
        out = GeoDataset(
            features={"type": "FeatureCollection", "features": kept},
            crs=features.crs,
            geometry_type=features.geometry_type,
            key_property=features.key_property,
            name_property=features.name_property,
        )
        handle = ctx.store.put(out)
        ctx.sink.emit(
            "status", {"state": f"{len(kept)} of {len(feats)} features matched {args.predicate}"}
        )
        return ToolOutcome(descriptor=describe(handle, out))
