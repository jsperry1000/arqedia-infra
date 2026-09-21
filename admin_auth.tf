# admin_auth.tf
#
# The staff directory. ARQEDIA's own people sign in here; a customer never
# does, and a staff member is not a user of any tenant.
#
# A SECOND POOL, NOT A ROLE IN THE FIRST. Group 16 decided the staff console
# shares nothing with the customer path except the database. One pool holding
# both would mean a single token audience covering a tenant's own screens and
# a cross-tenant one, and one mistake in a claim check would be the whole
# isolation model. Two pools cannot be confused: a customer's token is issued
# by a pool the admin API does not trust, and the reverse.
#
# NO custom:tenant_id, DELIBERATELY. auth.tf signs a tenant number into every
# token and every API function reads the tenant from there and nowhere else.
# A staff member belongs to no tenant, so there is no number to sign, and an
# empty one would be a value some future reader could mistake for tenant 0 -
# which is the catalogue every tenant forks from. The admin API's authority
# comes from its own IAM role, read-only and cross-tenant, not from a claim.
#
# NO SEED USERS. auth.tf creates three by hand because dev needed somebody to
# sign in as before signup existed. A staff account is created deliberately,
# by a person, and is not something an apply from any branch can conjure.

resource "aws_cognito_user_pool" "staff" {
  name = "${local.name_prefix}-staff"

  # Essentials carries TOTP multi-factor; Lite does not. Plus adds adaptive
  # authentication and compromised-credential detection, which is a decision
  # about money and nobody has asked for it.
  user_pool_tier = "ESSENTIALS"

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  # REQUIRED, not offered. The customer pool is OPTIONAL because a firm
  # chooses its own posture; this pool reads every tenant's data, so the
  # second factor is not a preference. TOTP only: no SMS configuration
  # exists on this stack, and an authenticator app needs no carrier.
  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  # The same verified sender as everything else the product sends. One
  # address, verified once, outside Terraform - see auth.tf.
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = data.aws_ses_domain_identity.sender.arn
    from_email_address    = "ARQEDIA <${var.signup_sender}>"
  }

  # The password reset code. Written with \n rather than a heredoc, for the
  # reason auth.tf gives: a heredoc in a checkout that writes CRLF makes this
  # resource plan as changed on every run, for ever.
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your ARQEDIA staff password reset code"
    email_message        = "Your ARQEDIA staff password reset code is {####}\n\nIt lasts one hour, and asking for another stops this one working.\n\nIf you did not ask to reset your password, ignore this - your password has not changed - and tell the team.\n\nARQEDIA\nThis address does not take replies."
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  # Admin-create-only, as the customer pool is. There is no signup route to
  # this pool at all: nothing in the stack holds admin permissions on it, so
  # an account is made by a person at the console or the CLI.
  admin_create_user_config {
    allow_admin_create_user_only = true

    invite_message_template {
      email_subject = "Your ARQEDIA staff account"
      email_message = "Your ARQEDIA staff username is {username} and your temporary password is {####}. You will be asked to set a new password and register an authenticator app on first sign-in."
      sms_message   = "Username {username}, temporary password {####}"
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    mutable             = true
    required            = true

    string_attribute_constraints {
      min_length = 1
      max_length = 128
    }
  }

  tags = { Name = "${local.name_prefix}-staff" }

  # From the first line, before anything is in it. auth.tf earned this the
  # hard way: a custom attribute is added to the live pool with the
  # AddCustomAttributes API and the schema here brought into line afterwards,
  # ignored so that no edit to it can produce a destroy. Starting with the
  # lifecycle block means this pool never has a window in which an edit to
  # schema could take its users with it.
  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "admin" {
  name         = "${local.name_prefix}-admin"
  user_pool_id = aws_cognito_user_pool.staff.id

  generate_secret = false # a browser cannot keep a secret

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
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

  read_attributes  = ["email", "name"]
  write_attributes = ["name"]

  # Never say whether an address has an account. It matters more here than on
  # the customer pool: the addresses in this one are a list of the people who
  # can read every tenant's data.
  prevent_user_existence_errors = "ENABLED"
}

output "staff_user_pool_id" {
  value = aws_cognito_user_pool.staff.id
}

output "staff_user_pool_client_id" {
  value = aws_cognito_user_pool_client.admin.id
}
