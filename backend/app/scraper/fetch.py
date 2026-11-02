"""HTTP fetching with browser TLS impersonation and SSRF protection.

Redirects are followed manually so every hop is re-checked against the
public-address rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from curl_cffi import requests as curl

from app.urls import InvalidUrl, assert_public_host

MAX_REDIRECTS = 3
MAX_BODY_BYTES = 5 * 1024 * 1024
TIMEOUT_S = 15

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

# Different browser fingerprints for the retry.
PROFILES = ("chrome", "safari", "firefox")


class FetchError(Exception):
    pass


class HttpStatusError(FetchError):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status

    @property
    def looks_blocked(self) -> bool:
        """Shops answer bots with 403/429/503 rather than a real error."""
        return self.status in (403, 429, 503)


@dataclass
class Page:
    url: str  # final URL after redirects
    html: str


def fetch(url: str, profile: str = "chrome", timeout: float = TIMEOUT_S) -> Page:
    current = url
    with curl.Session(impersonate=profile) as session:  # type: ignore[arg-type]
        for _ in range(MAX_REDIRECTS + 1):
            try:
                assert_public_host(current)
            except InvalidUrl as exc:
                raise FetchError(str(exc)) from exc
            try:
                response = session.get(
                    current,
                    headers=HEADERS,
                    timeout=timeout,
                    allow_redirects=False,
                    stream=True,
                )
            except Exception as exc:  # curl_cffi raises its own RequestException tree
                raise FetchError(f"Request failed: {type(exc).__name__}") from exc
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError("Redirect without location")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise HttpStatusError(response.status_code)
                body = bytearray()
                for chunk in response.iter_content():
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        raise FetchError("Response too large")
                encoding = response.encoding or "utf-8"
                return Page(current, bytes(body).decode(encoding, errors="replace"))
            finally:
                response.close()
    raise FetchError("Too many redirects")


def resolve_redirects(url: str, timeout: float = 8) -> str:
    """Follows redirects without reading bodies and returns the final URL.

    Used for share links (amzn.eu/d/..., a.co/...) so the real product URL is
    stored. Every hop passes the same public-address check as fetch().
    """
    current = url
    with curl.Session(impersonate="chrome") as session:  # type: ignore[arg-type]
        for _ in range(MAX_REDIRECTS + 1):
            try:
                assert_public_host(current)
            except InvalidUrl as exc:
                raise FetchError(str(exc)) from exc
            try:
                response = session.get(
                    current, headers=HEADERS, timeout=timeout, allow_redirects=False, stream=True
                )
            except Exception as exc:
                raise FetchError(f"Request failed: {type(exc).__name__}") from exc
            try:
                location = response.headers.get("location")
                if response.status_code not in (301, 302, 303, 307, 308) or not location:
                    return current
                current = urljoin(current, location)
            finally:
                response.close()
    raise FetchError("Too many redirects")
