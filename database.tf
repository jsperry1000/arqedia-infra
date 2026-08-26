# ---------------------------------------------------------------------------
# Aurora MySQL Serverless v2.
#   min_capacity 0       -> pauses when idle, no instance charge while paused
#   enable_http_endpoint -> Data API, so nothing holds a database connection
#   engine_mode provisioned is correct: Serverless v2 is an instance class,
#   not an engine mode. Only the retired v1 used "serverless" here.
# Master credentials are generated and rotated by AWS. No password in code,
# no password in state.
# ---------------------------------------------------------------------------

resource "aws_rds_cluster" "main" {
  cluster_identifier          = "${local.name_prefix}-aurora"
  engine                      = "aurora-mysql"
  engine_version              = "8.0.mysql_aurora.3.12.0"
  engine_mode                 = "provisioned"
  database_name               = "arqedia"
  master_username             = "arqedia_admin"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]

  storage_encrypted    = true
  enable_http_endpoint = true

  serverlessv2_scaling_configuration {
    min_capacity             = 0
    max_capacity             = 4
    seconds_until_auto_pause = 300
  }

  backup_retention_period   = 7
  preferred_backup_window   = "03:00-04:00"
  copy_tags_to_snapshot     = true
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name_prefix}-aurora-final"

  tags = { Name = "${local.name_prefix}-aurora" }
}

resource "aws_rds_cluster_instance" "main" {
  identifier         = "${local.name_prefix}-aurora-1"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version

  tags = { Name = "${local.name_prefix}-aurora-1" }
}

output "cluster_arn" {
  value = aws_rds_cluster.main.arn
}

output "cluster_endpoint" {
  value = aws_rds_cluster.main.endpoint
}

output "master_secret_arn" {
  value       = aws_rds_cluster.main.master_user_secret[0].secret_arn
  description = "Where AWS stores the generated master password."
}
