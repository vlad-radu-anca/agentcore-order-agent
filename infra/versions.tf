terraform {
  # 1.10 for S3 native state locking (use_lockfile in backend.hcl).
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # 6.67 fixes an "inconsistent result after apply" error on harnesses
      # that leave environment_variables unset, as this one does.
      version = "~> 6.67"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Partial configuration: bucket, key and region come from backend.hcl.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.name
      ManagedBy = "terraform"
    }
  }
}
