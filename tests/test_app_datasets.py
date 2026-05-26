"""GET /api/datasets/{handle}: serve the full GeoJSON / table behind a handle, 404 when unknown."""

from __future__ import annotations

import surveyor.app.main as main
from surveyor.data.models import GeoDataset, TableDataset

_FC = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"LAD21CD": "E08000003", "rate": 12.4},
            "geometry": {"type": "Point", "coordinates": [-2.24, 53.48]},
        }
    ],
}


def test_serves_table(client):
    handle = main.STORE.put(
        TableDataset(rows=[{"code": "E1", "pop": 5}], key_column="code", value_columns=["pop"])
    )
    body = client.get(f"/api/datasets/{handle}").json()
    assert body["kind"] == "table"
    assert body["rows"] == [{"code": "E1", "pop": 5}]


def test_serves_geo_with_geometry(client):
    handle = main.STORE.put(
        GeoDataset(features=_FC, geometry_type="Point", key_property="LAD21CD")
    )
    body = client.get(f"/api/datasets/{handle}").json()
    assert body["kind"] == "geo"
    # the full geometry must reach the client (unlike the model-facing descriptor)
    assert body["features"]["features"][0]["geometry"]["coordinates"] == [-2.24, 53.48]


def test_unknown_handle_is_404(client):
    assert client.get("/api/datasets/ds_does_not_exist").status_code == 404
