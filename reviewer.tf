# ---------------------------------------------------------------------------
# Reviewer (REV-01). Reads a tenant's open draft and suggests changes to its
# field descriptions, section prompts and document type descriptions, the
# facts its memoranda need and where each is sought. Writes the draft only
# when a person accepts a suggestion, through editor.py in the layer.
#
# Invoked by the API. "open" invokes this function again asynchronously for
# the read, which takes minutes; "poll", "accept" and "close" answer at once.
#
# Not in the VPC, for the same reason as the proposer: Data API to Aurora,
# public endpoints to S3 and Bedrock, and no NAT gateway in the design.
# ---------------------------------------------------------------------------

data "archive_file" "reviewer" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/reviewer"
  output_path = "${path.module}/build/reviewer.zip"
}

resource "aws_iam_role" "reviewer" {
  name = "${local.name_prefix}-reviewer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-reviewer" }
}

resource "aws_iam_role_policy_attachment" "reviewer_logs" {
  role       = aws_iam_role.reviewer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "reviewer" {
  # The review object, what was accepted from it, and whether it is closed.
  # tenants/<id>/reviews/ only: this function has no business with a
  # proposal's sample or anything else in the bucket.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["review"].arn}/tenants/*/reviews/*"]
  }

  # Poll lists what was accepted. A list is an action on the bucket, so it is
  # narrowed by prefix here as well as in the handler.
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data["review"].arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["tenants/*/reviews/*"]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # Reads the draft, writes it on an accept, and charges for the session.
  # The charge runs in a transaction, and the three transaction actions are
  # separate from ExecuteStatement (CLAUDE.md, Money).
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

  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }

  # "open" starts the read by invoking this function again, asynchronously.
  # Named by constructed ARN rather than by the resource: the function
  # depends on this role, and the role's policy naming the function's arn
  # attribute is a dependency the other way round.
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}-reviewer"]
  }
}

resource "aws_iam_role_policy" "reviewer" {
  name   = "${local.name_prefix}-reviewer"
  role   = aws_iam_role.reviewer.id
  policy = data.aws_iam_policy_document.reviewer.json
}

resource "aws_lambda_function" "reviewer" {
  function_name    = "${local.name_prefix}-reviewer"
  role             = aws_iam_role.reviewer.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.reviewer.output_path
  source_code_hash = data.archive_file.reviewer.output_base64sha256

  # One model call per part - the vocabulary, each memorandum, coverage - so
  # the ceiling is the number of memoranda. 900 is Lambda's maximum. The
  # synchronous acts return in seconds and are not what this is sized for.
  timeout     = 900
  memory_size = 512
  layers      = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      REVIEW_BUCKET = aws_s3_bucket.data["review"].id
      CLUSTER_ARN   = aws_rds_cluster.main.arn
      SECRET_ARN    = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE      = "arqedia"
      # Sonnet (D2). Critiquing prose prompts is judgement rather than
      # bounded extraction.
      MODEL_ID = var.composition_model_id
    }
  }

  tags = { Name = "${local.name_prefix}-reviewer" }
}

output "reviewer_function" {
  value = aws_lambda_function.reviewer.function_name
}
