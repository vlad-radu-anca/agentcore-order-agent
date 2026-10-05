# agentcore-order-agent

A customer support agent for an online store, built on Amazon Bedrock AgentCore. It looks up orders, checks stock, opens returns and answers policy questions from a knowledge base. The agent runs on the AgentCore managed harness with Claude Opus 5.5. Its tools are a Python Lambda function served as MCP tools through an AgentCore Gateway. Everything is defined in Terraform.

[![CI](https://github.com/vlad-radu-anca/agentcore-order-agent/actions/workflows/ci.yaml/badge.svg)](https://github.com/vlad-radu-anca/agentcore-order-agent/actions/workflows/ci.yaml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

## Why AgentCore and not Bedrock Agents

Bedrock Agents, now called Agents Classic, went into maintenance mode on 30 July 2026. Accounts that have not used it in the past year can no longer create agents, and its model catalogue is frozen. AWS points new work to AgentCore, whose managed harness is the configuration-driven equivalent. [ADR 0001](docs/decisions/0001-agentcore-harness-over-agents-classic.md) covers the tradeoffs, including why the harness fits better here than a code-defined agent.

## Architecture

```
customer (scripts/chat.py)
   │  InvokeHarness, SigV4
   ▼
AgentCore harness ──────────────▶ Claude Opus 5.5, eu. inference profile
   │  system prompt, memory          Bedrock Guardrail on every request
   │  allowed tools: gateway only
   │  MCP, SigV4
   ▼
AgentCore Gateway
   │  gateway IAM role
   ▼
Lambda: order_tools ──┬──▶ DynamoDB: orders, inventory
                      └──▶ Bedrock Knowledge Base ──▶ S3 Vectors index
                                                       (policy documents from S3)
```

## Tools

| Tool | What it does |
| --- | --- |
| `get_order` | Looks up an order by order number **and** the email it was placed with |
| `check_inventory` | Stock level and restock date for a SKU |
| `request_return` | Opens a return for a delivered order inside the return window. Creates a request; never moves money |
| `search_policies` | Retrieves passages from the returns, shipping and warranty policies |

The schemas the model sees live in [`schemas/tools.json`](schemas/tools.json). Terraform publishes them to the gateway, and [a test](tests/test_schema.py) fails if they drift from the Python implementations or if a required argument isn't enforced.

## Demo

Deployed to `us-west-2` on 5 October 2026 and driven from `make chat` against the sample data, on Claude Opus 4.6 (the account did not yet have Opus 5.5 enabled; the model is a variable). An excerpt, with the agent's words unedited:

```text
you> Hi, where is my order ORD-1001? My email is alex@example.com
agent> Let me look that up for you right away.
  [tool] order-tools___get_order
Your order ORD-1001 has been **delivered** — it arrived on 30 September 2026.
...
you> How long will my refund take?
agent> Let me check the store's refund policy for you.
  [tool] order-tools___search_policies
Refunds are issued to your original payment method within **5 business days** of the returned parcel arriving at our warehouse. ...

you> Can you give me 20% off for the trouble?
agent> Sorry, I can't help with that. I can help with orders, stock, returns and store policies.
  [guardrail intervened]
```

The [full transcript](docs/demo/transcript-2026-10-05.md) shows all four tools running (order lookup, policy search, stock check, and opening a return after the customer confirms), the guardrail refusing a discount without ending the conversation, and conversation memory carrying two open requests across seven turns.

## Design decisions

**Tool arguments are untrusted input.** The model fills them in, and the model is reading text the customer wrote. Every argument is type checked, length capped and matched against a pattern before it reaches DynamoDB or the knowledge base.

**An order lookup needs the order number and the email.** A wrong email and a missing order produce the same error, so the agent cannot be used to find out which order numbers exist.

**Business rules live in the tool, not the prompt.** The prompt tells the agent about the 30 day return window, but `request_return` is what enforces it. If a customer talks the model into trying anyway, the tool still refuses.

**Opening a return is idempotent and safe under concurrency.** A conditional write lets exactly one request create the return. A repeated call returns the existing return ID instead of failing, because conversational callers retry.

**Expected failures are results, not exceptions.** "Return window closed" is an answer the agent should give the customer, so tools return it as an error code and message the model can read. Only genuine faults raise, and those show up as Lambda errors.

**The agent can only use its own tools.** A harness gets a shell and file access by default. `allowed_tools` limits it to the gateway's tools, which removes capabilities a support agent should never have and saves about 900 input tokens per model call.

**The guardrail enforces what the prompt asks for.** The Bedrock Guardrail blocks harmful content, prompt attacks and card details, and denies discount and compensation requests, because the agent has no authority to grant them.

**Least privilege, one role per component.** The Lambda can read two tables, update one, and query one knowledge base. The gateway can invoke one function. The harness can call one model, one guardrail, one gateway and one memory. Data at rest is encrypted with a customer managed KMS key.

**Logs record outcomes, not arguments.** The Lambda logs the tool name, result code and request ID, but never the arguments, because those contain customer email addresses.

## Layout

```
src/order_tools/    Lambda package: handler, tools, validation
schemas/tools.json  Tool definitions, shared by Terraform and the tests
prompts/system.md   The agent's system prompt
knowledge/          Policy documents indexed into the knowledge base
data/               Sample orders and inventory
scripts/            seed.py (load sample data), chat.py (talk to the agent)
tests/              pytest, with moto for DynamoDB and botocore Stubber for Bedrock
infra/              Terraform: harness, gateway, Lambda, tables, knowledge base, guardrail
docs/decisions/     Architecture decision records
docs/demo/          Transcript of a run against a real deployment
```

## Development

Linux is the reference platform; CI runs on Ubuntu with Python 3.13.

```sh
make venv       # .venv with the pinned test and lint tools
make check      # ruff, pytest with coverage, terraform fmt and validate
```

The Makefile uses the tools in `.venv` when it exists, so there is nothing to activate. The tests need no AWS account: DynamoDB is mocked with moto, the knowledge base call is stubbed, and fake credentials are set so nothing can reach a real account.

CI runs the same checks, plus `tflint` with the AWS ruleset and a `trivy` misconfiguration scan that fails the build on high or critical findings.

## Deploying

Requirements:

- Terraform >= 1.10 and AWS provider ~> 6.67
- A region with the AgentCore harness, gateway and memory. The default is `eu-central-1`
- Access to Claude Opus 5.5 and Titan Text Embeddings V2 in Amazon Bedrock

Before the first deploy, call the model once yourself with an administrator identity:

```sh
aws bedrock-runtime converse --model-id <model_id> \
  --messages '[{"role":"user","content":[{"text":"hello"}]}]'
```

The first call to an Anthropic model creates the account's AWS Marketplace subscription, and is made with the caller's permissions. If that first call comes from the harness, it fails, because the harness role deliberately has no `aws-marketplace:Subscribe`. The subscription belongs to the account, so after one call from an administrator the harness only needs the model permissions it already has. That call also needs the Anthropic use case form to have been submitted in the Bedrock console, and a payment method on the account. Newly created accounts may also have the newest models restricted; `aws bedrock list-inference-profiles` shows what the account can see, and a single `converse` call shows what it can use.

```sh
cp infra/backend.hcl.example infra/backend.hcl   # point at your state bucket
terraform -chdir=infra init -backend-config=backend.hcl
terraform -chdir=infra apply

make seed     # sample orders and inventory
make ingest   # index the policy documents
make chat
```

The sample data has an order inside the return window (ORD-1001), one outside it (ORD-1002), one in transit (ORD-1003) and one not yet shipped (ORD-1004). Orders 1001 and 1002 belong to `alex@example.com`; 1003 and 1004 belong to `sam@example.com`. Dates are relative to when you seed, so the scenarios stay valid.

The model is a variable. `eu.anthropic.claude-opus-5-5` keeps inference inside EU regions; use `global.anthropic.claude-opus-5-5` for global routing.

## Cost

Nothing here bills while idle except storage and the KMS key (about 1 USD a month). DynamoDB is on demand, the Lambda and the gateway are per request, and S3 Vectors charges for storage and queries rather than for a running cluster, unlike an OpenSearch Serverless collection. The harness has no charge of its own. The main cost is model tokens.

## Status

The Terraform validates and passes tflint and trivy in CI, and the tools are covered by unit tests. The stack was applied to a real account on 5 October 2026, exercised with the [demo](#demo) above, and destroyed afterwards.

## License

[Apache-2.0](LICENSE)
