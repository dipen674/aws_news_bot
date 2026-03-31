variable "aws_region" {
  description = "The AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "The AWS CLI profile to use"
  type        = string
  default     = "default"
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

variable "news_webhook_url" {
  description = "The Discord webhook URL for news notifications"
  type        = string
  sensitive   = true
}

variable "groq_api_key" {
  description = "The Groq API Key for AI summarization"
  type        = string
  sensitive   = true
}

variable "table_name" {
  description = "The name of the DynamoDB table"
  type        = string
  default     = "aws-news-tracker"
}



resource "aws_dynamodb_table" "news_tracker" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "article_id"
  attribute {
    name = "article_id"
    type = "S"
  }
}

resource "aws_sns_topic" "daily_briefing" {
  name = "aws-daily-briefing"
}

resource "aws_iam_role" "lambda_role" {
  name = "ai_curator_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "ai_curator_policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow",
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"],
        Resource = aws_dynamodb_table.news_tracker.arn
      },
      {
        Effect   = "Allow",
        Action   = "sns:Publish",
        Resource = aws_sns_topic.daily_briefing.arn
      }
    ]
  })
}

data "archive_file" "news_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/src/news_bot.py"
  output_path = "${path.module}/news_bot.zip"
}

resource "aws_lambda_function" "news_bot" {
  filename         = data.archive_file.news_lambda_zip.output_path
  function_name    = "aws-news-bot"
  role             = aws_iam_role.lambda_role.arn
  handler          = "news_bot.lambda_handler"
  runtime          = "python3.9"
  timeout          = 90
  source_code_hash = data.archive_file.news_lambda_zip.output_base64sha256
  environment {
    variables = {
      TABLE_NAME          = aws_dynamodb_table.news_tracker.name
      DISCORD_WEBHOOK_URL = var.news_webhook_url
      GROQ_API_KEY        = var.groq_api_key
    }
  }
}

# --- 5. EventBridge Scheduler for News ---
resource "aws_cloudwatch_event_rule" "morning_news_trigger" {
  name                = "morning-news-trigger"
  description         = "Daily news at 9:30 AM NPT"
  schedule_expression = "cron(45 3 * * ? *)"
}

resource "aws_cloudwatch_event_rule" "evening_news_trigger" {
  name                = "evening-news-trigger"
  description         = "Daily news at 7:00 PM NPT"
  schedule_expression = "cron(15 13 * * ? *)"
}

resource "aws_cloudwatch_event_target" "news_target_morning" {
  rule      = aws_cloudwatch_event_rule.morning_news_trigger.name
  target_id = "SendNewsToLambdaMorning"
  arn       = aws_lambda_function.news_bot.arn
}

resource "aws_cloudwatch_event_target" "news_target_evening" {
  rule      = aws_cloudwatch_event_rule.evening_news_trigger.name
  target_id = "SendNewsToLambdaEvening"
  arn       = aws_lambda_function.news_bot.arn
}

resource "aws_lambda_permission" "allow_eventbridge_news_morning" {
  statement_id  = "AllowExecutionFromEventBridgeNewsMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_news_trigger.arn
}

resource "aws_lambda_permission" "allow_eventbridge_news_evening" {
  statement_id  = "AllowExecutionFromEventBridgeNewsEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.evening_news_trigger.arn
}

# --- 6. The Knowledge Bot Lambda ---
data "archive_file" "knowledge_zip" {
  type        = "zip"
  source_file = "${path.module}/src/knowledge_bot.py"
  output_path = "${path.module}/knowledge_bot.zip"
}

variable "knowledge_webhook_url" {
  description = "The Discord webhook URL for the knowledge channel"
  type        = string
  sensitive   = true
}

resource "aws_lambda_function" "knowledge_bot" {
  filename         = data.archive_file.knowledge_zip.output_path
  function_name    = "aws-knowledge-bot"
  role             = aws_iam_role.lambda_role.arn # Reuse same role
  handler          = "knowledge_bot.lambda_handler"
  runtime          = "python3.9"
  timeout          = 90
  source_code_hash = data.archive_file.knowledge_zip.output_base64sha256
  environment {
    variables = {
      DISCORD_WEBHOOK_URL = var.knowledge_webhook_url
      GROQ_API_KEY        = var.groq_api_key
      TABLE_NAME          = aws_dynamodb_table.news_tracker.name
    }
  }
}

# --- 8. EventBridge Scheduler for Knowledge ---
resource "aws_cloudwatch_event_rule" "morning_knowledge" {
  name                = "morning-knowledge-trigger"
  description         = "Daily knowledge at 10:00 AM NPT"
  schedule_expression = "cron(15 4 * * ? *)"
}

resource "aws_cloudwatch_event_rule" "evening_knowledge" {
  name                = "evening-knowledge-trigger"
  description         = "Daily knowledge at 7:00 PM NPT"
  schedule_expression = "cron(15 13 * * ? *)"
}

resource "aws_cloudwatch_event_target" "knowledge_target_morning" {
  rule      = aws_cloudwatch_event_rule.morning_knowledge.name
  target_id = "SendKnowledgeToLambdaMorning"
  arn       = aws_lambda_function.knowledge_bot.arn
}

resource "aws_cloudwatch_event_target" "knowledge_target_evening" {
  rule      = aws_cloudwatch_event_rule.evening_knowledge.name
  target_id = "SendKnowledgeToLambdaEvening"
  arn       = aws_lambda_function.knowledge_bot.arn
}

resource "aws_lambda_permission" "allow_eventbridge_knowledge_morning" {
  statement_id  = "AllowExecutionFromEventBridgeKnowledgeMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.knowledge_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_knowledge.arn
}

resource "aws_lambda_permission" "allow_eventbridge_knowledge_evening" {
  statement_id  = "AllowExecutionFromEventBridgeKnowledgeEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.knowledge_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.evening_knowledge.arn
}

# --- 9. Weekly Highlight Trigger (Sundays at 7:45 PM NPT / 14:00 UTC) ---
resource "aws_cloudwatch_event_rule" "weekly_highlight" {
  name                = "weekly-highlight-trigger"
  description         = "Weekly AWS News Champion on Sundays"
  schedule_expression = "cron(0 14 ? * SUN *)"
}

resource "aws_cloudwatch_event_target" "news_target_weekly" {
  rule      = aws_cloudwatch_event_rule.weekly_highlight.name
  target_id = "SendWeeklyNewsHighlight"
  arn       = aws_lambda_function.news_bot.arn
  input     = jsonencode({"weekly": true})
}

resource "aws_lambda_permission" "allow_eventbridge_news_weekly" {
  statement_id  = "AllowExecutionFromEventBridgeNewsWeekly"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_highlight.arn
}
