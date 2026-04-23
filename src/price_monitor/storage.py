from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from price_monitor.models import PriceDropEvent, Product, ScrapeResult, ScrapeStatus

log = logging.getLogger(__name__)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS products (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    url     TEXT    NOT NULL UNIQUE,
    name    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS price_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    checked_at  TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    price       REAL,
    currency    TEXT,
    attempts    INTEGER NOT NULL DEFAULT 1,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    check_id    INTEGER NOT NULL REFERENCES price_checks(id),
    fired_at    TEXT    NOT NULL,
    prev_price  REAL    NOT NULL,
    new_price   REAL    NOT NULL,
    drop_pct    REAL    NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        log.info("storage_opened", extra={"db_path": db_path})

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- products ---

    def upsert_product(self, url: str, name: str) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO products (url, name) VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE SET name=excluded.name
            RETURNING id
            """,
            (url, name),
        )
        row = cur.fetchone()
        self._conn.commit()
        product_id: int = row["id"]
        log.debug("product_upserted", extra={"product_id": product_id, "url": url})
        return product_id

    def list_products(self) -> list[Product]:
        cur = self._conn.execute("SELECT id, url, name FROM products ORDER BY id")
        return [Product(id=r["id"], url=r["url"], name=r["name"]) for r in cur.fetchall()]

    # --- price checks ---

    def save_check(self, product_id: int, result: ScrapeResult) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO price_checks
                (product_id, checked_at, status, price, currency, attempts, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                product_id,
                result.checked_at,
                result.status.value,
                result.price,
                result.currency,
                result.attempts,
                result.error,
            ),
        )
        row = cur.fetchone()
        self._conn.commit()
        check_id: int = row["id"]
        log.debug(
            "check_saved",
            extra={"check_id": check_id, "product_id": product_id, "status": result.status},
        )
        return check_id

    def get_last_ok_price(
        self, product_id: int, exclude_check_id: int | None = None
    ) -> float | None:
        if exclude_check_id is not None:
            cur = self._conn.execute(
                """
                SELECT price FROM price_checks
                WHERE product_id = ? AND status = ? AND id != ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (product_id, ScrapeStatus.OK.value, exclude_check_id),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT price FROM price_checks
                WHERE product_id = ? AND status = ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (product_id, ScrapeStatus.OK.value),
            )
        row = cur.fetchone()
        return float(row["price"]) if row and row["price"] is not None else None

    def get_history(self, product_id: int, days: int = 30) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            """
            SELECT id, checked_at, status, price, currency, attempts, error
            FROM price_checks
            WHERE product_id = ? AND checked_at >= ?
            ORDER BY checked_at ASC
            """,
            (product_id, cutoff),
        )
        return [dict(r) for r in cur.fetchall()]

    # --- notifications ---

    def save_notification(
        self, event: PriceDropEvent, delivered: bool, error: str | None = None
    ) -> int:
        fired_at = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO notifications
                (product_id, check_id, fired_at, prev_price, new_price, drop_pct, delivered, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                event.product.id,
                event.check_id,
                fired_at,
                event.prev_price,
                event.new_price,
                event.drop_pct,
                int(delivered),
                error,
            ),
        )
        row = cur.fetchone()
        self._conn.commit()
        notification_id: int = row["id"]
        log.debug(
            "notification_saved",
            extra={"notification_id": notification_id, "delivered": delivered},
        )
        return notification_id

    def recent_notifications(self, limit: int = 10) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT n.id, n.fired_at, n.prev_price, n.new_price, n.drop_pct,
                   n.delivered, n.error, p.name AS product_name, p.url AS product_url
            FROM notifications n
            JOIN products p ON p.id = n.product_id
            ORDER BY n.fired_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
        log.debug("storage_closed", extra={"db_path": self._db_path})
