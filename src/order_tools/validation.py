"""Input validation for tool arguments.

The model fills in tool arguments, so every argument is treated as untrusted
input: type checked, length capped and matched against a pattern before it
reaches DynamoDB or the knowledge base.
"""

import re
from collections.abc import Callable, Mapping
from typing import Any

ORDER_ID = re.compile(r"ORD-\d{4,10}")
SKU = re.compile(r"[A-Z0-9-]{3,32}")
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,63}")


class ToolError(Exception):
    """A failure the agent can explain to the customer.

    These are returned to the model as a normal tool result with an error
    code, not raised out of the Lambda, so the agent can recover: ask for a
    corrected order number, explain that the return window has closed, and
    so on. Anything else that goes wrong is a genuine fault and is raised.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def required_str(
    args: Mapping[str, Any],
    name: str,
    *,
    max_len: int,
    pattern: re.Pattern[str] | None = None,
    normalize: Callable[[str], str] = str.strip,
) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ToolError("INVALID_INPUT", f"'{name}' is required.")
    value = normalize(value.strip())
    if len(value) > max_len:
        raise ToolError("INVALID_INPUT", f"'{name}' must be at most {max_len} characters.")
    if pattern is not None and not pattern.fullmatch(value):
        raise ToolError("INVALID_INPUT", f"'{name}' is not in the expected format.")
    return value
