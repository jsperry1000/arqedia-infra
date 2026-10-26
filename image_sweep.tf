# ---------------------------------------------------------------------------
# The image sweep (graphics-insert, decided 26 October 2026): once a day,
# every image in a memo's working prefix older than 24 hours that no working
# copy of that memo names - in its text or its undo history - is removed,
# every version of it. The shape of reconcile.tf: a schedule, a function, a
# role holding exactly what it touches. lambda/image_sweep/app.py says why.
# ---------------------------------------------------------------------------

data "archive_file" "image_sweep" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/image_sweep"
  output_path = "${path.module}/build/image_sweep.zip"
  excludes    = ["__pycache__"]
}

resource "aws_iam_role" "image_sweep" {
  name = "${local.name_prefix}-image-sweep"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-image-sweep" }
}

resource "aws_iam_role_policy_attachment" "image_sweep_logs" {
  role       = aws_iam_role.image_sweep.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# READS WORKING COPIES, DELETES WORKING IMAGES, AND NOTHING ELSE.
#
# It lists the tenant folders, the working image prefixes and the working
# copies; reads the copies, which is why it decrypts; and deletes only under
# the working image prefix. A revision's own images (tenants/*/images/), the
# memos, the documents: none of them can be listed, read or deleted by this
# role, whatever its code says. That part is enforced by IAM.
data "aws_iam_policy_document" "image_sweep" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data["curated"].arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "tenants/",
        "tenants/*/working/images/memos/*",
        "tenants/*/working/memos/*",
      ]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucketVersions"]
    resources = [aws_s3_bucket.data["curated"].arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["tenants/*/working/images/memos/*"]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/tenants/*/working/memos/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/tenants/*/working/images/memos/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.data.arn]
  }
}

resource "aws_iam_role_policy" "image_sweep" {
  name   = "${local.name_prefix}-image-sweep"
  role   = aws_iam_role.image_sweep.id
  policy = data.aws_iam_policy_document.image_sweep.json
}

resource "aws_lambda_function" "image_sweep" {
  function_name    = "${local.name_prefix}-image-sweep"
  role             = aws_iam_role.image_sweep.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.image_sweep.output_path
  source_code_hash = data.archive_file.image_sweep.output_base64sha256
  timeout          = 300
  memory_size      = 256

  environment {
    variables = {
      CURATED_BUCKET = aws_s3_bucket.data["curated"].id
      GRACE_HOURS    = "24"
    }
  }

  tags = { Name = "${local.name_prefix}-image-sweep" }
}

# Daily, at 03:00 UTC: night in the Americas and before the working day in
# Europe, so nobody is mid-edit on the 24th hour of an upload as a rule.
resource "aws_cloudwatch_event_rule" "image_sweep" {
  name                = "${local.name_prefix}-image-sweep"
  description         = "Working images no working copy names, after 24 hours"
  schedule_expression = "cron(0 3 * * ? *)"
  tags                = { Name = "${local.name_prefix}-image-sweep" }
}

resource "aws_cloudwatch_event_target" "image_sweep" {
  rule      = aws_cloudwatch_event_rule.image_sweep.name
  target_id = "image-sweep"
  arn       = aws_lambda_function.image_sweep.arn
}

resource "aws_lambda_permission" "image_sweep" {
  statement_id  = "AllowEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.image_sweep.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.image_sweep.arn
}
