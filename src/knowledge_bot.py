import json
import os
import urllib.request
import re
import random
import time
from datetime import datetime
import boto3

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
AI_MODEL = "llama-3.3-70b-versatile"

def safe_request(url, data=None, headers=None, method='POST', timeout=30):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req_headers = headers or {}
            if 'User-Agent' not in req_headers:
                req_headers['User-Agent'] = 'AWS-Knowledge-Bot/1.0 (https://github.com/dipen674/aws_news_bot)'
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"Request failed (Attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait:.2f}s...")
            if attempt == max_retries - 1: raise
            time.sleep(wait)

# Massive AWS Services List
SERVICES = {
    # Core Infrastructure
    "EC2": "https://aws.amazon.com/ec2/", "Lambda": "https://aws.amazon.com/lambda/",
    "S3": "https://aws.amazon.com/s3/", "RDS": "https://aws.amazon.com/rds/",
    "DynamoDB": "https://aws.amazon.com/dynamodb/", "VPC": "https://aws.amazon.com/vpc/",
    "Route 53": "https://aws.amazon.com/route53/", "IAM": "https://aws.amazon.com/iam/",
    # Containers & Serverless
    "ECS": "https://aws.amazon.com/ecs/", "EKS": "https://aws.amazon.com/eks/",
    "Fargate": "https://aws.amazon.com/fargate/", "App Runner": "https://aws.amazon.com/apprunner/",
    # Data & Analytics
    "Athena": "https://aws.amazon.com/athena/", "Redshift": "https://aws.amazon.com/redshift/",
    "Glue": "https://aws.amazon.com/glue/", "Lake Formation": "https://aws.amazon.com/lake-formation/",
    "OpenSearch": "https://aws.amazon.com/opensearch-service/", "EMR": "https://aws.amazon.com/emr/",
    # AI & ML
    "SageMaker": "https://aws.amazon.com/sagemaker/", "Bedrock": "https://aws.amazon.com/bedrock/",
    "Forecast": "https://aws.amazon.com/forecast/", "Personalize": "https://aws.amazon.com/personalize/",
    "Kendra": "https://aws.amazon.com/kendra/", "Rekognition": "https://aws.amazon.com/rekognition/",
    # Specialized & Niche
    "Ground Station": "https://aws.amazon.com/ground-station/", "Braket": "https://aws.amazon.com/braket/",
    "Nimble Studio": "https://aws.amazon.com/nimble-studio/", "RoboMaker": "https://aws.amazon.com/robomaker/",
    "AppStream 2.0": "https://aws.amazon.com/appstream2/", "WorkSpaces": "https://aws.amazon.com/workspaces/",
    "Mainframe Modernization": "https://aws.amazon.com/mainframe-modernization/",
    # Security & Resilience
    "WAF": "https://aws.amazon.com/waf/", "KMS": "https://aws.amazon.com/kms/",
    "Shield": "https://aws.amazon.com/shield/", "FIS": "https://aws.amazon.com/fault-injection-service/",
    # Integration & Management
    "SQS": "https://aws.amazon.com/sqs/", "SNS": "https://aws.amazon.com/sns/",
    "EventBridge": "https://aws.amazon.com/eventbridge/", "AppConfig": "https://aws.amazon.com/systems-manager/features/appconfig/",
    "CloudFormation": "https://aws.amazon.com/cloudformation/", "CloudWatch": "https://aws.amazon.com/cloudwatch/"
}

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME', 'aws-news-tracker')

