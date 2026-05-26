"""fetch_features — OS NGD site features of a curated type within a region, as a GeoDataset.

The type filter is applied server-side via the manifest's CQL (so the model never authors a query
predicate), and the region resolves to the bbox OS NGD requires. Feature fetches are *regional*,
not national — the region must carry a bbox (the feasible-question envelope, architecture §12). An
over-cap fetch surfaces as a recoverable error so the agent narrows the bbox or picks a sparser
type rather than aggregating over truncated data.

Feature datasets have no GSS join key of their own; they are assigned to boundaries by spatial
join in ``aggregate``, so ``key_property`` is left unset.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ... import config
from ...data.models import GeoDataset, describe
from ...manifest import capabilities as cap
from ...sources import os_ngd
from ..base import ToolContext, ToolOutcome


class FetchFeaturesInput(BaseModel):
    feature_type: str = Field(
        ..., description="A manifest feature type, e.g. 'health_centre'."
    )
    region: str = Field(
        ...,
        description="A manifest-named region that has a bbox, e.g. 'greater_manchester'.",
    )
    max_features: int = Field(
        2000,
        ge=1,
        le=5000,
        description="Cap on features returned. Over it, narrow the bbox or pick a sparser type.",
    )


class FetchFeatures:
    name = "fetch_features"
    description = (
        "Fetch OS NGD site features of a curated type (already type-filtered server-side) within "
        "a named region's bbox, as a WGS84 GeoDataset keyed for spatial aggregation. Feature "
        "fetches are regional, not national: the region must have a bbox. If the fetch reports "
        "over-cap, narrow the bbox or choose a sparser feature type and say so."
    )
    Input = FetchFeaturesInput

    def run(self, ctx: ToolContext, args: FetchFeaturesInput) -> ToolOutcome:
        try:
            ft = cap.FEATURE_TYPES[args.feature_type]
        except KeyError:
            raise ValueError(
                f"unknown feature_type {args.feature_type!r}; "
                f"available: {sorted(cap.FEATURE_TYPES)}"
            )
        try:
            region = cap.REGIONS[args.region]
        except KeyError:
            raise ValueError(f"unknown region {args.region!r}; available: {sorted(cap.REGIONS)}")
        if region.bbox is None:
            raise ValueError(
                f"region {args.region!r} has no bbox; feature fetches are regional, not national. "
                f"Use a bounded region such as 'greater_manchester'."
            )

        ctx.sink.emit(
            "status",
            {"state": f"fetching {args.feature_type} sites in {region.label} (OS NGD, server-side CQL)"},
        )
        fc = os_ngd.fetch_items(
            ft.collection,
            api_key=config.os_data_hub_key(),
            bbox=region.bbox,
            cql_filter=ft.cql_filter,
            max_features=args.max_features,
        )
        feats = fc.get("features", [])
        geometry_type = feats[0]["geometry"]["type"] if feats else ft.geometry
        dataset = GeoDataset(features=fc, geometry_type=geometry_type, key_property=None)
        handle = ctx.store.put(dataset)
        ctx.sink.emit("status", {"state": f"got {len(feats)} {args.feature_type} sites"})
        return ToolOutcome(descriptor=describe(handle, dataset))
