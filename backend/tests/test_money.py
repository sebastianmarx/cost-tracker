from decimal import Decimal

import pytest

from app.money import format_money, parse_price, to_decimal


@pytest.mark.parametrize(
    ("text", "price", "currency"),
    [
        ("1.299,99 €", "1299.99", "EUR"),
        ("€1,299.99", "1299.99", "EUR"),
        ("12,99\xa0€", "12.99", "EUR"),
        ("EUR 12,-", "12.00", "EUR"),
        ("$5.5", "5.50", "USD"),
        ("1 299,00 €", "1299.00", "EUR"),
        ("CHF 1'299.90", "1299.90", "CHF"),
        ("£1,299", "1299.00", "GBP"),
        ("49", "49.00", None),
    ],
)
def test_parse_price(text: str, price: str, currency: str | None) -> None:
    assert parse_price(text) == (Decimal(price), currency)


@pytest.mark.parametrize("text", ["", "free", "0,00 €", "–"])
def test_parse_price_rejects(text: str) -> None:
    assert parse_price(text)[0] is None


def test_to_decimal_machine_values() -> None:
    assert to_decimal("1299.9") == Decimal("1299.90")
    assert to_decimal(19.99) == Decimal("19.99")
    assert to_decimal(20) == Decimal("20.00")
    assert to_decimal("1.299,00") == Decimal("1299.00")
    assert to_decimal(None) is None
    assert to_decimal(True) is None


def test_format_money() -> None:
    assert format_money(Decimal("1299.9"), "EUR") == "1.299,90 €"
    assert format_money(None) == "–"
    assert format_money(Decimal("5"), "USD") == "5,00 $"
