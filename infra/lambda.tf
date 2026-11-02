# ---------------------------------------------------------------------------
# Two functions from one package: the API and the scraper. Each has its own
# role with only the permissions it needs.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${local.name}-scraper"
  retention_in_days = var.log_retention_days
}

# --- API ------------------------------------------------------------------
data "aws_iam_policy_document" "api" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:BatchWriteItem",
    ]
    resources = [aws_dynamodb_table.main.arn, "${aws_dynamodb_table.main.arn}/index/GSI1"]
  }

  statement {
    sid       = "InvokeScraper"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.scraper.arn]
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "api" {
  name   = "${local.name}-api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn
  runtime       = "python3.13"
  handler       = "app.api.handler.handler"
  architectures = ["arm64"] # ~20% cheaper per GB-second than x86_64

  filename         = local.lambda_zip
  source_code_hash = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null

  memory_size = 256
  timeout     = 29 # API Gateway cuts off at 30 s

  environment {
    variables = {
      TABLE_NAME                   = aws_dynamodb_table.main.name
      SCRAPER_FUNCTION_NAME        = aws_lambda_function.scraper.function_name
      OWNER_SUB                    = aws_cognito_user.owner.sub
      REFRESH_MIN_INTERVAL_SECONDS = tostring(var.refresh_min_interval_seconds)
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
}

# --- Scraper --------------------------------------------------------------
data "aws_iam_policy_document" "scraper" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.scraper.arn}:*"]
  }

  statement {
    sid = "Table"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [aws_dynamodb_table.main.arn, "${aws_dynamodb_table.main.arn}/index/GSI1"]
  }

  # Sending is limited to the verified domain identity and one From address.
  statement {
    sid       = "SendAlerts"
    actions   = ["ses:SendEmail"]
    resources = [local.ses_identity_arn]

    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [local.ses_from]
    }
  }
}

resource "aws_iam_role" "scraper" {
  name               = "${local.name}-scraper"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "scraper" {
  name   = "${local.name}-scraper"
  role   = aws_iam_role.scraper.id
  policy = data.aws_iam_policy_document.scraper.json
}

resource "aws_lambda_function" "scraper" {
  function_name = "${local.name}-scraper"
  role          = aws_iam_role.scraper.arn
  runtime       = "python3.13"
  handler       = "app.scraper.handler.handler"
  architectures = ["arm64"]

  filename         = local.lambda_zip
  source_code_hash = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null

  memory_size = 512
  timeout     = 900

  # Caps cost and the number of parallel requests hitting the shops.
  reserved_concurrent_executions = 2

  environment {
    variables = {
      TABLE_NAME                   = aws_dynamodb_table.main.name
      SES_FROM                     = "Cost Tracker <${local.ses_from}>"
      ALERT_TO                     = var.owner_email
      APP_URL                      = local.app_url
      REFRESH_MIN_INTERVAL_SECONDS = tostring(var.refresh_min_interval_seconds)
    }
  }

  depends_on = [aws_cloudwatch_log_group.scraper]
}

# Async invocations (refresh all, new links) must not be retried: a retry
# would hammer the shops and the rate limit would skip the links anyway.
resource "aws_lambda_function_event_invoke_config" "scraper" {
  function_name                = aws_lambda_function.scraper.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}
