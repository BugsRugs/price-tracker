from __future__ import annotations

from price_monitor.models import PriceDropEvent, Product
from price_monitor.notifier import ConsoleNotifier, ToastNotifier, build_notifier


def _make_event() -> PriceDropEvent:
    product = Product(id=1, url="https://www.amazon.com/dp/FAKE", name="Test Paddle")
    return PriceDropEvent(
        product=product,
        prev_price=100.0,
        new_price=75.0,
        drop_pct=25.0,
        check_id=1,
    )


def test_console_notifier_prints_banner(capsys) -> None:
    event = _make_event()
    ConsoleNotifier().send(event)
    captured = capsys.readouterr()
    assert "Test Paddle" in captured.out
    assert "75.00" in captured.out
    assert "100.00" in captured.out


def test_build_notifier_factory_returns_correct_class() -> None:
    assert isinstance(build_notifier("console"), ConsoleNotifier)
    assert isinstance(build_notifier("toast"), ToastNotifier)
