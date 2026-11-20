# The ECS cluster and the one-off "ops" task (deploy/ops.Dockerfile): database
# bootstrap, roles, migrations and the data pipeline, run on demand with
# `make aws-task CMD=...` (deploy/aws-task.sh). Step 3 adds the app service to
# the same cluster.

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled" # step 4 decides on monitoring
  }
}

resource "aws_cloudwatch_log_group" "ops" {
  name              = "/ecs/${local.name}/ops"
  retention_in_days = var.log_retention_days
}

resource "aws_security_group" "ops" {
  name        = "${local.name}-ops"
  description = "One-off ops task: outbound only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_egress_rule" "ops_all" {
  security_group_id = aws_security_group.ops.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "database, ECR, Lahman download"
}

# --- execution role: what ECS itself needs to start the task ---

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "ops_execution" {
  name               = "${local.name}-ops-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "ops_execution" {
  role       = aws_iam_role.ops_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Read exactly the secrets the ops task is given, nothing else.
data "aws_iam_policy_document" "ops_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_db_instance.main.master_user_secret[0].secret_arn,
      aws_secretsmanager_secret.db_role["reader"].arn,
      aws_secretsmanager_secret.db_role["app"].arn,
    ]
  }
}

resource "aws_iam_role_policy" "ops_secrets" {
  name   = "read-ops-secrets"
  role   = aws_iam_role.ops_execution.id
  policy = data.aws_iam_policy_document.ops_secrets.json
}

# --- task definition ---

locals {
  master_secret = aws_db_instance.main.master_user_secret[0].secret_arn
}

resource "aws_ecs_task_definition" "ops" {
  family                   = "${local.name}-ops"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ops_cpu
  memory                   = var.ops_memory
  execution_role_arn       = aws_iam_role.ops_execution.arn
  # No task role: the ops container calls no AWS APIs.

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64" # Graviton; the images are built for arm64
  }

  container_definitions = jsonencode([{
    name      = "ops"
    image     = "${aws_ecr_repository.repo["ops"].repository_url}:${var.ops_image_tag}"
    essential = true
    command   = ["help"] # overridden per run: first-load, migrate, refresh-data, ...
    environment = [
      { name = "PGHOST", value = aws_db_instance.main.address },
      { name = "PGPORT", value = tostring(aws_db_instance.main.port) },
      { name = "PGDATABASE", value = aws_db_instance.main.db_name },
      { name = "PGSSLMODE", value = "require" },
      { name = "RELEASE", value = var.lahman_release },
    ]
    secrets = [
      { name = "PGUSER", valueFrom = "${local.master_secret}:username::" },
      { name = "PGPASSWORD", valueFrom = "${local.master_secret}:password::" },
      { name = "READER_PASSWORD", valueFrom = aws_secretsmanager_secret.db_role["reader"].arn },
      { name = "APP_PASSWORD", valueFrom = aws_secretsmanager_secret.db_role["app"].arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.ops.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "ops"
      }
    }
  }])

  depends_on = [aws_secretsmanager_secret_version.db_role]
}
