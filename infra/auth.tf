# ---------------------------------------------------------------------------
# Cognito: exactly one user, created by Terraform. Self-signup is off, TOTP
# MFA is mandatory, and the API Lambda additionally pins the allowed `sub`.
# ---------------------------------------------------------------------------
resource "aws_cognito_user_pool" "main" {
  name = local.name

  # No public sign-up path exists.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }

  mfa_configuration = "ON"
  software_token_mfa_configuration {
    enabled = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  deletion_protection = "ACTIVE"
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.main.id
  # managed_login_version defaults to 1 (classic hosted UI), which is free.
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name}-web"
  user_pool_id = aws_cognito_user_pool.main.id

  # Public SPA client: no secret, authorization code flow with PKCE only.
  generate_secret = false

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = concat([local.callback_url], var.extra_callback_urls)
  logout_urls = concat(
    ["${local.app_url}/"],
    [for url in var.extra_callback_urls : replace(url, "/callback", "/")],
  )

  # The hosted UI handles authentication; the SPA only exchanges and refreshes.
  explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]

  access_token_validity  = 60
  id_token_validity      = 60
  # Cognito's maximum (10 years): effectively never log in again.
  refresh_token_validity = 3650

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
}

# The single allowed user. The password is set out of band (see README) so it
# never enters Terraform state.
resource "aws_cognito_user" "owner" {
  user_pool_id = aws_cognito_user_pool.main.id
  username     = var.owner_email

  attributes = {
    email          = var.owner_email
    email_verified = true
  }

  message_action = "SUPPRESS"

  lifecycle {
    ignore_changes = [temporary_password, password]
  }
}
