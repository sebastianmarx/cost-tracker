from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app import db
from app.api import handler as api
from app.scraper import handler as scraper
from app.scraper import notify
from app.scraper.fetch import HttpStatusError, Page

PAGE = """<script type="application/ld+json">{"@type":"Product","name":"Lamp",
"image":"https://img.example/lamp.jpg","offers":{"@type":"Offer","price":"%s","priceCurrency":"EUR",
"availability":"https://schema.org/InStock"}}</script>"""


def call(
    method: str, path: str, body: Any = None, query: dict[str, str] | None = None, sub: str = "owner-sub"
) -> tuple[int, Any]:
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method}, "authorizer": {"jwt": {"claims": {"sub": sub}}}},
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }
    response = api.handler(event)
    return response["statusCode"], json.loads(response["body"]) if response["body"] else None


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every call to now_iso() advances one minute, so price points never collide."""
    start = datetime.now(UTC)
    ticks = iter(range(10_000))
    monkeypatch.setattr(
        db, "now_iso", lambda: (start + timedelta(minutes=next(ticks))).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@pytest.fixture(autouse=True)
def no_network_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """Share links resolve to a fixed Amazon product without network access."""
    monkeypatch.setattr(
        api,
        "resolve_redirects",
        lambda url: "https://www.amazon.de/dp/B0DD2HYX6L?ref=cm_sw_r_cso_cp_apan_dp_X&social_share=x",
    )


@pytest.fixture
def invoked(monkeypatch: pytest.MonkeyPatch, table: Any) -> list[tuple[list[str], bool]]:
    """Runs the scraper in-process instead of invoking the Lambda."""
    calls: list[tuple[list[str], bool]] = []

    def fake_invoke(link_ids: list[str], sync: bool) -> dict[str, Any]:
        calls.append((link_ids, sync))
        return scraper.handler({"mode": "manual", "link_ids": link_ids, "claimed": sync})

    monkeypatch.setattr(api, "_invoke_scraper", fake_invoke)
    monkeypatch.setattr(scraper.time, "sleep", lambda _s: None)
    return calls


@pytest.fixture
def prices(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"price": "59.90"}

    def fake_fetch(url: str, profile: str = "chrome", timeout: float = 15) -> Page:
        if isinstance(state["price"], Exception):
            raise state["price"]
        return Page(url, PAGE % state["price"])

    monkeypatch.setattr(scraper, "fetch", fake_fetch)
    return state


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[Decimal]:
    sent: list[Decimal] = []
    monkeypatch.setattr(
        notify, "send_alert", lambda product, link, links, price, previous, all_time_low: sent.append(price)
    )
    return sent


def test_rejects_other_user(table: Any) -> None:
    status, body = call("GET", "/api/products", sub="intruder")
    assert status == 403 and body["error"] == "forbidden"


def test_unknown_route_and_method(table: Any) -> None:
    assert call("GET", "/api/nope")[0] == 404
    assert call("PATCH", "/api/products")[0] == 405


def test_validation(table: Any) -> None:
    status, body = call("POST", "/api/products", {"name": "", "links": []})
    assert status == 400
    status, body = call("POST", "/api/products", {"name": "x", "links": ["http://127.0.0.1/"]})
    assert status == 400 and "IP addresses" in body["message"]
    status, _ = call("POST", "/api/products", {"name": "x", "target_price": -1})
    assert status == 400
    status, _ = call("POST", "/api/products", {"name": "x", "evil": True})
    assert status == 400


def test_full_flow(invoked: Any, prices: dict[str, Any], mails: list[Decimal]) -> None:
    status, product = call(
        "POST",
        "/api/products",
        {"name": "Lamp", "target_price": "50", "links": ["https://shop.example.de/lamp#x"]},
    )
    assert status == 201
    pid = product["id"]
    lid = product["links"][0]["id"]
    assert product["links"][0]["url"] == "https://shop.example.de/lamp"
    assert invoked == [([lid], False)]

    status, detail = call("GET", f"/api/products/{pid}")
    assert status == 200
    link = detail["links"][0]
    assert link["last_price"] == 59.9 and link["last_status"] == "ok" and link["title"] == "Lamp"
    assert detail["image_url"] == "https://img.example/lamp.jpg"
    assert link["stats"]["d30"]["min"] == 59.9
    assert mails == []

    # Manual refresh is rate limited because the new-link scrape just ran.
    status, body = call("POST", f"/api/links/{lid}/refresh")
    assert status == 429

    # Simulate the rate-limit window having passed, and a price drop under target.
    db.update_link(pid, lid, {"last_attempt": "2000-01-01T00:00:00Z"})
    prices["price"] = "45.00"
    status, refreshed = call("POST", f"/api/links/{lid}/refresh")
    assert status == 200 and refreshed["last_price"] == 45.0
    assert mails == [Decimal("45.00")]

    # Same price again -> no second mail.
    db.update_link(pid, lid, {"last_attempt": "2000-01-01T00:00:00Z"})
    call("POST", f"/api/links/{lid}/refresh")
    assert mails == [Decimal("45.00")]

    # Shop blocks us -> last price kept, status updated.
    db.update_link(pid, lid, {"last_attempt": "2000-01-01T00:00:00Z"})
    prices["price"] = HttpStatusError(503)
    _, refreshed = call("POST", f"/api/links/{lid}/refresh")
    assert refreshed["last_status"] == "blocked" and refreshed["last_price"] == 45.0

    status, history = call("GET", f"/api/links/{lid}/history", query={"days": "30"})
    assert status == 200 and [p["price"] for p in history["points"]] == [59.9, 45.0, 45.0]
    assert call("GET", f"/api/links/{lid}/history", query={"days": "7"})[0] == 400

    status, listing = call("GET", "/api/products")
    assert status == 200 and len(listing) == 1
    summary = listing[0]
    assert summary["best"]["price"] == 45.0 and summary["best"]["shop"] == "shop.example.de"
    assert summary["status"] == "blocked"
    assert len(summary["sparkline"]) == 3
    assert summary["change_30d_pct"] == -24.9

    # Changing the target re-arms alerts.
    status, updated = call("PUT", f"/api/products/{pid}", {"target_price": None, "name": "Desk lamp"})
    assert status == 200 and updated["name"] == "Desk lamp" and "target_price" not in updated

    status, _ = call("DELETE", f"/api/products/{pid}")
    assert status == 204
    assert call("GET", f"/api/products/{pid}")[0] == 404
    assert db.history(lid) == []


def test_links_crud(invoked: Any, prices: dict[str, Any], mails: list[Decimal]) -> None:
    _, product = call("POST", "/api/products", {"name": "Chair"})
    pid = product["id"]
    status, link = call(
        "POST", f"/api/products/{pid}/links", {"url": "https://www.amazon.de/x/dp/B0ABCDEF12?tag=1"}
    )
    assert (
        status == 201 and link["url"] == "https://www.amazon.de/dp/B0ABCDEF12" and link["shop"] == "amazon.de"
    )
    status, _ = call("POST", f"/api/products/{pid}/links", {"url": "https://amazon.de/dp/B0ABCDEF12"})
    assert status == 201  # different host spelling is a different URL
    status, body = call("POST", f"/api/products/{pid}/links", {"url": "https://www.amazon.de/dp/B0ABCDEF12"})
    assert status == 409 and body["error"] == "duplicate"

    status, _ = call("DELETE", f"/api/products/{pid}/links/{link['id']}")
    assert status == 204
    assert call("DELETE", f"/api/products/{pid}/links/{link['id']}")[0] == 404


def test_refresh_all(invoked: Any, prices: dict[str, Any], mails: list[Decimal]) -> None:
    call(
        "POST", "/api/products", {"name": "A", "links": ["https://a.example.de/1", "https://b.example.de/1"]}
    )
    invoked.clear()
    status, body = call("POST", "/api/refresh")
    assert status == 202 and body["queued"] == 2
    assert invoked and invoked[0][1] is False


def test_scheduled_run(
    table: Any, prices: dict[str, Any], mails: list[Decimal], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scraper.time, "sleep", lambda _s: None)
    product = db.create_product("X", Decimal("100"))
    db.add_link(product["id"], "https://a.example.de/1", "a.example.de", "EUR")
    db.add_link(product["id"], "https://b.example.de/1", "b.example.de", "EUR")
    result = scraper.handler({"source": "schedule"})
    assert result["summary"] == {"ok": 2}
    assert len(mails) == 2
    # A second overlapping run within a minute skips everything.
    assert scraper.handler({"source": "schedule"})["summary"] == {"skipped": 2}


def test_tags(invoked: Any, prices: dict[str, Any], mails: list[Decimal]) -> None:
    status, product = call(
        "POST", "/api/products", {"name": "Headphones", "tags": [" Audio ", "audio", "Over  Ear", ""]}
    )
    assert status == 201 and product["tags"] == ["Audio", "Over Ear"]
    pid = product["id"]

    status, listing = call("GET", "/api/products")
    assert listing[0]["tags"] == ["Audio", "Over Ear"]

    status, updated = call("PUT", f"/api/products/{pid}", {"tags": ["Audio", "Gift"]})
    assert status == 200 and updated["tags"] == ["Audio", "Gift"]

    status, updated = call("PUT", f"/api/products/{pid}", {"tags": []})
    assert status == 200 and "tags" not in updated

    assert call("PUT", f"/api/products/{pid}", {"tags": ["x" * 31]})[0] == 400
    assert call("PUT", f"/api/products/{pid}", {"tags": [f"t{i}" for i in range(11)]})[0] == 400
    assert call("POST", "/api/products", {"name": "x", "tags": "audio"})[0] == 400


AMAZON_PAGE = """<html><head><link rel="canonical" href="https://www.amazon.de/Garmin/dp/B0DD2HYX6L"></head><body>
<span id="productTitle">Garmin Forerunner 265</span>
<div id="corePriceDisplay_desktop_feature_div"><span class="a-price priceToPay"><span class="a-offscreen">329,99 €</span></span></div>
</body></html>"""


def test_share_link_resolved_on_add(
    invoked: Any, monkeypatch: pytest.MonkeyPatch, mails: list[Decimal]
) -> None:
    monkeypatch.setattr(scraper, "fetch", lambda url, profile="chrome", timeout=15: Page(url, AMAZON_PAGE))
    status, product = call(
        "POST", "/api/products", {"name": "Watch", "links": ["https://amzn.eu/d/03kI9SjY"]}
    )
    assert status == 201
    link = product["links"][0]
    assert link["url"] == "https://www.amazon.de/dp/B0DD2HYX6L" and link["shop"] == "amazon.de"
    # Same product shared again from the app is recognised as a duplicate.
    status, body = call("POST", f"/api/products/{product['id']}/links", {"url": "https://amzn.eu/d/0other"})
    assert status == 409 and body["error"] == "duplicate"


def test_share_link_resolved_by_scraper(
    table: Any, monkeypatch: pytest.MonkeyPatch, mails: list[Decimal]
) -> None:
    """Links stored before resolution existed are fixed on the next scrape."""
    monkeypatch.setattr(scraper.time, "sleep", lambda _s: None)
    final = "https://www.amazon.de/dp/B0DD2HYX6L?ref=cm_sw_r_cso_cp_apan_dp_X"
    monkeypatch.setattr(scraper, "fetch", lambda url, profile="chrome", timeout=15: Page(final, AMAZON_PAGE))
    product = db.create_product("Watch", None)
    stored = db.add_link(product["id"], "https://amzn.eu/d/03kI9SjY", "amzn.eu", "EUR")
    assert scraper.handler({"source": "schedule"})["summary"] == {"ok": 1}
    link = db.get_link(stored["id"])
    assert link is not None
    assert (link["url"], link["shop"], link["last_price"]) == (
        "https://www.amazon.de/dp/B0DD2HYX6L",
        "amazon.de",
        Decimal("329.99"),
    )


def test_amazon_without_buy_box_uses_offers(
    table: Any, monkeypatch: pytest.MonkeyPatch, mails: list[Decimal]
) -> None:
    monkeypatch.setattr(scraper.time, "sleep", lambda _s: None)
    no_buy_box = """<html><body><input type="hidden" id="ASIN" value="B0BS1T9J4Y">
    <span id="productTitle">Garmin Forerunner 255</span>
    <div id="availability"><span>Derzeit nicht verfügbar.</span></div></body></html>"""
    offers = """<div id="aod-offer"><div id="aod-offer-heading"><h5>Gebraucht - Wie neu</h5></div>
      <span id="aod-price-1"><span class="a-price apex-pricetopay-value"><span class="a-offscreen">199,00 €</span></span></span></div>
    <div id="aod-offer"><div id="aod-offer-heading"><h5>Neu</h5></div>
      <span id="aod-price-2"><span class="a-price apex-pricetopay-value"><span class="a-offscreen"> </span>
      <span class="a-price-symbol">€</span><span class="a-price-whole">379,</span><span class="a-price-fraction">99</span></span></span></div>"""
    requested: list[str] = []

    def fake_fetch(url: str, profile: str = "chrome", timeout: float = 15) -> Page:
        requested.append(url)
        return Page(url, offers if "aodAjaxMain" in url else no_buy_box)

    monkeypatch.setattr(scraper, "fetch", fake_fetch)
    product = db.create_product("Watch", None)
    stored = db.add_link(product["id"], "https://www.amazon.de/dp/B0BS1T9J4Y", "amazon.de", "EUR")
    assert scraper.handler({"source": "schedule"})["summary"] == {"ok": 1}
    link = db.get_link(stored["id"])
    assert link is not None and link["last_price"] == Decimal("379.99") and link["last_in_stock"] is True
    assert link["title"] == "Garmin Forerunner 255"
    assert (
        requested[1]
        == "https://www.amazon.de/gp/product/ajax/aodAjaxMain/?asin=B0BS1T9J4Y&pc=dp&experienceId=aodAjaxMain"
    )
