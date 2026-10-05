"""Tool implementations.

Each tool takes the arguments the model supplied and returns a
JSON-serialisable dict. The schemas the model sees live in
schemas/tools.json; tests/test_schema.py keeps the two in step.
"""

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from order_tools import aws
from order_tools.validation import EMAIL, ORDER_ID, SKU, ToolError, required_str

Args = dict[str, Any]


# One message for both "no such order" and "wrong email", so the tool cannot
# be used to discover which order numbers exist.
def _order_not_found() -> ToolError:
    return ToolError("ORDER_NOT_FOUND", "No order matches that order number and email address.")


def _now() -> datetime:
    return datetime.now(UTC)


def _plain(value: Any) -> Any:
    """Convert DynamoDB Decimals to int or float so the result serialises."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _orders():
    return aws.dynamodb().Table(os.environ["ORDERS_TABLE"])


def _inventory():
    return aws.dynamodb().Table(os.environ["INVENTORY_TABLE"])


def _load_order(args: Args) -> Args:
    order_id = required_str(args, "order_id", max_len=16, pattern=ORDER_ID, normalize=str.upper)
    email = required_str(args, "customer_email", max_len=320, pattern=EMAIL, normalize=str.lower)

    order = _orders().get_item(Key={"order_id": order_id}).get("Item")
    if order is None or order["customer_email"] != email:
        raise _order_not_found()
    return order


def get_order(args: Args) -> Args:
    order = _load_order(args)
    return _plain(
        {
            "order_id": order["order_id"],
            "status": order["status"],
            "placed_at": order["placed_at"],
            "delivered_at": order.get("delivered_at"),
            "items": order["items"],
            "total": order["total"],
            "currency": order["currency"],
            "return_request": order.get("return_request"),
        }
    )


def check_inventory(args: Args) -> Args:
    sku = required_str(args, "sku", max_len=32, pattern=SKU, normalize=str.upper)

    item = _inventory().get_item(Key={"sku": sku}).get("Item")
    if item is None:
        raise ToolError("SKU_NOT_FOUND", f"There is no product with SKU {sku}.")
    return _plain(
        {
            "sku": item["sku"],
            "name": item["name"],
            "available": item["available"],
            "in_stock": item["available"] > 0,
            "restock_date": item.get("restock_date"),
        }
    )


def request_return(args: Args) -> Args:
    reason = required_str(args, "reason", max_len=500)
    order = _load_order(args)

    existing = order.get("return_request")
    if existing is not None:
        # Retries and repeated requests are expected from a conversational
        # caller. Answer with the original return rather than failing.
        return _plain({**existing, "status": order["status"], "already_requested": True})

    if order["status"] != "DELIVERED":
        raise ToolError(
            "NOT_RETURNABLE",
            f"This order is {order['status'].lower()}. Only delivered orders can be returned.",
        )

    window = int(os.environ.get("RETURN_WINDOW_DAYS", "30"))
    closes = datetime.fromisoformat(order["delivered_at"]) + timedelta(days=window)
    if _now() > closes:
        raise ToolError(
            "RETURN_WINDOW_CLOSED",
            f"The {window} day return window for this order closed on {closes.date().isoformat()}.",
        )

    return_request = {
        "return_id": f"RET-{uuid.uuid4().hex[:10].upper()}",
        "reason": reason,
        "requested_at": _now().isoformat(timespec="seconds"),
        "refund_amount": order["total"],
        "currency": order["currency"],
    }
    try:
        # The condition makes the write safe against a concurrent request for
        # the same order: exactly one of them creates the return.
        _orders().update_item(
            Key={"order_id": order["order_id"]},
            UpdateExpression="SET #status = :requested, return_request = :request",
            ConditionExpression="#status = :delivered AND attribute_not_exists(return_request)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":requested": "RETURN_REQUESTED",
                ":delivered": "DELIVERED",
                ":request": return_request,
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        raise ToolError(
            "CONFLICT",
            "The order changed while the return was being created. Look the order up again.",
        ) from exc

    return _plain({**return_request, "status": "RETURN_REQUESTED", "already_requested": False})


def search_policies(args: Args) -> Args:
    query = required_str(args, "query", max_len=500)

    response = aws.bedrock_agent_runtime().retrieve(
        knowledgeBaseId=os.environ["KNOWLEDGE_BASE_ID"],
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 4}},
    )
    return {
        "results": [
            {
                "text": result["content"]["text"],
                "source": result.get("location", {}).get("s3Location", {}).get("uri"),
                "score": round(result.get("score", 0.0), 3),
            }
            for result in response["retrievalResults"]
        ]
    }


TOOLS: dict[str, Callable[[Args], Args]] = {
    "get_order": get_order,
    "check_inventory": check_inventory,
    "request_return": request_return,
    "search_policies": search_policies,
}
