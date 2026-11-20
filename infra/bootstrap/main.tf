# The S3 bucket that holds the main stack's Terraform state. Applied once, with
# local state (infra/bootstrap/terraform.tfstate, git-ignored): it only describes
# this bucket, and the bucket's versioning protects everything else.
#
# Credentials come from deploy/tf.sh, which turns your `aws login` session
# (profile baseball-gpt) into short-lived keys for Terraform:
#
#   echo 'aws_account_id = "<baseball-gpt account ID>"' > infra/bootstrap/terraform.tfvars
#   deploy/tf.sh -chdir=infra/bootstrap init
#   deploy/tf.sh -chdir=infra/bootstrap apply
#   deploy/tf.sh -chdir=infra/bootstrap output -raw backend_config > infra/backend.hcl

terraform {
  required_version = ">= 1.10" # S3 native locking (use_lockfile)
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "aws_account_id" {
  description = "The baseball-gpt AWS account ID; Terraform refuses to run against any other account (set in terraform.tfvars)"
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-2"
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { Project = "baseball-gpt", ManagedBy = "terraform", Stack = "bootstrap" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  # Bucket names are global; the account ID keeps this one unique.
  bucket = "baseball-gpt-tfstate-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "state" {
  bucket = local.bucket
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Refuse plain-HTTP access.
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# Old state versions are kept 90 days, enough to roll back a bad apply.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
  depends_on = [aws_s3_bucket_versioning.state]
}

output "bucket" {
  value = aws_s3_bucket.state.id
}

# Backend settings for the main stack (infra/backend.hcl, git-ignored so the
# account ID stays out of this public repo).
output "backend_config" {
  value = <<-EOT
    bucket       = "${aws_s3_bucket.state.id}"
    key          = "infra/terraform.tfstate"
    region       = "${var.region}"
    encrypt      = true
    use_lockfile = true
  EOT
}
