from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class ParseError(Exception):
    pass


class NoBuyBox(ParseError):
    """Amazon does not sell the item itself; other sellers' offers must be loaded."""

    def __init__(self, asin: str, title: str | None, image_url: str | None) -> None:
        super().__init__("No buy-box price; checking other sellers")
        self.asin, self.title, self.image_url = asin, title, image_url


class Blocked(Exception):
    """The shop served a captcha / bot wall instead of the product page."""


@dataclass
class ParseResult:
    price: Decimal
    currency: str
    in_stock: bool | None = None
    title: str | None = None
    image_url: str | None = None


def clean_text(value: str | None, limit: int = 300) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def clean_image(value: str | None) -> str | None:
    """Only https images are stored; they are rendered by the SPA and emails."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("//"):
        value = "https:" + value
    if not value.startswith("https://") or len(value) > 2048:
        return None
    return value
