"""Keep schemas/tools.json, which Terraform publishes to the gateway, in step
with the tool implementations."""

import json
from pathlib import Path

import pytest

from order_tools import tools
from order_tools.validation import ToolError

SCHEMAS = json.loads((Path(__file__).resolve().parent.parent / "schemas" / "tools.json").read_text())

VALID_ARGS = {
    "get_order": {"order_id": "ORD-1001", "customer_email": "alex@example.com"},
    "check_inventory": {"sku": "KB-ALU-75"},
    "request_return": {"order_id": "ORD-1001", "customer_email": "alex@example.com", "reason": "Too heavy"},
    "search_policies": {"query": "refund timing"},
}


def test_every_tool_has_a_schema_and_an_implementation():
    assert {schema["name"] for schema in SCHEMAS} == set(tools.TOOLS) == set(VALID_ARGS)


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda schema: schema["name"])
def test_schema_shape(schema):
    input_schema = schema["inputSchema"]
    assert schema["description"].strip()
    assert input_schema["type"] == "object"
    assert set(input_schema["required"]) <= set(input_schema["properties"])
    for prop in input_schema["properties"].values():
        # The Terraform gateway target maps flat, scalar properties only.
        assert prop["type"] in {"string", "integer", "number", "boolean"}
        assert prop["description"].strip()


@pytest.mark.parametrize(
    ("tool", "argument"),
    [(schema["name"], name) for schema in SCHEMAS for name in schema["inputSchema"]["required"]],
)
def test_required_arguments_are_enforced(tool, argument):
    args = {key: value for key, value in VALID_ARGS[tool].items() if key != argument}

    with pytest.raises(ToolError) as exc:
        tools.TOOLS[tool](args)

    assert exc.value.code == "INVALID_INPUT"
