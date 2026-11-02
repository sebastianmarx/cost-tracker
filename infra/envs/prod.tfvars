project               = "cost-tracker"
aws_region            = "eu-central-1"
owner_email           = "sebastian.sm.marx@gmail.com"
domain_name           = "costtracker.marxai.de"
route53_zone_name     = "marxai.de"
cognito_domain_prefix = "costtracker-marx"
ses_domain            = "familiemarx.click"

extra_callback_urls = ["http://localhost:5173/callback"]
allowed_countries   = ["DE", "AT", "CH"]
log_retention_days  = 14
create_budget       = false
