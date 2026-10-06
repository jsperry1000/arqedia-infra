# ---------------------------------------------------------------------------
# Sharing a memorandum, and the person it is shared with.
#
# share_viewer_spec_v1, as decided on share-recipient (30 September -
# 1 October 2026). Four DynamoDB tables, a second Cognito pool for viewers who
# register, and one function that serves the viewer.
#
# WHY DYNAMODB AND NOT AURORA. The viewer is the first thing a recipient sees
# of this product, and the cluster pauses at zero capacity and takes about
# fifteen seconds to wake (Isolation section 3). Nothing a recipient does
# touches Aurora: the grant carries everything the viewer needs, and the
# memorandum it shows was rendered and watermarked when the grant was made.
#
# The tenant side - sending, listing, revoking - is three routes on the API
# function (lambda/api/share.py), which already holds Aurora, the wallet and
# the renderer. The viewer side is its own function, holding none of them.
# ---------------------------------------------------------------------------

# --- tables ----------------------------------------------------------------
#
# hash_key AND range_key, WHICH VALIDATE AS DEPRECATED, DELIBERATELY. Provider
# 6.29 added key_schema in their place, and key_schema inside a
# global_secondary_index plans as changed on every run (hashicorp/
# terraform-provider-aws #46513, #46335) - the CRLF defect CLAUDE.md warns
# about, from another cause. The deprecated form does not drift. Move when
# those are closed, not before.

# One item per memorandum per recipient. The key IS the uniqueness rule:
# "<memo_id>#<viewer_account_id>", so a second send of the same memorandum to
# the same address finds the same item - reinstating it if it was revoked -
# and never makes a second one.
#
# Revoking flips a flag. The item stays, because the audit of who was sent
# what, who opened it and who revoked it is the point of the record.
resource "aws_dynamodb_table" "share_grant" {
  name         = "${local.name_prefix}-share-grant"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "grant_id"

  attribute {
    name = "grant_id"
    type = "S"
  }

  attribute {
    name = "tenant_id"
    type = "N"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  attribute {
    name = "viewer_account_id"
    type = "S"
  }

  # The tenant's own list, newest first.
  global_secondary_index {
    name            = "tenant-index"
    hash_key        = "tenant_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  # Every grant one recipient holds, across tenants. Registering recomputes
  # each of them, and a registered viewer lists them.
  global_secondary_index {
    name            = "viewer-index"
    hash_key        = "viewer_account_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = { Name = "${local.name_prefix}-share-grant" }
}

# A recipient. Made the first time they open a link - not when the tenant
# sends, because sending is the tenant collecting an address and opening is
# the recipient arriving. The key is derived from the address (the first 32
# hex characters of sha256 of it, lower-cased), so a grant can name its
# recipient before the recipient exists.
resource "aws_dynamodb_table" "viewer_account" {
  name         = "${local.name_prefix}-viewer-account"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "viewer_account_id"

  attribute {
    name = "viewer_account_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = { Name = "${local.name_prefix}-viewer-account" }
}

# Every open and every download. Written by the viewer function invoking
# itself asynchronously, so the record costs the recipient no wait.
resource "aws_dynamodb_table" "share_access_log" {
  name         = "${local.name_prefix}-share-access-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "grant_id"
  range_key    = "occurred_at"

  attribute {
    name = "grant_id"
    type = "S"
  }

  attribute {
    name = "occurred_at"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  deletion_protection_enabled = true

  tags = { Name = "${local.name_prefix}-share-access-log" }
}

# Counters, one per tenant per period: "trial", "p<period end>" for a
# billing month, "d<date>" for the daily limit. An atomic ADD that returns the
# new count is what makes the allowance safe against two sends at nine of ten
# both going out free, which counting grants with a query would allow.
resource "aws_dynamodb_table" "share_usage" {
  name         = "${local.name_prefix}-share-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  range_key    = "period"

  attribute {
    name = "tenant_id"
    type = "N"
  }

  attribute {
    name = "period"
    type = "S"
  }

  tags = { Name = "${local.name_prefix}-share-usage" }
}

locals {
  share_tables = [
    aws_dynamodb_table.share_grant.arn,
    "${aws_dynamodb_table.share_grant.arn}/index/*",
    aws_dynamodb_table.viewer_account.arn,
    aws_dynamodb_table.share_access_log.arn,
    aws_dynamodb_table.share_usage.arn,
  ]

  # The SES configuration set attached by default to arqedia.com. Made in the
  # console on 14 September 2026 (CloudTrail: CreateConfigurationSet,
  # jperry-admin) and not managed here - read as a name rather than a
  # resource, so this stack cannot delete it. It has no event destinations:
  # nothing watches a bounce yet (CLAUDE.md, What is open, 10.6).
  ses_configuration_set = "my-first-configuration-set"

  share_env = {
    SHARE_GRANT_TABLE      = aws_dynamodb_table.share_grant.name
    VIEWER_ACCOUNT_TABLE   = aws_dynamodb_table.viewer_account.name
    SHARE_ACCESS_LOG_TABLE = aws_dynamodb_table.share_access_log.name
    SHARE_USAGE_TABLE      = aws_dynamodb_table.share_usage.name
  }
}

# --- the API's half --------------------------------------------------------
#
# Sending writes a grant and counts it; listing reads the tenant's index;
# revoking flips the flag. It reads a recipient's account to know whether they
# have registered, and never writes one - that is the viewer's.
#
# The share PDFs are written by the renderer, which already holds the curated
# bucket. The API deletes them only to undo a send whose charge was refused.
resource "aws_iam_role_policy" "api_share" {
  name = "${local.name_prefix}-api-share"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
        ]
        Resource = local.share_tables
      },
      {
        Effect   = "Allow"
        Action   = ["s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.data["curated"].arn}/shares/*"]
      },
      # share.purge_tenant lists a tenant's shares/ folder to delete it. Not
      # called yet (account deletion does not exist); scoped to the prefix so
      # the role cannot list anything else in the bucket.
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [aws_s3_bucket.data["curated"].arn]
        Condition = {
          StringLike = { "s3:prefix" = ["shares/*"] }
        }
      },
    ]
  })
}

