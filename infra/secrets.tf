# Secrets Manager. The database master password is created and rotated by RDS
# itself (database.tf). The two app-role passwords are generated here, so they
# are also in Terraform state; the state bucket is private and encrypted.
# Letters and digits only: they go into psql variables and connection URLs.

resource "random_password" "db_role" {
  for_each = toset(["reader", "app"])
  length   = 32
  special  = false
}

resource "aws_secretsmanager_secret" "db_role" {
  for_each                = random_password.db_role
  name                    = "${local.name}/db/${each.key}-password"
  description             = "Password for the bgpt_${each.key} database role"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_role" {
  for_each      = random_password.db_role
  secret_id     = aws_secretsmanager_secret.db_role[each.key].id
  secret_string = each.value.result
}

# The Anthropic API key. Terraform creates the empty secret only; you put the
# value in with the AWS CLI, so the key never touches Terraform state or Git
# (see docs/deploy-plan.md, "Anthropic key").
resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name                    = "${local.name}/anthropic-api-key"
  description             = "Anthropic API key for Ask AI (value set by hand)"
  recovery_window_in_days = 7
}
