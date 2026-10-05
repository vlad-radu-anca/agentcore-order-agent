"""Load the sample orders and inventory into DynamoDB.

    python scripts/seed.py --orders-table NAME --inventory-table NAME

Dates in data/sample_data.json are relative ("delivered_days_ago"), so a
fresh seed always has one order inside the return window, one outside it,
one in transit and one not yet shipped.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3

SAMPLE_DATA = Path(__file__).resolve().parent.parent / "data" / "sample_data.json"


def build_items(data: dict[str, Any], now: datetime) -> tuple[list[dict], list[dict]]:
    def days_ago(days: int) -> str:
        return (now - timedelta(days=days)).isoformat(timespec="seconds")

    orders = []
    for source in data["orders"]:
        order = {key: value for key, value in source.items() if not key.endswith("_days_ago")}
        order["placed_at"] = days_ago(source["placed_days_ago"])
        if "delivered_days_ago" in source:
            order["delivered_at"] = days_ago(source["delivered_days_ago"])
        order["total"] = sum(item["unit_price"] * item["quantity"] for item in source["items"])
        orders.append(order)

    inventory = []
    for source in data["inventory"]:
        item = {key: value for key, value in source.items() if key != "restock_in_days"}
        if "restock_in_days" in source:
            item["restock_date"] = (now + timedelta(days=source["restock_in_days"])).date().isoformat()
        inventory.append(item)

    return orders, inventory


def load_sample_data(path: Path = SAMPLE_DATA) -> dict[str, Any]:
    # DynamoDB rejects floats, so prices are parsed straight into Decimal.
    return json.loads(path.read_text(), parse_float=Decimal)


def seed(orders_table: str, inventory_table: str, now: datetime | None = None) -> tuple[int, int]:
    orders, inventory = build_items(load_sample_data(), now or datetime.now(UTC))
    dynamodb = boto3.resource("dynamodb")
    for table_name, items in ((orders_table, orders), (inventory_table, inventory)):
        with dynamodb.Table(table_name).batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)
    return len(orders), len(inventory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--orders-table", required=True)
    parser.add_argument("--inventory-table", required=True)
    args = parser.parse_args()

    orders, inventory = seed(args.orders_table, args.inventory_table)
    print(f"Seeded {orders} orders and {inventory} inventory items.")


if __name__ == "__main__":
    main()
