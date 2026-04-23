from __future__ import annotations

import logging
import subprocess
import sys
from typing import Protocol

from price_monitor.models import PriceDropEvent

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, event: PriceDropEvent) -> None: ...


_BOLD_GREEN = "\033[1;32m"
_RESET = "\033[0m"


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
        g = _BOLD_GREEN
        r = _RESET
        print(
            f"\n{g}{'=' * 60}{r}\n"
            f"{g}  PRICE DROP ALERT{r}\n"
            f"{g}  {event.product.name}{r}\n"
            f"{g}  ${event.prev_price:.2f} → ${event.new_price:.2f}  ({event.drop_pct:.1f}% off){r}\n"
            f"{g}  {event.product.url}{r}\n"
            f"{g}{'=' * 60}{r}\n"
        )


class DesktopNotifier:
    """Persistent OS notification + audio alert.

    On Linux, calls notify-send directly so that --expire-time=0 and
    --urgency=critical can be set — this keeps the banner on-screen until
    the user explicitly dismisses it, which plyer's wrapper does not expose.
    Other platforms fall back to plyer.
    """

    def send(self, event: PriceDropEvent) -> None:
        title = f"Price Drop: {event.product.name}"
        message = (
            f"${event.prev_price:.2f} → ${event.new_price:.2f} "
            f"({event.drop_pct:.1f}% off)"
        )

        if sys.platform == "linux":
            self._notify_send(event, title, message)
        else:
            self._plyer_notify(event, title, message)

    def _notify_send(
        self, event: PriceDropEvent, title: str, message: str
    ) -> None:
        """Send a persistent notification via notify-send (Linux)."""
        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "--expire-time=0",   # stay until the user clicks X
                    "--urgency=critical",
                    "--app-name=Price Monitor",
                    title,
                    message,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info(
                "desktop_notification_sent",
                extra={"product_id": event.product.id, "drop_pct": event.drop_pct},
            )
        except Exception as exc:
            log.warning(
                "desktop_notification_failed",
                extra={"product_id": event.product.id, "error": str(exc)},
            )

    def _plyer_notify(
        self, event: PriceDropEvent, title: str, message: str
    ) -> None:
        """Send a notification via plyer (macOS / Windows fallback)."""
        try:
            from plyer import notification  # type: ignore[import-untyped]

            notification.notify(
                title=title,
                message=message,
                app_name="Price Monitor",
                timeout=0,
            )
            log.info(
                "desktop_notification_sent",
                extra={"product_id": event.product.id, "drop_pct": event.drop_pct},
            )
        except Exception as exc:
            log.warning(
                "desktop_notification_failed",
                extra={"product_id": event.product.id, "error": str(exc)},
            )


class CompositeNotifier:
    """Chains multiple notifiers. A failure in one never blocks the rest."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    def send(self, event: PriceDropEvent) -> None:
        for notifier in self._notifiers:
            try:
                notifier.send(event)
            except Exception as exc:
                log.warning(
                    "notifier_child_failed",
                    extra={
                        "notifier": type(notifier).__name__,
                        "product_id": event.product.id,
                        "error": str(exc),
                    },
                )


def _make_one(channel: str) -> Notifier:
    if channel == "console":
        return ConsoleNotifier()
    if channel == "desktop":
        return DesktopNotifier()
    raise ValueError(f"unknown notification channel: {channel!r}")


def build_notifier(channels: list[str]) -> Notifier:
    """Build a notifier from a list of channel names.

    A single channel returns that notifier directly; multiple channels
    are wrapped in a CompositeNotifier so all fire on each event.
    """
    if not channels:
        raise ValueError("at least one notification channel must be specified")
    notifiers = [_make_one(ch) for ch in channels]
    if len(notifiers) == 1:
        return notifiers[0]
    return CompositeNotifier(notifiers)
