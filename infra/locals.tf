data "aws_caller_identity" "current" {}

locals {
  name       = var.project
  account_id = data.aws_caller_identity.current.account_id

  site_bucket_name = "${var.project}-site-${local.account_id}"
  table_name       = var.project

  app_url        = "https://${var.domain_name}"
  callback_url   = "https://${var.domain_name}/callback"
  cognito_domain = "${var.cognito_domain_prefix}.auth.${var.aws_region}.amazoncognito.com"

  ses_from         = "${var.ses_from_local_part}@${var.ses_domain}"
  ses_identity_arn = "arn:aws:ses:${var.aws_region}:${local.account_id}:identity/${var.ses_domain}"

  lambda_zip = "${path.module}/../backend/build/lambda.zip"
}
