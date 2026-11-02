import socket

import pytest

from app.urls import InvalidUrl, assert_public_host, is_short_link, normalize_url, shop_name, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "javascript:alert(1)",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "https://user:pw@example.com/",
        "https://example.com:8443/",
        "https://localhost/",
        "",
        "https://example.com/" + "a" * 3000,
    ],
)
def test_validate_url_rejects(url: str) -> None:
    with pytest.raises(InvalidUrl):
        validate_url(url)


def test_normalize_amazon() -> None:
    url = "https://www.amazon.de/Some-Product-Name/dp/B0ABCDEF12/ref=sr_1_3?keywords=x&tag=abc"
    assert normalize_url(url) == "https://www.amazon.de/dp/B0ABCDEF12"
    assert (
        normalize_url("https://amazon.com/gp/product/b0abcdef12?th=1") == "https://amazon.com/dp/B0ABCDEF12"
    )


def test_normalize_generic_keeps_query_drops_fragment() -> None:
    assert (
        normalize_url("HTTPS://Shop.Example.COM/p/1?variant=2#reviews")
        == "https://shop.example.com/p/1?variant=2"
    )


def test_shop_name() -> None:
    assert shop_name("https://www.otto.de/p/1") == "otto.de"


def _fake_resolver(ip: str):  # type: ignore[no-untyped-def]
    def resolve(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolve


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "169.254.169.254",
        "192.168.1.1",
        "100.64.0.1",
        "::1",
        "fd00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_assert_public_host_blocks_private(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolver(ip))
    with pytest.raises(InvalidUrl):
        assert_public_host("https://evil.example.com/")


def test_assert_public_host_allows_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolver("93.184.216.34"))
    assert_public_host("https://example.com/")


def test_short_links() -> None:
    assert is_short_link("https://amzn.eu/d/03kI9SjY")
    assert is_short_link("https://amzn.to/3abc")
    assert is_short_link("https://a.co/d/xyz")
    assert not is_short_link("https://www.amazon.de/dp/B0ABCDEF12")
