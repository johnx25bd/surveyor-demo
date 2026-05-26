"""Core data layer: the handle store (roundtrip, TTL eviction) and the model-facing descriptor."""

from __future__ import annotations

import pytest

from surveyor.data.models import GeoDataset, TableDataset, describe
from surveyor.data.store import DatasetStore

_FC = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"LAD21CD": "E08000003", "LAD21NM": "Stockport", "rate": 12.4},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-2.2, 53.4], [-2.0, 53.4], [-2.0, 53.5], [-2.2, 53.5], [-2.2, 53.4]]],
            },
        }
    ],
}


def test_store_roundtrip():
    store = DatasetStore()
    handle = store.put(TableDataset(rows=[{"code": "E1"}], key_column="code", value_columns=[]))
    assert store.get(handle).rows == [{"code": "E1"}]
    assert handle.startswith("ds_")


def test_store_unknown_handle_raises():
    with pytest.raises(KeyError):
        DatasetStore().get("ds_nope")


def test_store_evicts_after_ttl():
    store = DatasetStore(ttl_seconds=-1)  # everything is already past its TTL
    handle = store.put(TableDataset(rows=[], key_column="code", value_columns=[]))
    with pytest.raises(KeyError):
        store.get(handle)


def test_describe_geo_strips_geometry_but_keeps_bbox():
    d = describe("ds_1", GeoDataset(features=_FC, geometry_type="Polygon", key_property="LAD21CD"))
    assert d["kind"] == "geo"
    assert d["count"] == 1
    assert d["geometry_type"] == "Polygon"
    assert d["bbox"] == [-2.2, 53.4, -2.0, 53.5]
    # the sample carries properties only — geometry never reaches the model's context
    assert d["sample"] == [{"properties": {"LAD21CD": "E08000003", "LAD21NM": "Stockport", "rate": 12.4}}]


def test_describe_table_lists_columns_and_samples_rows():
    rows = [{"code": "E1", "pop": 5}, {"code": "E2", "pop": 9}, {"code": "E3", "pop": 1}]
    d = describe("ds_2", TableDataset(rows=rows, key_column="code", value_columns=["pop"]))
    assert d["kind"] == "table"
    assert d["count"] == 3
    assert d["columns"] == ["code", "pop"]
    assert len(d["sample"]) == 2  # a small sample, not the whole table
