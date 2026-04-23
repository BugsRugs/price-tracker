from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError
from curl_cffi.requests.exceptions import RequestException as CurlRequestException
from curl_cffi.requests.exceptions import Timeout as CurlTimeout
from selectolax.parser import HTMLParser

from price_monitor.models import ScrapeResult, ScrapeStatus

log = logging.getLogger(__name__)

AMAZON_PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#corePrice_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
    ".a-price .a-offscreen",
]

BOT_SIGNATURES = [
    "robot check",
    "/errors/validatecaptcha",
    "enter the characters you see",
    "api-services-support@amazon",
]

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
]

_HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def _build_headers() -> dict[str, str]:
    return {**_HEADERS_BASE, "User-Agent": random.choice(_USER_AGENTS)}


_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")


def _canonical_url(url: str) -> str:
    """Strip tracking params and reduce to the clean /dp/ASIN form.

    Removes referrer tokens (dib=, crid=, ref=, etc.) that signal the request
    originated from a search-results page rather than direct navigation.
    Falls back to stripping only the query string for non-ASIN URLs.
    """
    m = _ASIN_RE.search(url)
    if m:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, f"/dp/{m.group(1)}", "", "", ""))
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

_RETRYABLE = {ScrapeStatus.NETWORK_ERROR, ScrapeStatus.HTTP_ERROR}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_price(text: str) -> float | None:
    cleaned = text.strip().lstrip("$£€").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


# Amazon embeds structured data in every page as inline JSON. The price is
# available under "priceAmount" even when the visible DOM element is empty
# because JS hasn't executed.
_PRICE_AMOUNT_RE = re.compile(r'"priceAmount"\s*:\s*([\d]+\.[\d]+)')


def _extract_price_from_json(body: str) -> float | None:
    """Extract the first priceAmount value from Amazon's embedded JSON blobs."""
    match = _PRICE_AMOUNT_RE.search(body)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def fetch_price(url: str, product_id: int) -> ScrapeResult:
    checked_at = _now()
    url = _canonical_url(url)
    try:
        with cffi_requests.Session(impersonate="chrome124") as session:
            response = session.get(url, headers=_build_headers(), timeout=15)
    except (CurlConnectionError, CurlTimeout) as exc:
        log.warning(
            "scrape_network_error",
            extra={"product_id": product_id, "url": url, "error": str(exc)},
        )
        return ScrapeResult(
            product_id=product_id,
            status=ScrapeStatus.NETWORK_ERROR,
            checked_at=checked_at,
            attempts=1,
            error=str(exc),
        )
    except CurlRequestException as exc:
        log.warning(
            "scrape_http_error",
            extra={"product_id": product_id, "url": url, "error": str(exc)},
        )
        return ScrapeResult(
            product_id=product_id,
            status=ScrapeStatus.HTTP_ERROR,
            checked_at=checked_at,
            attempts=1,
            error=str(exc),
        )

    if not response.ok:
        log.warning(
            "scrape_http_error",
            extra={"product_id": product_id, "url": url, "status_code": response.status_code},
        )
        return ScrapeResult(
            product_id=product_id,
            status=ScrapeStatus.HTTP_ERROR,
            checked_at=checked_at,
            attempts=1,
            error=f"HTTP {response.status_code}",
        )


    body = response.text.lower()
    for sig in BOT_SIGNATURES:
        if sig in body:
            log.warning(
                "scrape_bot_detected",
                extra={"product_id": product_id, "url": url, "signature": sig},
            )
            return ScrapeResult(
                product_id=product_id,
                status=ScrapeStatus.BOT_DETECTED,
                checked_at=checked_at,
                attempts=1,
                error=f"bot signature detected: {sig!r}",
            )

    tree = HTMLParser(response.text)
    for selector in AMAZON_PRICE_SELECTORS:
        node = tree.css_first(selector)
        if node is None:
            continue
        raw_text = node.text(strip=True)
        if not raw_text:
            # Element exists but is empty — price is JS-rendered; keep trying.
            log.debug("selector_empty", extra={"product_id": product_id, "selector": selector})
            continue
        log.debug(
            "selector_matched",
            extra={"product_id": product_id, "selector": selector, "raw": raw_text},
        )
        price = _parse_price(raw_text)
        if price is not None and price > 0:
            log.info("scrape_ok", extra={"product_id": product_id, "price": price})
            return ScrapeResult(
                product_id=product_id,
                status=ScrapeStatus.OK,
                checked_at=checked_at,
                attempts=1,
                price=price,
                currency="USD",
            )

    # CSS selectors yielded nothing usable — try embedded JSON (priceAmount).
    price = _extract_price_from_json(response.text)
    if price is not None and price > 0:
        log.info("scrape_ok_json", extra={"product_id": product_id, "price": price})
        return ScrapeResult(
            product_id=product_id,
            status=ScrapeStatus.OK,
            checked_at=checked_at,
            attempts=1,
            price=price,
            currency="USD",
        )

    log.warning("scrape_parse_error", extra={"product_id": product_id, "url": url})
    return ScrapeResult(
        product_id=product_id,
        status=ScrapeStatus.PARSE_ERROR,
        checked_at=checked_at,
        attempts=1,
        error="no price selector matched and no priceAmount in page JSON",
    )


def fetch_with_retry(url: str, product_id: int, max_attempts: int = 3) -> ScrapeResult:
    result = fetch_price(url, product_id)
    total_attempts = 1

    while total_attempts < max_attempts and result.status in _RETRYABLE:
        delay = 2**total_attempts + random.random()
        log.debug(
            "scrape_retry",
            extra={
                "product_id": product_id,
                "attempt": total_attempts,
                "delay": round(delay, 2),
                "status": result.status,
            },
        )
        time.sleep(delay)
        result = fetch_price(url, product_id)
        total_attempts += 1

    return ScrapeResult(
        product_id=result.product_id,
        status=result.status,
        checked_at=result.checked_at,
        attempts=total_attempts,
        price=result.price,
        currency=result.currency,
        error=result.error,
    )
