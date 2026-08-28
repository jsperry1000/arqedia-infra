# ---------------------------------------------------------------------------
# Optical character recognition.
#
# A certified scan carries only its stamp as text. Reading the document beneath
# it is asynchronous - a twelve-page scan takes minutes - so nothing waits. The
# job starts, Textract publishes to a topic on completion, and the collector
# picks up the result and releases the document to extraction.
#
# The docs bucket policy permitting Textract to read a document lives in
# storage.tf, alongside the TLS rule for all three buckets.
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "textract" {
  name = "${local.name_prefix}-textract-complete"
  tags = { Name = "${local.name_prefix}-textract-complete" }
}

# The role Textract assumes to publish the completion notification. Textract is
# the principal here, not us.
resource "aws_iam_role" "textract_publish" {
  name = "${local.name_prefix}-textract-publish"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "textract.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-textract-publish" }
}

resource "aws_iam_role_policy" "textract_publish" {
  name = "${local.name_prefix}-textract-publish"
  role = aws_iam_role.textract_publish.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sns:Publish"
      Resource = aws_sns_topic.textract.arn
    }]
  })
}

# --- collector -------------------------------------------------------------

data "archive_file" "collector" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/collector"
  output_path = "${path.module}/build/collector.zip"
}

resource "aws_iam_role" "collector" {
  name = "${local.name_prefix}-collector"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-collector" }
}

resource "aws_iam_role_policy_attachment" "collector_logs" {
  role       = aws_iam_role.collector.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "collector" {
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
    actions   = ["rds-data:ExecuteStatement"]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }

  # Collecting a finished job. A Textract job id is not a resource ARN, so
  # these actions cannot be scoped further than the account.
  statement {
    effect = "Allow"
    actions = [
      "textract:GetDocumentTextDetection",
      "textract:GetDocumentAnalysis",
      "textract:GetExpenseAnalysis",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "collector" {
  name   = "${local.name_prefix}-collector"
  role   = aws_iam_role.collector.id
  policy = data.aws_iam_policy_document.collector.json
}

resource "aws_lambda_function" "collector" {
  function_name    = "${local.name_prefix}-collector"
  role             = aws_iam_role.collector.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.collector.output_path
  source_code_hash = data.archive_file.collector.output_base64sha256
  timeout          = 300
  memory_size      = 1024
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      REVIEW_BUCKET = aws_s3_bucket.data["review"].id
      CLUSTER_ARN   = aws_rds_cluster.main.arn
      SECRET_ARN    = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE      = "arqedia"
    }
  }

  tags = { Name = "${local.name_prefix}-collector" }
}

resource "aws_sns_topic_subscription" "collector" {
  topic_arn = aws_sns_topic.textract.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.collector.arn
}

resource "aws_lambda_permission" "collector_sns" {
  statement_id  = "AllowSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.collector.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.textract.arn
}

# --- the API starts the jobs -----------------------------------------------

data "aws_iam_policy_document" "api_textract" {
  statement {
    effect = "Allow"
    actions = [
      "textract:StartDocumentTextDetection",
      "textract:StartDocumentAnalysis",
      "textract:StartExpenseAnalysis",
    ]
    resources = ["*"]
  }

  # Starting a job validates the object metadata using OUR credentials, not
  # Textract's - so the caller needs to read it even though Textract does the
  # reading afterwards.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data["docs"].arn}/*"]
  }

  # Handing Textract the role it publishes the completion notice with.
  statement {
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.textract_publish.arn]
  }
}

resource "aws_iam_role_policy" "api_textract" {
  name   = "${local.name_prefix}-api-textract"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api_textract.json
}

output "textract_topic_arn" {
  value = aws_sns_topic.textract.arn
}

output "collector_function" {
  value = aws_lambda_function.collector.function_name
}

