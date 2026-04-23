from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from price_monitor.config import load_config
from price_monitor.notifier import build_notifier
from price_monitor.scheduler import build_scheduler
from price_monitor.storage import Storage
import price_monitor.dashboard as _dashboard

log = logging.getLogger(__name__)

# Built-in LogRecord attributes that are not user-supplied extras.
_LOG_RECORD_BUILTINS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


class _ExtraFormatter(logging.Formatter):
    """Appends user-supplied extra fields as key=value pairs after the message."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _LOG_RECORD_BUILTINS and not k.startswith("_")
        }
        if extras:
            pairs = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base}  {pairs}"
        return base


def _setup_logging(log_dir: str = "logs") -> None:
    Path(log_dir).mkdir(exist_ok=True)
    fmt = _ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "price_monitor.log"),
        when="h",
        interval=1,
        backupCount=720,
        utc=True,
    )
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


def main(config_path: str = "config.yaml") -> None:
    _setup_logging()
    cfg = load_config(config_path)

    storage = Storage(cfg.db_path)
    for product_cfg in cfg.products:
        storage.upsert_product(product_cfg.url, product_cfg.name)

    notifier = build_notifier(cfg.notification_channels)
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
