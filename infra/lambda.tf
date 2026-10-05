# The tool implementations. boto3 ships with the Lambda runtime, so the
# bundle is just the package source.
data "archive_file" "tools" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/order_tools.zip"
  excludes    = ["**/__pycache__/**"]
}

resource "aws_cloudwatch_log_group" "tools" {
  name              = "/aws/lambda/${var.name}-tools"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.this.arn
}

resource "aws_lambda_function" "tools" {
  function_name    = "${var.name}-tools"
  description      = "Order support tools served through the AgentCore Gateway"
  role             = aws_iam_role.tools.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "order_tools.handler.lambda_handler"
  filename         = data.archive_file.tools.output_path
  source_code_hash = data.archive_file.tools.output_base64sha256
  timeout          = 15
  memory_size      = 256

  environment {
    variables = {
      ORDERS_TABLE       = aws_dynamodb_table.orders.name
      INVENTORY_TABLE    = aws_dynamodb_table.inventory.name
      KNOWLEDGE_BASE_ID  = aws_bedrockagent_knowledge_base.policies.id
      RETURN_WINDOW_DAYS = tostring(var.return_window_days)
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.tools.name
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_iam_role_policy.tools]
}

resource "aws_iam_role" "tools" {
  name               = "${var.name}-tools"
  assume_role_policy = data.aws_iam_policy_document.tools_trust.json
}

data "aws_iam_policy_document" "tools_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "tools" {
  name   = "tools"
  role   = aws_iam_role.tools.id
  policy = data.aws_iam_policy_document.tools.json
}

# Exactly what the four tools do, and nothing else: read both tables, update
# orders (to open a return), and query the one knowledge base.
data "aws_iam_policy_document" "tools" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.tools.arn}:*"]
  }

  statement {
    sid       = "ReadOrdersAndStock"
    actions   = ["dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn, aws_dynamodb_table.inventory.arn]
  }

  statement {
    sid       = "OpenReturns"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }

  statement {
    sid       = "TableEncryption"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.this.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["dynamodb.${local.region}.amazonaws.com"]
    }
  }

  statement {
    sid       = "SearchPolicies"
    actions   = ["bedrock:Retrieve"]
    resources = [aws_bedrockagent_knowledge_base.policies.arn]
  }

  # X-Ray has no resource-level permissions for these actions.
  statement {
    sid       = "Tracing"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}
