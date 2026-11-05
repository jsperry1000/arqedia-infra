# ---------------------------------------------------------------------------
# What extraction could not finish, finished (EXT-02 case 3, decided 5
# November 2026).
#
# Extraction marks and refunds its own failures (#341). What it cannot catch -
# a timeout at 300 seconds, an out-of-memory kill, a crash at start-up - left
# the document "extracting..." for ever with its $0.25 taken, because
# extraction had no failure destination and Lambda dropped the event after
# its two retries.
#
# Now the third failure lands here as an on-failure invocation record, and
# lambda/extraction_failed marks the document failed and refunds it if it
# holds no values - extraction's own rule, and wallet.refund()'s own key, so
# a document is refunded once whichever path came first.
#
# A SEPARATE FUNCTION, as composition-failed is (decided 19 October 2026): an
# extraction that dies at start-up would break the thing meant to clean up
# after it.
#
# Case 4 - extraction never starting at all - is not caught here. The
# reconcile job reports it as [stuck], alert only (reconcile.tf, ops_alerts.tf).
# ---------------------------------------------------------------------------

# --- the queue -------------------------------------------------------------
#
# Fourteen days, as the other failure queues are. The visibility timeout is
# six times the handler's, as AWS recommends for a queue a Lambda reads.
resource "aws_sqs_queue" "extraction_failed" {
  name                       = "${local.name_prefix}-extraction-failed"
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 360
  sqs_managed_sse_enabled    = true
  tags                       = { Name = "${local.name_prefix}-extraction-failed" }
}

# Lambda writes the invocation record as extraction's own identity, so the
# EXECUTION ROLE needs this (reconcile.tf explains the difference).
resource "aws_iam_role_policy" "extraction_dlq" {
  name = "${local.name_prefix}-extraction-dlq"
  role = aws_iam_role.extraction.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.extraction_failed.arn
    }]
  })
}

# Two retries, the default and what extraction has always had: a Bedrock
# throttle or a cluster waking deserves another go. Only the third failure
# comes here.
resource "aws_lambda_function_event_invoke_config" "extraction" {
  function_name          = aws_lambda_function.extraction.function_name
  maximum_retry_attempts = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.extraction_failed.arn
    }
  }
}

# On messages SENT, as composition-failed's is: the handler deletes each
# within seconds, so a count of what waits would almost never be above zero.
# The document is already refunded; the email is so that a death is seen.
resource "aws_cloudwatch_metric_alarm" "extraction_failed" {
  alarm_name          = "${local.name_prefix}-extraction-failed"
  alarm_description   = "Extraction died - timed out, ran out of memory or crashed. extraction-failed marked the document and refunded it if it read nothing; its log line is [extraction-died]."
  namespace           = "AWS/SQS"
  metric_name         = "NumberOfMessagesSent"
  dimensions          = { QueueName = aws_sqs_queue.extraction_failed.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  tags                = { Name = "${local.name_prefix}-extraction-failed" }
}

# --- the handler -----------------------------------------------------------

data "archive_file" "extraction_failed" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/extraction_failed"
  output_path = "${path.module}/build/extraction_failed.zip"
  # Running the tests writes bytecode here; it must not change the zip.
  excludes = ["__pycache__"]
}

resource "aws_iam_role" "extraction_failed" {
  name = "${local.name_prefix}-extraction-failed"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-extraction-failed" }
}

resource "aws_iam_role_policy_attachment" "extraction_failed_logs" {
  role       = aws_iam_role.extraction_failed.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "extraction_failed" {
  # Reading the queue, as the event source mapping does on its behalf.
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.extraction_failed.arn]
  }

  # The envelope, for which document it was. Read only.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data["review"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
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

resource "aws_iam_role_policy" "extraction_failed" {
  name   = "${local.name_prefix}-extraction-failed"
  role   = aws_iam_role.extraction_failed.id
  policy = data.aws_iam_policy_document.extraction_failed.json
}

# The layer for wallet.py: the refund is the same code extraction and the
# collector run, not a copy of it.
resource "aws_lambda_function" "extraction_failed" {
  function_name    = "${local.name_prefix}-extraction-failed"
  role             = aws_iam_role.extraction_failed.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.extraction_failed.output_path
  source_code_hash = data.archive_file.extraction_failed.output_base64sha256
  timeout          = 60
  memory_size      = 256
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      CLUSTER_ARN = aws_rds_cluster.main.arn
      SECRET_ARN  = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE    = "arqedia"
    }
  }

  tags = { Name = "${local.name_prefix}-extraction-failed" }
}

# A batch of ten at most, each message answered on its own.
resource "aws_lambda_event_source_mapping" "extraction_failed" {
  event_source_arn        = aws_sqs_queue.extraction_failed.arn
  function_name           = aws_lambda_function.extraction_failed.arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
}

output "extraction_failed_queue" {
  value = aws_sqs_queue.extraction_failed.url
}
