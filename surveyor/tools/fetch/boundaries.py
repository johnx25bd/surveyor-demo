"""fetch_boundaries — administrative boundary polygons (WGS84) for a geography level + region."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...data.models import GeoDataset, describe
from ...manifest import capabilities as cap
from ...sources import arcgis
from ..base import ToolContext, ToolOutcome


class FetchBoundariesInput(BaseModel):
    geography_level: str = Field(
        "local_authority",
        description="The boundary geography. v0.1: 'local_authority'.",
    )
    region: str = Field(
        ...,
        description="A manifest-named region, e.g. 'england' or 'greater_manchester'.",
    )


class FetchBoundaries:
    name = "fetch_boundaries"
    description = (
        "Fetch administrative boundary polygons (WGS84 GeoJSON) for a geography level within a "
        "named region. Returns a dataset handle keyed by GSS code."
    )
    Input = FetchBoundariesInput

    def run(self, ctx: ToolContext, args: FetchBoundariesInput) -> ToolOutcome:
        try:
            geo = cap.GEOGRAPHIES[args.geography_level]
        except KeyError:
            raise ValueError(
                f"unknown geography_level {args.geography_level!r}; "
                f"available: {sorted(cap.GEOGRAPHIES)}"
            )
        try:
            region = cap.REGIONS[args.region]
        except KeyError:
            raise ValueError(
                f"unknown region {args.region!r}; available: {sorted(cap.REGIONS)}"
            )

        ctx.sink.emit(
            "status", {"state": f"fetching {geo.key_field} boundaries for {region.label}"}
        )
        fc = arcgis.query(
            geo.service_url,
            where=region.where,
            out_fields=f"{geo.key_field},{geo.name_field}",
            out_sr=4326,
            return_geometry=True,
        )
        feats = fc.get("features", [])
        geometry_type = feats[0]["geometry"]["type"] if feats else "Unknown"
        dataset = GeoDataset(
            features=fc, geometry_type=geometry_type, key_property=geo.key_field
        )
        handle = ctx.store.put(dataset)
        return ToolOutcome(descriptor=describe(handle, dataset))
