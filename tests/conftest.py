from __future__ import annotations

from pathlib import Path

import pytest

from price_monitor.config import AppConfig, load_config
from price_monitor.storage import Storage

_CONFIG_EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", default=False, help="Run live Amazon tests")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip = pytest.mark.skip(reason="Pass --live to run live Amazon tests")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def config() -> AppConfig:
    return load_config(str(_CONFIG_EXAMPLE))


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    yield s
    s.close()
