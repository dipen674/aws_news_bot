import json
import os
import urllib.request
import re
import random
from datetime import datetime

DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
AI_MODEL = "llama-3.3-70b-versatile"

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
    # Integration & Messaging
    "SQS": "https://aws.amazon.com/sqs/", "SNS": "https://aws.amazon.com/sns/",
    "EventBridge": "https://aws.amazon.com/eventbridge/", "Step Functions": "https://aws.amazon.com/step-functions/",
    # Networking & Content Delivery
    "CloudFront": "https://aws.amazon.com/cloudfront/", "API Gateway": "https://aws.amazon.com/api-gateway/",
    "App Mesh": "https://aws.amazon.com/app-mesh/", "Global Accelerator": "https://aws.amazon.com/global-accelerator/",
    # Security
    "WAF": "https://aws.amazon.com/waf/", "KMS": "https://aws.amazon.com/kms/",
    "Secrets Manager": "https://aws.amazon.com/secrets-manager/", "Security Hub": "https://aws.amazon.com/security-hub/",
    "Macie": "https://aws.amazon.com/macie/", "Inspector": "https://aws.amazon.com/inspector/",
    # Developer Tools
    "CloudFormation": "https://aws.amazon.com/cloudformation/", "CloudWatch": "https://aws.amazon.com/cloudwatch/",
    "CloudShell": "https://aws.amazon.com/cloudshell/", "Proton": "https://aws.amazon.com/proton/",
    # Specialized
    "Connect": "https://aws.amazon.com/connect/", "Chime": "https://aws.amazon.com/chime/",
    "Braket": "https://aws.amazon.com/braket/", "Marketplace": "https://aws.amazon.com/marketplace/"
}

import boto3

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('TABLE_NAME', 'aws-news-tracker')

def lambda_handler(event, context):
    table = dynamodb.Table(TABLE_NAME)
    
    # 1. Check if user asked for a specific service manually
    service = event.get('service')
    
    if not service:
        # 2. "Variety Shield": Try to pick a service we haven't shown recently
        all_services = list(SERVICES.keys())
        random.shuffle(all_services)
        
        service = all_services[0] # Default
        for s in all_services:
            # Check if this service was 'recently' posted
            # (article_id for knowledge items starts with 'KB_')
            dup = table.get_item(Key={'article_id': f"KB_{s}"})
            if 'Item' not in dup:
                service = s
                break
    
    # Standardize casing
    for s in SERVICES.keys():
        if s.lower() == service.lower():
            service = s
            break

    url = SERVICES.get(service)
    if not url: return {'statusCode': 404, 'body': json.dumps("Service not found")}

    try:
        print(f"Generating Catchy Masterclass for {service}...")
        ai_data = query_groq_direct(service)
        if not ai_data: raise Exception("Groq failure")
        
        send_to_discord(service, url, ai_data)
        
        # 3. Mark as 'Seen' in the tracker
        table.put_item(Item={
            'article_id': f"KB_{service}", 
            'processed_at': str(datetime.now()), 
            'title': f"Knowledge: {service}"
        })
        
        return {'statusCode': 200, 'body': json.dumps(f"Posted {service}")}
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return {'statusCode': 500, 'body': json.dumps(str(e))}

def query_groq_direct(service_name):
    prompt = f"""You are a legendary Technical Bard who LOVES simplifying things.
Tell the EPIC and FUNNY story of AWS {service_name} using VERY SIMPLE everyday English.

RULES:
- Use ULTRASIMPLE English (no complex words, no corporate speak).
- 1-2 SHORT sentences max per part.
- Prefix every list item with ONLY "1.", "2.", or "3.".
- Be funny and slightly dramatic, like a campfire story.
- Technical Detail: Still mention the specific service mechanics but in plain English.
- Rival Kingdoms: Name Azure [Service] and GCP [Service] as rival characters.

Respond ONLY with valid JSON (no markdown):
{{
  "description": "The Origin Story (Simple English version): Why this hero was born and what it does. (Max 3 lines)",
  "features": ["1. [Simple Technical Superpower]", "2. [Simple Technical Superpower]", "3. [Simple Technical Superpower]"],
  "devops_crucials": ["1. [Funny but critical simple advice]", "2. [Advice]", "3. [Advice]"],
  "use_cases": ["1. [A small funny story-based example]", "2. [Example]", "3. [Example]"],
  "comparison": "The Rivalry Saga (Simple English): A witty technical battle between {service_name} and its Azure/GCP rivals. Name the services."
}}"""

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a fun mentor who simplifies cloud. ONLY JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }
    
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json", "User-Agent": "AWS-Architect-Bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=40) as response:
            result = json.loads(response.read().decode('utf-8'))
            raw = result['choices'][0]['message']['content'].strip()
            if '```' in raw:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
                if match: raw = match.group(1)
            return json.loads(raw)
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

def send_to_discord(service_name, url, ai_data):
    fields = []
    if ai_data.get('features'):
        fields.append({"name": "\n\n🛠️  The Superpowers", "value": "\n\n".join([f"✅ {f}" for f in ai_data['features'][:5]])[:1024], "inline": False})
    
    if ai_data.get('use_cases'):
        fields.append({"name": "\n\n🏗️  Where to use it?", "value": "\n\n".join([f"🚀 {u}" for u in ai_data['use_cases'][:4]])[:1024], "inline": False})

    if ai_data.get('devops_crucials'):
        crucials = ai_data['devops_crucials']
        text = "\n\n".join([f"🔹 {c}" for c in crucials]) if isinstance(crucials, list) else str(crucials)
        fields.append({"name": "\n\n⚡  Mentor 'Secret' Tips", "value": text[:1024], "inline": False})
        
    if ai_data.get('comparison'):
        fields.append({"name": "\n\n⚖️  The Rival Roundup", "value": f"\n{ai_data['comparison']}"[:1024], "inline": False})

    payload = {
        "username": "AWS Mentor AI",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2855/2855011.png",
        "embeds": [{
            "title": f"🎓 Senior Master Class: {service_name}",
            "description": f"{ai_data.get('description', 'Exciting AWS service!')}\n\n[📖 Read The Full Manual]({url})",
            "url": url,
            "color": 3447003,
            "fields": fields,
            "footer": {"text": f"Making Cloud Simple • {datetime.utcnow().strftime('%Y-%m-%d')}"}
        }]
    }
    
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'AWS-Bot/1.0'})
    with urllib.request.urlopen(req, timeout=10) as response:
        print(f"Discord: {response.getcode()}")
