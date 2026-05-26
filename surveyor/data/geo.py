"""GeoPandas conversion and CRS constants — the bridge to the geometry engine.

Datasets live in the store as WGS84 GeoJSON. Spatial *containment* is topologically valid in WGS84
at GB scale, so ``aggregate`` joins there directly with no reprojection; only metric tests
(``relate within_distance``) reproject to British National Grid, and that step is surfaced in the
trace. This module is the single place GeoJSON becomes a GeoDataFrame.
"""

from __future__ import annotations

import geopandas as gpd

from .models import GeoDataset

WGS84 = "EPSG:4326"
BRITISH_NATIONAL_GRID = "EPSG:27700"  # metric CRS for distance/area tests


def to_gdf(ds: GeoDataset) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame (geometry + flat properties) from a stored GeoDataset."""
    return gpd.GeoDataFrame.from_features(ds.features.get("features", []), crs=ds.crs)
