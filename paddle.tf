# ---------------------------------------------------------------------------
# Paddle. Two functions, a queue and an alarm.
#
# THE RECEIVER is the only thing Paddle calls. It checks the signature on the
# raw body, hands the event to the processor, and answers 200. It never
# touches the database: the cluster pauses at zero capacity and can take
# longer to wake than the five seconds Paddle waits before retrying.
#
# THE PROCESSOR applies an event - the subscription, and any bucket a
# completed transaction grants - inserting paddle_event and applying the
# change in one transaction, so an event is either wholly applied or not
# recorded at all.
#
# THE QUEUE receives Lambda's failure record for every event the processor
# still failed on after two retries. Nothing is lost silently.
#
# THE ALARM goes into ALARM when the queue holds any message. It has no
# action yet: no notification target exists in this stack, and creating one
# is a decision of its own.
#
# The queue holds verified Paddle payloads, which carry the customer's email
# address. Retention is fourteen days, the SQS maximum, and it is encrypted.
#
# REPLAYING A FAILED EVENT
#
# Find and fix the cause first - the processor's log names it - or the replay
# fails the same way and returns to the queue.
#
#   1. Read one message. It stays hidden from other readers for five minutes.
#
#        $q = terraform output -raw paddle_failed_queue_url
#        $m = (aws sqs receive-message --profile arqedia --region us-east-2 `
#               --queue-url $q --max-number-of-messages 1 `
#               --visibility-timeout 300 | ConvertFrom-Json).Messages[0]
#
#   2. The body is Lambda's failure record. requestContext.condition says why
#      it failed; requestPayload is the event exactly as the receiver passed
#      it. Write the payload to a file.
#
#        $r = $m.Body | ConvertFrom-Json
#        $r.requestContext.condition
#        $r.requestPayload | ConvertTo-Json -Depth 20 -Compress |
#          Set-Content -Encoding ascii -NoNewline payload.json
#
#   3. Invoke the processor with it, asynchronously. Expect StatusCode 202.
#
#        aws lambda invoke --profile arqedia --region us-east-2 `
#          --function-name arqedia-dev-paddle-processor `
#          --invocation-type Event --payload fileb://payload.json out.json
#
#   4. Only once step 3 returned 202, delete the message.
#
#        aws sqs delete-message --profile arqedia --region us-east-2 `
#          --queue-url $q --receipt-handle $m.ReceiptHandle
#
#   5. Delete payload.json. It holds a customer's email address.
#
# Replaying the same event twice is safe: the processor skips an event_id it
# has already recorded. A replay that fails lands in the queue again as a new
# message.
#
# SECRETS are created empty. Their values are set outside Terraform, so they
# never reach state:
#
#   aws secretsmanager put-secret-value --profile arqedia --region us-east-2 `
#     --secret-id arqedia-dev/paddle/api-key --secret-string <key>
# ---------------------------------------------------------------------------

locals {
  # The sandbox catalog, read from the file that records it. One file, one
  # environment - see ENV-01 and the decision record's open items.
  paddle_catalog = jsondecode(file("${path.module}/config/paddle/sandbox.json"))
  paddle_prices  = { for p in local.paddle_catalog.products : p.name => p.price_id }

  paddle_price_env = {
    PADDLE_PRICE_BASE     = local.paddle_prices["ARQEDIA Base"]
    PADDLE_PRICE_BUSINESS = local.paddle_prices["ARQEDIA Small Business"]
    PADDLE_PRICE_TOPUP    = local.paddle_prices["ARQEDIA Top-up"]
  }

  paddle_api_base = "https://sandbox-api.paddle.com"
}

# --- secrets ---------------------------------------------------------------
#
# The AWS-managed key, not aws_kms_key.data: that key's policy is scoped to S3
# and widening it is a change of its own.

resource "aws_secretsmanager_secret" "paddle_api_key" {
  name        = "${local.name_prefix}/paddle/api-key"
  description = "Paddle sandbox API key. Value set outside Terraform."
  tags        = { Name = "${local.name_prefix}-paddle-api-key" }
}

resource "aws_secretsmanager_secret" "paddle_webhook_secret" {
  name        = "${local.name_prefix}/paddle/webhook-secret"
  description = "Paddle notification destination secret (pdl_ntfset_). Value set outside Terraform."
  tags        = { Name = "${local.name_prefix}-paddle-webhook-secret" }
}

# --- the failure queue -----------------------------------------------------

resource "aws_sqs_queue" "paddle_processor_failed" {
  name                      = "${local.name_prefix}-paddle-processor-failed"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = { Name = "${local.name_prefix}-paddle-processor-failed" }
}

# Any message at all is an event that was not applied: a subscription not
# recorded, or credit somebody paid for and did not receive.
resource "aws_cloudwatch_metric_alarm" "paddle_processor_failed" {
  alarm_name          = "${local.name_prefix}-paddle-processor-failed"
  alarm_description   = "A Paddle event failed processing and is waiting in the failure queue. Replay procedure: paddle.tf header."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.paddle_processor_failed.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  tags                = { Name = "${local.name_prefix}-paddle-processor-failed" }
}

