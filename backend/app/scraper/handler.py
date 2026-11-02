"""Scraper Lambda.

Events:
  {"source": "schedule"}                                  every link (06:00/18:00)
  {"mode": "manual", "link_ids": [...]}                   async refresh / new links
  {"mode": "manual", "link_ids": [lid], "claimed": true}  sync single refresh;
                                                          the API already claimed it
"""

from __future__ import annotations

import logging
import random
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from app import config, db
from app.scraper import notify
from app.scraper.fetch import PROFILES, FetchError, HttpStatusError, fetch
from app.scraper.parsers import Blocked, NoBuyBox, ParseError, ParseResult, amazon, parse
from app.urls import InvalidUrl, is_short_link, normalize_url, shop_name

log = logging.getLogger()
log.setLevel(logging.INFO)

# Stop starting new links when less than this is left of the Lambda timeout.
SAFETY_MARGIN_MS = 45_000
# Scheduled runs skip links that were tried in the last minute (overlapping runs).
SCHEDULE_MIN_INTERVAL_S = 60


def _fetch_and_parse(url: str, profile: str, timeout: float) -> tuple[ParseResult, str]:
    """Returns the parse result and the final URL after redirects."""
    page = fetch(url, profile, timeout)
    try:
        return parse(page.url, page.html), page.url
    except NoBuyBox as missing:
        # Amazon does not sell it itself: use the cheapest new offer of other sellers.
        host = urlsplit(page.url).hostname or ""
        offers = fetch(amazon.offers_url(host, missing.asin), profile, timeout)
        result = amazon.parse_offers(offers.html, host)
        result.title, result.image_url = missing.title, missing.image_url
        return result, page.url


def _scrape(url: str, attempts: int, timeout: float) -> tuple[ParseResult | None, str, str | None, str]:
    status, error = "http_error", "not attempted"
    for attempt in range(attempts):
        try:
            result, final_url = _fetch_and_parse(url, PROFILES[attempt % len(PROFILES)], timeout)
            return result, "ok", None, final_url
        except Blocked as exc:
            status, error = "blocked", str(exc)
        except HttpStatusError as exc:
            status, error = ("blocked" if exc.looks_blocked else "http_error"), str(exc)
        except FetchError as exc:
            status, error = "http_error", str(exc)
        except ParseError as exc:
            return None, "parse_error", str(exc), url  # a retry would parse the same page
        if attempt + 1 < attempts:
            time.sleep(random.uniform(3, 6))
    return None, status, error, url


def _canonical(stored: str, final: str) -> str | None:
    """The product URL to store instead of a share link, or None to keep it."""
    if not is_short_link(stored) or final == stored:
        return None
    try:
        return normalize_url(final)
    except InvalidUrl:
        return None


class _Products:
    """Per-invocation cache of product metadata and links."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[dict[str, Any] | None, list[dict[str, Any]]]] = {}

    def get(self, pid: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if pid not in self._cache:
            self._cache[pid] = db.get_product(pid)
        return self._cache[pid]


def process_link(link: dict[str, Any], products: _Products, attempts: int, timeout: float) -> dict[str, Any]:
    pid, lid = link["product_id"], link["id"]
    result, status, error, final_url = _scrape(link["url"], attempts, timeout)
    now = db.now_iso()
    canonical = _canonical(link["url"], final_url)

    if result is None:
        db.update_link(pid, lid, {"last_status": status, "last_error": (error or "")[:300]})
        log.warning("Link %s (%s): %s %s", lid, link.get("shop"), status, error)
        return {"link_id": lid, "status": status, "error": error}

    price = result.price
    currency = result.currency or link.get("currency") or "EUR"
    previous = Decimal(link["last_price"]) if link.get("last_price") is not None else None
    lowest = Decimal(link["lowest_price"]) if link.get("lowest_price") is not None else None

    db.put_price(pid, lid, now, price, currency, result.in_stock)
    # A price point is keyed by its second; a re-run in the same second replaces it.
    recent = [point for point in (link.get("recent") or []) if point[0] != now]
    recent = [*recent, [now, price]][-db.RECENT_POINTS :]
    fields: dict[str, Any] = {
        "last_price": price,
        "last_in_stock": result.in_stock,
        "last_checked": now,
        "last_status": "ok",
        "last_error": None,
        "currency": currency,
        "recent": recent,
    }
    if canonical:
        # Share links (amzn.eu/d/...) are replaced by the real product URL.
        fields["url"], fields["shop"] = canonical, shop_name(canonical)
    if lowest is None or price < lowest:
        fields["lowest_price"] = price
    if result.title and not link.get("title"):
        fields["title"] = result.title

    product, links = products.get(pid)
    if product is not None:
        target = Decimal(product["target_price"]) if product.get("target_price") is not None else None
        last_notified = (
            Decimal(link["last_notified_price"]) if link.get("last_notified_price") is not None else None
        )
        send, re_arm = notify.should_notify(price, target, last_notified)
        if re_arm:
            fields["last_notified_price"] = None
        if send and result.in_stock is not False:
            current = {**link, **{k: v for k, v in fields.items() if v is not None}}
            others = [current if item["id"] == lid else item for item in links]
            try:
                notify.send_alert(
                    product,
                    current,
                    others,
                    price,
                    previous,
                    all_time_low=lowest is not None and price < lowest,
                )
                fields["last_notified_price"] = price
            except Exception:
                log.exception("Sending alert for link %s failed", lid)
        if result.image_url and not product.get("image_url"):
            db.update_product(pid, {"image_url": result.image_url})
            product["image_url"] = result.image_url

    db.update_link(pid, lid, fields)
    log.info("Link %s (%s): %s %s", lid, link.get("shop"), price, currency)
    return {"link_id": lid, "status": "ok", "price": float(price), "currency": currency}


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    manual = event.get("mode") == "manual"
    ids = event.get("link_ids") or []
    if ids:
        links = [link for link in (db.get_link(lid) for lid in ids) if link is not None]
    else:
        links = db.list_all_links()
        random.shuffle(links)  # spread requests to the same shop

    single_sync = manual and bool(event.get("claimed")) and len(links) == 1
    products = _Products()
    results: list[dict[str, Any]] = []
    for index, link in enumerate(links):
        if context is not None and context.get_remaining_time_in_millis() < SAFETY_MARGIN_MS:
            log.warning("Stopping early, %d links left", len(links) - index)
            break
        if not event.get("claimed"):
            interval = config.refresh_min_interval() if manual else SCHEDULE_MIN_INTERVAL_S
            if not db.claim_attempt(link["product_id"], link["id"], interval):
                results.append({"link_id": link["id"], "status": "skipped"})
                continue
        if index and not single_sync:
            time.sleep(random.uniform(1.5, 4))
        try:
            if single_sync:
                # Must fit into the API Gateway 30 s limit (page + offers fetch).
                results.append(process_link(link, products, attempts=1, timeout=10))
            else:
                results.append(process_link(link, products, attempts=2, timeout=15))
        except Exception:
            log.exception("Link %s failed unexpectedly", link.get("id"))
            results.append({"link_id": link.get("id"), "status": "error"})

    summary: dict[str, int] = {}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    log.info("Run finished: %s", summary)
    return {"summary": summary, "results": results}
