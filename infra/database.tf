# RDS PostgreSQL 17 (pgvector and pg_trgm are available as extensions; the ops
# task's `bootstrap` creates them). Isolated subnets, encrypted, TLS required.

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.isolated[*].id
}

resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "Postgres: reachable only from the app and ops tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_ops" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.ops.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "ops task"
}

resource "aws_db_parameter_group" "main" {
  name   = "${local.name}-pg17"
  family = "postgres17"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot" # a static parameter; PostgreSQL 17 on RDS defaults to 1 anyway
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # log queries slower than 1 s
  }
}

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "17"
  instance_class = var.db_instance_class

  db_name  = "baseball"
  username = "bgpt_admin"
  # RDS generates the master password, keeps it in Secrets Manager and rotates it.
  manage_master_user_password = true

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  multi_az               = var.db_multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.main.name

  backup_retention_period    = 7
  backup_window              = "10:00-10:30"         # UTC, about 3 am Pacific
  maintenance_window         = "sun:11:00-sun:12:00" # UTC
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-final"

  performance_insights_enabled          = true
  performance_insights_retention_period = 7 # free tier
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]
}
