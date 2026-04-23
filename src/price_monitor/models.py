from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ScrapeStatus(StrEnum):
    OK = "ok"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    BOT_DETECTED = "bot_detected"
    PARSE_ERROR = "parse_error"
    PRICE_INVALID = "price_invalid"


@dataclass(frozen=True)
class ScrapeResult:
    product_id: int
    status: ScrapeStatus
    checked_at: str
    attempts: int
    price: float | None = None
    currency: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Product:
    id: int
    url: str
    name: str


@dataclass(frozen=True)
class PriceDropEvent:
    product: Product
    prev_price: float
    new_price: float
    drop_pct: float
    check_id: int
