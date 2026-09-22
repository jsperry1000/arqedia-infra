# ---------------------------------------------------------------------------
# The staff console's database credential (16.9).
#
# WHAT THIS IS FOR. The admin Lambda reads every tenant's rows and must never
# write one. Today that is true because cross_tenant.py refuses any statement
# that is not a SELECT - a guard on the code, which survives exactly as long
# as nobody routes around it. OBS-02 says why that is not enough in the words
# it was written in: "rds-data:ExecuteStatement outside a transaction
# autocommits", so the IAM policy permits a write that the code declines to
# make.
#
# The control is a database user granted SELECT and nothing else. Then a write
# from this function fails at the database, whoever wrote it and whatever the
# IAM policy says.
#
# THE VALUE IS SET OUTSIDE TERRAFORM, like the two Paddle secrets and for a
# sharper reason. Generating the password here - random_password and a
# secretsmanager_secret_version - would write it into the state file in
# plaintext, and that state is an S3 object; server-side encryption stops
# somebody reading the disk, not somebody with s3:GetObject. Every plan file
# and every `terraform show` would carry it too. So Terraform declares the
# container and never learns what is in it.
#
# WHAT GOES IN IT, which is the shape the Data API reads:
#
#     {"username": "arqedia_admin_reader", "password": "..."}
#
# The cluster's own master secret holds exactly those two keys and is what the
# Data API authenticates with today, so that is the shape by evidence rather
# than by documentation.
#
# THE PASSWORD IS NEVER TYPED. It comes from `aws secretsmanager
# get-random-password`, goes straight into this secret and into one CREATE
# USER statement, and is not written to a file or echoed. The statement text
# does not reach a log either: AWS's own words on Data API and CloudTrail are
# "Event data doesn't reveal the database name, schema name, or SQL statements
# in requests to the Data API", the cluster exports no logs, and general_log
# is 0.
#
# NOT ROTATED, DELIBERATELY, and that is 16.10. The master secret rotates every
# seven days through an RDS-managed function; this one has no rotation at all.
# A rotation function needs VPC placement and a strategy, which is a piece of
# work rather than a line here - and a half-built rotation is worse than a
# recorded absence.
#
# The user itself, its GRANT, and the switch of the Lambda's SECRET_ARN are
# separate steps. This file on its own changes nothing: an empty secret that
# nothing reads.
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "admin_reader" {
  name        = "${local.name_prefix}/db/admin-reader"
  description = "SELECT-only database user for the staff console (16.9). Value set outside Terraform. Not rotated - 16.10."
  tags        = { Name = "${local.name_prefix}-db-admin-reader" }
}

# Where to put the value, and what the next step points SECRET_ARN at.
output "admin_reader_secret_arn" {
  value = aws_secretsmanager_secret.admin_reader.arn
}
