from __future__ import annotations

import logging
from typing import Protocol

from price_monitor.models import PriceDropEvent

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, event: PriceDropEvent) -> None: ...


class ConsoleNotifier:
    def send(self, event: PriceDropEvent) -> None:
        log.warning(
            "drop_detected",
            extra={
                "product_id": event.product.id,
                "product_name": event.product.name,
                "prev_price": event.prev_price,
                "new_price": event.new_price,
                "drop_pct": round(event.drop_pct, 2),
            },
        )
        print(
            f"\n{'=' * 60}\n"
            f"  PRICE DROP ALERT\n"
            f"  {event.product.name}\n"
            f"  ${event.prev_price:.2f} → ${event.new_price:.2f}"
            f"  ({event.drop_pct:.1f}% off)\n"
            f"  {event.product.url}\n"
            f"{'=' * 60}\n"
        )


class ToastNotifier:
    def send(self, event: PriceDropEvent) -> None:
        try:
            from plyer import notification  # type: ignore[import-untyped]

            notification.notify(
                title=f"Price Drop: {event.product.name}",
                message=(
                    f"${event.prev_price:.2f} → ${event.new_price:.2f} "
                    f"({event.drop_pct:.1f}% off)"
                ),
                app_name="Price Monitor",
                timeout=10,
            )
            log.info(
                "toast_sent",
                extra={"product_id": event.product.id, "drop_pct": event.drop_pct},
            )
        except Exception as exc:
            log.warning(
                "toast_failed",
                extra={"product_id": event.product.id, "error": str(exc)},
            )


def build_notifier(channel: str) -> Notifier:
    if channel == "console":
        return ConsoleNotifier()
    if channel == "toast":
        return ToastNotifier()
    raise ValueError(f"unknown notification channel: {channel!r}")
