# 1. Build on the AgentCore harness rather than Bedrock Agents Classic

Date: 2026-10-05

Status: accepted

## Context

AWS has offered two managed ways to run an agent on Bedrock.

**Bedrock Agents**, launched in November 2023, configures an agent declaratively: a model, instructions, action groups backed by Lambda, and knowledge bases attached directly to the agent. On 30 July 2026 it was renamed **Bedrock Agents Classic** and put into maintenance mode. Accounts with no Bedrock Agents activity in the previous 12 months get `AccessDeniedException` from `CreateAgent`, with no exception process. Existing agents keep working and there is no end-of-life date, but no new features are planned and its model catalogue is frozen as of that date, so newer models will not reach it.

**Amazon Bedrock AgentCore** is the replacement AWS recommends. It offers two ways to run an agent:

- The **managed harness** is the closest equivalent to Agents Classic. It is also configured rather than coded: model, system prompt, tools, memory. AgentCore runs the orchestration loop in an isolated microVM per session.
- **Code-defined agents on AgentCore Runtime**, where you bring your own loop, written in any framework (Strands, LangGraph, the Claude Agent SDK, or your own), and AgentCore hosts it.

## Decision

Build the agent on the AgentCore managed harness, with its tools served by a Lambda function behind an AgentCore Gateway.

## Consequences

What this buys:

- **It deploys in a new account.** A repository built on `aws_bedrockagent_agent` could only be applied by someone who already used Agents Classic in the last year.
- **Current models.** The harness takes any Bedrock model, including ones released after the Agents Classic catalogue was frozen.
- **Tools are standard MCP.** The gateway exposes the Lambda as MCP tools. The same gateway could serve a different agent, or an MCP client such as an IDE, without changing the Lambda.
- **Less configuration to own.** Memory, tracing and session isolation come with the harness; the Terraform declares them rather than building them.

What it costs:

- **No stage-level prompt overrides.** Agents Classic allowed overriding the pre-processing, orchestration and post-processing prompts separately. The harness has one system prompt. This agent doesn't need more.
- **A newer surface.** There are fewer examples to lean on, and the Terraform resource is still settling: provider 6.64 added the model arguments this repository uses, and 6.67 fixed an apply error it would otherwise hit.
- **A different Lambda contract.** Gateway targets receive the tool arguments as the event and the tool name in the client context. Action group Lambdas written for Agents Classic need changing before they can sit behind a gateway.

## Why the harness and not a code-defined agent

A code-defined agent is the right call when the orchestration itself is the product: multi-agent routing, custom planning, or an existing framework codebase to migrate. Here the interesting parts are the tools, the data rules behind them and the guardrails. The loop is the standard one, so owning it would add code to maintain without adding anything a reviewer could not get from the harness. If that changes, the harness can export its configuration as Strands code to run on AgentCore Runtime.
