"""Price statistics computed from history points."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

WINDOWS = (30, 90, 180, 365)
_CENT = Decimal("0.01")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def window_stats(
    points: list[dict[str, Any]], days: int, now: datetime | None = None
) -> dict[str, Any] | None:
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days) if days else None
    prices = [Decimal(p["price"]) for p in points if since is None or _parse(p["ts"]) >= since]
    if not prices:
        return None
    avg = (sum(prices) / len(prices)).quantize(_CENT, ROUND_HALF_UP)
    return {"min": min(prices), "max": max(prices), "avg": avg, "count": len(prices)}


def change_pct(points: list[dict[str, Any]], days: int, now: datetime | None = None) -> float | None:
    """Change of the latest price against the first price inside the window."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    inside = [p for p in points if _parse(p["ts"]) >= since]
    if len(inside) < 2:
        return None
    first, last = Decimal(inside[0]["price"]), Decimal(inside[-1]["price"])
    if first == 0:
        return None
    return float(((last - first) / first * 100).quantize(Decimal("0.1"), ROUND_HALF_UP))


def link_stats(points: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """`points` must be sorted oldest first."""
    stats: dict[str, Any] = {f"d{d}": window_stats(points, d, now) for d in WINDOWS}
    stats["all"] = window_stats(points, 0, now)
    low = min(points, key=lambda p: (Decimal(p["price"]), p["ts"]), default=None)
    stats["all_time_low"] = {"price": low["price"], "ts": low["ts"]} if low else None
    stats["change_30d_pct"] = change_pct(points, 30, now)
    return stats
