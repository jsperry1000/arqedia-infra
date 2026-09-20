# ---------------------------------------------------------------------------
# Authentication. Cognito holds the users; each carries a tenant number and a
# role as custom attributes.
#
# tenant_id is mutable = false: the user cannot change it, and it is signed
# into every token they present. Every API function reads the tenant from the
# token and from nowhere else. That single rule is the whole isolation model -
# one function reading a tenant from a request parameter and the boundary is
# gone.
#
# role is mutable, because promoting a member to admin is a normal act, but it
# is excluded from the client's writable attributes so a user cannot promote
# themselves. Today every user is an admin and nothing is refused; the check
# is in place from the start so that Component 9's seat model can begin
# creating members without any rule being rewritten.
# ---------------------------------------------------------------------------

# The verified identity every message in the product goes out as. Verified
# outside Terraform, along with its DKIM records, and read here rather than
# managed: the domain is the account's, not this stack's, and a second stack
# must not be able to delete it.
data "aws_ses_domain_identity" "sender" {
  domain = local.root_domain
}

resource "aws_cognito_user_pool" "main" {
  name                     = "${local.name_prefix}-users"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  # The password reset code comes from us, not from Cognito (10.4).
  #
  # THE DEFAULT SENDER WAS NEVER MEANT FOR PRODUCTION. Cognito's own
  # documentation: "For typical production environments, the default email
  # limit is below the required delivery volume." It is 50 messages a day for
  # the whole AWS account, resetting at 0900 UTC and not adjustable, shared
  # with everything else the account sends through it. Our SES quota is
  # 50,000 a day.
  #
  # AND IT CAME FROM A DOMAIN NOBODY RECOGNISES. A reset code for ARQEDIA
  # arriving from no-reply@verificationemail.com is indistinguishable from
  # the phishing it looks like. It now comes from the same address as the
  # signup code.
  #
  # A BOUNCE BECOMES OURS. Under the default configuration a hard bounce puts
  # the address on an AWS-managed suppression list we cannot see or clear -
  # "An email address can remain on the AWS-managed suppression list
  # indefinitely." Under ours it is our list. Nothing watches it yet; that is
  # 10.6 and is not built here.
  #
  # The apply that first sets this creates a service-linked role, so the
  # session running it needs iam:CreateServiceLinkedRole.
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = data.aws_ses_domain_identity.sender.arn
    from_email_address    = "ARQEDIA <${var.signup_sender}>"
  }

  # What the password reset code says (10.4).
  #
  # THIS IS THE FORGOT-PASSWORD MESSAGE. Cognito's own table names the
  # verification message template as the one ForgotPassword and
  # AdminResetUserPassword use; {####} is the code. The signup code is our own
  # Lambda's text and is not affected by anything here.
  #
  # It names the hour because the reset card names the hour, and two places
  # stating a duration must agree. It says to ignore an unasked-for code
  # rather than to contact us, because that is true - nothing changes until
  # the code is used - and because there is no mailbox to contact.
  #
  # WRITTEN WITH \n RATHER THAN A HEREDOC, deliberately. A heredoc in a
  # checkout that writes CRLF puts \r\n into the message and makes this
  # resource plan as changed on every run, for ever.
  verification_message_template {
    # Code, not link. A link in an email asking about a password is the shape
    # of every phishing message there is.
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your ARQEDIA password reset code"
    email_message        = "Your ARQEDIA password reset code is {####}\n\nIt lasts one hour, and asking for another stops this one working.\n\nIf you did not ask to reset your password, ignore this - your password has not changed.\n\nARQEDIA\nThis address does not take replies."
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = true

    invite_message_template {
      email_subject = "Your ARQEDIA account"
      email_message = "Your ARQEDIA username is {username} and your temporary password is {####}. You will be asked to set a new password on first sign-in."
      sms_message   = "Username {username}, temporary password {####}"
    }
  }

  schema {
    name                     = "tenant_id"
    attribute_data_type      = "String"
    mutable                  = false
    developer_only_attribute = false
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 16
    }
  }

  schema {
    name                     = "role"
    attribute_data_type      = "String"
    mutable                  = true
    developer_only_attribute = false
    required                 = false

    string_attribute_constraints {
      min_length = 1
      max_length = 16
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

  tags = { Name = "${local.name_prefix}-users" }

  # The provider has treated a schema change as forcing replacement since
  # 2018, and reports remain open. Replacing this pool would destroy every
  # user and every password in it. A new custom attribute is therefore added
  # to the live pool first, with the AddCustomAttributes API, and the schema
  # here is brought into line afterwards - ignored so that no edit to it can
  # ever produce a destroy.
  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.main.id

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

  read_attributes = ["email", "name", "custom:tenant_id", "custom:role"]

  # Deliberately neither tenant_id nor role: a user may not move themselves
  # between tenants, nor promote themselves.
  write_attributes = ["name"]

  # Never say whether an address has an account.
  #
  # Created through the API rather than the console, this defaults to LEGACY -
  # so sign-in answered "User does not exist." for an unknown address and
  # "Incorrect username or password." for a known one with the wrong password,
  # which tells anybody who asks which firms are customers. ENABLED makes both
  # the same generic failure.
  #
  # It matters more from 10.1 onwards: "Forgotten your password?" takes an
  # address from anybody, signed out, and would otherwise be an enumeration
  # oracle that needs no password at all. With this set, Cognito's answer for
  # an unknown address alternates between a code-sent response naming a
  # simulated destination and an InvalidParameterException, and the sign-in
  # card treats both as the same sentence.
  prevent_user_existence_errors = "ENABLED"
}

# --- Users -----------------------------------------------------------------
# Two tenants: one firm on its own, one firm with two people sharing a
# workspace. Tests isolation between firms and collaboration within one.
#
# All three are admins. Until Component 9 there is no way to create a member,
# so nothing is refused - but the boundary is real rather than added later.

resource "aws_cognito_user" "testco_a" {
  user_pool_id = aws_cognito_user_pool.main.id
  username     = "sperry@vmac.com"

  attributes = {
    email              = "sperry@vmac.com"
    email_verified     = true
    name               = "S Perry"
    "custom:tenant_id" = "1"
    "custom:role"      = "admin"
  }

  # Attributes are set at creation and ignored thereafter. tenant_id is
  # immutable, and the provider reads it back without the custom: prefix - so
  # every plan would show a phantom change and every apply would fail against
  # Cognito refusing to update it. Moving a user between tenants means
  # deleting and recreating, which is the correct amount of friction.
  lifecycle {
    ignore_changes = [attributes]
  }
}

resource "aws_cognito_user" "testco_b_1" {
  user_pool_id = aws_cognito_user_pool.main.id
  username     = "joeschmoe1000@gmail.com"

  attributes = {
    email              = "joeschmoe1000@gmail.com"
    email_verified     = true
    name               = "Joe Schmoe"
    "custom:tenant_id" = "2"
    "custom:role"      = "admin"
  }

  lifecycle {
    ignore_changes = [attributes]
  }
}

resource "aws_cognito_user" "testco_b_2" {
  user_pool_id = aws_cognito_user_pool.main.id
  username     = "jonathanscottperry@gmail.com"

  attributes = {
    email              = "jonathanscottperry@gmail.com"
    email_verified     = true
    name               = "Jonathan Perry"
    "custom:tenant_id" = "2"
    "custom:role"      = "admin"
  }

  lifecycle {
    ignore_changes = [attributes]
  }
}

output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.web.id
}
