"""Test data shared across test modules."""

from datetime import UTC, datetime
from decimal import Decimal

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def make_order(**overrides):
    order = {
        "order_id": "ORD-1001",
        "customer_email": "alex@example.com",
        "status": "DELIVERED",
        "placed_at": "2026-09-26T12:00:00+00:00",
        "delivered_at": "2026-09-30T12:00:00+00:00",
        "currency": "EUR",
        "total": Decimal("174.00"),
        "items": [
            {"sku": "KB-ALU-75", "name": "Keyboard", "quantity": 1, "unit_price": Decimal("149.00")},
            {"sku": "CB-USBC-2M", "name": "Cable", "quantity": 2, "unit_price": Decimal("12.50")},
        ],
    }
    order.update(overrides)
    return order
