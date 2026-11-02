"""DynamoDB single-table repository.

| Entity      | PK               | SK               | GSI1PK   | GSI1SK       |
|-------------|------------------|------------------|----------|--------------|
| Product     | PRODUCT#<pid>    | META             | PRODUCT  | <created_at> |
| Link        | PRODUCT#<pid>    | LINK#<lid>       | LINK     | <lid>        |
| Price point | LINK#<lid>       | PRICE#<iso-ts>   | -        | -            |
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from app import config

# Points kept on the link item itself so the dashboard needs no history queries.
RECENT_POINTS = 60

_table: Any = None


def table() -> Any:
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(config.table_name())
    return _table


def reset() -> None:
    """Drops the cached table handle (tests)."""
    global _table
    _table = None


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id() -> str:
    return uuid.uuid4().hex


def _query_all(**kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        page = table().query(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _strip(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK")}


def _update_expression(fields: dict[str, Any]) -> dict[str, Any]:
    """Builds UpdateItem kwargs. `None` values remove the attribute."""
    sets = {k: v for k, v in fields.items() if v is not None}
    removes = [k for k, v in fields.items() if v is None]
    clauses = []
    if sets:
        clauses.append("SET " + ", ".join(f"#{k} = :{k}" for k in sets))
    if removes:
        clauses.append("REMOVE " + ", ".join(f"#{k}" for k in removes))
    kwargs: dict[str, Any] = {
        "UpdateExpression": " ".join(clauses),
        "ExpressionAttributeNames": {f"#{k}": k for k in fields},
    }
    if sets:
        kwargs["ExpressionAttributeValues"] = {f":{k}": v for k, v in sets.items()}
    return kwargs


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
def create_product(name: str, target_price: Decimal | None, tags: list[str] | None = None) -> dict[str, Any]:
    pid = new_id()
    ts = now_iso()
    item: dict[str, Any] = {
        "PK": f"PRODUCT#{pid}",
        "SK": "META",
        "GSI1PK": "PRODUCT",
        "GSI1SK": ts,
        "id": pid,
        "name": name,
        "created_at": ts,
        "updated_at": ts,
    }
    if target_price is not None:
        item["target_price"] = target_price
    if tags:
        item["tags"] = tags
    table().put_item(Item=item)
    return _strip(item)


def list_products() -> list[dict[str, Any]]:
    items = _query_all(
        IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("PRODUCT"), ScanIndexForward=False
    )
    return [_strip(i) for i in items]


def get_product(pid: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    items = _query_all(KeyConditionExpression=Key("PK").eq(f"PRODUCT#{pid}"))
    meta = next((_strip(i) for i in items if i["SK"] == "META"), None)
    links = [_strip(i) for i in items if i["SK"].startswith("LINK#")]
    links.sort(key=lambda link: link.get("created_at", ""))
    return meta, links


def update_product(pid: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """`None` values remove the attribute."""
    try:
        result = table().update_item(
            Key={"PK": f"PRODUCT#{pid}", "SK": "META"},
            **_update_expression({**fields, "updated_at": now_iso()}),
            ConditionExpression="attribute_exists(PK)",
            ReturnValues="ALL_NEW",
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException:
        return None
    return _strip(result["Attributes"])


def delete_product(pid: str) -> None:
    items = _query_all(KeyConditionExpression=Key("PK").eq(f"PRODUCT#{pid}"))
    with table().batch_writer() as batch:
        for item in items:
            if item["SK"].startswith("LINK#"):
                _delete_history(batch, item["id"])
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


# --------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------
def add_link(pid: str, url: str, shop: str, currency: str) -> dict[str, Any]:
    lid = new_id()
    item = {
        "PK": f"PRODUCT#{pid}",
        "SK": f"LINK#{lid}",
        "GSI1PK": "LINK",
        "GSI1SK": lid,
        "id": lid,
        "product_id": pid,
        "url": url,
        "shop": shop,
        "currency": currency,
        "last_status": "pending",
        "recent": [],
        "created_at": now_iso(),
    }
    table().put_item(Item=item)
    return _strip(item)


def list_all_links() -> list[dict[str, Any]]:
    items = _query_all(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("LINK"))
    return [_strip(i) for i in items]


def get_link(lid: str) -> dict[str, Any] | None:
    items = _query_all(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq("LINK") & Key("GSI1SK").eq(lid),
    )
    return _strip(items[0]) if items else None


def count_links() -> int:
    page = table().query(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq("LINK"), Select="COUNT")
    return int(page.get("Count", 0))


def update_link(pid: str, lid: str, fields: dict[str, Any]) -> None:
    try:
        table().update_item(
            Key={"PK": f"PRODUCT#{pid}", "SK": f"LINK#{lid}"},
            **_update_expression(fields),
            ConditionExpression="attribute_exists(PK)",
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException:
        pass  # link was deleted while it was being scraped


def claim_attempt(pid: str, lid: str, min_interval_s: int) -> bool:
    """Atomically sets last_attempt unless the link was tried too recently."""
    now = now_iso()
    cutoff = (datetime.now(UTC) - timedelta(seconds=min_interval_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        table().update_item(
            Key={"PK": f"PRODUCT#{pid}", "SK": f"LINK#{lid}"},
            UpdateExpression="SET last_attempt = :now",
            ConditionExpression="attribute_exists(PK) AND "
            "(attribute_not_exists(last_attempt) OR last_attempt < :cutoff)",
            ExpressionAttributeValues={":now": now, ":cutoff": cutoff},
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True


def delete_link(pid: str, lid: str) -> bool:
    try:
        table().delete_item(
            Key={"PK": f"PRODUCT#{pid}", "SK": f"LINK#{lid}"},
            ConditionExpression="attribute_exists(PK)",
        )
    except table().meta.client.exceptions.ConditionalCheckFailedException:
        return False
    with table().batch_writer() as batch:
        _delete_history(batch, lid)
    return True


# --------------------------------------------------------------------------
# Price history
# --------------------------------------------------------------------------
def put_price(pid: str, lid: str, ts: str, price: Decimal, currency: str, in_stock: bool | None) -> None:
    item: dict[str, Any] = {
        "PK": f"LINK#{lid}",
        "SK": f"PRICE#{ts}",
        "product_id": pid,
        "ts": ts,
        "price": price,
        "currency": currency,
    }
    if in_stock is not None:
        item["in_stock"] = in_stock
    table().put_item(Item=item)


def history(lid: str, days: int = 0) -> list[dict[str, Any]]:
    """Price points, oldest first. days=0 returns everything."""
    condition = Key("PK").eq(f"LINK#{lid}")
    if days > 0:
        condition = condition & Key("SK").gte(f"PRICE#{iso_days_ago(days)}")
    else:
        condition = condition & Key("SK").begins_with("PRICE#")
    return [
        {"ts": i["ts"], "price": i["price"], "in_stock": i.get("in_stock")}
        for i in _query_all(KeyConditionExpression=condition)
    ]


def _delete_history(batch: Any, lid: str) -> None:
    keys = _query_all(
        KeyConditionExpression=Key("PK").eq(f"LINK#{lid}"),
        ProjectionExpression="PK, SK",
    )
    for key in keys:
        batch.delete_item(Key={"PK": key["PK"], "SK": key["SK"]})
