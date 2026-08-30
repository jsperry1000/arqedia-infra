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

resource "aws_cognito_user_pool" "main" {
  name                     = "${local.name_prefix}-users"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]
  mfa_configuration        = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
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