# --- viewers who register --------------------------------------------------
#
# A pool of its own. A viewer is not a seat, carries no tenant, and must never
# be able to present a token the API's authorizer would accept - which one
# pool for both would allow the first time somebody forgot a claim check.
#
# ONLY REGISTERED VIEWERS ARE HERE. A recipient who has only opened the link
# is a viewer_account item and nothing in Cognito; the link token is what they
# hold. Registering - a password, multi-factor and our terms - is what makes a
# user in this pool.
#
# MFA IS ON, not optional (share_viewer_spec section 3; UX02 decision of
# 20 September reinstating it). The first sign-in after registering is the
# MFA_SETUP challenge.
resource "aws_cognito_user_pool" "viewer" {
  name                     = "${local.name_prefix}-viewers"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  # Same sender as the customer pool (auth.tf), for the same reasons. Nothing
  # in the share flow asks Cognito to send anything today: the share email is
  # ours (mail.share_invitation) and registration sets the password directly.
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = data.aws_ses_domain_identity.sender.arn
    from_email_address    = "ARQEDIA <${var.signup_sender}>"
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  # Nobody makes themselves a viewer. The viewer function makes the user when
  # somebody holding a valid link registers - the same one door the customer
  # pool has, for the same reason. Since fix/share-registration-takeover the
  # link is not enough: registering also takes a code emailed to the
  # recipient's own address, because a link can be forwarded.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  tags = { Name = "${local.name_prefix}-viewers" }

  # As auth.tf: a schema change has forced replacement in the provider since
  # 2018, and replacing this pool would destroy every registered viewer.
  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "viewer" {
  name         = "${local.name_prefix}-viewer-web"
  user_pool_id = aws_cognito_user_pool.viewer.id

  generate_secret = false

  # Sign-in runs through the viewer function (POST /viewer/sign-in), which is
  # why the admin flow. The browser never talks to this pool directly, so the
  # application keeps a single Amplify configuration - the customer pool's.
  explicit_auth_flows = [
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  read_attributes  = ["email"]
  write_attributes = []

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_apigatewayv2_authorizer" "viewer" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "viewer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.viewer.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.viewer.id}"
  }
}

# --- the viewer function ---------------------------------------------------

data "archive_file" "share_viewer" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/share_viewer"
  output_path = "${path.module}/build/share_viewer.zip"
}

resource "aws_iam_role" "share_viewer" {
  name = "${local.name_prefix}-share-viewer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name_prefix}-share-viewer" }
}

