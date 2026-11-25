# baseball_gpt on AWS (see docs/deploy-plan.md). State lives in the S3 bucket
# from infra/bootstrap; its settings come from backend.hcl (git-ignored).
# Run Terraform through deploy/tf.sh, which supplies credentials from your
# `aws login` session (profile baseball-gpt):
#
#   deploy/tf.sh -chdir=infra init -backend-config=backend.hcl
#   deploy/tf.sh -chdir=infra plan -out=infra.tfplan

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { Project = var.project, ManagedBy = "terraform" }
  }
}

# CloudFront's certificate and web ACL must live in us-east-1.
provider "aws" {
  alias               = "us_east_1"
  region              = "us-east-1"
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { Project = var.project, ManagedBy = "terraform" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = var.project
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}
