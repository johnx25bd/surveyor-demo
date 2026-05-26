"""os_maps_key precedence: a dedicated maps key wins, else reuse the NGD key, else raise."""

from __future__ import annotations

import pytest

from surveyor import config


def test_prefers_dedicated_maps_key(monkeypatch):
    monkeypatch.setenv("OS_MAPS_API_KEY", "maps-key")
    monkeypatch.setenv("OS_DATA_HUB_KEY", "ngd-key")
    assert config.os_maps_key() == "maps-key"


def test_falls_back_to_data_hub_key(monkeypatch):
    monkeypatch.delenv("OS_MAPS_API_KEY", raising=False)
    monkeypatch.setenv("OS_DATA_HUB_KEY", "ngd-key")
    assert config.os_maps_key() == "ngd-key"


def test_raises_when_neither_is_set(monkeypatch):
    monkeypatch.delenv("OS_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("OS_DATA_HUB_KEY", raising=False)
    with pytest.raises(config.ConfigError):
        config.os_maps_key()
