# ---------------------------------------------------------------------------
# What composition could not finish, finished (UX02 20.2).
#
# Composition catches its own failures and refunds where nothing was written
# (20.1). What it cannot catch - a timeout, an out-of-memory kill, a crash at
# start-up, anything raised before a path's own try - is not retried
# (maximum_retry_attempts = 0, composition.tf) and lands here as an on-failure
# invocation record. lambda/composition_failed reads each one and does what
# composition would have done: refund a generation or an Update that wrote
# nothing, and write its run failed; write a rewrite's row failed.
#
# A SEPARATE FUNCTION, deliberately (decided 19 October 2026). Composition
# reading its own failure queue would be one fewer resource, and a composition
# that dies at start-up - a stale layer, a bad import - would break the very
# thing meant to clean up after it.
# ---------------------------------------------------------------------------

# --- the queue -------------------------------------------------------------
#
# Fourteen days, as the normalizer's and the Paddle processor's are. A message
# is deleted once handled; one the handler could not handle is named back to
# SQS and comes round again, so it stays here to be looked at rather than
# being dropped.
#
# THE VISIBILITY TIMEOUT IS SIX TIMES THE HANDLER'S, which is what AWS
# recommends for a queue a Lambda reads: a message mid-handling must not
# reappear to a second invocation.
resource "aws_sqs_queue" "composition_failed" {
  name                       = "${local.name_prefix}-composition-failed"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 360
  sqs_managed_sse_enabled    = true
  tags                       = { Name = "${local.name_prefix}-composition-failed" }
}

# ANY FAILURE AT ALL, AND NOBODY IS WOKEN (decided 19 October 2026). Visible
# in the console; who gets paged is a separate decision.
#
# ON MESSAGES SENT, NOT MESSAGES VISIBLE - unlike the Paddle alarm, and for a
# reason. The handler below deletes each message within seconds, so a count
# of what is waiting would almost never be above zero, and the alarm would
# never show that composition died at all. Sent counts every one.
resource "aws_cloudwatch_metric_alarm" "composition_failed" {
  alarm_name          = "${local.name_prefix}-composition-failed"
  alarm_description   = "Composition died - timed out, ran out of memory or crashed before it could record the run. The run was finished by composition-failed; its log line is [composition-died]."
  namespace           = "AWS/SQS"
  metric_name         = "NumberOfMessagesSent"
  dimensions          = { QueueName = aws_sqs_queue.composition_failed.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = { Name = "${local.name_prefix}-composition-failed" }
}

# --- the handler -----------------------------------------------------------

data "archive_file" "composition_failed" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/composition_failed"
  output_path = "${path.module}/build/composition_failed.zip"
  # Running the tests writes bytecode here; it must not change the zip.
  excludes = ["__pycache__"]
}

resource "aws_iam_role" "composition_failed" {
  name = "${local.name_prefix}-composition-failed"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-composition-failed" }
}

resource "aws_iam_role_policy_attachment" "composition_failed_logs" {
  role       = aws_iam_role.composition_failed.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "composition_failed" {
  # Reading the queue, as the event source mapping does on its behalf.
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.composition_failed.arn]
  }

  # A run's progress: read it, and write it failed.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # A refund is two rows in one transaction, so all four are needed
  # (CLAUDE.md, Money).
  statement {
    effect = "Allow"
    actions = [
      "rds-data:ExecuteStatement", "rds-data:BeginTransaction",
      "rds-data:CommitTransaction", "rds-data:RollbackTransaction",
    ]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "composition_failed" {
  name   = "${local.name_prefix}-composition-failed"
  role   = aws_iam_role.composition_failed.id
  policy = data.aws_iam_policy_document.composition_failed.json
}

# The layer for wallet.py: the refund is the same code composition and the
# collector run, not a copy of it.
resource "aws_lambda_function" "composition_failed" {
  function_name    = "${local.name_prefix}-composition-failed"
  role             = aws_iam_role.composition_failed.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.composition_failed.output_path
  source_code_hash = data.archive_file.composition_failed.output_base64sha256
  timeout          = 60
  memory_size      = 256
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      CURATED_BUCKET = aws_s3_bucket.data["curated"].id
      CLUSTER_ARN    = aws_rds_cluster.main.arn
      SECRET_ARN     = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE       = "arqedia"
    }
  }

  tags = { Name = "${local.name_prefix}-composition-failed" }
}

# A batch of ten at most, with each message answered on its own: one that
# cannot be handled goes back to the queue and the rest are deleted.
resource "aws_lambda_event_source_mapping" "composition_failed" {
  event_source_arn        = aws_sqs_queue.composition_failed.arn
  function_name           = aws_lambda_function.composition_failed.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

output "composition_failed_queue" {
  value = aws_sqs_queue.composition_failed.url
}
