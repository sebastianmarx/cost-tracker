from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from app import db


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("TABLE_NAME", "cost-tracker-test")
    monkeypatch.setenv("OWNER_SUB", "owner-sub")
    monkeypatch.setenv("SES_FROM", "Cost Tracker <costtracker@example.com>")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    monkeypatch.setenv("APP_URL", "https://costtracker.example.com")
    os.environ.pop("AWS_PROFILE", None)


@pytest.fixture
def table() -> Iterator[Any]:
    with mock_aws():
        db.reset()
        resource = boto3.resource("dynamodb", region_name="eu-central-1")
        created = resource.create_table(
            TableName="cost-tracker-test",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        yield created
        db.reset()
