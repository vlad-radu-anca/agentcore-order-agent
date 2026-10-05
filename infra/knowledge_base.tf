# Policy documents (returns, shipping, warranty), embedded into an S3 Vectors
# index. S3 Vectors bills for storage and queries only, so an idle knowledge
# base costs close to nothing, unlike an OpenSearch Serverless collection.

resource "aws_s3_bucket" "policies" {
  bucket_prefix = "${var.name}-policies-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "policies" {
  bucket                  = aws_s3_bucket.policies.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "policies" {
  bucket = aws_s3_bucket.policies.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "policies" {
  bucket = aws_s3_bucket.policies.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "policies" {
  bucket = aws_s3_bucket.policies.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
  }
}

resource "aws_s3_object" "policies" {
  for_each = fileset("${path.module}/../knowledge", "policies/*.md")

  bucket       = aws_s3_bucket.policies.id
  key          = each.value
  source       = "${path.module}/../knowledge/${each.value}"
  source_hash  = filemd5("${path.module}/../knowledge/${each.value}")
  content_type = "text/markdown"

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.policies]
}

resource "aws_s3vectors_vector_bucket" "policies" {
  vector_bucket_name = "${var.name}-vectors"
  force_destroy      = true
}

resource "aws_s3vectors_index" "policies" {
  vector_bucket_name = aws_s3vectors_vector_bucket.policies.vector_bucket_name
  index_name         = "policies"
  data_type          = "float32"
  dimension          = var.embedding_dimensions
  distance_metric    = "cosine"

  # Bedrock stores each chunk's text and its own metadata on the vector. They
  # come back with search results but are never filtered on, and filterable
  # metadata is capped at 2 KB per vector, so mark them non-filterable.
  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }
}

resource "aws_bedrockagent_knowledge_base" "policies" {
  name        = "${var.name}-policies"
  description = "Store policies: returns, refunds, shipping and warranty"
  role_arn    = aws_iam_role.knowledge_base.arn

  knowledge_base_configuration {
    type = "VECTOR"

    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"

      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "S3_VECTORS"

    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.policies.index_arn
    }
  }

  # Bedrock checks the role's permissions when the knowledge base is created.
  depends_on = [aws_iam_role_policy.knowledge_base]
}

resource "aws_bedrockagent_data_source" "policies" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.policies.id
  name              = "policy-documents"

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn         = aws_s3_bucket.policies.arn
      inclusion_prefixes = ["policies/"]
    }
  }
}

resource "aws_iam_role" "knowledge_base" {
  name               = "${var.name}-knowledge-base"
  assume_role_policy = data.aws_iam_policy_document.knowledge_base_trust.json
}

data "aws_iam_policy_document" "knowledge_base_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    # Only knowledge bases in this account can use the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "knowledge-base"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.knowledge_base.json
}

data "aws_iam_policy_document" "knowledge_base" {
  statement {
    sid       = "Embed"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"]
  }

  statement {
    sid       = "ListDocuments"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.policies.arn]
  }

  statement {
    sid       = "ReadDocuments"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.policies.arn}/*"]
  }

  statement {
    sid       = "DecryptDocuments"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }

  statement {
    sid = "VectorIndex"
    actions = [
      "s3vectors:GetIndex",
      "s3vectors:QueryVectors",
      "s3vectors:PutVectors",
      "s3vectors:GetVectors",
      "s3vectors:DeleteVectors",
    ]
    resources = [aws_s3vectors_index.policies.index_arn]
  }
}
