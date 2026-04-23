from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from price_monitor.config import load_config
from price_monitor.notifier import build_notifier
from price_monitor.scheduler import build_scheduler
from price_monitor.storage import Storage
import price_monitor.dashboard as _dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def main(config_path: str = "config.yaml") -> None:
    cfg = load_config(config_path)

    storage = Storage(cfg.db_path)
    for product_cfg in cfg.products:
        storage.upsert_product(product_cfg.url, product_cfg.name)

    notifier = build_notifier(cfg.notification_channel)
    scheduler = build_scheduler(storage, cfg, notifier)

    _dashboard.set_storage(storage)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        scheduler.start()
        log.info("scheduler_started", extra={"interval_min": cfg.check_interval_minutes})
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            storage.close()
            log.info("scheduler_stopped")

    _dashboard.app.router.lifespan_context = lifespan

    uvicorn.run(
        _dashboard.app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
