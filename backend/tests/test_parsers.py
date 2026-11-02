from decimal import Decimal

import pytest

from app.scraper.parsers import Blocked, ParseError, parse

AMAZON_PAGE = """
<html><head><title>Amazon.de: Kopfhörer</title></head><body>
<span id="productTitle">  Sony WH-1000XM6   Kopfhörer </span>
<div id="corePrice_feature_div">
  <span class="a-price"><span class="a-offscreen">1.299,99&nbsp;€</span>
  <span aria-hidden="true"><span class="a-price-whole">1.299,</span><span class="a-price-fraction">99</span></span></span>
</div>
<div id="availability"><span>Auf Lager</span></div>
<img id="landingImage" data-old-hires="https://m.media-amazon.com/images/I/abc.jpg" src="https://m.media-amazon.com/images/I/abc._SX300_.jpg">
</body></html>
"""

AMAZON_WHOLE_ONLY = """
<html><body>
<div id="corePriceDisplay_desktop_feature_div">
  <span class="a-price"><span class="a-offscreen"></span>
  <span class="a-price-whole">349,</span><span class="a-price-fraction">00</span><span class="a-price-symbol">€</span></span>
</div>
<div id="availability">Derzeit nicht verfügbar.</div>
</body></html>
"""

AMAZON_CAPTCHA = """
<html><head><title>Amazon.de</title></head><body>
<form method="get" action="/errors/validateCaptcha"><input name="amzn"></form>
</body></html>
"""

JSON_LD_PAGE = """
<html><head>
<meta property="og:image" content="https://cdn.shop.example/og.jpg">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"BreadcrumbList"}</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"Product","name":"Espresso Machine",
 "image":["https://cdn.shop.example/p1.jpg"],
 "offers":{"@type":"Offer","price":"549.00","priceCurrency":"EUR",
           "availability":"https://schema.org/InStock"}}]}
</script></head><body></body></html>
"""

JSON_LD_AGGREGATE = """
<script type="application/ld+json">
[{"@type":["Product"],"name":"Bike","offers":{"@type":"AggregateOffer","lowPrice":999.5,"highPrice":1200,
  "priceCurrency":"EUR"}}]
</script>
"""

META_PAGE = """
<html><head>
<meta property="og:title" content="Desk Lamp">
<meta property="product:price:amount" content="39.95">
<meta property="product:price:currency" content="EUR">
<meta property="product:availability" content="out of stock">
</head></html>
"""

MICRODATA_PAGE = """
<div itemscope itemtype="https://schema.org/Product">
  <h1 itemprop="name">Chair</h1>
  <span itemprop="price" content="129.00">129,00 €</span>
  <meta itemprop="priceCurrency" content="EUR">
  <link itemprop="availability" href="https://schema.org/InStock">
</div>
"""


def test_amazon_offscreen_price() -> None:
    result = parse("https://www.amazon.de/dp/B0ABCDEF12", AMAZON_PAGE)
    assert result.price == Decimal("1299.99")
    assert result.currency == "EUR"
    assert result.in_stock is True
    assert result.title == "Sony WH-1000XM6 Kopfhörer"
    assert result.image_url == "https://m.media-amazon.com/images/I/abc.jpg"


def test_amazon_whole_fraction_and_unavailable() -> None:
    result = parse("https://www.amazon.de/dp/B0ABCDEF12", AMAZON_WHOLE_ONLY)
    assert result.price == Decimal("349.00")
    assert result.in_stock is False


def test_amazon_captcha() -> None:
    with pytest.raises(Blocked):
        parse("https://www.amazon.de/dp/B0ABCDEF12", AMAZON_CAPTCHA)


def test_amazon_no_price() -> None:
    with pytest.raises(ParseError):
        parse("https://www.amazon.de/dp/B0ABCDEF12", "<html><body>nothing</body></html>")


def test_json_ld_graph() -> None:
    result = parse("https://shop.example/p/1", JSON_LD_PAGE)
    assert (result.price, result.currency, result.in_stock) == (Decimal("549.00"), "EUR", True)
    assert result.title == "Espresso Machine"
    assert result.image_url == "https://cdn.shop.example/p1.jpg"


def test_json_ld_aggregate_offer() -> None:
    result = parse("https://bikes.example.de/p", JSON_LD_AGGREGATE)
    assert result.price == Decimal("999.50")
    assert result.in_stock is None


def test_meta_tags() -> None:
    result = parse("https://lamps.example.de/p", META_PAGE)
    assert (result.price, result.currency, result.in_stock, result.title) == (
        Decimal("39.95"),
        "EUR",
        False,
        "Desk Lamp",
    )


def test_microdata() -> None:
    result = parse("https://chairs.example.de/p", MICRODATA_PAGE)
    assert (result.price, result.currency, result.in_stock, result.title) == (
        Decimal("129.00"),
        "EUR",
        True,
        "Chair",
    )


def test_generic_bot_wall() -> None:
    with pytest.raises(Blocked):
        parse("https://shop.example/p", '<html><div id="challenge-platform"></div></html>')


def test_generic_nothing() -> None:
    with pytest.raises(ParseError):
        parse("https://shop.example/p", "<html><title>Hi</title></html>")


AMAZON_APEX_DEAL = """
<html><body><span id="productTitle">Watch</span>
<div id="corePriceDisplay_desktop_feature_div">
  <span class="a-price a-text-price"><span class="a-offscreen">419,99 €</span></span>
  <span class="a-price apex-pricetopay-value"><span class="a-offscreen"> </span>
    <span class="a-price-whole">379,</span><span class="a-price-fraction">99</span><span class="a-price-symbol">€</span></span>
</div>
<div id="availability"><script>var x = "derzeit nicht verfügbar";</script><span>Auf Lager</span></div>
</body></html>
"""


def test_amazon_prefers_price_to_pay_over_list_price() -> None:
    result = parse("https://www.amazon.de/dp/B0ABCDEF12", AMAZON_APEX_DEAL)
    assert result.price == Decimal("379.99")
    assert result.in_stock is True  # script text is ignored


def test_amazon_no_buy_box() -> None:
    from app.scraper.parsers import NoBuyBox

    html = '<input id="ASIN" value="B0BS1T9J4Y"><span id="productTitle">Watch</span>'
    with pytest.raises(NoBuyBox) as info:
        parse("https://www.amazon.de/dp/B0BS1T9J4Y", html)
    assert info.value.asin == "B0BS1T9J4Y" and info.value.title == "Watch"


def test_amazon_offers_only_used() -> None:
    from app.scraper.parsers import amazon

    html = """<div id="aod-offer"><div id="aod-offer-heading">Gebraucht - Gut</div>
      <span id="aod-price-1"><span class="a-price"><span class="a-offscreen">99,00 €</span></span></span></div>"""
    with pytest.raises(ParseError):
        amazon.parse_offers(html, "www.amazon.de")
