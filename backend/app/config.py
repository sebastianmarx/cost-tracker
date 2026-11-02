"""Runtime configuration, read from the Lambda environment on every access so
tests can override values with monkeypatch."""

from __future__ import annotations

import os


def table_name() -> str:
    return os.environ.get("TABLE_NAME", "cost-tracker")


def scraper_function() -> str:
    return os.environ.get("SCRAPER_FUNCTION_NAME", "cost-tracker-scraper")


def owner_sub() -> str:
    """Cognito `sub` of the single allowed user. Empty disables the check."""
    return os.environ.get("OWNER_SUB", "")


def refresh_min_interval() -> int:
    return int(os.environ.get("REFRESH_MIN_INTERVAL_SECONDS", "300"))


def ses_from() -> str:
    return os.environ.get("SES_FROM", "")


def alert_to() -> str:
    return os.environ.get("ALERT_TO", "")


def app_url() -> str:
    return os.environ.get("APP_URL", "http://localhost:5173").rstrip("/")
