"""Price-alert emails via SES (HTML + plain-text)."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import config
from app.money import format_money

log = logging.getLogger()

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["money"] = format_money
_ses: Any = None


def should_notify(price: Decimal, target: Decimal | None, last_notified: Decimal | None) -> tuple[bool, bool]:
    """Returns (send, re_arm).

    An alert is sent the first time a price reaches the target and again only
    when it drops further. Once the price climbs back above the target, the
    alert is re-armed for the next crossing.
    """
    if target is None:
        return False, last_notified is not None
    if price <= target:
        return last_notified is None or price < last_notified, False
    return False, last_notified is not None


def render(context: dict[str, Any]) -> tuple[str, str, str]:
    subject = (
        f"📉 {context['product']['name']} now {format_money(context['price'], context['currency'])}"
        f" at {context['link']['shop']}"
    )
    html = _env.get_template("alert.html.j2").render(**context)
    text = _env.get_template("alert.txt.j2").render(**context)
    return subject, html, text


def send_alert(
    product: dict[str, Any],
    link: dict[str, Any],
    links: list[dict[str, Any]],
    price: Decimal,
    previous: Decimal | None,
    all_time_low: bool,
) -> None:
    sender, recipient = config.ses_from(), config.alert_to()
    if not sender or not recipient:
        log.warning("SES_FROM/ALERT_TO not configured, skipping alert")
        return
    drop_abs = (previous - price) if previous is not None and previous > price else None
    drop_pct = float(drop_abs / previous * 100) if drop_abs is not None and previous else None
    context = {
        "product": product,
        "link": link,
        "links": sorted(
            (item for item in links if item.get("last_price") is not None),
            key=lambda item: Decimal(item["last_price"]),
        ),
        "price": price,
        "previous": previous,
        "currency": link.get("currency", "EUR"),
        "target": product.get("target_price"),
        "drop_abs": drop_abs,
        "drop_pct": drop_pct,
        "all_time_low": all_time_low,
        "product_url": f"{config.app_url()}/products/{product['id']}",
        "app_url": config.app_url(),
    }
    subject, html, text = render(context)
    global _ses
    if _ses is None:
        _ses = boto3.client("sesv2")
    _ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [recipient]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html, "Charset": "UTF-8"},
                    "Text": {"Data": text, "Charset": "UTF-8"},
                },
            }
        },
    )
    log.info("Alert sent for product %s link %s at %s", product["id"], link["id"], price)
