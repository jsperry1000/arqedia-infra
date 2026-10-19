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
  excludes    = ["__pycache__"]
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

  # Update reads the memo a person saved, and its own run's progress, from
  # the curated bucket. Reading only: nothing here lists or deletes.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # The three transaction actions are for wallet.refund_generation (UX02
  # 20.1): a generation that writes no memo gives its charge back, and a
  # refund is two rows in one transaction. They are separate IAM actions
  # from ExecuteStatement, and all four are needed (CLAUDE.md, Money).
  statement {
    effect = "Allow"
    actions = [
      "rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement",
      "rds-data:BeginTransaction", "rds-data:CommitTransaction",
      "rds-data:RollbackTransaction",
    ]
    resources = [aws_rds_cluster.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_rds_cluster.main.master_user_secret[0].secret_arn]
  }

  # The on-failure destination (20.2). Lambda writes the invocation record as
  # the function's own identity, so the EXECUTION ROLE needs this - not a
  # policy on the queue (reconcile.tf, the normalizer's queue).
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.composition_failed.arn]
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
  # The ceiling Lambda allows. Update is a whole generation followed by its
  # comparison passes, four at a time, and a long memo's generation alone has
  # come close to 600 (decision of 16 October 2026).
  timeout     = 900
  memory_size = 512
  layers      = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      CURATED_BUCKET  = aws_s3_bucket.data["curated"].id
      CLUSTER_ARN     = aws_rds_cluster.main.arn
      SECRET_ARN      = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE        = "arqedia"
      MODEL_ID        = var.composition_model_id
      RENDER_FUNCTION = aws_lambda_function.render.function_name
    }
  }

  tags = { Name = "${local.name_prefix}-composition" }
}

# NO RETRIES (UX02 20.1, decided 19 October 2026). Every path in the function
# catches its own failure, refunds where nothing was written, and records the
# run, so a retry can only be a timeout or a crash - and a retry of those runs
# every model call again on a run already paid for and already failing.
#
# WHAT IT CANNOT CATCH GOES TO THE QUEUE (20.2): a timeout, an out-of-memory
# kill, a crash at start-up, anything raised before a path's own try. The
# invocation record carries the original event, and composition_failed.tf
# finishes the run from it - refund, and the run written failed.
resource "aws_lambda_function_event_invoke_config" "composition" {
  function_name          = aws_lambda_function.composition.function_name
  maximum_retry_attempts = 0

  destination_config {
    on_failure {
      destination = aws_sqs_queue.composition_failed.arn
    }
  }
}

output "composition_function" {
  value = aws_lambda_function.composition.function_name
}
