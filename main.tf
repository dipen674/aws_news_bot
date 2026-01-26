provider "aws" {
  region = "us-east-1"
}

# --- Variables ---
variable "news_webhook_url" {
  description = "The Discord webhook URL for news notifications"
  type        = string
  sensitive   = true
}

variable "gemini_api_key" {
  description = "The Google Gemini API Key for AI summarization"
  type        = string
  sensitive   = true
}
# --- 1. DynamoDB for Deduplication ---
resource "aws_dynamodb_table" "news_tracker" {
  name         = "aws-news-tracker"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "article_id"
  attribute {
    name = "article_id"
    type = "S"
  }
}
# --- 2. SNS Topic (Optional/Cleanup) ---
resource "aws_sns_topic" "daily_briefing" {
  name = "aws-daily-briefing"
}
# --- 3. IAM Role & Permissions ---
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
# --- 4. News Bot Lambda Function ---
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
      GEMINI_API_KEY      = var.gemini_api_key
    }
  }
}
# --- 5. EventBridge Scheduler for News (Runs daily at 9:30 AM UTC) ---
resource "aws_cloudwatch_event_rule" "daily_news_trigger" {
  name                = "daily-news-trigger"
  schedule_expression = "cron(30 9 * * ? *)"
}

resource "aws_cloudwatch_event_target" "news_target" {
  rule      = aws_cloudwatch_event_rule.daily_news_trigger.name
  target_id = "SendNewsToLambda"
  arn       = aws_lambda_function.news_bot.arn
}

resource "aws_lambda_permission" "allow_eventbridge_news" {
  statement_id  = "AllowExecutionFromEventBridgeNews"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_news_trigger.arn
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
      GEMINI_API_KEY      = var.gemini_api_key
    }
  }
}

# --- 7. Instant Trigger for Knowledge Bot (For Testing) ---


# --- 8. EventBridge Scheduler for Knowledge (Twice Daily: 10 AM & 7 PM UTC) ---
resource "aws_cloudwatch_event_rule" "daily_knowledge" {
  name                = "daily-knowledge-trigger"
  schedule_expression = "cron(0 10,19 * * ? *)"
}

resource "aws_cloudwatch_event_target" "knowledge_target" {
  rule      = aws_cloudwatch_event_rule.daily_knowledge.name
  target_id = "SendKnowledgeToLambda"
  arn       = aws_lambda_function.knowledge_bot.arn
}

resource "aws_lambda_permission" "allow_eventbridge_knowledge" {
  statement_id  = "AllowExecutionFromEventBridgeKnowledge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.knowledge_bot.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_knowledge.arn
}


