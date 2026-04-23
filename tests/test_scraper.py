from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from price_monitor.models import ScrapeStatus
from price_monitor.scraper import fetch_price, _extract_price_from_json

_FIXTURES = Path(__file__).parent / "fixtures"
_PRODUCT_ID = 1
_FAKE_URL = "https://www.amazon.com/dp/FAKE"


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.ok = status_code < 400
    response.status_code = status_code
    response.text = html
    return response


def _patch_session(html: str, status_code: int = 200):
    """Patch curl_cffi Session so no real HTTP request is made."""
    mock_session = MagicMock()
    mock_session.get.return_value = _mock_response(html, status_code)
    mock_session.__enter__ = lambda s: mock_session
    mock_session.__exit__ = MagicMock(return_value=False)
    return patch(
        "price_monitor.scraper.cffi_requests.Session",
        return_value=mock_session,
    )


def test_fetch_price_ok() -> None:
    html = (_FIXTURES / "product.html").read_text()
    with _patch_session(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.OK
    assert result.price == pytest.approx(29.99)
    assert result.currency == "USD"
    assert result.product_id == _PRODUCT_ID
    assert result.error is None


def test_fetch_price_bot_detected() -> None:
    html = (_FIXTURES / "bot_check.html").read_text()
    with _patch_session(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.BOT_DETECTED
    assert result.price is None
    assert result.error is not None


def test_fetch_price_parse_error() -> None:
    html = "<html><body><p>No price here.</p></body></html>"
    with _patch_session(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.PARSE_ERROR
    assert result.price is None


def test_fetch_price_http_error() -> None:
    html = "<html><body>Forbidden</body></html>"
    with _patch_session(html, status_code=403):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.HTTP_ERROR
    assert result.error == "HTTP 403"


def test_fetch_price_falls_back_to_json_when_selector_empty() -> None:
    """Selector element exists but is empty (JS-rendered) — should fall through to JSON."""
    html = """
    <html><body>
    <div id="corePriceDisplay_desktop_feature_div">
      <span class="a-price"><span class="a-offscreen"></span></span>
    </div>
    <script>var data = {"priceAmount": 49.99};</script>
    </body></html>
    """
    with _patch_session(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.OK
    assert result.price == pytest.approx(49.99)


def test_fetch_price_parse_error_when_no_json_fallback() -> None:
    """No selector match and no priceAmount JSON → PARSE_ERROR."""
    html = "<html><body><p>No price anywhere.</p></body></html>"
    with _patch_session(html):
        result = fetch_price(_FAKE_URL, _PRODUCT_ID)

    assert result.status == ScrapeStatus.PARSE_ERROR
    assert result.price is None


def test_extract_price_from_json() -> None:
    assert _extract_price_from_json('{"priceAmount": 29.99}') == pytest.approx(29.99)
    assert _extract_price_from_json('no price here') is None
    assert _extract_price_from_json('"priceAmount" : 0.00') == pytest.approx(0.0)  # caller guards > 0
