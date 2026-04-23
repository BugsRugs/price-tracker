from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from price_monitor.models import PriceDropEvent, Product
from price_monitor.notifier import (
    CompositeNotifier,
    ConsoleNotifier,
    DesktopNotifier,
    build_notifier,
)


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


def test_build_notifier_returns_single_notifier_for_one_channel() -> None:
    assert isinstance(build_notifier(["console"]), ConsoleNotifier)
    assert isinstance(build_notifier(["desktop"]), DesktopNotifier)


def test_build_notifier_returns_composite_for_multiple_channels() -> None:
    notifier = build_notifier(["console", "desktop"])
    assert isinstance(notifier, CompositeNotifier)


def test_build_notifier_raises_for_empty_channels() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_notifier([])


def test_build_notifier_raises_for_unknown_channel() -> None:
    with pytest.raises(ValueError, match="unknown notification channel"):
        build_notifier(["slack"])


def test_composite_notifier_calls_all_children() -> None:
    event = _make_event()
    a = MagicMock()
    b = MagicMock()
    CompositeNotifier([a, b]).send(event)
    a.send.assert_called_once_with(event)
    b.send.assert_called_once_with(event)


def test_composite_notifier_continues_after_child_failure() -> None:
    event = _make_event()
    failing = MagicMock()
    failing.send.side_effect = RuntimeError("boom")
    healthy = MagicMock()
    CompositeNotifier([failing, healthy]).send(event)
    healthy.send.assert_called_once_with(event)


def test_desktop_notifier_sends_persistent_notification_on_linux(monkeypatch) -> None:
    """On Linux, notify-send must be called with --expire-time=0 and --urgency=critical."""
    event = _make_event()
    monkeypatch.setattr("price_monitor.notifier.sys.platform", "linux")

    with patch("price_monitor.notifier.subprocess.Popen") as mock_popen:
        DesktopNotifier().send(event)

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args.args[0]
    assert "notify-send" in cmd
    assert "--expire-time=0" in cmd
    assert "--urgency=critical" in cmd
    assert any("Test Paddle" in arg for arg in cmd)
    assert any("75.00" in arg for arg in cmd)


def test_desktop_notifier_handles_notify_send_failure() -> None:
    """A broken notify-send must not propagate."""
    event = _make_event()
    with patch(
        "price_monitor.notifier.subprocess.Popen",
        side_effect=FileNotFoundError("notify-send not found"),
    ):
        DesktopNotifier().send(event)  # must not raise


def test_desktop_notifier_plyer_fallback_on_non_linux(monkeypatch) -> None:
    """On non-Linux platforms, plyer is used instead of notify-send."""
    event = _make_event()
    monkeypatch.setattr("price_monitor.notifier.sys.platform", "darwin")

    mock_plyer = MagicMock()
    mock_notify = MagicMock()
    mock_plyer.notification.notify = mock_notify

    with patch.dict("sys.modules", {"plyer": mock_plyer}):
        DesktopNotifier().send(event)

    mock_notify.assert_called_once()
    kw = mock_notify.call_args.kwargs
    assert "Test Paddle" in kw["title"]
    assert "75.00" in kw["message"]
