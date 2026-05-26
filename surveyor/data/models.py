"""The two dataset shapes Surveyor passes between tools, and the small descriptor the model sees.

Tools never hand raw geodata to the model. They write a `GeoDataset` or `TableDataset` into the
`DatasetStore` and return a `DatasetDescriptor` (built by `describe`) — counts, bounds, columns,
and a tiny sample, keyed by an opaque handle. The universal join key across every source is the
GSS code (e.g. ``E08000003``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GeoDataset(BaseModel):
    """A GeoJSON FeatureCollection plus the metadata Surveyor reasons about."""

    kind: Literal["geo"] = "geo"
    features: dict[str, Any]  # a GeoJSON FeatureCollection
    crs: str = "EPSG:4326"
    geometry_type: str  # e.g. "MultiPolygon", "Point"
    key_property: str | None = None  # the feature property holding the GSS code
    name_property: str | None = None  # the feature property holding the human-readable name

    @property
    def count(self) -> int:
        return len(self.features.get("features", []))


class TableDataset(BaseModel):
    """Rows keyed by a GSS code, with one or more named value columns."""

    kind: Literal["table"] = "table"
    rows: list[dict[str, Any]]
    key_column: str  # column holding the GSS code
    value_columns: list[str]

    @property
    def count(self) -> int:
        return len(self.rows)


Dataset = GeoDataset | TableDataset


class DatasetDescriptor(BaseModel):
    """The small object a tool returns *to the model* — never the data itself."""

    handle: str
    kind: Literal["geo", "table"]
    count: int
    crs: str | None = None
    geometry_type: str | None = None
    bbox: list[float] | None = None
    key_column: str | None = None
    columns: list[str] | None = None
    sample: list[dict[str, Any]] = Field(default_factory=list)


def _bbox(features: list[dict[str, Any]]) -> list[float] | None:
    """Compute [minLon, minLat, maxLon, maxLat] by walking GeoJSON coordinates."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(coords: Any) -> None:
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
            return
        for c in coords:
            walk(c)

    for feature in features:
        walk((feature.get("geometry") or {}).get("coordinates"))
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def describe(handle: str, ds: Dataset) -> dict[str, Any]:
    """Build the small `DatasetDescriptor` payload a tool returns to the model."""
    if isinstance(ds, GeoDataset):
        feats = ds.features.get("features", [])
        # Sample carries properties only — geometry stays in the store, off the model's context.
        sample = [{"properties": f.get("properties", {})} for f in feats[:1]]
        columns = list(feats[0].get("properties", {})) if feats else None
        return DatasetDescriptor(
            handle=handle,
            kind="geo",
            count=len(feats),
            crs=ds.crs,
            geometry_type=ds.geometry_type,
            bbox=_bbox(feats),
            key_column=ds.key_property,
            columns=columns,
            sample=sample,
        ).model_dump(exclude_none=True)

    return DatasetDescriptor(
        handle=handle,
        kind="table",
        count=ds.count,
        key_column=ds.key_column,
        columns=[ds.key_column, *ds.value_columns],
        sample=ds.rows[:2],
    ).model_dump(exclude_none=True)
