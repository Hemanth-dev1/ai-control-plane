# =============================================================================
# RDS Postgres Module — Enterprise AI Control Plane
# =============================================================================

resource "aws_security_group" "rds" {
  name_prefix = "${var.db_name}-rds-"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  tags = {
    Name = "${var.db_name}-rds-sg"
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.db_name}-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "${var.db_name}-subnet-group"
  }
}

resource "aws_db_instance" "postgres" {
  identifier        = "${var.db_name}-postgres"
  engine            = "postgres"
  engine_version    = "16.2"
  instance_class    = var.db_instance_class
  allocated_storage = 20
  storage_type      = "gp3"

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.db_name}-final-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  storage_encrypted = true
  deletion_protection = true

  tags = {
    Name        = "${var.db_name}-postgres"
    Environment = "production"
  }
}

output "endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "security_group_id" {
  value = aws_security_group.rds.id
}
