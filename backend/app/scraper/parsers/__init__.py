"""Shop parsers. `parse(url, html)` picks the right one by host name."""

from __future__ import annotations

from urllib.parse import urlsplit

from app.scraper.parsers import amazon, generic
from app.scraper.parsers.base import Blocked, NoBuyBox, ParseError, ParseResult
from app.urls import is_amazon

__all__ = ["Blocked", "NoBuyBox", "ParseError", "ParseResult", "parse", "amazon"]


def parse(url: str, html: str) -> ParseResult:
    host = urlsplit(url).hostname or ""
    if is_amazon(host):
        return amazon.parse(html, host)
    return generic.parse(html, host)
