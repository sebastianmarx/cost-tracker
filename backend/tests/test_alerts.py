from decimal import Decimal as D

import pytest

from app.scraper import notify


@pytest.mark.parametrize(
    ("price", "target", "last", "expected"),
    [
        (D("90"), None, None, (False, False)),
        (D("90"), None, D("80"), (False, True)),  # target removed -> clear
        (D("110"), D("100"), None, (False, False)),
        (D("100"), D("100"), None, (True, False)),  # first crossing
        (D("95"), D("100"), D("100"), (True, False)),  # dropped further
        (D("95"), D("100"), D("95"), (False, False)),  # same price, no spam
        (D("99"), D("100"), D("95"), (False, False)),  # rose but still below
        (D("105"), D("100"), D("95"), (False, True)),  # back above -> re-arm
    ],
)
def test_should_notify(price: D, target: D | None, last: D | None, expected: tuple[bool, bool]) -> None:
    assert notify.should_notify(price, target, last) == expected


def test_render_escapes_and_formats() -> None:
    product = {
        "id": "p1",
        "name": "<b>Lamp</b>",
        "image_url": "https://img.example/x.jpg",
        "target_price": D("50"),
    }
    link = {"id": "l1", "shop": "shop.example", "url": "https://shop.example/p?a=1&b=2", "currency": "EUR"}
    others = [
        {**link, "last_price": D("45")},
        {
            "id": "l2",
            "shop": "other.example",
            "url": "https://other.example/p",
            "last_price": D("48"),
            "currency": "EUR",
        },
    ]
    subject, html, text = notify.render(
        {
            "product": product,
            "link": link,
            "links": others,
            "price": D("45"),
            "previous": D("60"),
            "currency": "EUR",
            "target": D("50"),
            "drop_abs": D("15"),
            "drop_pct": 25.0,
            "all_time_low": True,
            "product_url": "https://app.example/products/p1",
            "app_url": "https://app.example",
        }
    )
    assert "45,00 €" in subject
    assert "&lt;b&gt;Lamp&lt;/b&gt;" in html and "<b>Lamp</b>" not in html
    assert "−15,00 € (25.0 %)" in html
    assert "Lowest price so far" in html
    assert "other.example" in html
    assert "https://shop.example/p?a=1&amp;b=2" in html
    assert "Before: 60,00 €" in text
