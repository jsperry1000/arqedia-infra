# ---------------------------------------------------------------------------
# The staff console's API. Its own gateway, its own function, its own role.
#
# NOTHING IS SHARED WITH api.tf. Not the gateway, not the authorizer, not the
# integration, not the role. Group 16 decided the staff console shares the
# database with the customer path and nothing else, and this file is where
# that decision is either kept or quietly lost: a route added to
# aws_apigatewayv2_api.main would inherit the customer pool's authorizer, and
# a permission added to aws_iam_role.api would be held by a function serving
# tenants.
#
# A CUSTOMER'S TOKEN CANNOT REACH THIS FUNCTION. The authorizer below names
# the staff pool's client as its audience and the staff pool as its issuer.
# A token from aws_cognito_user_pool.main fails both. That is the control;
# the check in app.py is a second reading of the same claim.
# ---------------------------------------------------------------------------

data "archive_file" "admin" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/admin"
  output_path = "${path.module}/build/admin.zip"
}

resource "aws_iam_role" "admin" {
  name = "${local.name_prefix}-admin"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-admin" }
}

# Writing to its own log group, and nothing else. Without this the function
# runs and records nothing at all - not a START line - and the access log on
# the stage covers the gateway rather than the handler.
resource "aws_iam_role_policy_attachment" "admin_logs" {
  role       = aws_iam_role.admin.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# TWO ACTIONS. No BeginTransaction, CommitTransaction or RollbackTransaction:
# this function never groups writes because it never writes. No S3, no SES,
# no lambda:InvokeFunction, no KMS - the staff console reads rows and returns
# them.
#
# WHAT THIS IS NOT. ExecuteStatement outside a transaction autocommits, so
# these two actions would permit a write if one were ever added to the code.
# The read-only property of this function comes from cross_tenant.py refusing
# any statement that is not a SELECT, which is a guard on the code rather
# than on the credentials. The credential-level control is a SELECT-only
# database user with its own secret - OBS-02 - and it is not built.
data "aws_iam_policy_document" "admin" {
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

resource "aws_iam_role_policy" "admin" {
  name   = "${local.name_prefix}-admin"
  role   = aws_iam_role.admin.id
  policy = data.aws_iam_policy_document.admin.json
}

# NO LAYER. The docprocessing layer carries the shared modules the customer
# path imports; attaching it here would put them one import statement away
# from a function that is meant to share nothing. This function's two files
# are the whole of it.
resource "aws_lambda_function" "admin" {
  function_name    = "${local.name_prefix}-admin"
  role             = aws_iam_role.admin.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.admin.output_path
  source_code_hash = data.archive_file.admin.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      CLUSTER_ARN = aws_rds_cluster.main.arn
      SECRET_ARN  = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE    = "arqedia"

      # The same issuer the authorizer trusts, read by the handler so that a
      # mismatch between the two fails closed.
      STAFF_POOL_ISSUER = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.staff.id}"
    }
  }

  tags = { Name = "${local.name_prefix}-admin" }
}

resource "aws_apigatewayv2_api" "admin" {
  name          = "${local.name_prefix}-admin"
  protocol_type = "HTTP"

  # ONE ORIGIN. local.browser_origins carries the application, the marketing
  # site and three localhost ports; none of them may call this. The staff
  # console answers on one hostname and that is the only one listed, so a
  # page on app.arqedia.com cannot read a tenant list even with a staff
  # token in its hands.
  cors_configuration {
    allow_origins = ["https://${local.admin_host}"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 3600
  }

  tags = { Name = "${local.name_prefix}-admin" }
}

resource "aws_apigatewayv2_authorizer" "staff" {
  api_id           = aws_apigatewayv2_api.admin.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "staff"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.admin.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.staff.id}"
  }
}

resource "aws_apigatewayv2_integration" "admin" {
  api_id                 = aws_apigatewayv2_api.admin.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.admin.invoke_arn
  payload_format_version = "2.0"
}

locals {
  # GET only. A write route on this API is a decision, not an addition.
  admin_routes = [
    "GET /tenants",
    "GET /tenants/{id}/seats",
    "GET /signups",
  ]
}

resource "aws_apigatewayv2_route" "admin" {
  for_each = toset(local.admin_routes)

  api_id             = aws_apigatewayv2_api.admin.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.admin.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.staff.id
}

# Its own access log, beside the customer API's in observability.tf rather
# than in it: everything this console needs is in this file, so withdrawing
# the console is deleting one file rather than editing three.
resource "aws_cloudwatch_log_group" "admin_access" {
  name              = "/aws/apigateway/${local.name_prefix}-admin-access"
  retention_in_days = 30

  tags = { Name = "${local.name_prefix}-admin-access" }
}

resource "aws_apigatewayv2_stage" "admin" {
  api_id      = aws_apigatewayv2_api.admin.id
  name        = "$default"
  auto_deploy = true

  # The same fields as the customer API's, for the same reason: a request the
  # gateway answered itself - a preflight, a 401 from the authorizer - leaves
  # no other trace. On this API the 401s are the interesting line: they are
  # attempts to reach every tenant's data.
  #
  # No body, no headers, no query string.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.admin_access.arn
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

      authorizerError  = "$context.authorizer.error"
      integrationError = "$context.integrationErrorMessage"
      errorMessage     = "$context.error.message"
    })
  }

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 25
  }

  tags = { Name = "${local.name_prefix}-admin" }
}

resource "aws_lambda_permission" "admin_gateway" {
  statement_id  = "AllowAdminAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.admin.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.admin.execution_arn}/*/*"
}

output "admin_api_url" {
  value = aws_apigatewayv2_stage.admin.invoke_url
}
