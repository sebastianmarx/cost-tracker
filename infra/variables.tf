variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "cost-tracker"
}

variable "aws_region" {
  description = "Primary region."
  type        = string
  default     = "eu-central-1"
}

variable "owner_email" {
  description = "Email of the single user allowed to use the app. Also receives price alerts and alarms."
  type        = string
}

variable "domain_name" {
  description = "Fully qualified domain the app is served from."
  type        = string
  default     = "costtracker.marxai.de"
}

variable "route53_zone_name" {
  description = "Existing public hosted zone that contains domain_name."
  type        = string
  default     = "marxai.de"
}

variable "cognito_domain_prefix" {
  description = "Globally unique prefix for the Cognito hosted-UI domain."
  type        = string
  default     = "costtracker-marx"
}

variable "ses_domain" {
  description = "Already verified SES domain identity used as the sender domain."
  type        = string
  default     = "familiemarx.click"
}

variable "ses_from_local_part" {
  description = "Local part of the sender address (<local>@ses_domain)."
  type        = string
  default     = "costtracker"
}

variable "extra_callback_urls" {
  description = "Additional OAuth callback URLs, e.g. http://localhost:5173/callback for local development."
  type        = list(string)
  default     = []
}

variable "schedule_expression" {
  description = "When the scraper runs (EventBridge Scheduler cron, in schedule_timezone)."
  type        = string
  default     = "cron(0 6,18 * * ? *)"
}

variable "schedule_timezone" {
  type    = string
  default = "Europe/Berlin"
}

variable "refresh_min_interval_seconds" {
  description = "Minimum time between two manual refreshes of the same link."
  type        = number
  default     = 300
}

variable "allowed_countries" {
  description = "ISO country codes allowed to reach CloudFront. Empty list disables geo restriction."
  type        = list(string)
  default     = ["DE", "AT", "CH"]
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "create_budget" {
  description = "A project budget. The account already has more than the two free budgets, so each extra one costs ~0.60 USD/month."
  type        = bool
  default     = false
}

variable "budget_limit_usd" {
  type    = number
  default = 3
}
