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
        bbox=(-2.75, 53.32, -1.91, 53.69),
    ),
}
