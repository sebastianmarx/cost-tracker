"""Price parsing and formatting. Prices are always Decimal, never float."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_SYMBOLS: list[tuple[str, str]] = [
    ("CHF", "CHF"),
    ("EUR", "EUR"),
    ("USD", "USD"),
    ("GBP", "GBP"),
    ("PLN", "PLN"),
    ("SEK", "SEK"),
    ("zł", "PLN"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("US$", "USD"),
    ("$", "USD"),
]
_NUMBER = re.compile(r"\d[\d.,' ]*")
_PLAIN = re.compile(r"^\d+(\.\d+)?$")
_CENT = Decimal("0.01")

_TLD_CURRENCY = {
    "de": "EUR",
    "at": "EUR",
    "fr": "EUR",
    "it": "EUR",
    "es": "EUR",
    "nl": "EUR",
    "be": "EUR",
    "ie": "EUR",
    "fi": "EUR",
    "pt": "EUR",
    "eu": "EUR",
    "ch": "CHF",
    "uk": "GBP",
    "com": "USD",
    "us": "USD",
    "pl": "PLN",
    "se": "SEK",
}


def currency_from_text(text: str) -> str | None:
    for token, code in _SYMBOLS:
        if token in text:
            return code
    return None


def currency_for_host(host: str) -> str:
    return _TLD_CURRENCY.get(host.rsplit(".", 1)[-1].lower(), "EUR")


def to_decimal(value: object) -> Decimal | None:
    """Machine-readable values (JSON-LD, meta tags) use a dot decimal separator."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value)).quantize(_CENT, ROUND_HALF_UP)
    text = str(value).strip()
    if _PLAIN.match(text):
        return Decimal(text).quantize(_CENT, ROUND_HALF_UP)
    return parse_price(text)[0]


def parse_price(text: str) -> tuple[Decimal | None, str | None]:
    """Parses human-formatted prices such as '1.299,99 €', '€1,299.99', '12,-'.

    The last separator followed by one or two digits is the decimal separator,
    every other separator groups thousands.
    """
    if not text:
        return None, None
    cleaned = text.replace("\xa0", " ").replace(" ", " ").strip()
    currency = currency_from_text(cleaned)
    match = _NUMBER.search(cleaned)
    if not match:
        return None, currency
    number = match.group().strip().rstrip(".,' ").replace(" ", "").replace("'", "")
    last_sep = max(number.rfind(","), number.rfind("."))
    if last_sep == -1:
        digits = number
    else:
        tail = number[last_sep + 1 :]
        head = re.sub(r"[.,]", "", number[:last_sep])
        digits = f"{head}.{tail}" if len(tail) in (1, 2) else re.sub(r"[.,]", "", number)
    try:
        value = Decimal(digits).quantize(_CENT, ROUND_HALF_UP)
    except InvalidOperation:
        return None, currency
    if value <= 0:
        return None, currency
    return value, currency


_SYMBOL_OUT = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "PLN": "zł", "SEK": "kr"}


def format_money(value: Decimal | float | None, currency: str | None = "EUR") -> str:
    """German-style formatting: 1.299,99 €."""
    if value is None:
        return "–"
    amount = Decimal(str(value)).quantize(_CENT, ROUND_HALF_UP)
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} {_SYMBOL_OUT.get(currency or 'EUR', currency or '')}".strip()
