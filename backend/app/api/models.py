"""Request bodies. Unknown fields are rejected."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.urls import InvalidUrl, normalize_url

MAX_LINKS_PER_PRODUCT = 10
MAX_LINKS_TOTAL = 200
MAX_TAGS = 10
MAX_TAG_LENGTH = 30

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Price = Annotated[Decimal, Field(gt=0, lt=1_000_000, max_digits=9, decimal_places=2)]


def _url(value: str) -> str:
    try:
        return normalize_url(value)
    except InvalidUrl as exc:
        raise ValueError(str(exc)) from exc


def _tags(value: list[str] | None) -> list[str] | None:
    """Trims, collapses whitespace and drops case-insensitive duplicates.

    The first spelling wins, so "Audio" and "audio" stay one tag.
    """
    if value is None:
        return None
    seen: dict[str, str] = {}
    for raw in value:
        tag = " ".join(str(raw).split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"Tags can have at most {MAX_TAG_LENGTH} characters")
        seen.setdefault(tag.casefold(), tag)
    if len(seen) > MAX_TAGS:
        raise ValueError(f"At most {MAX_TAGS} tags per product")
    return list(seen.values())


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    target_price: Price | None = None
    links: list[str] = Field(default_factory=list, max_length=MAX_LINKS_PER_PRODUCT)
    tags: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("tags")
    @classmethod
    def _valid_tags(cls, value: list[str]) -> list[str]:
        return _tags(value) or []

    @field_validator("links")
    @classmethod
    def _links(cls, value: list[str]) -> list[str]:
        normalized = [_url(v) for v in value]
        return list(dict.fromkeys(normalized))


class ProductUpdate(BaseModel):
    """Only fields present in the body are changed; `target_price: null` removes it."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    target_price: Price | None = None
    tags: list[str] | None = Field(default=None, max_length=50)

    @field_validator("tags")
    @classmethod
    def _valid_tags(cls, value: list[str] | None) -> list[str] | None:
        return _tags(value)


class LinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str

    @field_validator("url")
    @classmethod
    def _valid(cls, value: str) -> str:
        return _url(value)
