"""Lambda entry point for the AgentCore Gateway target.

The gateway invokes the function with the tool arguments as the event. The
tool name arrives in the client context, prefixed with the gateway target
name and three underscores, for example ``order-tools___get_order``.
"""

import json
import logging
from typing import Any

from order_tools.tools import TOOLS
from order_tools.validation import ToolError

DELIMITER = "___"

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def tool_name(context: Any) -> str:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None) or {}
    full_name = custom.get("bedrockAgentCoreToolName", "")
    _, found, name = full_name.partition(DELIMITER)
    return name if found else full_name


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    name = tool_name(context)
    tool = TOOLS.get(name)

    if tool is None:
        result = _error(ToolError("UNKNOWN_TOOL", f"There is no tool named '{name}'."))
    elif not isinstance(event, dict):
        result = _error(ToolError("INVALID_INPUT", "Tool arguments must be a JSON object."))
    else:
        try:
            result = tool(event)
        except ToolError as exc:
            result = _error(exc)

    # Log the outcome, not the arguments: those carry customer email addresses.
    logger.info(
        json.dumps(
            {
                "tool": name,
                "outcome": result.get("error", "ok"),
                "request_id": getattr(context, "aws_request_id", None),
            }
        )
    )
    return result


def _error(exc: ToolError) -> dict[str, Any]:
    return {"error": exc.code, "message": exc.message}
