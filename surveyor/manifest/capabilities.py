"""The curated capability manifest (England-only for v0.1).

Maps the friendly names the agent reasons about to the exact upstream specifics — service URLs,
field names, geography vintages, region predicates, and value vocabularies. Region predicates live
here, never in model output, so the agent never authors a raw query filter.

England-only is a deliberate v0.1 scope decision (the deprivation index is England-only); the
shapes here are nation-agnostic, so Wales/Scotland are a data + entry addition, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geography:
    service_url: str
    key_field: str  # the GSS-code field (the universal join key)
    name_field: str


@dataclass(frozen=True)
class Region:
    label: str
    where: str  # ArcGIS attribute predicate, manifest-owned
    lad_codes: tuple[str, ...] | None = None  # GSS codes, for filtering non-ArcGIS sources (Nomis)
    bbox: tuple[float, float, float, float] | None = None  # lon/lat, for OS NGD feature fetches


_LAD_BGC = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2021_UK_BGC_2022/FeatureServer/0/query"
)

GEOGRAPHIES: dict[str, Geography] = {
    "local_authority": Geography(service_url=_LAD_BGC, key_field="LAD21CD", name_field="LAD21NM"),
}

# The ten Greater Manchester metropolitan boroughs, E08000001–E08000010.
_GM_CODES = [f"E0800000{n}" for n in range(1, 10)] + ["E08000010"]

REGIONS: dict[str, Region] = {
    "england": Region(label="England", where="LAD21CD LIKE 'E%'"),
    "greater_manchester": Region(
        label="Greater Manchester",
        where="LAD21CD IN (" + ", ".join(f"'{code}'" for code in _GM_CODES) + ")",
        lad_codes=tuple(_GM_CODES),
        bbox=(-2.75, 53.32, -1.91, 53.69),
    ),
}


@dataclass(frozen=True)
class Metric:
    source: str
    dataset_id: str
    geography_type: dict[str, str]  # geography level -> Nomis TYPE code (dataset/vintage-specific)
    parent_geography: str  # Nomis parent geography id (England = 2092957699)
    pinned_dims: dict[str, int]  # every dataset dimension pinned to one code
    key_column: str  # GSS-code column in the response
    name_column: str
    value_column: str


METRICS: dict[str, Metric] = {
    "population": Metric(
        source="nomis",
        dataset_id="NM_2021_1",  # 2021 Census TS001 — usual residents
        geography_type={"local_authority": "TYPE154"},  # 2022 local authority districts
        parent_geography="2092957699",  # England
        pinned_dims={"measures": 20100, "c2021_restype_3": 0},  # 20100 = count; 0 = all usual residents
        key_column="GEOGRAPHY_CODE",
        name_column="GEOGRAPHY_NAME",
        value_column="OBS_VALUE",
    ),
}


@dataclass(frozen=True)
class FeatureType:
    collection: str  # OS NGD collection id
    cql_filter: str  # server-side CQL — the model never authors one
    geometry: str  # the geometry kind the collection returns
    density: str  # "sparse" — only sparse civic types are safe for regional aggregation


# Only SPARSE civic site types belong here: dense types blow past OS NGD's 100/page ceiling even
# within a city-region (verified live). The cql_filter values are documented OS NGD code-list
# strings, confirmed against live responses. Adding a type is one verified entry — no code change.
FEATURE_TYPES: dict[str, FeatureType] = {
    "health_centre": FeatureType(
        collection="lus-fts-site-2",
        cql_filter="description='Health Centre'",
        geometry="MultiPolygon",
        density="sparse",  # ~668 across Greater Manchester — safe for regional aggregation
    ),
}