resource "aws_iam_role_policy_attachment" "share_viewer_logs" {
  role       = aws_iam_role.share_viewer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# NO rds-data, NO secretsmanager, NO wallet. Nothing a recipient does reaches
# Aurora, and this role is what guarantees it rather than a convention.
#
# COGNITO ADMIN ON THE VIEWER POOL ONLY. The second holder of Cognito
# administrative permissions in the system, beside the signup function, and
# each is scoped to its own pool (CLAUDE.md, One door).
data "aws_iam_policy_document" "share_viewer" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = local.share_tables
  }

  # The two PDFs the renderer made at send, and the downloads this function
  # stamps from them. Under shares/ and nowhere else in the bucket.
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.data["curated"].arn}/shares/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }

  # Named one by one. AdminCreateUser and AdminSetUserPassword register;
  # AdminGetUser refuses a second registration; AdminDeleteUser undoes one
  # whose MFA setup never finished; AdminInitiateAuth and
  # AdminRespondToAuthChallenge sign in, through the MFA challenge;
  # AdminSetUserMFAPreference records the authenticator once it is verified.
  statement {
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminSetUserPassword",
      "cognito-idp:AdminGetUser",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminInitiateAuth",
      "cognito-idp:AdminRespondToAuthChallenge",
      "cognito-idp:AdminSetUserMFAPreference",
    ]
    resources = [aws_cognito_user_pool.viewer.arn]
  }

  # The one-time code sent to a recipient's own address before they may
  # register (fix/share-registration-takeover).
  #
  # SCOPED IN THE POLICY, NOT ONLY IN THE CODE. The handler sends from SENDER
  # and nothing else; this makes that a rule IAM enforces as well. Two parts,
  # because SES authorises a send against the VERIFIED IDENTITY, and the one
  # verified here is the domain, arqedia.com - there is no identity for the
  # address itself. So:
  #   resource   the domain identity, the same one auth.tf reads, and
  #   condition  ses:FromAddress equal to the one sender, so no other address
  #              at the domain can be used either.
  # A resource naming only identity/no-reply@arqedia.com would match no
  # identity SES checks, and every send would be refused.
  #
  statement {
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = [data.aws_ses_domain_identity.sender.arn]

    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.signup_sender]
    }
  }

  # AND THE CONFIGURATION SET. arqedia.com carries a default configuration
  # set, and SES authorises a send against it as well as against the
  # identity. Without it every send was refused - the live failure of
  # 6 October: "not authorized to perform 'ses:SendEmail' on resource
  # ...configuration-set/my-first-configuration-set".
  #
  # A STATEMENT OF ITS OWN, WITHOUT THE FromAddress CONDITION, deliberately.
  # Whether SES evaluates ses:FromAddress when it checks a configuration set
  # could not be confirmed: IAM's policy simulator does not model this
  # resource for ses:SendEmail at all (it denies even Resource "*"). Left
  # unconditioned it grants nothing alone - every send still needs the
  # identity statement above, and that one is held to the one sender.
  statement {
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = ["arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:configuration-set/${local.ses_configuration_set}"]
  }
}

resource "aws_iam_role_policy" "share_viewer" {
  name   = "${local.name_prefix}-share-viewer"
  role   = aws_iam_role.share_viewer.id
  policy = data.aws_iam_policy_document.share_viewer.json
}

# The access log is written by this function invoking itself asynchronously.
# A policy of its own, because it names the function and the function names
# the role.
resource "aws_iam_role_policy" "share_viewer_self" {
  name = "${local.name_prefix}-share-viewer-self"
  role = aws_iam_role.share_viewer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.share_viewer.arn
    }]
  })
}

resource "aws_lambda_function" "share_viewer" {
  function_name    = "${local.name_prefix}-share-viewer"
  role             = aws_iam_role.share_viewer.arn
  handler          = "app.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.share_viewer.output_path
  source_code_hash = data.archive_file.share_viewer.output_base64sha256
  timeout          = 30
  memory_size      = 512

  # pypdf and reportlab stamp a download, and share_rules and stamp are the
  # shared modules. Rebuild the layer (build-layer.ps1) before applying.
  layers = [aws_lambda_layer_version.docprocessing.arn]

  environment {
    variables = merge(local.share_env, {
      CURATED_BUCKET   = aws_s3_bucket.data["curated"].id
      VIEWER_POOL_ID   = aws_cognito_user_pool.viewer.id
      VIEWER_CLIENT_ID = aws_cognito_user_pool_client.viewer.id
      # One sender for the whole product, declared in signup.tf.
      SENDER = var.signup_sender
    })
  }

  tags = { Name = "${local.name_prefix}-share-viewer" }
}

resource "aws_apigatewayv2_integration" "share_viewer" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.share_viewer.invoke_arn
  payload_format_version = "2.0"
}

# authorization_type NONE. The link token travels in the Authorization header
# as "Share <token>" and the function checks it against the grant on every
# request. Sign-in is here because a person signing in has no token yet.
resource "aws_apigatewayv2_route" "share_viewer_open" {
  for_each = toset([
    "GET /view/{grant_id}",
    "POST /view/{grant_id}/download",
    # Emails the recipient a code before they may register. The address is
    # the grant's, never one from the request.
    "POST /view/{grant_id}/register/code",
    "POST /view/{grant_id}/register",
    "POST /view/{grant_id}/register/confirm",
    "POST /viewer/sign-in",
    "POST /viewer/sign-in/mfa",
  ])

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.share_viewer.id}"
  authorization_type = "NONE"
}

# A registered viewer, signed in, without the link to hand. The viewer
# pool's authorizer - the customer pool's token is refused here at the
# gateway, and a viewer's is refused on every customer route.
resource "aws_apigatewayv2_route" "share_viewer_signed_in" {
  for_each = toset([
    "GET /viewer/shares",
    "GET /viewer/shares/{grant_id}",
    "POST /viewer/shares/{grant_id}/download",
  ])

  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.share_viewer.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.viewer.id
}

resource "aws_lambda_permission" "share_viewer_gateway" {
  statement_id  = "AllowAPIGatewayShareViewer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.share_viewer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

output "viewer_pool_id" {
  value = aws_cognito_user_pool.viewer.id
}

output "share_viewer_function" {
  value = aws_lambda_function.share_viewer.function_name
}
