"""Phase-1 smoke: fetch_statistic (population) live from Nomis, scoped to Greater Manchester.

    uv run python -m scripts.try_statistic
"""

from __future__ import annotations

import json

from surveyor.data.store import DatasetStore
from surveyor.manifest import capabilities
from surveyor.tools.base import ToolContext
from surveyor.tools.fetch.statistic import FetchStatistic, FetchStatisticInput


class PrintSink:
    def emit(self, event: str, data: dict) -> None:
        print(f"  · {event}: {data}")


def main() -> None:
    store = DatasetStore()
    ctx = ToolContext(store=store, manifest=capabilities, sink=PrintSink())
    tool = FetchStatistic()

    print("→ fetch_statistic(metric='population', region='greater_manchester')")
    outcome = tool.run(ctx, FetchStatisticInput(region="greater_manchester"))
    print("← descriptor:")
    print(json.dumps(outcome.descriptor, indent=2))

    dataset = store.get(outcome.descriptor["handle"])
    print(f"\nstore holds {dataset.count} rows:")
    for row in dataset.rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
