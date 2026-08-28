# ---------------------------------------------------------------------------
# Composition. Manually invoked with a tenant and engagement. Assembles the
# deterministic sections, drafts the composed ones, writes a markdown memo,
# and records claims bound to the values behind them.
#
# Sonnet 4.6: narrative quality shows here, and it runs once per memo rather
# than once per document.
# ---------------------------------------------------------------------------

data "archive_file" "composition" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/composition"
  output_path = "${path.module}/build/composition.zip"
}

resource "aws_iam_role" "composition" {
  name = "${local.name_prefix}-composition"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-composition" }
}

resource "aws_iam_role_policy_attachment" "composition_logs" {
  role       = aws_iam_role.composition.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "composition" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/*"]
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

  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "composition" {
  name   = "${local.name_prefix}-composition"
  role   = aws_iam_role.composition.id
  policy = data.aws_iam_policy_document.composition.json
}

resource "aws_lambda_function" "composition" {
  function_name    = "${local.name_prefix}-composition"
  role             = aws_iam_role.composition.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.composition.output_path
  source_code_hash = data.archive_file.composition.output_base64sha256
  timeout          = 600
  memory_size      = 512
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      CURATED_BUCKET = aws_s3_bucket.data["curated"].id
      CLUSTER_ARN    = aws_rds_cluster.main.arn
      SECRET_ARN     = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE       = "arqedia"
      MODEL_ID       = var.composition_model_id
      RENDER_FUNCTION = aws_lambda_function.render.function_name
    }
  }

  tags = { Name = "${local.name_prefix}-composition" }
}

output "composition_function" {
  value = aws_lambda_function.composition.function_name
}
