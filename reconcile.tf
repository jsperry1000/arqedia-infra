# ---------------------------------------------------------------------------
# Stage 2: catch what never reaches the code.
#
# Stage 1 made every exit of the normalizer write a row, so a refused document
# says so instead of leaving a person waiting ten minutes. That holds only
# while the code RUNS. Two things here cover the cases where it does not.
#
#   the dead-letter queue   the invocation failed - a timeout, an out-of-
#                           memory kill, or a crash before the try block that
#                           Stage 1 cannot reach
#   the reconciliation      the invocation never happened at all, so there is
#                           no failure anywhere to catch
#
# The second is the only one that finds a rule somebody disabled.
# ---------------------------------------------------------------------------

# --- the dead-letter queue -------------------------------------------------
#
# AN ON-FAILURE DESTINATION, NOT DeadLetterConfig. They are different features
# and the difference matters here: a destination delivers an INVOCATION RECORD
# carrying the request AND the response, so the message says what went wrong.
# DeadLetterConfig delivers the event as-is and leaves the reason in message
# attributes. When a document goes missing, the question is why, and only one
# of these answers it.
#
# WHAT ACTUALLY LANDS HERE IS NARROW, and that is by design. Stage 1 catches
# every exception below the fetch and writes a refusal row rather than
# re-raising - deliberately, so EventBridge does not retry and write three
# rows for one file. So the function almost never errors. What is left for
# this queue is what Stage 1 cannot reach:
#
#   a timeout at 300 seconds, where the function is killed mid-flight
#   an out-of-memory kill
#   a crash BEFORE the try block - an unrecognised event shape, a key that
#     does not match the layout, a get_object refused by KMS
#   the one re-raise Stage 1 keeps, where the refusal row itself could not be
#     written
#
# Fourteen days, because a document nobody noticed missing on a Friday should
# still be there to look at.
resource "aws_sqs_queue" "normalizer_failed" {
  name                      = "${local.name_prefix}-normalizer-failed"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = { Name = "${local.name_prefix}-normalizer-failed" }
}

# The EXECUTION ROLE needs this, not a resource policy on the queue. Lambda
# writes the invocation record as the function's own identity; the queue
# policy pattern is what EventBridge needs for its own target DLQ, which is a
# different mechanism (see the note at the foot of this file).
resource "aws_iam_role_policy" "normalizer_dlq" {
  name = "${local.name_prefix}-normalizer-dlq"
  role = aws_iam_role.normalizer.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.normalizer_failed.arn
    }]
  })
}

# maximum_retry_attempts is left at 2, the default, deliberately. A KMS blip
# or an S3 five-hundred deserves another go; what does not deserve one is an
# exception in our own code, and Stage 1 already stops those becoming retries
# by not re-raising them.
resource "aws_lambda_function_event_invoke_config" "normalizer" {
  function_name          = aws_lambda_function.normalizer.function_name
  maximum_retry_attempts = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.normalizer_failed.arn
    }
  }
}

# --- the reconciliation ----------------------------------------------------

data "archive_file" "reconcile" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/reconcile"
  output_path = "${path.module}/build/reconcile.zip"
  excludes    = ["__pycache__"]
}

resource "aws_iam_role" "reconcile" {
  name = "${local.name_prefix}-reconcile"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-reconcile" }
}

resource "aws_iam_role_policy_attachment" "reconcile_logs" {
  role       = aws_iam_role.reconcile.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# LIST AND READ NOTHING. It needs the names of objects and no access to their
# contents: it is checking that a row exists, not looking inside a customer's
# document. No s3:GetObject, and no KMS. That part IS enforced by IAM.
#
# THE DATABASE PART IS NOT. rds-data:ExecuteStatement outside a transaction
# AUTOCOMMITS, so this role can INSERT, UPDATE and DELETE with the one action
# it holds. Withholding BeginTransaction stops it grouping writes; it does not
# stop it making them. What keeps this function read-only is its own code,
# which issues SELECTs and nothing else - a convention, not a control.
#
# A database user with SELECT only would make it a control. Backlog OBS-02.
data "aws_iam_policy_document" "reconcile" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data["docs"].arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["rds-data:ExecuteStatement"]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "reconcile" {
  name   = "${local.name_prefix}-reconcile"
  role   = aws_iam_role.reconcile.id
  policy = data.aws_iam_policy_document.reconcile.json
}

# ORPHAN_AFTER_MINUTES = 30, and the number is arithmetic rather than taste.
#
# An asynchronous invocation that TIMES OUT is retried twice, with a backoff
# of roughly one minute and then two. At the normalizer's 300-second timeout
# that is 300 + 60 + 300 + 120 + 300, about eighteen minutes before the event
# is finally dead and the queue above hears about it. Anything under that
# would report a file that is still legitimately in flight, and a backstop
# that cries wolf is one nobody reads.
#
# Thirty minutes clears it with room. The person at the screen has already
# been told - the review screen stops asking after ten - so this is for
# whoever is watching the system, not for them.
resource "aws_lambda_function" "reconcile" {
  function_name    = "${local.name_prefix}-reconcile"
  role             = aws_iam_role.reconcile.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.reconcile.output_path
  source_code_hash = data.archive_file.reconcile.output_base64sha256
  timeout          = 120
  memory_size      = 256

  environment {
    variables = {
      DOCS_BUCKET          = aws_s3_bucket.data["docs"].id
      CLUSTER_ARN          = aws_rds_cluster.main.arn
      SECRET_ARN           = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE             = "arqedia"
      ORPHAN_AFTER_MINUTES = "30"
    }
  }

  tags = { Name = "${local.name_prefix}-reconcile" }
}

# Every fifteen minutes, so an orphan is reported within forty-five of the
# upload at worst. It is a safety net rather than a pager: nothing it finds is
# urgent in the minute it finds it, and everything it finds is worth knowing
# before the customer asks.
resource "aws_cloudwatch_event_rule" "reconcile" {
  name                = "${local.name_prefix}-reconcile"
  description         = "Objects in the docs bucket with no document row"
  schedule_expression = "rate(15 minutes)"
  tags                = { Name = "${local.name_prefix}-reconcile" }
}

resource "aws_cloudwatch_event_target" "reconcile" {
  rule      = aws_cloudwatch_event_rule.reconcile.name
  target_id = "reconcile"
  arn       = aws_lambda_function.reconcile.arn
}

resource "aws_lambda_permission" "reconcile" {
  statement_id  = "AllowEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reconcile.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reconcile.arn
}

# --- what this does NOT cover, recorded ------------------------------------
#
# EVENTBRIDGE'S OWN TARGET DEAD-LETTER QUEUE is a third mechanism and is not
# configured. It catches what EventBridge cannot deliver at all - NO_PERMIS-
# SIONS, NO_RESOURCE, THROTTLING, TIMEOUT - which is a different failure from
# the function erroring, and it needs a RESOURCE POLICY on the queue granting
# events.amazonaws.com sqs:SendMessage, which is not created automatically
# outside the console.
#
# Left out because the reconciliation above already finds its symptom: an
# event EventBridge never delivered leaves an object with no row, which is
# exactly what is reported. Worth adding when somebody wants the cause as
# well as the symptom.
#
# NOBODY IS ALARMED ON EITHER. A message on the queue and an orphan in the
# log both sit there until read. The paddle processor has an alarm on exactly
# this shape of queue (paddle.tf) and the same would fit here; it was not
# added because the instruction was to report and not to act, and an alarm is
# a decision about who gets woken.
