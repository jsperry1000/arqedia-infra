# ---------------------------------------------------------------------------
# Signing up. The only way an account comes into being.
#
# A function of its own rather than two more routes on the API, for two
# reasons.
#
# The pool stays admin-create-only. If Cognito accepted registrations
# directly, anyone could call it and skip the controls in this handler
# entirely, ending up with an account that carries no tenant.
#
# And this function holds Cognito administrative permissions. The API holds
# none and must not: a defect in any of its fifty routes would otherwise be a
# defect that can create users.
#
# Both routes are unauthenticated, which is the point - a person signing up
# has no token. Nothing here reads a tenant from a request, because at this
# moment there is not one.
# ---------------------------------------------------------------------------

data "archive_file" "signup" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/signup"
  output_path = "${path.module}/build/signup.zip"
}

resource "aws_iam_role" "signup" {
  name = "${local.name_prefix}-signup"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-signup" }
}

resource "aws_iam_role_policy_attachment" "signup_logs" {
  role       = aws_iam_role.signup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "signup" {
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

  # Named one by one. AdminCreateUser and AdminSetUserPassword make the
  # account; AdminGetUser tells somebody who already has one to sign in
  # instead; AdminDeleteUser is the undo when the tenant row cannot be
  # completed. Nothing else, and nothing with a wildcard.
  statement {
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminDeleteUser",
    ]
    resources = [aws_cognito_user_pool.main.arn]
  }

  statement {
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "signup" {
  name   = "${local.name_prefix}-signup"
  role   = aws_iam_role.signup.id
  policy = data.aws_iam_policy_document.signup.json
}

resource "aws_lambda_function" "signup" {
  function_name    = "${local.name_prefix}-signup"
  role             = aws_iam_role.signup.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.signup.output_path
  source_code_hash = data.archive_file.signup.output_base64sha256
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      CLUSTER_ARN  = aws_rds_cluster.main.arn
      SECRET_ARN   = aws_rds_cluster.main.master_user_secret[0].secret_arn
      DATABASE     = "arqedia"
      USER_POOL_ID = aws_cognito_user_pool.main.id
      SENDER       = var.signup_sender
    }
  }

  tags = { Name = "${local.name_prefix}-signup" }
}

resource "aws_apigatewayv2_integration" "signup" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.signup.invoke_arn
  payload_format_version = "2.0"
}

# authorization_type NONE, deliberately and only here. Everything else on this
# API is JWT. These two are the only routes in the product a person without a
# token may reach.
resource "aws_apigatewayv2_route" "signup" {
  for_each = toset(["POST /signup", "POST /signup/verify"])

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.signup.id}"
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "signup_gateway" {
  statement_id  = "AllowAPIGatewaySignup"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.signup.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

variable "signup_sender" {
  description = "Verified SES sender for signup codes."
  type        = string
  default     = "no-reply@arqedia.com"
}

output "signup_function" {
  value = aws_lambda_function.signup.function_name
}
