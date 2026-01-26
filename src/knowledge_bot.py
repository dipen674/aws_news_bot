import json
import os
import urllib.request
import re
import html as html_lib
import random
from datetime import datetime

# --- Configuration ---
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Massive AWS Services List
SERVICES = {
    "EC2": "https://aws.amazon.com/ec2/",
    "Lambda": "https://aws.amazon.com/lambda/",
    "S3": "https://aws.amazon.com/s3/",
    "RDS": "https://aws.amazon.com/rds/",
    "DynamoDB": "https://aws.amazon.com/dynamodb/",
    "API Gateway": "https://aws.amazon.com/api-gateway/",
    "VPC": "https://aws.amazon.com/vpc/",
    "CloudFront": "https://aws.amazon.com/cloudfront/",
    "IAM": "https://aws.amazon.com/iam/",
    "CloudWatch": "https://aws.amazon.com/cloudwatch/",
    "ECS": "https://aws.amazon.com/ecs/",
    "EKS": "https://aws.amazon.com/eks/",
    "Route 53": "https://aws.amazon.com/route53/",
    "SNS": "https://aws.amazon.com/sns/",
    "SQS": "https://aws.amazon.com/sqs/",
    "CloudFormation": "https://aws.amazon.com/cloudformation/",
    "Elastic Beanstalk": "https://aws.amazon.com/elasticbeanstalk/",
    "Step Functions": "https://aws.amazon.com/step-functions/",
    "Kinesis": "https://aws.amazon.com/kinesis/",
    "Athena": "https://aws.amazon.com/athena/",
    "Glue": "https://aws.amazon.com/glue/",
    "Redshift": "https://aws.amazon.com/redshift/",
    "Aurora": "https://aws.amazon.com/rds/aurora/",
    "SageMaker": "https://aws.amazon.com/sagemaker/",
    "Bedrock": "https://aws.amazon.com/bedrock/",
    "Cognito": "https://aws.amazon.com/cognito/",
    "Secrets Manager": "https://aws.amazon.com/secrets-manager/",
    "KMS": "https://aws.amazon.com/kms/",
    "WAF": "https://aws.amazon.com/waf/",
    "CloudTrail": "https://aws.amazon.com/cloudtrail/",
    "Config": "https://aws.amazon.com/config/",
    "Systems Manager": "https://aws.amazon.com/systems-manager/",
    "EventBridge": "https://aws.amazon.com/eventbridge/",
    "Amplify": "https://aws.amazon.com/amplify/",
    "AppSync": "https://aws.amazon.com/appsync/",
    "Direct Connect": "https://aws.amazon.com/directconnect/",
    "Global Accelerator": "https://aws.amazon.com/global-accelerator/",
    "Backup": "https://aws.amazon.com/backup/",
    "DataSync": "https://aws.amazon.com/datasync/",
    "Snowball": "https://aws.amazon.com/snowball/",
    "Inspector": "https://aws.amazon.com/inspector/",
    "GuardDuty": "https://aws.amazon.com/guardduty/",
    "Macie": "https://aws.amazon.com/macie/",
    "Security Hub": "https://aws.amazon.com/security-hub/",
    "EFS": "https://aws.amazon.com/efs/",
    "FSx": "https://aws.amazon.com/fsx/",
    "QuickSight": "https://aws.amazon.com/quicksight/",
    "EMR": "https://aws.amazon.com/emr/",
    "OpenSearch": "https://aws.amazon.com/opensearch-service/",
    "MSK": "https://aws.amazon.com/msk/",
    "Neptune": "https://aws.amazon.com/neptune/",
    "DocumentDB": "https://aws.amazon.com/documentdb/",
    "QLDB": "https://aws.amazon.com/qldb/",
    "IoT Core": "https://aws.amazon.com/iot-core/",
    "Cost Explorer": "https://aws.amazon.com/aws-cost-management/aws-cost-explorer/"
}

def lambda_handler(event, context):
    print("Starting AI-Powered Knowledge Bot...")
    
    # 1. Select a Service
    target_service = event.get('service')
    available_services = list(SERVICES.keys())
    
    if not target_service:
        target_service = random.choice(available_services)
        print(f"Selected random service: {target_service}")
    else:
        # Case insensitive lookup
        for s in available_services:
            if s.lower() == target_service.lower():
                target_service = s
                break

    url = SERVICES.get(target_service)
    if not url:
        return {'statusCode': 404, 'body': json.dumps("Service not found")}

    print(f"Scraping: {url}")

    # 2. Scrape and Clean HTML
    try:
        html_content = fetch_html(url)
        clean_text_content = clean_html_to_text(html_content)
    except Exception as e:
        print(f"Scraping Error: {e}")
        return {'statusCode': 500, 'body': json.dumps("Failed to scrape")}

    # 3. Get AI Analysis from Gemini
    try:
        ai_data = query_gemini(target_service, clean_text_content)
    except Exception as e:
        error_msg = str(e)
        print(f"Gemini AI Error: {error_msg}")
        # Fallback to a basic card but include the ERROR MESSAGE so the user can see it
        ai_data = {
            "description": f"❌ **AI Synthesis Error**: {error_msg}\n\nPlease check the official documentation for now.",
            "features": ["Error occurred during AI generation"],
            "use_cases": ["Check Lambda logs for full trace"],
            "comparison": f"Technical Details: {error_msg[:100]}"
        }

    # 4. Send to Discord
    send_knowledge_card(target_service, url, ai_data)

    return {
        'statusCode': 200,
        'body': json.dumps(f"AI Knowledge posted for {target_service}")
    }

