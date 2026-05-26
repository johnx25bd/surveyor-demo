"""fetch_statistic — a statistic by geography from ONS Nomis, as a table keyed by GSS code.

Rows are canonicalised to ``{"code", "name", <metric>}`` so every table in the chain joins on the
same ``code`` column.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...data.models import TableDataset, describe
from ...manifest import capabilities as cap
from ...sources import nomis
from ..base import ToolContext, ToolOutcome


class FetchStatisticInput(BaseModel):
    metric: str = Field("population", description="A manifest metric, e.g. 'population'.")
    geography_level: str = Field("local_authority", description="v0.1: 'local_authority'.")
    region: str = Field(..., description="A manifest-named region, e.g. 'greater_manchester'.")


class FetchStatistic:
    name = "fetch_statistic"
    description = (
        "Fetch a statistic by geography from ONS (a table keyed by GSS code), scoped to a named "
        "region. v0.1 metric: 'population'."
    )
    Input = FetchStatisticInput

    def run(self, ctx: ToolContext, args: FetchStatisticInput) -> ToolOutcome:
        try:
            metric = cap.METRICS[args.metric]
        except KeyError:
            raise ValueError(f"unknown metric {args.metric!r}; available: {sorted(cap.METRICS)}")
        try:
            type_code = metric.geography_type[args.geography_level]
        except KeyError:
            raise ValueError(
                f"metric {args.metric!r} has no geography level {args.geography_level!r}; "
                f"available: {sorted(metric.geography_type)}"
            )
        try:
            region = cap.REGIONS[args.region]
        except KeyError:
            raise ValueError(f"unknown region {args.region!r}; available: {sorted(cap.REGIONS)}")

        ctx.sink.emit(
            "status",
            {"state": f"fetching {args.metric} for {region.label} ({args.geography_level})"},
        )
        raw = nomis.fetch_csv(
            metric.dataset_id,
            geography=f"{metric.parent_geography}{type_code}",
            select=[metric.key_column, metric.name_column, metric.value_column],
            dims=metric.pinned_dims,
        )

        keep = set(region.lad_codes) if region.lad_codes else None
        rows: list[dict] = []
        for r in raw:
            code = r[metric.key_column]
            if keep is not None and code not in keep:
                continue
            rows.append(
                {"code": code, "name": r[metric.name_column], args.metric: int(r[metric.value_column])}
            )

        dataset = TableDataset(rows=rows, key_column="code", value_columns=[args.metric])
        handle = ctx.store.put(dataset)
        return ToolOutcome(descriptor=describe(handle, dataset))
