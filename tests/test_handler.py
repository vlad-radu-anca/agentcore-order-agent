import json
import logging
from types import SimpleNamespace

from factories import make_order

from order_tools.handler import lambda_handler, tool_name


def context(name):
    return SimpleNamespace(
        client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name}),
        aws_request_id="req-1",
    )


def test_strips_the_target_prefix():
    assert tool_name(context("order-tools___get_order")) == "get_order"


def test_tolerates_a_missing_prefix_or_context():
    assert tool_name(context("get_order")) == "get_order"
    assert tool_name(SimpleNamespace(client_context=None)) == ""


def test_dispatches_to_the_tool(orders):
    orders.put_item(Item=make_order())

    result = lambda_handler(
        {"order_id": "ORD-1001", "customer_email": "alex@example.com"},
        context("order-tools___get_order"),
    )

    assert result["order_id"] == "ORD-1001"


def test_tool_errors_become_results_the_agent_can_read(orders):
    result = lambda_handler(
        {"order_id": "ORD-9999", "customer_email": "alex@example.com"},
        context("order-tools___get_order"),
    )

    assert result == {"error": "ORDER_NOT_FOUND", "message": "No order matches that order number and email address."}


def test_unknown_tool():
    result = lambda_handler({}, context("order-tools___delete_everything"))

    assert result["error"] == "UNKNOWN_TOOL"


def test_non_object_arguments():
    result = lambda_handler(["ORD-1001"], context("order-tools___get_order"))

    assert result["error"] == "INVALID_INPUT"


def test_logs_the_outcome_but_not_the_arguments(orders, caplog):
    caplog.set_level(logging.INFO)

    lambda_handler(
        {"order_id": "ORD-9999", "customer_email": "alex@example.com"},
        context("order-tools___get_order"),
    )

    record = json.loads(caplog.records[-1].getMessage())
    assert record == {"tool": "get_order", "outcome": "ORDER_NOT_FOUND", "request_id": "req-1"}
    assert "alex@example.com" not in caplog.text
