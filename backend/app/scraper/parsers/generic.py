"""Any shop that publishes structured product data.

Order: JSON-LD (schema.org Product/Offer) → Open Graph / product meta tags →
schema.org microdata.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from selectolax.parser import HTMLParser

from app.money import currency_for_host, parse_price, to_decimal
from app.scraper.parsers.base import Blocked, ParseError, ParseResult, clean_image, clean_text

BOT_WALL_MARKERS = (
    "cf-challenge",
    "challenge-platform",
    "px-captcha",
    "g-recaptcha",
    "hcaptcha",
    "datadome",
)


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type", [])
    return {str(v) for v in (value if isinstance(value, list) else [value])}


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _image(value: Any) -> str | None:
    value = _first(value)
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return clean_image(value) if isinstance(value, str) else None


def _offer_price(offer: dict[str, Any]) -> tuple[Decimal | None, str | None, bool | None]:
    price = to_decimal(offer.get("price"))
    if price is None:
        price = to_decimal(offer.get("lowPrice"))
    currency = offer.get("priceCurrency")
    spec = _first(offer.get("priceSpecification"))
    if isinstance(spec, dict):
        if price is None:
            price = to_decimal(spec.get("price"))
        currency = currency or spec.get("priceCurrency")
    availability = str(offer.get("availability", ""))
    in_stock: bool | None = None
    if availability:
        in_stock = any(
            s in availability for s in ("InStock", "LimitedAvailability", "OnlineOnly", "PreOrder")
        )
    return price, currency, in_stock


def _from_json_ld(tree: HTMLParser) -> ParseResult | None:
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text(), strict=False)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _walk(data):
            if not _types(node) & {"Product", "ProductGroup", "IndividualProduct"}:
                continue
            offers = node.get("offers")
            if offers is None and isinstance(node.get("hasVariant"), list):
                offers = [v.get("offers") for v in node["hasVariant"] if isinstance(v, dict)]
            candidates = [o for o in _walk(offers) if _types(o) & {"Offer", "AggregateOffer"} or "price" in o]
            priced = [(p, c, s) for p, c, s in map(_offer_price, candidates) if p is not None]
            if not priced:
                continue
            available = [entry for entry in priced if entry[2] is not False] or priced
            price, currency, in_stock = min(available, key=lambda entry: entry[0])
            return ParseResult(
                price=price,
                currency=str(currency or ""),
                in_stock=in_stock,
                title=clean_text(str(node.get("name") or "")),
                image_url=_image(node.get("image")),
            )
    return None


def _meta(tree: HTMLParser, *names: str) -> str | None:
    for name in names:
        node = tree.css_first(f'meta[property="{name}"]') or tree.css_first(f'meta[name="{name}"]')
        if node is not None and node.attributes.get("content"):
            return node.attributes["content"]
    return None


def _from_meta(tree: HTMLParser) -> ParseResult | None:
    raw = _meta(tree, "product:price:amount", "og:price:amount", "product:sale_price:amount")
    price = to_decimal(raw) if raw else None
    if price is None:
        return None
    availability = (_meta(tree, "product:availability", "og:availability") or "").lower()
    return ParseResult(
        price=price,
        currency=_meta(tree, "product:price:currency", "og:price:currency") or "",
        in_stock=None
        if not availability
        else ("instock" in availability.replace(" ", "") or availability == "in stock"),
        title=clean_text(_meta(tree, "og:title")),
        image_url=clean_image(_meta(tree, "og:image")),
    )


def _from_microdata(tree: HTMLParser) -> ParseResult | None:
    node = tree.css_first('[itemprop="price"]')
    if node is None:
        return None
    raw = node.attributes.get("content") or node.text(strip=True)
    price = to_decimal(raw)
    currency: str | None = None
    if price is None:
        price, currency = parse_price(raw or "")
    if price is None:
        return None
    currency_node = tree.css_first('[itemprop="priceCurrency"]')
    if currency_node is not None:
        currency = currency_node.attributes.get("content") or currency_node.text(strip=True) or currency
    availability = tree.css_first('[itemprop="availability"]')
    in_stock = None
    if availability is not None:
        value = availability.attributes.get("href") or availability.attributes.get("content") or ""
        in_stock = "InStock" in value if value else None
    name = tree.css_first('[itemprop="name"]')
    return ParseResult(
        price=price,
        currency=currency or "",
        in_stock=in_stock,
        title=clean_text(name.text() if name else None),
        image_url=clean_image(_meta(tree, "og:image")),
    )


def parse(html: str, host: str) -> ParseResult:
    tree = HTMLParser(html)
    for extractor in (_from_json_ld, _from_meta, _from_microdata):
        result = extractor(tree)
        if result is not None:
            result.currency = (result.currency or currency_for_host(host)).upper()[:3]
            if not result.title:
                title = _meta(tree, "og:title")
                if not title and tree.css_first("title") is not None:
                    title = tree.css_first("title").text()
                result.title = clean_text(title)
            if not result.image_url:
                result.image_url = clean_image(_meta(tree, "og:image"))
            return result
    lowered = html[:200_000].lower()
    if any(marker in lowered for marker in BOT_WALL_MARKERS):
        raise Blocked("Shop served a bot challenge")
    raise ParseError("No structured price data found")
