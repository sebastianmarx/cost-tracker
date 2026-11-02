"""URL validation shared by the API (on input) and the scraper (before every
request, including redirects)."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}

_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/asin)/([A-Z0-9]{10})(?:[/?]|$)", re.I)


class InvalidUrl(ValueError):
    pass


def validate_url(url: str) -> str:
    """Syntactic checks. Returns the URL with a lowercased host."""
    url = url.strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise InvalidUrl("URL is empty or too long")
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidUrl("Only http and https URLs are allowed")
    if parts.username or parts.password:
        raise InvalidUrl("URLs with credentials are not allowed")
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        raise InvalidUrl("URL needs a public host name")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise InvalidUrl("IP addresses are not allowed, use a host name")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("Invalid port") from exc
    if port not in ALLOWED_PORTS:
        raise InvalidUrl("Only ports 80 and 443 are allowed")
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


# Share links from the Amazon app and other shops. They only redirect, so the
# real product URL is resolved and stored instead.
SHORT_LINK_HOSTS = {"amzn.eu", "amzn.to", "amzn.com", "a.co", "amzn.asia"}


def is_short_link(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host in SHORT_LINK_HOSTS


def is_amazon(host: str) -> bool:
    host = host.lower()
    return host.startswith(("amazon.", "www.amazon.", "smile.amazon.")) or ".amazon." in host


def normalize_url(url: str) -> str:
    """Validates and strips shop-specific noise. Amazon links become /dp/<ASIN>."""
    url = validate_url(url)
    parts = urlsplit(url)
    if is_amazon(parts.hostname or ""):
        match = _ASIN.search(parts.path)
        if match:
            return f"https://{parts.hostname}/dp/{match.group(1).upper()}"
    return url


def shop_name(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_public_host(url: str) -> None:
    """Resolves the host and rejects anything that is not a public address.

    Blocks loopback (incl. the Lambda runtime API on 127.0.0.1), link-local
    (169.254.0.0/16 metadata ranges), RFC1918, CGNAT, ULA and multicast.
    """
    validate_url(url)
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise InvalidUrl(f"Host cannot be resolved: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not _is_public_ip(ip):
            raise InvalidUrl(f"Host resolves to a non-public address: {host}")
