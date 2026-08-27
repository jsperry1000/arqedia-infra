# ---------------------------------------------------------------------------
# Normalizer. Fires on an object landing in the docs bucket, extracts text
# and unit boundaries, writes an envelope to review, records a document row.
#
# Not in the VPC: it reaches Aurora over the Data API and S3 over the public
# endpoint. That is what keeps the NAT gateway out of the design.
# ---------------------------------------------------------------------------

resource "aws_lambda_layer_version" "docprocessing" {
  layer_name          = "${local.name_prefix}-docprocessing"
  filename            = "${path.module}/build/layer-docprocessing.zip"
  source_code_hash    = filebase64sha256("${path.module}/build/layer-docprocessing.zip")
  compatible_runtimes = ["python3.12"]
  description         = "pypdf, python-docx, openpyxl"
}

data "archive_file" "normalizer" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/normalizer"
  output_path = "${path.module}/build/normalizer.zip"
}

resource "aws_iam_role" "normalizer" {
  name = "${local.name_prefix}-normalizer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-normalizer" }
}

resource "aws_iam_role_policy_attachment" "normalizer_logs" {
  role       = aws_iam_role.normalizer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "normalizer" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.data["docs"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data["review"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  statement {
    effect = "Allow"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BatchExecuteStatement",
    ]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }

  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "normalizer" {
  name   = "${local.name_prefix}-normalizer"
  role   = aws_iam_role.normalizer.id
  policy = data.aws_iam_policy_document.normalizer.json
}

resource "aws_lambda_function" "normalizer" {
  function_name    = "${local.name_prefix}-normalizer"
  role             = aws_iam_role.normalizer.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.normalizer.output_path
  source_code_hash = data.archive_file.normalizer.output_base64sha256
  timeout          = 300
  memory_size      = 1024
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      REVIEW_BUCKET = aws_s3_bucket.data["review"].id
      CLUSTER_ARN   = aws_rds_cluster.main.arn
      SECRET_ARN    = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE            = "arqedia"
      CLASSIFIER_MODEL_ID = var.extraction_model_id
    }
  }

  tags = { Name = "${local.name_prefix}-normalizer" }
}

resource "aws_lambda_permission" "normalizer_s3" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.normalizer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.docs_created.arn
}

# EventBridge rather than a bucket notification. A bucket has one notification
# config that every consumer must share; EventBridge rules are independent, so
# adding progress tracking, vault indexing or virus scanning later touches
# nothing that already exists.
resource "aws_s3_bucket_notification" "docs" {
  bucket      = aws_s3_bucket.data["docs"].id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "docs_created" {
  name        = "${local.name_prefix}-docs-created"
  description = "Object created in the docs bucket"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.data["docs"].id] }
      object = { key = [{ prefix = "tenants/" }] }
    }
  })

  tags = { Name = "${local.name_prefix}-docs-created" }
}

resource "aws_cloudwatch_event_target" "normalizer" {
  rule      = aws_cloudwatch_event_rule.docs_created.name
  target_id = "normalizer"
  arn       = aws_lambda_function.normalizer.arn
}

output "normalizer_function" {
  value = aws_lambda_function.normalizer.function_name
}


