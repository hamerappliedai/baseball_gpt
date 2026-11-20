variable "aws_account_id" {
  description = "The baseball-gpt AWS account ID; Terraform refuses to run against any other account (set in terraform.tfvars)"
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-2"
}

variable "project" {
  description = "Name prefix for resources"
  type        = string
  default     = "baseball-gpt"
}

# --- network ---

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "single_nat_gateway" {
  description = "One shared NAT gateway instead of one per zone (saves about $35 a month, loses zone redundancy for outbound calls)"
  type        = bool
  default     = false
}

# --- database ---

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_allocated_storage" {
  description = "GB of gp3 storage; grows automatically up to db_max_allocated_storage"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  type    = number
  default = 100
}

variable "db_deletion_protection" {
  description = "Set false (and apply) before you can destroy the database"
  type        = bool
  default     = true
}

# --- one-off ops task ---

variable "ops_image_tag" {
  type    = string
  default = "latest"
}

variable "ops_cpu" {
  description = "Fargate CPU units for the ops task (1024 = 1 vCPU)"
  type        = number
  default     = 2048
}

variable "ops_memory" {
  description = "MiB of memory for the ops task"
  type        = number
  default     = 4096
}

variable "lahman_release" {
  description = "Lahman release the ops task loads"
  type        = string
  default     = "2025"
}

variable "log_retention_days" {
  type    = number
  default = 30
}
