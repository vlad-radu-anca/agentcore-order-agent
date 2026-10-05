"""Chat with the deployed agent from a terminal.

    python scripts/chat.py --harness-arn ARN

Every line you type is sent to the same runtime session, so the agent keeps
the conversation. Tool calls are printed as they happen. Ctrl-D to quit.
"""

import argparse
import uuid
from collections.abc import Iterable, Iterator
from typing import Any

import boto3


def render(stream: Iterable[dict[str, Any]]) -> Iterator[str]:
    """Turn InvokeHarness stream events into printable text."""
    for event in stream:
        if "contentBlockStart" in event:
            tool_use = event["contentBlockStart"].get("start", {}).get("toolUse")
            if tool_use:
                yield f"\n  [tool] {tool_use['name']}\n"
        elif "contentBlockDelta" in event:
            text = event["contentBlockDelta"].get("delta", {}).get("text")
            if text:
                yield text
        elif "messageStop" in event:
            if event["messageStop"].get("stopReason") == "guardrail_intervened":
                yield "\n  [guardrail intervened]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--harness-arn", required=True)
    args = parser.parse_args()

    client = boto3.client("bedrock-agentcore")
    session_id = str(uuid.uuid4())
    print(f"Session {session_id}. Ctrl-D to quit.\n")

    while True:
        try:
            prompt = input("you> ").strip()
        except EOFError:
            print()
            return
        if not prompt:
            continue

        response = client.invoke_harness(
            harnessArn=args.harness_arn,
            runtimeSessionId=session_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        print("agent> ", end="", flush=True)
        for chunk in render(response["stream"]):
            print(chunk, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
