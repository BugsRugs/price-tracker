from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

import httpx
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_RETRYABLE = {ScrapeStatus.NETWORK_ERROR, ScrapeStatus.HTTP_ERROR}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_price(text: str) -> float | None:
    cleaned = text.strip().lstrip("$£€").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def fetch_price(url: str, product_id: int) -> ScrapeResult:
    checked_at = _now()
    try:
        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=15.0) as client:
            response = client.get(url)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
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
    except httpx.HTTPError as exc:
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

    if not response.is_success:
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
        if node is not None:
            raw_text = node.text(strip=True)
            log.debug(
                "selector_matched",
                extra={"product_id": product_id, "selector": selector, "raw": raw_text},
            )
            price = _parse_price(raw_text)
            if price is None or price <= 0:
                log.warning(
                    "scrape_price_invalid",
                    extra={"product_id": product_id, "raw": raw_text},
                )
                return ScrapeResult(
                    product_id=product_id,
                    status=ScrapeStatus.PRICE_INVALID,
                    checked_at=checked_at,
                    attempts=1,
                    error=f"unparseable price text: {raw_text!r}",
                )
            log.info(
                "scrape_ok",
                extra={"product_id": product_id, "price": price},
            )
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
        error="no price selector matched",
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
