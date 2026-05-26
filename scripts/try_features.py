"""Phase-1 smoke: fetch_features (health centres) live from OS NGD, scoped to Greater Manchester.

    uv run python -m scripts.try_features

Needs OS_DATA_HUB_KEY (loaded from .env.dev by surveyor.config). Proves the OS NGD client's
header auth, server-side CQL, and rel="next" paging end to end against the real premium API.
"""

from __future__ import annotations

import json

from surveyor.data.store import DatasetStore
from surveyor.manifest import capabilities
from surveyor.tools.base import ToolContext
from surveyor.tools.fetch.features import FetchFeatures, FetchFeaturesInput


class PrintSink:
    def emit(self, event: str, data: dict) -> None:
        print(f"  · {event}: {data}")


def main() -> None:
    store = DatasetStore()
    ctx = ToolContext(store=store, manifest=capabilities, sink=PrintSink())
    tool = FetchFeatures()

    print("→ fetch_features(feature_type='health_centre', region='greater_manchester')")
    outcome = tool.run(
        ctx, FetchFeaturesInput(feature_type="health_centre", region="greater_manchester")
    )

    print("← descriptor (what the model sees):")
    print(json.dumps(outcome.descriptor, indent=2))

    dataset = store.get(outcome.descriptor["handle"])
    print(f"\nstore holds {dataset.count} features ({dataset.geometry_type})")


if __name__ == "__main__":
    main()
