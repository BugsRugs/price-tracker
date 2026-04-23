from __future__ import annotations

from pathlib import Path

import pytest

from price_monitor.config import AppConfig, load_config
from price_monitor.storage import Storage

_CONFIG_EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


@pytest.fixture(scope="session")
def config() -> AppConfig:
    return load_config(str(_CONFIG_EXAMPLE))


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    yield s
    s.close()
