# The web app: an ECS service of app tasks (deploy/app.Dockerfile) behind an
# Application Load Balancer that only CloudFront can reach:
#   - its security group accepts only CloudFront's origin-facing addresses;
#   - its listener forwards only requests carrying the secret header CloudFront
#     adds (everything else gets a 403).
# That is what makes the CloudFront-Viewer-Address header trustworthy for the
# app's per-IP login limits (CLIENT_IP_HEADER).

# --- connection strings, as secrets (they embed the role passwords) ---

locals {
  db_url = {
    for role in ["reader", "app"] :
    role => "postgresql://bgpt_${role}:${random_password.db_role[role].result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${aws_db_instance.main.db_name}?sslmode=require"
  }
}

resource "aws_secretsmanager_secret" "db_url" {
  for_each                = local.db_url
  name                    = "${local.name}/db/${each.key}-url"
  description             = "Connection URL for the bgpt_${each.key} role"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_url" {
  for_each      = local.db_url
  secret_id     = aws_secretsmanager_secret.db_url[each.key].id
  secret_string = each.value
}

# --- security groups ---

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Load balancer: HTTPS from CloudFront only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "CloudFront origin-facing"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "app tasks"
}

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "App tasks: port 8000 from the load balancer"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "load balancer"
}

resource "aws_vpc_security_group_egress_rule" "app_all" {
  security_group_id = aws_security_group.app.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "database, Claude API, ECR"
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "app tasks"
}

# --- load balancer ---

resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

resource "aws_lb" "main" {
  name                       = local.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb.id]
  idle_timeout               = 120 # Ask AI answers stream for a while
  drop_invalid_header_fields = true
  enable_deletion_protection = true
}

resource "aws_lb_target_group" "app" {
  name                 = "${local.name}-app"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.main.id
  deregistration_delay = 30
  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 15
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.origin.certificate_arn
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}

resource "aws_lb_listener_rule" "from_cloudfront" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [random_password.origin_verify.result]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# --- task roles ---

resource "aws_iam_role" "app_execution" {
  name               = "${local.name}-app-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "app_execution" {
  role       = aws_iam_role.app_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "app_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.db_url["reader"].arn,
      aws_secretsmanager_secret.db_url["app"].arn,
      aws_secretsmanager_secret.anthropic_api_key.arn,
    ]
  }
}

resource "aws_iam_role_policy" "app_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.app_execution.id
  policy = data.aws_iam_policy_document.app_secrets.json
}

# The task role allows only ECS Exec (a shell in a running task, for the
# account commands in backend/manage.py). The app calls no AWS APIs itself.
resource "aws_iam_role" "app_task" {
  name               = "${local.name}-app-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "ecs_exec" {
  statement {
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "app_exec" {
  name   = "ecs-exec"
  role   = aws_iam_role.app_task.id
  policy = data.aws_iam_policy_document.ecs_exec.json
}

# --- service ---

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}/app"
  retention_in_days = var.log_retention_days
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name}-app"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.app_cpu
  memory                   = var.app_memory
  execution_role_arn       = aws_iam_role.app_execution.arn
  task_role_arn            = aws_iam_role.app_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name         = "app"
    image        = "${aws_ecr_repository.repo["app"].repository_url}:${var.app_image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "CLAUDE_MODEL", value = var.claude_model },
      { name = "COOKIE_SECURE", value = "true" },
      { name = "CLIENT_IP_HEADER", value = "CloudFront-Viewer-Address" },
    ]
    secrets = [
      { name = "READER_DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url["reader"].arn },
      { name = "APP_DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url["app"].arn },
      { name = "ANTHROPIC_API_KEY", valueFrom = aws_secretsmanager_secret.anthropic_api_key.arn },
    ]
    linuxParameters = { initProcessEnabled = true } # needed by ECS Exec
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])

  depends_on = [aws_secretsmanager_secret_version.db_url]
}

resource "aws_ecs_service" "app" {
  name                              = "app"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.app.arn
  desired_count                     = var.app_min_tasks
  launch_type                       = "FARGATE"
  enable_execute_command            = true
  health_check_grace_period_seconds = 60
  propagate_tags                    = "SERVICE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [desired_count] # auto-scaling owns it
  }

  depends_on = [aws_lb_listener_rule.from_cloudfront]
}

resource "aws_appautoscaling_target" "app" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.app_min_tasks
  max_capacity       = var.app_max_tasks
}

resource "aws_appautoscaling_policy" "app_cpu" {
  name               = "${local.name}-app-cpu"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  resource_id        = aws_appautoscaling_target.app.resource_id
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension
  policy_type        = "TargetTrackingScaling"
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
