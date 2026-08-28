# ---------------------------------------------------------------------------
# Rendering. The consolidated markdown becomes a branded PDF - the deliverable
# a customer receives and shares. The markdown remains as the intermediate it
# is rendered from.
#
# Branding is gated by plan: Base takes the platform's colours and mark,
# Business and Enterprise may set their own, and only Enterprise may remove
# the ARQEDIA footer.
# ---------------------------------------------------------------------------

# Logos live apart from document data: they are small, they are read on every
# render, and a tenant's own mark is not confidential material.
resource "aws_s3_bucket" "brand" {
  bucket = "${local.name_prefix}-brand-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name_prefix}-brand" }
}

resource "aws_s3_bucket_versioning" "brand" {
  bucket = aws_s3_bucket.brand.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "brand" {
  bucket = aws_s3_bucket.brand.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "brand" {
  bucket                  = aws_s3_bucket.brand.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "brand" {
  bucket = aws_s3_bucket.brand.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "brand" {
  bucket = aws_s3_bucket.brand.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.brand.arn,
        "${aws_s3_bucket.brand.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

# The browser uploads a logo straight to S3, as it does a document.
resource "aws_s3_bucket_cors_configuration" "brand" {
  bucket = aws_s3_bucket.brand.id

  cors_rule {
    allowed_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}",
    "http://localhost:5173"]
    allowed_methods = ["PUT"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# --- render function -------------------------------------------------------

data "archive_file" "render" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/render"
  output_path = "${path.module}/build/render.zip"
}

resource "aws_iam_role" "render" {
  name = "${local.name_prefix}-render"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-render" }
}

resource "aws_iam_role_policy_attachment" "render_logs" {
  role       = aws_iam_role.render.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "render" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.brand.arn}/*"]
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
}

resource "aws_iam_role_policy" "render" {
  name   = "${local.name_prefix}-render"
  role   = aws_iam_role.render.id
  policy = data.aws_iam_policy_document.render.json
}

resource "aws_lambda_function" "render" {
  function_name    = "${local.name_prefix}-render"
  role             = aws_iam_role.render.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.render.output_path
  source_code_hash = data.archive_file.render.output_base64sha256
  timeout          = 120
  memory_size      = 1024
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = {
      CURATED_BUCKET = aws_s3_bucket.data["curated"].id
      BRAND_BUCKET   = aws_s3_bucket.brand.id
      CLUSTER_ARN    = aws_rds_cluster.main.arn
      SECRET_ARN     = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE       = "arqedia"
    }
  }

  tags = { Name = "${local.name_prefix}-render" }
}

# Composition starts the render once the memo is written, so the PDF exists by
# the time the person looks for it.
resource "aws_iam_role_policy" "composition_render" {
  name = "${local.name_prefix}-composition-render"
  role = aws_iam_role.composition.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.render.arn
    }]
  })
}

output "brand_bucket" {
  value = aws_s3_bucket.brand.id
}

output "render_function" {
  value = aws_lambda_function.render.function_name
}
