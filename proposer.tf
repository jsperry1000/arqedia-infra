# ---------------------------------------------------------------------------
# Proposer. Reads a client's OWN memorandum and proposes a configuration from
# it - the sections it carries, the facts each reports, the documents those
# facts come from. Writes nothing to the draft; a person accepts.
#
# Invoked by the API, never triggered by a bucket. The file it reads is a
# SAMPLE, not a document: it lands under proposals/ in the review bucket,
# which nothing watches, and the function deletes it once read. Anything
# landing in the docs bucket is classified and filed, which is precisely what
# must not happen to somebody's blank form.
#
# Not in the VPC, for the same reason as the normalizer: Data API to Aurora,
# public endpoint to S3, and no NAT gateway in the design.
# ---------------------------------------------------------------------------

data "archive_file" "proposer" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/proposer"
  output_path = "${path.module}/build/proposer.zip"
}

resource "aws_iam_role" "proposer" {
  name = "${local.name_prefix}-proposer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-proposer" }
}

resource "aws_iam_role_policy_attachment" "proposer_logs" {
  role       = aws_iam_role.proposer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "proposer" {
  # The review bucket only. This function has no business in the docs bucket,
  # and DeleteObject is here because deleting the sample is the last thing it
  # does - a sample that survives the read has become a document by accident.
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.data["review"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # Reads the draft's field vocabulary, so it can offer a match against what
  # the tenant already holds. Reads only - the draft is written by the editor.
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

  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "proposer" {
  name   = "${local.name_prefix}-proposer"
  role   = aws_iam_role.proposer.id
  policy = data.aws_iam_policy_document.proposer.json
}

resource "aws_lambda_function" "proposer" {
  function_name    = "${local.name_prefix}-proposer"
  role             = aws_iam_role.proposer.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.proposer.output_path
  source_code_hash = data.archive_file.proposer.output_base64sha256

  # One model call per section, so the ceiling is the length of somebody's
  # memorandum rather than the size of their file. Thirteen sections is
  # thirteen calls. 900 is Lambda's maximum and there is no second chance:
  # a timeout at section nine leaves a proposal that stops mid-document.
  timeout     = 900
  memory_size = 1024
  layers      = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      REVIEW_BUCKET = aws_s3_bucket.data["review"].id
      CLUSTER_ARN   = aws_rds_cluster.main.arn
      SECRET_ARN    = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE      = "arqedia"
      MODEL_ID      = var.extraction_model_id
    }
  }

  tags = { Name = "${local.name_prefix}-proposer" }
}

output "proposer_function" {
  value = aws_lambda_function.proposer.function_name
}
