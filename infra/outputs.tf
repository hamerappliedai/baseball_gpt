# Read by deploy/aws-push.sh and deploy/aws-task.sh.

output "region" {
  value = var.region
}

output "ecr_registry" {
  value = split("/", aws_ecr_repository.repo["app"].repository_url)[0]
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.repo : k => r.repository_url }
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ops_task_definition" {
  value = aws_ecs_task_definition.ops.family
}

output "ops_log_group" {
  value = aws_cloudwatch_log_group.ops.name
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "ops_security_group_id" {
  value = aws_security_group.ops.id
}

output "db_address" {
  value = aws_db_instance.main.address
}

output "anthropic_secret_name" {
  value = aws_secretsmanager_secret.anthropic_api_key.name
}

# --- step 3: records to add in Squarespace (Domains, DNS, Custom records) ---
# Squarespace wants the Host without the domain, e.g. `_abc123.baseballgpt`.

locals {
  zone_suffix = ".${var.dns_zone}."
  validation_records = {
    for o in concat(tolist(aws_acm_certificate.site.domain_validation_options), tolist(aws_acm_certificate.origin.domain_validation_options)) :
    o.domain_name => {
      type  = o.resource_record_type
      name  = trimsuffix(o.resource_record_name, local.zone_suffix)
      value = trimsuffix(o.resource_record_value, ".")
    }
  }
}

output "dns_records_validation" {
  description = "Add first: certificate validation CNAMEs (leave them in place for renewals)"
  value       = local.validation_records
}

output "dns_records_site" {
  description = "Add after the full apply: the site and origin CNAMEs"
  value = {
    site = {
      type  = "CNAME"
      name  = trimsuffix(var.domain_name, ".${var.dns_zone}")
      value = aws_cloudfront_distribution.main.domain_name
    }
    origin = {
      type  = "CNAME"
      name  = trimsuffix(var.origin_domain_name, ".${var.dns_zone}")
      value = aws_lb.main.dns_name
    }
  }
}

output "site_url" {
  value = "https://${var.domain_name}"
}
