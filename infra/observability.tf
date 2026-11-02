resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.owner_email
  # Confirm the subscription from the email AWS sends after the first apply.
}

# Unhandled crashes in either function. Shops blocking a request are not
# errors (they show up as a status badge in the UI).
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    api     = aws_lambda_function.api.function_name
    scraper = aws_lambda_function.scraper.function_name
  }

  alarm_name          = "${local.name}-${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 3600
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_description   = "The ${each.key} Lambda is throwing."
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = each.value
  }
}

resource "aws_budgets_budget" "monthly" {
  count = var.create_budget ? 1 : 0

  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$${var.project}"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.owner_email]
  }
}
