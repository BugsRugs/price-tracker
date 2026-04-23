from __future__ import annotations

from datetime import datetime, timezone

import pytest

from price_monitor.config import AppConfig
from price_monitor.models import PriceDropEvent, Product, ScrapeResult, ScrapeStatus
from price_monitor.storage import Storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok_result(product_id: int, price: float, checked_at: str | None = None) -> ScrapeResult:
    return ScrapeResult(
        product_id=product_id,
        status=ScrapeStatus.OK,
        checked_at=checked_at or _now(),
        attempts=1,
        price=price,
        currency="USD",
    )


def _fail_result(product_id: int) -> ScrapeResult:
    return ScrapeResult(
        product_id=product_id,
        status=ScrapeStatus.NETWORK_ERROR,
        checked_at=_now(),
        attempts=3,
        error="connection refused",
    )


def test_upsert_product_roundtrip(storage: Storage, config: AppConfig) -> None:
    p = config.products[0]
    pid = storage.upsert_product(p.url, p.name)
    products = storage.list_products()

    assert len(products) == 1
    assert products[0].id == pid
    assert products[0].url == p.url
    assert products[0].name == p.name


def test_save_ok_and_failed_check_last_ok_ignores_failure(storage: Storage, config: AppConfig) -> None:
    p = config.products[0]
    pid = storage.upsert_product(p.url, p.name)

    storage.save_check(pid, _ok_result(pid, price=99.99))
    storage.save_check(pid, _fail_result(pid))

    last_ok = storage.get_last_ok_price(pid)
    assert last_ok == pytest.approx(99.99)


def test_get_last_ok_price_exclude_check_id_returns_prior(storage: Storage, config: AppConfig) -> None:
    p = config.products[0]
    pid = storage.upsert_product(p.url, p.name)

    t1 = "2026-01-01T00:00:00+00:00"
    t2 = "2026-01-02T00:00:00+00:00"

    storage.save_check(pid, _ok_result(pid, price=50.00, checked_at=t1))
    check_id_2 = storage.save_check(pid, _ok_result(pid, price=45.00, checked_at=t2))

    prior = storage.get_last_ok_price(pid, exclude_check_id=check_id_2)
    assert prior == pytest.approx(50.00)


def test_save_notification_read_back(storage: Storage, config: AppConfig) -> None:
    p = config.products[0]
    pid = storage.upsert_product(p.url, p.name)
    check_id = storage.save_check(pid, _ok_result(pid, price=30.00))

    product = Product(id=pid, url=p.url, name=p.name)
    event = PriceDropEvent(
        product=product,
        prev_price=100.00,
        new_price=30.00,
        drop_pct=70.0,
        check_id=check_id,
    )

    storage.save_notification(event, delivered=False, error="plyer unavailable")

    notifications = storage.recent_notifications(limit=10)
    assert len(notifications) == 1
    n = notifications[0]
    assert n["delivered"] == 0
    assert n["error"] == "plyer unavailable"
    assert n["prev_price"] == pytest.approx(100.00)
    assert n["new_price"] == pytest.approx(30.00)
    assert n["drop_pct"] == pytest.approx(70.0)
    assert n["product_name"] == p.name