def lambda_handler(event, context):
    table = dynamodb.Table(TABLE_NAME)
    service = event.get('service')
    
    if not service:
        all_services = list(SERVICES.keys())
        random.shuffle(all_services)
        service = all_services[0]
        for s in all_services:
            dup = table.get_item(Key={'article_id': f"KB_{s}"})
            if 'Item' not in dup:
                service = s
                break
    
    for s in SERVICES.keys():
        if s.lower() == service.lower():
            service = s
            break

    url = SERVICES.get(service)
    if not url: return {'statusCode': 404, 'body': json.dumps("Service not found")}

    try:
        print(f"Generating Precise Masterclass for {service}...")
        is_repeat = table.get_item(Key={'article_id': f"KB_{service}"}).get('Item') is not None
        ai_data = query_groq_direct(service, is_repeat)
        if not ai_data: raise Exception("Groq failure")
        
        send_to_discord(service, url, ai_data)
        
        table.put_item(Item={
            'article_id': f"KB_{service}", 
            'processed_at': str(datetime.now()), 
            'title': f"Knowledge: {service}",
            'repeat_count': (table.get_item(Key={'article_id': f"KB_{service}"}).get('Item', {}).get('repeat_count', 0) + 1) if is_repeat else 1
        })
        
        return {'statusCode': 200, 'body': json.dumps(f"Posted {service}")}
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return {'statusCode': 500, 'body': json.dumps(str(e))}

def query_groq_direct(service_name, is_repeat=False):
    extra_instruction = "This is a repeated topic, so focus on a specific advanced architectural pattern or edge case." if is_repeat else ""
    prompt = f"""You are an Enterprise AWS Solutions Architect. Explain AWS {service_name} in a highly professional, technically precise manner for senior engineers. {extra_instruction}

STRICT CONSTRAINTS:
- ABSOLUTELY NO analogies, metaphors, or playful language (e.g., do NOT say "it's like a map" or "it's a hero").
- Use strict networking, system design, and cloud engineering terminology.
- Max 2 lines for the description.
- 3 short, highly technical bullet points for features.
- 1 'Architect's Secret' (a high-value, obscure technical tip or pitfall).

Respond ONLY with valid JSON (no markdown):
{{
  "description": "Core technical function of the service (Max 150 chars).",
  "features": ["Technical capability 1", "Technical capability 2", "Technical capability 3"],
  "architect_secret": "A highly technical, real-world limitation or pattern.",
  "comparison": "1-sentence strict technical contrast with Azure/GCP equivalent."
}}"""

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are an Enterprise Cloud Architect. Respond ONLY in valid JSON with a strictly technical, professional tone. DO NOT use layman analogies."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2, "max_tokens": 600
    }
    
    try:
        raw = safe_request("https://api.groq.com/openai/v1/chat/completions",
                          data=json.dumps(payload).encode('utf-8'),
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json", "User-Agent": "AWS-Architect-Bot/1.0"})
        result = json.loads(raw)
        content = result['choices'][0]['message']['content'].strip()
        if '```' in content:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match: content = match.group(1)
        return json.loads(content)
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

def send_to_discord(service_name, url, ai_data):
    fields = []
    if ai_data.get('features'):
        feature_text = "\n".join([f"• {f}" for f in ai_data['features'][:3]])
        if feature_text.strip():
            fields.append({"name": "🛠️ Key Features", "value": feature_text[:1024], "inline": True})
    if ai_data.get('architect_secret') and str(ai_data['architect_secret']).strip():
        fields.append({"name": "💡 Architect's Secret", "value": str(ai_data['architect_secret'])[:1024], "inline": False})
    if ai_data.get('comparison') and str(ai_data['comparison']).strip():
        fields.append({"name": "⚖️ Cloud Rivalry", "value": str(ai_data['comparison'])[:1024], "inline": False})

    description = (ai_data.get('description') or 'Exciting AWS service!')[:2048]

    payload = {
        "username": "AWS Architecture Guide",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2855/2855011.png",
        "embeds": [{
            "title": f"📐 Enterprise Architecture: {service_name}",
            "description": f"{description}\n\n[📖 Official Documentation]({url})",
            "url": url, "color": 3447003, "fields": fields,
            "footer": {"text": "Senior Technical Reference • AWS Ecosystem"}
        }]
    }
    try:
        safe_request(DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        print(f"Discord post SUCCESS: {service_name}")
    except Exception as e:
        print(f"Discord send FAILED for '{service_name}': {e}")
        raise
