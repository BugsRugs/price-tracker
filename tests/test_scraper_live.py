"""Live diagnostic tests — hit real Amazon URLs to check scraper health.

These are skipped in the normal test run. Run explicitly with:

    pytest tests/test_scraper_live.py -v -s --live

or to run just one product:

    pytest tests/test_scraper_live.py::test_live_stiga -v -s --live
"""
from __future__ import annotations

from pathlib import Path

import pytest
from curl_cffi import requests as cffi_requests
from selectolax.parser import HTMLParser

from price_monitor.scraper import (
    AMAZON_PRICE_SELECTORS,
    BOT_SIGNATURES,
    _HEADERS,
    fetch_price,
    fetch_with_retry,
)
from price_monitor.models import ScrapeStatus
from price_monitor.config import load_config


pytestmark = pytest.mark.live

# ---------------------------------------------------------------------------
# Shared URLs (same as config.example.yaml)
# ---------------------------------------------------------------------------

_STIGA_URL = (
    "https://www.amazon.com/STIGA-Evolution-Performance-Level-Approved-Tournament/dp/B00EFY9F1C/"
)
_NITTAKU_URL = (
    "https://www.amazon.com/Nittaku-3-stars-Premium-Table-Tennis/dp/B012WAQVYE/"
)
_BUTTERFLY_URL = (
    "https://www.amazon.com/Butterfly-Mens-Lezoline-Reiss-Shoes/dp/B0BG19DBTR/"
)

_ALL_URLS = [
    ("STIGA Ping Pong Paddles", _STIGA_URL),
    ("NITTAKU Balls", _NITTAKU_URL),
    ("Butterfly Shoes", _BUTTERFLY_URL),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _diagnose_response(name: str, url: str) -> dict:
    """Fetch URL and return a diagnosis dict with everything we can observe."""
    with cffi_requests.Session(impersonate="chrome124") as session:
        resp = session.get(url, headers=_HEADERS, timeout=20)

    body = resp.text
    body_lower = body.lower()

    # bot detection
    bot_hit = next((sig for sig in BOT_SIGNATURES if sig in body_lower), None)

    # price selector match
    tree = HTMLParser(body)
    price_match = None
    price_text = None
    for sel in AMAZON_PRICE_SELECTORS:
        node = tree.css_first(sel)
        if node:
            price_match = sel
            price_text = node.text(strip=True)
            break

    # page title
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else "(no title)"

    # key structural markers
    has_add_to_cart = "add to cart" in body_lower or "addtocart" in body_lower
    has_product_title = bool(tree.css_first("#productTitle"))
    has_captcha = "captcha" in body_lower

    return {
        "name": name,
        "url": url,
        "status_code": resp.status_code,
        "ok": resp.ok,
        "title": title,
        "bot_signature": bot_hit,
        "has_captcha": has_captcha,
        "price_selector_hit": price_match,
        "price_text": price_text,
        "has_add_to_cart": has_add_to_cart,
        "has_product_title": has_product_title,
        "body_length": len(body),
    }


def _print_diagnosis(d: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Product  : {d['name']}")
    print(f"  HTTP     : {d['status_code']} ({'ok' if d['ok'] else 'error'})")
    print(f"  Title    : {d['title']}")
    print(f"  Body len : {d['body_length']:,} bytes")
    print(f"  Bot sig  : {d['bot_signature'] or 'none'}")
    print(f"  Captcha  : {d['has_captcha']}")
    print(f"  #productTitle : {d['has_product_title']}")
    print(f"  Add-to-cart   : {d['has_add_to_cart']}")
    print(f"  Price selector: {d['price_selector_hit'] or 'none'}")
    print(f"  Price text    : {d['price_text'] or 'none'}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Diagnostic tests — these always pass; they print what we observe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,url", _ALL_URLS)
def test_raw_response_diagnosis(name: str, url: str) -> None:
    """Print a full diagnosis for each product URL. Never fails on bot-detection —
    the output tells us exactly where in the response pipeline we're blocked."""
    d = _diagnose_response(name, url)
    _print_diagnosis(d)

    # soft assertions — these print clearly in -s output without hiding the diagnosis
    if d["bot_signature"]:
        pytest.skip(f"Bot detected via signature: {d['bot_signature']!r} — see diagnosis above")

    if not d["ok"]:
        pytest.skip(f"HTTP {d['status_code']} — see diagnosis above")


# ---------------------------------------------------------------------------
# Assertion tests — only pass if we genuinely reached the product page
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,url", _ALL_URLS)
def test_product_page_reached(name: str, url: str) -> None:
    """Assert that we see product-page structure (title element, add-to-cart)."""
    d = _diagnose_response(name, url)
    _print_diagnosis(d)

    if d["bot_signature"] or d["has_captcha"]:
        pytest.skip(f"Blocked by bot detection: {d['bot_signature']}")

    assert d["ok"], f"Expected 200 OK, got {d['status_code']}"
    assert d["has_product_title"] or d["has_add_to_cart"], (
        "Neither #productTitle nor add-to-cart found — may be on wrong page. "
        f"Page title: {d['title']!r}"
    )


@pytest.mark.parametrize("name,url", _ALL_URLS)
def test_price_selector_matches(name: str, url: str) -> None:
    """Assert that at least one AMAZON_PRICE_SELECTORS matches and yields a parseable price."""
    d = _diagnose_response(name, url)
    _print_diagnosis(d)

    if d["bot_signature"] or d["has_captcha"]:
        pytest.skip(f"Blocked by bot detection: {d['bot_signature']}")

    assert d["price_selector_hit"] is not None, (
        f"No price selector matched. Page title: {d['title']!r}"
    )
    assert d["price_text"], "Selector matched but text was empty"

    price_clean = d["price_text"].lstrip("$£€").replace(",", "").strip()
    price = float(price_clean)
    assert price > 0, f"Price parsed as non-positive: {price}"
    print(f"\n  Parsed price: ${price:.2f}")


# ---------------------------------------------------------------------------
# End-to-end pipeline test (fetch_price + fetch_with_retry)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,url", _ALL_URLS)
def test_fetch_price_live(name: str, url: str) -> None:
    """Run fetch_price (the real scraper function) and report the ScrapeResult."""
    result = fetch_price(url, product_id=1)
    print(f"\n  {name}: status={result.status} price={result.price} error={result.error}")

    assert result.status in {
        ScrapeStatus.OK,
        ScrapeStatus.BOT_DETECTED,
        ScrapeStatus.PARSE_ERROR,
        ScrapeStatus.PRICE_INVALID,
    }, f"Unexpected error status: {result.status} — {result.error}"

    if result.status == ScrapeStatus.BOT_DETECTED:
        pytest.skip(f"Bot detected for {name} — curl_cffi impersonation not sufficient")

    assert result.status == ScrapeStatus.OK, (
        f"Expected OK for {name}, got {result.status}: {result.error}"
    )
    assert result.price is not None and result.price > 0
    print(f"  SUCCESS — price=${result.price:.2f}")
