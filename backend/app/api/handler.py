"""HTTP API (payload v2) entry point.

API Gateway's JWT authorizer has already validated the Cognito access token
before this code runs. As defense in depth the handler also pins the token's
`sub` to the single owner.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import boto3
from pydantic import ValidationError

from app import config, db
from app.api.models import (
    MAX_LINKS_PER_PRODUCT,
    MAX_LINKS_TOTAL,
    LinkCreate,
    ProductCreate,
    ProductUpdate,
)
from app.money import currency_for_host
from app.scraper.fetch import FetchError, resolve_redirects
from app.stats import change_pct, link_stats
from app.urls import InvalidUrl, is_short_link, normalize_url, shop_name

log = logging.getLogger()
log.setLevel(logging.INFO)

MAX_BODY_BYTES = 16 * 1024
HISTORY_DAYS = {0, 30, 90, 180, 365}
ID = r"[0-9a-f]{32}"

_lambda: Any = None


class HttpError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------
def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, set):
        return list(value)
    raise TypeError(f"Not serializable: {type(value)}")


def _response(status: int, body: Any = None) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": "" if body is None else json.dumps(body, default=_json_default),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    if len(raw.encode()) > MAX_BODY_BYTES:
        raise HttpError(413, "too_large", "Request body too large")
    if not raw:
        return {}
    try:
        data = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise HttpError(400, "invalid_json", "Body is not valid JSON") from exc
    if not isinstance(data, dict):
        raise HttpError(400, "invalid_json", "Body must be a JSON object")
    return data


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first.get("loc", ()))
    return f"{where}: {first.get('msg')}" if where else str(first.get("msg"))


def _invoke_scraper(link_ids: list[str], sync: bool) -> dict[str, Any] | None:
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    # A sync refresh has already claimed the link via claim_attempt.
    payload = json.dumps({"mode": "manual", "link_ids": link_ids, "claimed": sync}).encode()
    result = _lambda.invoke(
        FunctionName=config.scraper_function(),
        InvocationType="RequestResponse" if sync else "Event",
        Payload=payload,
    )
    if not sync:
        return None
    if result.get("FunctionError"):
        raise HttpError(502, "scraper_failed", "Price check failed")
    parsed: dict[str, Any] = json.loads(result["Payload"].read() or b"{}")
    return parsed


def _public_link(link: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in link.items() if k != "recent"}


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------
def _best_link(links: list[dict[str, Any]]) -> dict[str, Any] | None:
    priced = [link for link in links if link.get("last_price") is not None]
    if not priced:
        return None
    # Only compare like with like: use the most common currency.
    currency = Counter(link.get("currency") for link in priced).most_common(1)[0][0]
    same = [link for link in priced if link.get("currency") == currency]
    in_stock = [link for link in same if link.get("last_in_stock") is not False] or same
    return min(in_stock, key=lambda link: Decimal(link["last_price"]))


_STATUS_RANK = {"ok": 0, "pending": 1, "parse_error": 2, "http_error": 2, "blocked": 3}


def _summary(product: dict[str, Any], links: list[dict[str, Any]]) -> dict[str, Any]:
    best = _best_link(links)
    recent = [{"ts": ts, "price": price} for ts, price in (best or {}).get("recent", [])]
    worst = max(
        (link.get("last_status", "pending") for link in links),
        key=lambda s: _STATUS_RANK.get(s, 2),
        default=None,
    )
    return {
        **product,
        "link_count": len(links),
        "best": (
            {
                "link_id": best["id"],
                "shop": best["shop"],
                "price": best["last_price"],
                "currency": best.get("currency"),
                "in_stock": best.get("last_in_stock"),
            }
            if best
            else None
        ),
        "change_30d_pct": change_pct(recent, 30) if recent else None,
        "sparkline": recent,
        "status": worst,
    }


def list_products(_: dict[str, Any]) -> dict[str, Any]:
    products = db.list_products()
    links_by_product: dict[str, list[dict[str, Any]]] = {}
    for link in db.list_all_links():
        links_by_product.setdefault(link["product_id"], []).append(link)
    return _response(200, [_summary(p, links_by_product.get(p["id"], [])) for p in products])


def _product_detail(pid: str) -> dict[str, Any]:
    product, links = db.get_product(pid)
    if product is None:
        raise HttpError(404, "not_found", "Product not found")
    detailed = []
    for link in links:
        detailed.append({**_public_link(link), "stats": link_stats(db.history(link["id"]))})
    return {**product, "links": detailed}


def get_product(_: dict[str, Any], pid: str) -> dict[str, Any]:
    return _response(200, _product_detail(pid))


def _check_link_budget(extra: int) -> None:
    if db.count_links() + extra > MAX_LINKS_TOTAL:
        raise HttpError(409, "too_many_links", f"At most {MAX_LINKS_TOTAL} links in total")


def _resolve(url: str) -> str:
    """Expands share links (amzn.eu/d/..., amzn.to/...) to the product URL.

    On failure the share link is kept; the scraper resolves it on its next run.
    """
    if not is_short_link(url):
        return url
    try:
        return normalize_url(resolve_redirects(url))
    except (FetchError, InvalidUrl):
        log.warning("Could not resolve share link %s", url)
        return url


def _create_link(pid: str, url: str) -> dict[str, Any]:
    shop = shop_name(url)
    return db.add_link(pid, url, shop, currency_for_host(shop))


def create_product(event: dict[str, Any]) -> dict[str, Any]:
    try:
        body = ProductCreate.model_validate(_body(event))
    except ValidationError as exc:
        raise HttpError(400, "invalid", _validation_message(exc)) from exc
    urls = list(dict.fromkeys(_resolve(url) for url in body.links))
    _check_link_budget(len(urls))
    product = db.create_product(body.name, body.target_price, body.tags)
    links = [_create_link(product["id"], url) for url in urls]
    if links:
        _invoke_scraper([link["id"] for link in links], sync=False)
    return _response(201, {**product, "links": [_public_link(link) for link in links]})


def update_product(event: dict[str, Any], pid: str) -> dict[str, Any]:
    try:
        body = ProductUpdate.model_validate(_body(event))
    except ValidationError as exc:
        raise HttpError(400, "invalid", _validation_message(exc)) from exc
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    if not fields:
        raise HttpError(400, "invalid", "Nothing to update")
    if "name" in fields and fields["name"] is None:
        raise HttpError(400, "invalid", "name: cannot be empty")
    if "tags" in fields and not fields["tags"]:
        fields["tags"] = None  # an empty list removes the attribute
    if db.update_product(pid, fields) is None:
        raise HttpError(404, "not_found", "Product not found")
    if "target_price" in fields:
        # A new target re-arms the alert.
        _, links = db.get_product(pid)
        for link in links:
            db.update_link(pid, link["id"], {"last_notified_price": None})
    return _response(200, _product_detail(pid))


def delete_product(_: dict[str, Any], pid: str) -> dict[str, Any]:
    product, _links = db.get_product(pid)
    if product is None:
        raise HttpError(404, "not_found", "Product not found")
    db.delete_product(pid)
    return _response(204)


def add_link(event: dict[str, Any], pid: str) -> dict[str, Any]:
    try:
        body = LinkCreate.model_validate(_body(event))
    except ValidationError as exc:
        raise HttpError(400, "invalid", _validation_message(exc)) from exc
    product, links = db.get_product(pid)
    if product is None:
        raise HttpError(404, "not_found", "Product not found")
    if len(links) >= MAX_LINKS_PER_PRODUCT:
        raise HttpError(409, "too_many_links", f"At most {MAX_LINKS_PER_PRODUCT} links per product")
    url = _resolve(body.url)
    if any(link["url"] == url for link in links):
        raise HttpError(409, "duplicate", "This link is already tracked")
    _check_link_budget(1)
    link = _create_link(pid, url)
    _invoke_scraper([link["id"]], sync=False)
    return _response(201, _public_link(link))


def delete_link(_: dict[str, Any], pid: str, lid: str) -> dict[str, Any]:
    if not db.delete_link(pid, lid):
        raise HttpError(404, "not_found", "Link not found")
    return _response(204)


def link_history(event: dict[str, Any], lid: str) -> dict[str, Any]:
    link = db.get_link(lid)
    if link is None:
        raise HttpError(404, "not_found", "Link not found")
    raw_days = (event.get("queryStringParameters") or {}).get("days", "0")
    days = int(raw_days) if raw_days.isdigit() else -1
    if days not in HISTORY_DAYS:
        raise HttpError(400, "invalid", "days must be one of 0, 30, 90, 180, 365")
    return _response(
        200,
        {"link_id": lid, "currency": link.get("currency"), "points": db.history(lid, days)},
    )


def refresh_link(_: dict[str, Any], lid: str) -> dict[str, Any]:
    link = db.get_link(lid)
    if link is None:
        raise HttpError(404, "not_found", "Link not found")
    if not db.claim_attempt(link["product_id"], lid, config.refresh_min_interval()):
        raise HttpError(429, "too_soon", "This link was checked less than 5 minutes ago")
    _invoke_scraper([lid], sync=True)
    updated = db.get_link(lid) or link
    return _response(200, _public_link(updated))


def refresh_all(_: dict[str, Any]) -> dict[str, Any]:
    ids = [link["id"] for link in db.list_all_links()]
    if ids:
        _invoke_scraper(ids, sync=False)
    return _response(202, {"queued": len(ids)})


Route = tuple[str, re.Pattern[str], Callable[..., dict[str, Any]]]
ROUTES: list[Route] = [
    ("GET", re.compile(r"/api/products"), list_products),
    ("POST", re.compile(r"/api/products"), create_product),
    ("GET", re.compile(rf"/api/products/({ID})"), get_product),
    ("PUT", re.compile(rf"/api/products/({ID})"), update_product),
    ("DELETE", re.compile(rf"/api/products/({ID})"), delete_product),
    ("POST", re.compile(rf"/api/products/({ID})/links"), add_link),
    ("DELETE", re.compile(rf"/api/products/({ID})/links/({ID})"), delete_link),
    ("GET", re.compile(rf"/api/links/({ID})/history"), link_history),
    ("POST", re.compile(rf"/api/links/({ID})/refresh"), refresh_link),
    ("POST", re.compile(r"/api/refresh"), refresh_all),
]


def _authorized(event: dict[str, Any]) -> bool:
    owner = config.owner_sub()
    if not owner:
        return True
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    return claims.get("sub") == owner


def handler(event: dict[str, Any], _context: Any = None) -> dict[str, Any]:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "").rstrip("/") or "/"
    try:
        if not _authorized(event):
            raise HttpError(403, "forbidden", "Not allowed")
        path_matched = False
        for route_method, pattern, view in ROUTES:
            match = pattern.fullmatch(path)
            if not match:
                continue
            path_matched = True
            if route_method == method:
                return view(event, *match.groups())
        if path_matched:
            raise HttpError(405, "method_not_allowed", "Method not allowed")
        raise HttpError(404, "not_found", "Route not found")
    except HttpError as exc:
        return _response(exc.status, {"error": exc.code, "message": exc.message})
    except Exception:
        log.exception("Unhandled error on %s %s", method, path)
        return _response(500, {"error": "internal", "message": "Internal error"})
