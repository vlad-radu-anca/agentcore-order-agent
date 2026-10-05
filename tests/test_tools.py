import boto3
import pytest
from botocore.stub import Stubber
from factories import make_order

from order_tools import aws, tools
from order_tools.validation import ToolError

RETURN_ARGS = {"order_id": "ORD-1001", "customer_email": "alex@example.com", "reason": "Keys feel too heavy"}


def error_code(call, args):
    with pytest.raises(ToolError) as exc:
        call(args)
    return exc.value.code


class TestGetOrder:
    def test_returns_the_order_without_the_email(self, orders):
        orders.put_item(Item=make_order())

        result = tools.get_order({"order_id": "ORD-1001", "customer_email": "alex@example.com"})

        assert result["status"] == "DELIVERED"
        assert result["total"] == 174
        assert result["items"][1]["unit_price"] == 12.5
        assert "customer_email" not in result

    def test_normalises_case_and_whitespace(self, orders):
        orders.put_item(Item=make_order())

        result = tools.get_order({"order_id": " ord-1001 ", "customer_email": "Alex@Example.com"})

        assert result["order_id"] == "ORD-1001"

    def test_wrong_email_looks_the_same_as_a_missing_order(self, orders):
        orders.put_item(Item=make_order())

        wrong_email = error_code(tools.get_order, {"order_id": "ORD-1001", "customer_email": "eve@example.com"})
        missing = error_code(tools.get_order, {"order_id": "ORD-9999", "customer_email": "alex@example.com"})

        assert wrong_email == missing == "ORDER_NOT_FOUND"

    @pytest.mark.parametrize(
        "args",
        [
            {"customer_email": "alex@example.com"},
            {"order_id": "1001", "customer_email": "alex@example.com"},
            {"order_id": "ORD-1001", "customer_email": "not-an-email"},
            {"order_id": "ORD-1001", "customer_email": 42},
            {"order_id": "ORD-1001'; DROP", "customer_email": "alex@example.com"},
        ],
    )
    def test_rejects_malformed_input_before_touching_the_table(self, args):
        # No tables fixture: reaching DynamoDB would fail the test.
        assert error_code(tools.get_order, args) == "INVALID_INPUT"


class TestCheckInventory:
    def test_in_stock(self, inventory):
        inventory.put_item(Item={"sku": "KB-ALU-75", "name": "Keyboard", "available": 14})

        result = tools.check_inventory({"sku": "kb-alu-75"})

        assert result == {
            "sku": "KB-ALU-75",
            "name": "Keyboard",
            "available": 14,
            "in_stock": True,
            "restock_date": None,
        }

    def test_out_of_stock_reports_restock_date(self, inventory):
        inventory.put_item(Item={"sku": "MS-WL-02", "name": "Mouse", "available": 0, "restock_date": "2026-10-17"})

        result = tools.check_inventory({"sku": "MS-WL-02"})

        assert result["in_stock"] is False
        assert result["restock_date"] == "2026-10-17"

    def test_unknown_sku(self, inventory):
        assert error_code(tools.check_inventory, {"sku": "NOPE-1"}) == "SKU_NOT_FOUND"


class TestRequestReturn:
    def test_creates_a_return_and_updates_the_order(self, orders):
        orders.put_item(Item=make_order())

        result = tools.request_return(RETURN_ARGS)

        assert result["return_id"].startswith("RET-")
        assert result["refund_amount"] == 174
        assert result["already_requested"] is False
        stored = orders.get_item(Key={"order_id": "ORD-1001"})["Item"]
        assert stored["status"] == "RETURN_REQUESTED"
        assert stored["return_request"]["return_id"] == result["return_id"]
        assert stored["return_request"]["reason"] == "Keys feel too heavy"

    def test_is_idempotent(self, orders):
        orders.put_item(Item=make_order())

        first = tools.request_return(RETURN_ARGS)
        second = tools.request_return(RETURN_ARGS)

        assert second["already_requested"] is True
        assert second["return_id"] == first["return_id"]

    @pytest.mark.parametrize("status", ["PLACED", "SHIPPED", "CANCELLED"])
    def test_only_delivered_orders(self, orders, status):
        orders.put_item(Item=make_order(status=status))

        assert error_code(tools.request_return, RETURN_ARGS) == "NOT_RETURNABLE"

    def test_window_closed(self, orders):
        orders.put_item(Item=make_order(delivered_at="2026-08-20T12:00:00+00:00"))

        with pytest.raises(ToolError) as exc:
            tools.request_return(RETURN_ARGS)

        assert exc.value.code == "RETURN_WINDOW_CLOSED"
        assert "2026-09-19" in exc.value.message

    def test_window_is_configurable(self, orders, monkeypatch):
        monkeypatch.setenv("RETURN_WINDOW_DAYS", "60")
        orders.put_item(Item=make_order(delivered_at="2026-08-20T12:00:00+00:00"))

        assert tools.request_return(RETURN_ARGS)["already_requested"] is False

    def test_lost_race_is_reported_as_a_conflict(self, orders, monkeypatch):
        orders.put_item(Item=make_order())
        load_order = tools._load_order

        def load_then_lose_race(args):
            # Another request opens the return between our read and our write.
            order = load_order(args)
            orders.update_item(
                Key={"order_id": "ORD-1001"},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":s": "RETURN_REQUESTED"},
            )
            return order

        monkeypatch.setattr(tools, "_load_order", load_then_lose_race)

        assert error_code(tools.request_return, RETURN_ARGS) == "CONFLICT"

    def test_requires_a_reason(self, orders):
        orders.put_item(Item=make_order())
        args = {key: value for key, value in RETURN_ARGS.items() if key != "reason"}

        assert error_code(tools.request_return, args) == "INVALID_INPUT"


class TestSearchPolicies:
    def test_returns_passages_with_sources(self, monkeypatch):
        client = boto3.client("bedrock-agent-runtime", region_name="eu-central-1")
        stubber = Stubber(client)
        stubber.add_response(
            "retrieve",
            {
                "retrievalResults": [
                    {
                        "content": {"text": "Refunds are issued within 5 business days."},
                        "location": {"type": "S3", "s3Location": {"uri": "s3://docs/policies/returns.md"}},
                        "score": 0.81234,
                    }
                ]
            },
            expected_params={
                "knowledgeBaseId": "KB12345678",
                "retrievalQuery": {"text": "how long do refunds take"},
                "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 4}},
            },
        )
        monkeypatch.setattr(aws, "bedrock_agent_runtime", lambda: client)

        with stubber:
            result = tools.search_policies({"query": "how long do refunds take"})

        assert result == {
            "results": [
                {
                    "text": "Refunds are issued within 5 business days.",
                    "source": "s3://docs/policies/returns.md",
                    "score": 0.812,
                }
            ]
        }
        stubber.assert_no_pending_responses()

    def test_rejects_oversized_queries(self):
        assert error_code(tools.search_policies, {"query": "x" * 501}) == "INVALID_INPUT"
