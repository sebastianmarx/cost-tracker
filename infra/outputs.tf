output "app_url" {
  value = local.app_url
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.id
}

output "table_name" {
  value = aws_dynamodb_table.main.name
}

output "scraper_function_name" {
  value = aws_lambda_function.scraper.function_name
}

output "api_endpoint" {
  description = "Direct API Gateway URL (still requires a Cognito token)."
  value       = aws_apigatewayv2_api.main.api_endpoint
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "cognito_domain" {
  value = "https://${local.cognito_domain}"
}

output "owner_email" {
  value = var.owner_email
}
