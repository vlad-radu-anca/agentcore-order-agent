import boto3
import pytest
from factories import NOW
from moto import mock_aws

from order_tools import aws, tools


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    # Fake credentials, so nothing in the test run can reach a real account.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("ORDERS_TABLE", "orders")
    monkeypatch.setenv("INVENTORY_TABLE", "inventory")
    monkeypatch.setenv("KNOWLEDGE_BASE_ID", "KB12345678")
    monkeypatch.setenv("RETURN_WINDOW_DAYS", "30")
    monkeypatch.setattr(tools, "_now", lambda: NOW)

    # Every test starts with fresh clients, created inside its own mocks.
    aws.dynamodb.cache_clear()
    aws.bedrock_agent_runtime.cache_clear()


@pytest.fixture
def tables():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb")
        orders = dynamodb.create_table(
            TableName="orders",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        inventory = dynamodb.create_table(
            TableName="inventory",
            KeySchema=[{"AttributeName": "sku", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "sku", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield orders, inventory


@pytest.fixture
def orders(tables):
    return tables[0]


@pytest.fixture
def inventory(tables):
    return tables[1]
