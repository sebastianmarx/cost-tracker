"""Amazon product pages (amazon.de, amazon.com, ...).

When Amazon does not sell an item itself the buy box is empty and the page
only links to "Alle Angebote". Those offers come from a separate endpoint
(`offers_url`), parsed by `parse_offers`.
"""

from __future__ import annotations

import re
from decimal import Decimal

from selectolax.parser import HTMLParser, Node

from app.money import currency_for_host, parse_price, to_decimal
from app.scraper.parsers.base import Blocked, NoBuyBox, ParseError, ParseResult, clean_image, clean_text

# Ordered by reliability. The buy-box price is what a customer actually pays.
PRICE_CONTAINERS = (
    "#corePrice_feature_div",
    "#corePriceDisplay_desktop_feature_div",
    "#apex_desktop",
    "#apex_offerDisplay_desktop",
    "#buybox",
)
# The explicit "price to pay" inside a container, before any other .a-price
# (which may be the struck-through list price / RRP).
PRICE_TO_PAY = (".priceToPay", ".apex-pricetopay-value", ".reinventPricePriceToPayMargin")
LEGACY_SELECTORS = (
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "#priceblock_saleprice",
    "#price_inside_buybox",
    "#newBuyBoxPrice",
    "#kindle-price",
    "#price",
)
UNAVAILABLE = (
    "derzeit nicht verfügbar",
    "currently unavailable",
    "nicht auf lager",
    "temporarily out of stock",
    "vorübergehend nicht auf lager",
)
NEW_CONDITION = ("neu", "new")
_ASIN = re.compile(r"^[A-Z0-9]{10}$")


def _is_captcha(tree: HTMLParser) -> bool:
    if tree.css_first('form[action*="validateCaptcha"]') is not None:
        return True
    title = (tree.css_first("title").text() if tree.css_first("title") else "").lower()
    return "robot check" in title or "captcha" in title


def _price_text(price: Node) -> str | None:
    """Text of one `.a-price` element: the offscreen copy, or whole + fraction."""
    offscreen = price.css_first(".a-offscreen")
    if offscreen is not None and offscreen.text(strip=True):
        return offscreen.text(strip=True)
    whole = price.css_first(".a-price-whole")
    if whole is None:
        return None
    fraction = price.css_first(".a-price-fraction")
    symbol = price.css_first(".a-price-symbol")
    return (
        f"{whole.text(strip=True).rstrip('.,')},{fraction.text(strip=True) if fraction else '00'}"
        f" {symbol.text(strip=True) if symbol else ''}"
    )


def _price_from_container(node: Node) -> str | None:
    for selector in PRICE_TO_PAY:
        target = node.css_first(selector)
        if target is not None:
            text = _price_text(target)
            if text:
                return text
    label = node.css_first(".apex-pricetopay-accessibility-label")
    if label is not None and label.text(strip=True):
        return label.text(strip=True)  # "379,99 € mit 10 Prozent Einsparungen"
    for price in node.css(".a-price"):
        if "a-text-price" in (price.attributes.get("class") or ""):
            continue  # struck-through list price
        text = _price_text(price)
        if text:
            return text
    return None


def _asin(tree: HTMLParser) -> str | None:
    for node in (tree.css_first("input#ASIN"), tree.css_first('input[name="ASIN"]')):
        if node is not None and _ASIN.match(node.attributes.get("value") or ""):
            return node.attributes["value"]
    canonical = tree.css_first('link[rel="canonical"]')
    match = re.search(r"/dp/([A-Z0-9]{10})", (canonical.attributes.get("href") or "") if canonical else "")
    return match.group(1) if match else None


def parse(html: str, host: str) -> ParseResult:
    tree = HTMLParser(html)
    if _is_captcha(tree):
        raise Blocked("Amazon served a captcha")
    # Availability blocks embed scripts whose text would pollute matching.
    tree.strip_tags(["script", "style", "noscript"])

    raw: str | None = None
    for selector in PRICE_CONTAINERS:
        container = tree.css_first(selector)
        if container is not None:
            raw = _price_from_container(container)
            if raw:
                break
    if not raw:
        for selector in LEGACY_SELECTORS:
            node = tree.css_first(selector)
            if node is not None and node.text(strip=True):
                raw = node.text(strip=True)
                break

    price, currency = parse_price(raw) if raw else (None, None)
    if price is None:
        hidden = tree.css_first("input#twister-plus-price-data-price")
        if hidden is not None:
            price = to_decimal(hidden.attributes.get("value"))

    title_node = tree.css_first("#productTitle")
    title = clean_text(title_node.text() if title_node else None)
    image_node = tree.css_first("#landingImage") or tree.css_first("#imgBlkFront")
    image = None
    if image_node is not None:
        image = image_node.attributes.get("data-old-hires") or image_node.attributes.get("src")

    if price is None:
        asin = _asin(tree)
        if asin and title:
            raise NoBuyBox(asin, title, clean_image(image))
        raise ParseError("No price found on Amazon page")

    availability = tree.css_first("#availability")
    availability_text = availability.text(strip=True).lower() if availability else ""
    in_stock = not any(marker in availability_text for marker in UNAVAILABLE)

    return ParseResult(
        price=price,
        currency=currency or currency_for_host(host),
        in_stock=in_stock,
        title=title,
        image_url=clean_image(image),
    )


def offers_url(host: str, asin: str) -> str:
    return f"https://{host}/gp/product/ajax/aodAjaxMain/?asin={asin}&pc=dp&experienceId=aodAjaxMain"


def parse_offers(html: str, host: str) -> ParseResult:
    """Lowest price among the *new* offers of the "all offers" panel."""
    tree = HTMLParser(html)
    if _is_captcha(tree):
        raise Blocked("Amazon served a captcha")
    tree.strip_tags(["script", "style", "noscript"])

    best: tuple[Decimal, str | None] | None = None
    for offer in tree.css("#aod-pinned-offer, #aod-offer"):
        heading = offer.css_first("#aod-offer-heading")
        condition = heading.text(strip=True).lower() if heading is not None else ""
        if condition and not condition.startswith(NEW_CONDITION):
            continue  # used / refurbished
        price_node = offer.css_first('[id^="aod-price-"]')
        raw = _price_from_container(price_node) if price_node is not None else None
        price, currency = parse_price(raw) if raw else (None, None)
        if price is not None and (best is None or price < best[0]):
            best = (price, currency)
    if best is None:
        raise ParseError("Currently unavailable: no new offers on Amazon")
    return ParseResult(price=best[0], currency=best[1] or currency_for_host(host), in_stock=True)
