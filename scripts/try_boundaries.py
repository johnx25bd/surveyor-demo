"""Phase-1 smoke: run fetch_boundaries live against the ArcGIS service and print the descriptor.

    uv run python -m scripts.try_boundaries

Proves the data model + DatasetStore + ArcGIS source client + the Tool contract end to end against
the real API — no key needed (the boundary service is open).
"""

from __future__ import annotations

import json

from surveyor.data.store import DatasetStore
from surveyor.manifest import capabilities
from surveyor.tools.base import ToolContext
from surveyor.tools.fetch.boundaries import FetchBoundaries, FetchBoundariesInput


class PrintSink:
    def emit(self, event: str, data: dict) -> None:
        print(f"  · {event}: {data}")


def main() -> None:
    store = DatasetStore()
    ctx = ToolContext(store=store, manifest=capabilities, sink=PrintSink())
    tool = FetchBoundaries()

    print("→ fetch_boundaries(geography_level='local_authority', region='greater_manchester')")
    outcome = tool.run(
        ctx,
        FetchBoundariesInput(geography_level="local_authority", region="greater_manchester"),
    )

    print("← descriptor (what the model sees):")
    print(json.dumps(outcome.descriptor, indent=2))

    dataset = store.get(outcome.descriptor["handle"])
    first = dataset.features["features"][0]["properties"]
    print(f"\nstore holds {dataset.count} features ({dataset.geometry_type}); first = {first}")


if __name__ == "__main__":
    main()
