"""Phase-1 smoke: the headline analysis chain, live end to end (no render, no agent loop yet).

    uv run python -m scripts.try_analysis

fetch_boundaries(GM) + fetch_features(health_centre, GM) → aggregate(count)
→ fetch_statistic(population, GM) → normalize(per=10000) → rank(by rate desc) → attach.
Then a quick filter + relate check. Proves the §7 operation set against real API output.
Needs OS_DATA_HUB_KEY (loaded from .env.dev).
"""

from __future__ import annotations

import json

from surveyor.data.store import DatasetStore
from surveyor.manifest import capabilities
from surveyor.tools.analysis.aggregate import Aggregate, AggregateInput
from surveyor.tools.analysis.attach import Attach, AttachInput
from surveyor.tools.analysis.filter import Filter, FilterInput
from surveyor.tools.analysis.normalize import Normalize, NormalizeInput
from surveyor.tools.analysis.rank import Rank, RankInput
from surveyor.tools.analysis.relate import Relate, RelateInput
from surveyor.tools.base import ToolContext
from surveyor.tools.fetch.boundaries import FetchBoundaries, FetchBoundariesInput
from surveyor.tools.fetch.features import FetchFeatures, FetchFeaturesInput
from surveyor.tools.fetch.statistic import FetchStatistic, FetchStatisticInput


class PrintSink:
    def emit(self, event: str, data: dict) -> None:
        print(f"  · {event}: {data}")


def main() -> None:
    store = DatasetStore()
    ctx = ToolContext(store=store, manifest=capabilities, sink=PrintSink())

    def h(outcome):
        return outcome.descriptor["handle"]

    print("→ fetch_boundaries(local_authority, greater_manchester)")
    b = FetchBoundaries().run(
        ctx, FetchBoundariesInput(geography_level="local_authority", region="greater_manchester")
    )
    print("→ fetch_features(health_centre, greater_manchester)")
    f = FetchFeatures().run(
        ctx, FetchFeaturesInput(feature_type="health_centre", region="greater_manchester")
    )
    print("→ aggregate(features, boundaries, count)")
    counts = Aggregate().run(ctx, AggregateInput(features=h(f), boundaries=h(b), op="count"))
    print("→ fetch_statistic(population, greater_manchester)")
    pop = FetchStatistic().run(ctx, FetchStatisticInput(region="greater_manchester"))
    print("→ normalize(counts, population, per=10000)")
    norm = Normalize().run(ctx, NormalizeInput(numerator=h(counts), denominator=h(pop), per=10000))
    print("→ rank(by rate desc)")
    ranked = Rank().run(ctx, RankInput(table=h(norm), by="rate", order="desc"))
    print("→ attach(ranked, boundaries)")
    attached = Attach().run(ctx, AttachInput(table=h(ranked), boundaries=h(b)))

    print("\nhealth-centre provision per 10,000 residents, Greater Manchester LADs (ranked):")
    for r in store.get(h(ranked)).rows:
        rate = r.get("rate")
        rate_str = f"{rate:.3f}" if rate is not None else "n/a"
        print(f"  {r['name']:<24} count={r['count']:>3}  pop={r['population']:>8,}  rate={rate_str}")

    print("\nchoropleth-ready geo descriptor (what render_choropleth will receive):")
    print(json.dumps(attached.descriptor, indent=2))

    print("\n— operation checks —")
    print("→ filter(health centres, 'geometry_area_m2 > 1000')")
    big = Filter().run(ctx, FilterInput(dataset=h(f), where="geometry_area_m2 > 1000"))
    print(f"  kept {big.descriptor['count']} large-footprint health centres")
    print("→ relate(health centres within_distance:100 of GM boundaries)")
    near = Relate().run(
        ctx, RelateInput(features=h(f), reference=h(b), predicate="within_distance:100")
    )
    print(f"  {near.descriptor['count']} health centres within 100m of a GM boundary")


if __name__ == "__main__":
    main()
