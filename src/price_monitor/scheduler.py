from __future__ import annotations

import logging
import random
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from price_monitor.config import AppConfig
from price_monitor.detector import is_drop, drop_pct
from price_monitor.models import PriceDropEvent, Product, ScrapeStatus
from price_monitor.notifier import Notifier
from price_monitor.scraper import fetch_with_retry
from price_monitor.storage import Storage

log = logging.getLogger(__name__)


def check_product(
    product: Product,
    storage: Storage,
    notifier: Notifier,
    threshold_pct: float,
) -> None:
    log.info("tick_started", extra={"product_id": product.id, "product_name": product.name})

    result = fetch_with_retry(product.url, product_id=product.id)
    check_id = storage.save_check(product.id, result)

    log.info(
        "check_completed",
        extra={
            "product_id": product.id,
            "check_id": check_id,
            "status": result.status,
            "price": result.price,
            "attempts": result.attempts,
        },
    )

    if result.status != ScrapeStatus.OK or result.price is None:
        return

    prev_price = storage.get_last_ok_price(product.id, exclude_check_id=check_id)
    if prev_price is None:
        log.info("no_prior_price", extra={"product_id": product.id})
        return

    if is_drop(prev_price, result.price, threshold_pct):
        pct = drop_pct(prev_price, result.price)
        event = PriceDropEvent(
            product=product,
            prev_price=prev_price,
            new_price=result.price,
            drop_pct=pct,
            check_id=check_id,
        )
        delivered = False
        error: str | None = None
        try:
            notifier.send(event)
            delivered = True
        except Exception as exc:
            error = str(exc)
            log.warning("notifier_send_failed", extra={"product_id": product.id, "error": error})
        storage.save_notification(event, delivered=delivered, error=error)


def run_all_checks(storage: Storage, config: AppConfig, notifier: Notifier) -> None:
    products = storage.list_products()
    random.shuffle(products)
    ok_count = 0
    fail_count = 0
    for i, product in enumerate(products):
        try:
            check_product(product, storage, notifier, config.drop_threshold_pct)
            ok_count += 1
        except Exception:
            fail_count += 1
            log.exception("tick_failed_unexpectedly", extra={"product_id": product.id})
        if i < len(products) - 1:
            delay = random.uniform(*config.inter_product_delay)
            log.debug("inter_product_delay", extra={"delay": round(delay, 2)})
            time.sleep(delay)
    log.info("tick_complete", extra={"ok": ok_count, "failed": fail_count})


def build_scheduler(
    storage: Storage, config: AppConfig, notifier: Notifier
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_all_checks,
        trigger=IntervalTrigger(minutes=config.check_interval_minutes, jitter=config.jitter_seconds),
        args=[storage, config, notifier],
        max_instances=1,
        misfire_grace_time=60,
        id="price_check",
        name="Price Check",
        replace_existing=True,
    )
    return scheduler
