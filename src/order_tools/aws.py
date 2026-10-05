"""AWS clients, created on first use and reused across warm invocations.

Creating them lazily rather than at import time lets the tests set up
mocked AWS services before any client exists.
"""

import functools

import boto3


@functools.cache
def dynamodb():
    return boto3.resource("dynamodb")


@functools.cache
def bedrock_agent_runtime():
    return boto3.client("bedrock-agent-runtime")
