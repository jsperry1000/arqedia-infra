# ---------------------------------------------------------------------------
# The API. HTTP API with a Cognito authorizer: the token is verified at the
# gateway, so an invalid or expired one never reaches our code. The verified
# claims - including the tenant - are handed to the function.
# ---------------------------------------------------------------------------

data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/api"
  output_path = "${path.module}/build/api.zip"
}

resource "aws_iam_role" "api" {
  name = "${local.name_prefix}-api"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-api" }
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data["docs"].arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/*"]
  }

  # Filing reads the analysed envelope and writes it back as normalized,
  # which is what starts extraction.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.data["review"].arn}/*"]
  }

  # Listing proposals a person has read and not yet accepted, so one can be
  # put down and picked up tomorrow. Scoped to the bucket itself because a
  # list is an action on the bucket, not on the objects in it; the prefix is
  # the tenant's own and is enforced in the handler.
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data["review"].arn]
  }

  # Settings reads a logo to show it back, and writes one on upload.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.brand.arn}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # Transactions are separate actions from ExecuteStatement. The wallet
  # debits in one, so that a charge is all or nothing; without these three it
  # would fail on the first begin_transaction.
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

  # Checkout and top-ups call Paddle. The API key only; the webhook secret
  # belongs to the receiver alone.
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.paddle_api_key.arn]
  }

  # The seat invitation (10.5). The same action the signup function holds for
  # the signup code, and for the same reason: there is one verified sender and
  # SES scopes a send by the identity of the From address, which the handler
  # takes from SENDER rather than from anything a caller supplies.
  statement {
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = ["*"]
  }

  # Composition writes a memo; the proposer reads a sample memorandum and
  # proposes a configuration. Both take minutes, so both are started here and
  # polled for rather than waited on.
  statement {
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.composition.arn,
      aws_lambda_function.proposer.arn,
    ]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${local.name_prefix}-api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.api.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  timeout          = 30
  memory_size      = 512
  layers           = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = merge(local.paddle_price_env, {
      CLUSTER_ARN               = aws_rds_cluster.main.arn
      SECRET_ARN                = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE                  = "arqedia"
      DOCS_BUCKET               = aws_s3_bucket.data["docs"].id
      CURATED_BUCKET            = aws_s3_bucket.data["curated"].id
      BRAND_BUCKET              = aws_s3_bucket.brand.id
      REVIEW_BUCKET             = aws_s3_bucket.data["review"].id
      COMPOSITION_FUNCTION      = aws_lambda_function.composition.function_name
      APP_URL                   = "https://${local.app_host}"
      # One sender for the whole product, declared in signup.tf. A second
      # variable would be a second address to verify and a second one to
      # forget.
      SENDER                    = var.signup_sender
      TEXTRACT_TOPIC_ARN        = aws_sns_topic.textract.arn
      TEXTRACT_ROLE_ARN         = aws_iam_role.textract_publish.arn
      RENDER_FUNCTION           = aws_lambda_function.render.function_name
      PROPOSER_FUNCTION         = aws_lambda_function.proposer.function_name
      PADDLE_API_BASE           = local.paddle_api_base
      PADDLE_API_KEY_SECRET_ARN = aws_secretsmanager_secret.paddle_api_key.arn
    })
  }

  tags = { Name = "${local.name_prefix}-api" }
}

resource "aws_apigatewayv2_api" "main" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  # Every hostname the application answers on, from local.browser_origins in
  # dns.tf. The same list the three bucket CORS rules read: it was duplicated
  # here and in storage.tf, only this copy was maintained, and browser uploads
  # broke when an apply reconciled the other.
  #
  # arqedia.com is on it for signup only - the two unauthenticated routes in
  # signup.tf. Nothing else on this API is reachable from the marketing site.
  cors_configuration {
    allow_origins = local.browser_origins
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }

  tags = { Name = "${local.name_prefix}-api" }
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

locals {
  api_routes = [
    "GET /engagements",

    # Opening one from the form. A POST because it creates the row: since
    # the reads ask engagement_id (13.3 stage 4), a name with no row is a
    # 404, and the form that opens a new engagement has to make the row
    # exist rather than navigate to one that does not.
    "POST /engagements",

    "GET /engagements/{id}/documents",
    "GET /engagements/{id}/pending",

    # The company the memoranda in this engagement are about. One route
    # sets it and changes it: the row is resolved or created by name, so
    # naming a subject before anything has been uploaded opens the
    # engagement, and naming one afterwards edits it (SUBJ-01).
    "PUT /engagements/{id}/subject",
    "POST /engagements/{id}/file",
    "GET /engagements/{id}/memos",
    "POST /engagements/{id}/generate",
    "GET /memos/{memo_id}",
    "GET /memos/{memo_id}/pdf",
    "POST /memos/{memo_id}/revise",

    # Rewriting a section at a person's prompt. Started here, run by
    # composition, polled for. Saved only through revise.
    "POST /memos/{memo_id}/rewrites",
    "GET /memos/{memo_id}/rewrites",

    # A person's unsaved work on a memo, kept so leaving does not lose it.
    "GET /memos/{memo_id}/working",
    "PUT /memos/{memo_id}/working",
    "POST /uploads",
    "GET /settings",
    "POST /settings",
    "GET /settings/preview",
    "POST /settings/logo",
    "POST /settings/logo/confirm",
    "GET /templates",
    "GET /document-types",
    "DELETE /documents/{document_id}",
    "GET /config",
    "GET /config/{revision}",
    "PUT /config/active",
    "POST /config/draft",
    "DELETE /config/draft",
    "GET /config/draft/validate",
    "POST /config/publish",
    "GET /config/packs",
    "GET /config/draft",
    "POST /config/draft/sections",
    "DELETE /config/draft/templates/{template}/sections/{key}",
    "PUT /config/draft/templates/{template}/sections/{key}/fields",
    "POST /config/draft/templates",
    "POST /config/draft/templates/{template}/duplicate",
    "DELETE /config/draft/templates/{template}",
    "POST /config/draft/fields",
    "DELETE /config/draft/fields/{key}",
    "PUT /config/draft/fields/{key}/documents",
    "PUT /config/draft/types/{key}/fields",
    "POST /config/draft/types",
    "DELETE /config/draft/types/{key}",
    "POST /config/draft/categories",
    "DELETE /config/draft/categories/{key}",
    "POST /config/fork",

    # One base, and templates over it. The base is taken once; a memorandum
    # is taken whenever somebody wants another one, and goes into the draft.
    "GET /config/templates/available",
    "POST /config/templates/fork",

    # What those two offer. Refused to every tenant but the ARQEDIA workspace
    # in the dispatcher, which is where the control lives - a route exists for
    # everyone or for nobody.
    "GET /config/offer",
    "PUT /config/offer",

    # Configuring from the client's own memorandum. The sample goes to the
    # review bucket under proposals/, which nothing watches - a sample is
    # form, not substance, and must never be classified and filed.
    "POST /config/draft/sample",
    "POST /config/draft/propose",
    "GET /config/draft/proposal",

    # Deciding what a proposal said is an hour of a person's judgement.
    # Kept as they make it, beside the proposal, so a closed tab or an
    # accept that stops part way costs them nothing.
    "GET /config/draft/proposals",
    "GET /config/draft/working",
    "PUT /config/draft/working",
    "POST /documents/{document_id}/active",
    "GET /documents/{document_id}/values",
    "GET /documents/{document_id}/passage",

    # The wallet. What is left, what went where, and what a thing would cost
    # before anybody commits to it.
    "GET /wallet",
    "GET /wallet/ledger",
    "GET /wallet/quote",
    "POST /wallet/top-up",

    # Paying for a plan. Reading is open to any seat; checkout and a plan
    # change are refused to a member in the handler, as seats are.
    "GET /billing/subscription",
    "POST /billing/checkout",
    "POST /billing/plan",

    # Seats. Reading is open to anybody with one; changing is not, and the
    # handler refuses a member rather than the gateway - the message matters.
    "GET /seats",
    "POST /seats/invitations",
    "DELETE /seats/invitations/{invitation_id}",
    "PUT /seats/{seat_id}",
    "DELETE /seats/{seat_id}",
  ]
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = toset(local.api_routes)

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  # Every request, whether or not it reached the Lambda. Without this there is
  # no record of a request the gateway answered itself - a preflight, a 401
  # from the authorizer, a payload refused - and those are exactly the ones
  # nobody can otherwise account for (observability.tf).
  #
  # JSON rather than CLF, because it is read by a person grepping for a route
  # at the time somebody says an upload failed. integrationErrorMessage and
  # error.message are what say WHY the gateway answered as it did; without
  # them a 500 in this log is indistinguishable from a 500 in the other.
  #
  # No body, no headers, no query string - any of them could carry the
  # customer's address.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId       = "$context.requestId"
      requestTime     = "$context.requestTime"
      httpMethod      = "$context.httpMethod"
      routeKey        = "$context.routeKey"
      path            = "$context.path"
      status          = "$context.status"
      responseLength  = "$context.responseLength"
      responseLatency = "$context.responseLatency"
      sourceIp        = "$context.identity.sourceIp"
      # Why the gateway refused, where it did.
      authorizerError  = "$context.authorizer.error"
      integrationError = "$context.integrationErrorMessage"
      errorMessage     = "$context.error.message"
    })
  }

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 25
  }

  tags = { Name = "${local.name_prefix}-api" }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

output "api_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}