# --- the processor ---------------------------------------------------------

data "archive_file" "paddle_processor" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/paddle_processor"
  output_path = "${path.module}/build/paddle_processor.zip"
  # Running the tests writes bytecode here; it must not change the zip.
  excludes = ["__pycache__"]
}

resource "aws_iam_role" "paddle_processor" {
  name = "${local.name_prefix}-paddle-processor"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-paddle-processor" }
}

resource "aws_iam_role_policy_attachment" "paddle_processor_logs" {
  role       = aws_iam_role.paddle_processor.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "paddle_processor" {
  # An event and its effect are one transaction. The three transaction actions
  # are separate from ExecuteStatement and all four are needed.
  statement {
    effect = "Allow"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BeginTransaction",
      "rds-data:CommitTransaction",
      "rds-data:RollbackTransaction",
    ]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }

  # Lambda sends the failure record with the function's own role.
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.paddle_processor_failed.arn]
  }
}

resource "aws_iam_role_policy" "paddle_processor" {
  name   = "${local.name_prefix}-paddle-processor"
  role   = aws_iam_role.paddle_processor.id
  policy = data.aws_iam_policy_document.paddle_processor.json
}

resource "aws_lambda_function" "paddle_processor" {
  function_name    = "${local.name_prefix}-paddle-processor"
  role             = aws_iam_role.paddle_processor.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.paddle_processor.output_path
  source_code_hash = data.archive_file.paddle_processor.output_base64sha256
  # Long enough to wait out the cluster waking from zero capacity.
  timeout     = 90
  memory_size = 256

  environment {
    variables = merge(local.paddle_price_env, {
      CLUSTER_ARN = aws_rds_cluster.main.arn
      SECRET_ARN  = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE    = "arqedia"
    })
  }

  tags = { Name = "${local.name_prefix}-paddle-processor" }
}

# Two retries by Lambda, then the failure record goes to the queue.
resource "aws_lambda_function_event_invoke_config" "paddle_processor" {
  function_name                = aws_lambda_function.paddle_processor.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 21600

  destination_config {
    on_failure {
      destination = aws_sqs_queue.paddle_processor_failed.arn
    }
  }
}

# --- the receiver ----------------------------------------------------------

data "archive_file" "paddle_webhook" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/paddle_webhook"
  output_path = "${path.module}/build/paddle_webhook.zip"
  # Running the tests writes bytecode here; it must not change the zip.
  excludes = ["__pycache__"]
}

resource "aws_iam_role" "paddle_webhook" {
  name = "${local.name_prefix}-paddle-webhook"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-paddle-webhook" }
}

resource "aws_iam_role_policy_attachment" "paddle_webhook_logs" {
  role       = aws_iam_role.paddle_webhook.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# The webhook secret and the processor. Nothing else - no database, no API key.
data "aws_iam_policy_document" "paddle_webhook" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.paddle_webhook_secret.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.paddle_processor.arn]
  }
}

resource "aws_iam_role_policy" "paddle_webhook" {
  name   = "${local.name_prefix}-paddle-webhook"
  role   = aws_iam_role.paddle_webhook.id
  policy = data.aws_iam_policy_document.paddle_webhook.json
}

resource "aws_lambda_function" "paddle_webhook" {
  function_name    = "${local.name_prefix}-paddle-webhook"
  role             = aws_iam_role.paddle_webhook.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.paddle_webhook.output_path
  source_code_hash = data.archive_file.paddle_webhook.output_base64sha256
  timeout          = 10
  memory_size      = 256

  # PROPOSED value. An unauthenticated route: a flood of forged requests is
  # held to five at once and cannot take the account's concurrency with it.
  # Paddle retries anything throttled.
  reserved_concurrent_executions = 5

  environment {
    variables = {
      WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.paddle_webhook_secret.arn
      PROCESSOR_FUNCTION = aws_lambda_function.paddle_processor.function_name
    }
  }

  tags = { Name = "${local.name_prefix}-paddle-webhook" }
}

resource "aws_apigatewayv2_integration" "paddle_webhook" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.paddle_webhook.invoke_arn
  payload_format_version = "2.0"
}

# authorization_type NONE. Paddle holds no token; the signature is the
# control, and it is checked before anything else happens.
resource "aws_apigatewayv2_route" "paddle_webhook" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /paddle/webhook"
  target             = "integrations/${aws_apigatewayv2_integration.paddle_webhook.id}"
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "paddle_webhook_gateway" {
  statement_id  = "AllowAPIGatewayPaddleWebhook"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.paddle_webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

output "paddle_webhook_url" {
  value = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/paddle/webhook"
}

output "paddle_failed_queue_url" {
  value = aws_sqs_queue.paddle_processor_failed.url
}
