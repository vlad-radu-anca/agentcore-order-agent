data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  # Harness and memory names allow underscores but not hyphens.
  snake_name = replace(var.name, "-", "_")

  # The same file the unit tests check against the Python implementations.
  tools = jsondecode(file("${path.module}/../schemas/tools.json"))

  # An inference profile such as eu.anthropic.claude-opus-5-5 routes to the
  # underlying foundation model in several regions, and IAM checks both.
  foundation_model_id = replace(var.model_id, "/^(global|us|eu|apac|au|jp)\\./", "")
}

# One customer managed key for the data this stack owns: the tables, the
# policy documents and the Lambda logs.
resource "aws_kms_key" "this" {
  description             = "${var.name}: order data, policy documents and logs"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.kms.json
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name}"
  target_key_id = aws_kms_key.this.key_id
}

data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:Describe*",
    ]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["logs.${local.region}.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:*"]
    }
  }
}
