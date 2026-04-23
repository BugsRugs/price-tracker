from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

log = logging.getLogger(__name__)


class ProductConfig(BaseModel):
    url: str
    name: str


class AppConfig(BaseModel):
    products: list[ProductConfig]
    check_interval_minutes: int = 60
    drop_threshold_pct: float = 5.0
    notification_channel: str = "console"
    db_path: str = "price_monitor.db"

    @field_validator("products")
    @classmethod
    def at_least_one_product(cls, v: list[ProductConfig]) -> list[ProductConfig]:
        if not v:
            raise ValueError("config must contain at least one product")
        return v

    @field_validator("drop_threshold_pct")
    @classmethod
    def positive_threshold(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("drop_threshold_pct must be positive")
        return v

    @field_validator("check_interval_minutes")
    @classmethod
    def positive_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("check_interval_minutes must be >= 1")
        return v


def load_config(path: str = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        log.critical("config_not_found", extra={"path": path})
        raise FileNotFoundError(f"Config file not found: {path}")

    with config_path.open() as f:
        raw = yaml.safe_load(f)

    log.info("config_loaded", extra={"path": path, "product_count": len(raw.get("products", []))})
    return AppConfig.model_validate(raw)