def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode('utf-8', errors='ignore')

def clean_html_to_text(html_content):
    """Strip HTML tags and boilerplate to save tokens"""
    # Remove scripts and styles
    text = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    # Remove all other tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean up whitespace and entities
    text = html_lib.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:20000] # Limit to 20k chars to stay safe on context limits

def query_gemini(service_name, content):
    """Calls Gemini Pro API with safety settings and retry logic"""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise ValueError("Gemini API Key is missing or not configured.")

    prompt = f"""
    You are a Senior DevOps & Cloud Infrastructure Architect with 15 years of experience. 
    Analyze the following AWS {service_name} documentation and provide a punchy, "eye-catchy" masterclass summary.
    
    GUIDELINES:
    - Use SIMPLE, NO-NONSENSE language (no corporate jargon).
    - Summarize the intro into 3-4 short, high-impact bullet points or short paragraphs.
    - Focus on what a DEVOPS ENGINEER actually needs to know (scaling, security, reliability, infra-as-code).
    - Provide 3 real-world, practical use cases.
    - For the comparison, be blunt: When is it a win? When is it a mistake?
    
    RESPONSE FORMAT (STRICT JSON ONLY):
    {{
        "description": "Short, punchy 1-2 sentence overview followed by 3 bold 'Why it matters' points.",
        "features": ["DevOps Feature 1: Why it's cool", "DevOps Feature 2: Why it's cool", "..."],
        "devops_crucials": "The 3 most important technical 'gotchas' or settings every engineer must know about this service.",
        "use_cases": ["Practical Scenario 1", "Practical Scenario 2", "..."],
        "comparison": "Blunt comparison: AWS vs Azure/GCP alternatives + the 'Winner' for specific needs."
    }}
    
    CONTENT TO ANALYZE:
    {content[:15000]}
    """

    # In 2026, we use gemini-2.5-flash as the standard stable model
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }
    
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(
                api_url, 
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = response.read().decode('utf-8')
                result = json.loads(res_body)
                
                if 'candidates' not in result or not result['candidates']:
                    # Check for safety refuse
                    if 'promptFeedback' in result:
                        print(f"Gemini Safety Block: {result['promptFeedback']}")
                    raise Exception("No AI candidates returned")

                candidate = result['candidates'][0]
                if 'content' not in candidate or 'parts' not in candidate['content']:
                    # Likely blocked mid-generation
                    print(f"Candidate blocked/empty: {candidate.get('finishReason')}")
                    raise Exception(f"AI blocked generation: {candidate.get('finishReason')}")

                raw_ai_text = candidate['content']['parts'][0]['text']
                
                # Robust JSON extraction
                json_text = raw_ai_text.strip()
                if json_text.startswith("```"):
                    json_text = re.sub(r'^```(?:json)?\n?|\n?```$', '', json_text, flags=re.MULTILINE)
                
                return json.loads(json_text)
                
        except Exception as e:
            print(f"Gemini Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries:
                import time
                time.sleep(2) # Backoff
            else:
                raise

def send_knowledge_card(service_name, url, ai_data):
    embed_fields = []
    
    # 🔑 Masterclass Features
    if ai_data.get('features'):
        features = "\n".join([f"✅ {f}" for f in ai_data['features'][:5]])
        embed_fields.append({"name": "�️ Expert Feature Breakdown", "value": features[:1024], "inline": False})
    
    # 💼 Practical Use Cases
    if ai_data.get('use_cases'):
        use_cases = "\n".join([f"🚀 {u}" for u in ai_data['use_cases'][:4]])
        embed_fields.append({"name": "🎯 Real-World Scenarios", "value": use_cases[:1024], "inline": False})

    # 💡 DevOps Crucials (FIXED FORMATTING)
    if ai_data.get('devops_crucials'):
        crucials = ai_data['devops_crucials']
        # If AI returned a list, format it with bullets
        if isinstance(crucials, list):
            crucials_text = "\n".join([f"🔸 {c}" for c in crucials])
        else:
            crucials_text = str(crucials)
            
        embed_fields.append({
            "name": "⚡ DevOps Pro-Tips (The 'Must-Knows')", 
            "value": crucials_text[:1024], 
            "inline": False
        })
        
    # 📊 Architectural Comparison
    if ai_data.get('comparison'):
        embed_fields.append({"name": "⚖️ The Cloud Battle: AWS vs Rivals", "value": ai_data['comparison'][:1024], "inline": False})

    payload = {
        "username": "AWS Architect AI",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2855/2855011.png",
        "embeds": [
            {
                "title": f"🎓 Senior Master Class: {service_name}",
                "description": f"{ai_data.get('description')}\n\n[📖 Read Official Documentation]({url})",
                "url": url,
                "color": 3447003, # Nice blue for AI
                "fields": embed_fields,
                "footer": {"text": f"AI-Synthesized Masterclass • {datetime.utcnow().strftime('%Y-%m-%d')}"}
            }
        ]
    }
    
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, 
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'AWSProfessorAI/1.0'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Discord Response: {response.getcode()}")
    except Exception as e:
        print(f"Discord Webhook Error: {e}")
