from datetime import UTC, datetime
from decimal import Decimal

from chat import render
from factories import NOW
from seed import build_items, load_sample_data, seed

from order_tools import tools


def test_sample_data_covers_every_return_outcome():
    orders, _ = build_items(load_sample_data(), NOW)
    by_id = {order["order_id"]: order for order in orders}

    assert by_id["ORD-1001"]["delivered_at"] == "2026-09-30T12:00:00+00:00"
    assert by_id["ORD-1001"]["total"] == Decimal("174.00")
    assert "delivered_at" not in by_id["ORD-1003"]
    assert not any(key.endswith("_days_ago") for order in orders for key in order)


def test_restock_dates_are_relative():
    _, inventory = build_items(load_sample_data(), NOW)
    mouse = next(item for item in inventory if item["sku"] == "MS-WL-02")

    assert mouse["restock_date"] == "2026-10-17"
    assert "restock_in_days" not in mouse


def test_seeded_data_drives_the_tools(tables):
    seed("orders", "inventory", now=NOW)
    args = {"customer_email": "alex@example.com", "reason": "Changed my mind"}

    assert tools.request_return({**args, "order_id": "ORD-1001"})["already_requested"] is False
    assert tools.get_order({**args, "order_id": "ORD-1002"})["status"] == "DELIVERED"
    assert tools.check_inventory({"sku": "MS-WL-02"})["in_stock"] is False


def test_seed_defaults_to_the_current_time(tables):
    assert seed("orders", "inventory") == (4, 4)
    stored = tables[0].get_item(Key={"order_id": "ORD-1004"})["Item"]
    assert datetime.fromisoformat(stored["placed_at"]) < datetime.now(UTC)


def test_render_shows_text_and_tool_calls():
    stream = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"name": "orders___get_order"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "Your order "}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"text": "has shipped."}}},
        {"messageStop": {"stopReason": "end_turn"}},
    ]

    assert "".join(render(stream)) == "\n  [tool] orders___get_order\nYour order has shipped."


def test_render_flags_guardrail_interventions():
    stream = [{"messageStop": {"stopReason": "guardrail_intervened"}}]

    assert "".join(render(stream)) == "\n  [guardrail intervened]"
