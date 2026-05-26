"""attach — join a table's value columns onto boundary polygons by GSS code → choropleth-ready geo.

No geometry computation: each boundary feature gets the matching table row's value columns merged
into its properties. Boundaries with no matching row keep their geometry but get null values, so
the choropleth renders the full set with gaps rather than dropping polygons.
"""

from __future__ import annotations

import copy

from pydantic import BaseModel, Field

from ...data.models import GeoDataset, TableDataset, describe
from ..base import ToolContext, ToolOutcome


class AttachInput(BaseModel):
    table: str = Field(..., description="Handle of the table whose values to attach.")
    boundaries: str = Field(..., description="Handle of the boundary GeoDataset to attach onto.")


class Attach:
    name = "attach"
    description = (
        "Join a table's value columns onto boundary polygons by GSS code, producing a "
        "choropleth-ready GeoDataset. Boundaries with no matching row keep null values."
    )
    Input = AttachInput

    def run(self, ctx: ToolContext, args: AttachInput) -> ToolOutcome:
        table = ctx.store.get(args.table)
        boundaries = ctx.store.get(args.boundaries)
        if not isinstance(table, TableDataset):
            raise ValueError("attach needs a table as the first input")
        if not isinstance(boundaries, GeoDataset):
            raise ValueError("attach needs a boundary GeoDataset as the second input")
        key = boundaries.key_property
        if key is None:
            raise ValueError("boundaries dataset has no key_property to join on")

        by_code = {r[table.key_column]: r for r in table.rows}
        sample = table.rows[0] if table.rows else {}
        carry = [c for c in ["name", *table.value_columns] if c in sample]

        features = copy.deepcopy(boundaries.features)
        feature_list = features.get("features", [])
        matched = 0
        for feat in feature_list:
            props = feat.setdefault("properties", {})
            row = by_code.get(props.get(key))
            if row:
                matched += 1
                for c in carry:
                    props[c] = row.get(c)
            else:
                for c in carry:
                    props.setdefault(c, None)

        dataset = GeoDataset(
            features=features,
            crs=boundaries.crs,
            geometry_type=boundaries.geometry_type,
            key_property=key,
            name_property=boundaries.name_property,
        )
        handle = ctx.store.put(dataset)
        ctx.sink.emit(
            "status",
            {"state": f"attached {table.value_columns} onto {matched}/{len(feature_list)} boundaries"},
        )
        return ToolOutcome(descriptor=describe(handle, dataset))
