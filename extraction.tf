# ---------------------------------------------------------------------------
# Extraction. Fires on a normalized envelope landing in the review bucket.
# Runs each mapped schema, writes one row per value with its locator (EV-01).
#
# Haiku 4.5: extraction is a bounded, structured task and runs on every
# document, so it is the margin-sensitive call. Composition uses Sonnet.
# ---------------------------------------------------------------------------

data "archive_file" "extraction" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/extraction"
  output_path = "${path.module}/build/extraction.zip"
}

resource "aws_iam_role" "extraction" {
  name = "${local.name_prefix}-extraction"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-extraction" }
}

resource "aws_iam_role_policy_attachment" "extraction_logs" {
  role       = aws_iam_role.extraction.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "extraction" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["review"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }

  # An inference profile routes across regions, so both the profile and the
  # underlying foundation models must be invocable.
  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "extraction" {
  name   = "${local.name_prefix}-extraction"
  role   = aws_iam_role.extraction.id
  policy = data.aws_iam_policy_document.extraction.json
}

resource "aws_lambda_function" "extraction" {
  function_name    = "${local.name_prefix}-extraction"
  role             = aws_iam_role.extraction.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.extraction.output_path
  source_code_hash = data.archive_file.extraction.output_base64sha256
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      CLUSTER_ARN = aws_rds_cluster.main.arn
      SECRET_ARN  = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE    = "arqedia"
      MODEL_ID    = var.extraction_model_id
    }
  }

  tags = { Name = "${local.name_prefix}-extraction" }
}

resource "aws_s3_bucket_notification" "review" {
  bucket      = aws_s3_bucket.data["review"].id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "envelope_written" {
  name        = "${local.name_prefix}-envelope-written"
  description = "Normalized envelope written to the review bucket"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.data["review"].id] }
      object = { key = [{ suffix = ".normalized.json" }] }
    }
  })

  tags = { Name = "${local.name_prefix}-envelope-written" }
}

resource "aws_cloudwatch_event_target" "extraction" {
  rule      = aws_cloudwatch_event_rule.envelope_written.name
  target_id = "extraction"
  arn       = aws_lambda_function.extraction.arn
}

resource "aws_lambda_permission" "extraction_events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.extraction.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.envelope_written.arn
}

output "extraction_function" {
  value = aws_lambda_function.extraction.function_name
}
