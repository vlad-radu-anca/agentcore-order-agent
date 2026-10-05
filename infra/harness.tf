# The agent. AgentCore runs the orchestration loop; this file only declares
# the model, instructions, tools and memory it runs with.

locals {
  harness_name = local.snake_name

  # The name the harness gives the gateway's MCP server. allowed_tools
  # refers to it, so it is set once here.
  gateway_tool = "orders"
}

resource "aws_bedrockagentcore_memory" "this" {
  name                  = "${local.snake_name}_memory"
  description           = "Conversation history for the order support agent"
  event_expiry_duration = var.memory_expiry_days
}

resource "aws_bedrockagentcore_harness" "this" {
  harness_name       = local.harness_name
  execution_role_arn = aws_iam_role.harness.arn

  # A support agent needs its tools and nothing else. Every harness gets a
  # shell and file access by default; allowing only the gateway's tools
  # removes both, and also saves about 900 input tokens per model request.
  allowed_tools = ["@${local.gateway_tool}"]

  # Bounds on a single invocation, so a confused agent can't loop at length.
  max_iterations  = 10
  timeout_seconds = 120

  model {
    # Guardrails need the default Converse Stream API format, so api_format
    # is left unset.
    bedrock_model_config {
      model_id   = var.model_id
      max_tokens = 8192

      additional_params = jsonencode({
        guardrailConfig = {
          guardrailIdentifier = aws_bedrock_guardrail.this.guardrail_arn
          guardrailVersion    = aws_bedrock_guardrail_version.this.version
          trace               = "enabled"
        }
      })
    }
  }

  system_prompt {
    text = file("${path.module}/../prompts/system.md")
  }

  tool {
    type = "agentcore_gateway"
    name = local.gateway_tool

    config {
      agentcore_gateway {
        gateway_arn = aws_bedrockagentcore_gateway.this.gateway_arn

        outbound_auth {
          aws_iam = true
        }
      }
    }
  }

  memory {
    agentcore_memory_configuration {
      arn = aws_bedrockagentcore_memory.this.arn
    }
  }

  depends_on = [aws_iam_role_policy.harness]
}

resource "aws_iam_role" "harness" {
  name               = "${var.name}-harness"
  assume_role_policy = data.aws_iam_policy_document.harness_trust.json
}

data "aws_iam_policy_document" "harness_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role_policy" "harness" {
  name   = "harness"
  role   = aws_iam_role.harness.id
  policy = data.aws_iam_policy_document.harness.json
}

# Based on the sample execution role in the AgentCore harness documentation,
# narrowed to this agent: one model, one guardrail, one gateway, one memory,
# and no browser or code interpreter.
data "aws_iam_policy_document" "harness" {
  statement {
    sid     = "InvokeModel"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/${var.model_id}",
      # Geographic profiles route to the model in several regions, and the
      # global profile to a region-less ARN. IAM checks the model as well.
      "arn:${local.partition}:bedrock:*::foundation-model/${local.foundation_model_id}",
      "arn:${local.partition}:bedrock:::foundation-model/${local.foundation_model_id}",
    ]
  }

  statement {
    sid       = "ApplyGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [aws_bedrock_guardrail.this.guardrail_arn]
  }

  statement {
    sid       = "CallTools"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [aws_bedrockagentcore_gateway.this.gateway_arn]
  }

  statement {
    sid = "ConversationMemory"
    actions = [
      "bedrock-agentcore:CreateEvent",
      "bedrock-agentcore:DeleteEvent",
      "bedrock-agentcore:GetEvent",
      "bedrock-agentcore:ListEvents",
      "bedrock-agentcore:RetrieveMemoryRecords",
    ]
    resources = [aws_bedrockagentcore_memory.this.arn]
  }

  statement {
    sid     = "WorkloadIdentity"
    actions = ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT"]
    resources = [
      "arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default",
      "arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default/workload-identity/harness_${local.harness_name}-*",
    ]
  }

  statement {
    sid       = "RuntimeLogGroups"
    actions   = ["logs:CreateLogGroup", "logs:DescribeLogStreams"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"]
  }

  statement {
    sid       = "RuntimeLogStreams"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]
  }

  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:*"]
  }

  statement {
    sid       = "Metrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }

  # These actions have no resource-level permissions, so "*" is the only
  # resource they accept. The managed harness image is pulled from ECR
  # Public, which needs the bearer token.
  statement {
    sid = "TracingAndImagePull"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
      "ecr-public:GetAuthorizationToken",
      "sts:GetServiceBearerToken",
      "logs:PutResourcePolicy",
    ]
    resources = ["*"]
  }
}
