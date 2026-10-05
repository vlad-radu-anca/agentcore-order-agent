# The gateway turns the Lambda into MCP tools. Callers authenticate with
# SigV4 (AWS_IAM), so only principals granted bedrock-agentcore:InvokeGateway
# on this gateway, which here means the harness, can list or call the tools.

resource "aws_bedrockagentcore_gateway" "this" {
  name            = "${var.name}-tools"
  description     = "Order support tools"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
}

resource "aws_bedrockagentcore_gateway_target" "order_tools" {
  # Tool names reach the Lambda as "<target name>___<tool>"; the handler
  # strips this prefix.
  name               = "order-tools"
  description        = "Orders, inventory, returns and policy search"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.tools.arn

        tool_schema {
          dynamic "inline_payload" {
            for_each = local.tools

            content {
              name        = inline_payload.value.name
              description = inline_payload.value.description

              input_schema {
                type = "object"

                dynamic "property" {
                  for_each = inline_payload.value.inputSchema.properties

                  content {
                    name        = property.key
                    type        = property.value.type
                    description = property.value.description
                    required    = contains(inline_payload.value.inputSchema.required, property.key)
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.name}-gateway"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json
}

data "aws_iam_policy_document" "gateway_trust" {
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

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:gateway/*"]
    }
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "invoke-tools"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway.json
}

data "aws_iam_policy_document" "gateway" {
  statement {
    sid       = "InvokeTools"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.tools.arn]
  }
}
