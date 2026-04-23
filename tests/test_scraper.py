from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from price_monitor.models import ScrapeStatus
from price_monitor.scraper import fetch_price

_FIXTURES = Path(__file__).parent / "fixtures"
_PRODUCT_ID = 1
_FAKE_URL = "https://www.amazon.com/dp/FAKE"


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.is_success = status_code < 400
    response.status_code = status_code
    response.text = html
    return response


def _patch_get(html: str, status_code: int = 200):
    return patch(
        "price_monitor.scraper.httpx.Client",
        return_value=MagicMock(
            __enter__=lambda s, *a, **kw: MagicMock(
                get=MagicMock(return_value=_mock_response(html, status_code))
            ),
            __exit__=MagicMock(return_value=False),
        ),
    )


def test_fetch_price_ok() -> None:
    html = (_FIXTURES / "product.html").read_text()
    with _patch_get(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.OK
    assert result.price == pytest.approx(29.99)
    assert result.currency == "USD"
    assert result.product_id == _PRODUCT_ID
    assert result.error is None


def test_fetch_price_bot_detected() -> None:
    html = (_FIXTURES / "bot_check.html").read_text()
    with _patch_get(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.BOT_DETECTED
    assert result.price is None
    assert result.error is not None


def test_fetch_price_parse_error() -> None:
    html = "<html><body><p>No price here.</p></body></html>"
    with _patch_get(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.PARSE_ERROR
    assert result.price is None
