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
