import boto3
import json
import os
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import html
import random

# Initialize clients
dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['TABLE_NAME']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
RSS_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"

def lambda_handler(event, context):
    print("Fetching AWS RSS Feed with AI Analysis...")
    
    # 1. Fetch RSS Feed
    try:
        with urllib.request.urlopen(RSS_URL, timeout=10) as response:
            rss_data = response.read()
    except Exception as e:
        print(f"Error fetching RSS: {e}")
        return
        
    root = ET.fromstring(rss_data)
    items = root.findall(".//item")
    
    processed_count = 0
    table = dynamodb.Table(TABLE_NAME)
    
    # Limit to 3 new items at a time to stay within quotas
    for item in items:
        if processed_count >= 3: break
        
        title = item.find("title").text
        link = item.find("link").text
        guid = item.find("guid").text
        raw_description = item.find("description").text
        
        # Clean the description
        description = clean_text(raw_description)
        
        # 2. Deduplication check
        dup_check = table.get_item(Key={'article_id': guid})
        if 'Item' in dup_check:
            print(f"Skipping existing: {title}")
            continue
            
        print(f"Analyzing new announcement: {title}")
        
        # 3. Get AI Analysis
        ai_analysis = query_gemini_for_news(title, description)
        
        # 4. Send to Discord
        send_to_discord(title, description, ai_analysis, link)
        
        # 5. Save to DynamoDB
        table.put_item(
            Item={
                'article_id': guid,
                'processed_at': str(datetime.now()),
                'title': title
            }
        )
        processed_count += 1
        
    return {
        'statusCode': 200,
        'body': json.dumps(f'Processed {processed_count} news articles with AI.')
    }

def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text).strip()
    return text

def query_gemini_for_news(title, content):
    """Summarizes AWS news with a DevOps focus"""
    if not GEMINI_API_KEY:
        return None

    prompt = f"""
    You are a Senior DevOps Architect. Analyze this new AWS announcement and summarize it for a DevOps team.
    
    TITLE: {title}
    CONTENT: {content[:8000]}
    
    RESPONSE FORMAT (STRICT JSON ONLY):
    {{
        "devops_impact": "1-2 punchy sentences on how this affects production infra or workflows.",
        "key_takeaway": "The #1 most important technical detail or 'pro-tip' about this change.",
        "worth_it": "A 'Yes/No/Maybe' rating plus a 5-word reason."
    }}
    """

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
    }
    
    req = urllib.request.Request(api_url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            
            # JSON cleaning
            json_text = raw_text.strip()
            if json_text.startswith("```"):
                json_text = re.sub(r'^```(?:json)?\n?|\n?```$', '', json_text, flags=re.MULTILINE)
            
            return json.loads(json_text)
    except Exception as e:
        print(f"AI News Analysis Failed: {e}")
        return None

def send_to_discord(title, full_description, ai_analysis, link):
    embed_fields = []
    
    # 🧠 AI Insight Field
    if ai_analysis:
        insight_text = f"**⚙️ DevOps Impact**: {ai_analysis.get('devops_impact', 'N/A')}\n"
        insight_text += f"**💡 Key Takeaway**: {ai_analysis.get('key_takeaway', 'N/A')}\n"
        insight_text += f"**🚀 Deployment Recommendation**: {ai_analysis.get('worth_it', 'N/A')}"
        
        embed_fields.append({
            "name": "🧠 AI Architect's Insight",
            "value": insight_text[:1024],
            "inline": False
        })
    
    payload = {
        "username": "AWS Tech Curator",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/10061/10061805.png",
        "embeds": [
            {
                "title": title[:256],
                "description": full_description[:300] + "... [Read More]",
                "url": link,
                "color": 16753920, # AWS Orange
                "fields": embed_fields,
                "footer": {
                    "text": "Automated AI Briefing • " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                }
            }
        ]
    }
    
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL, 
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'AWSNewsCuratorAI/1.0'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"News posted to Discord: {response.getcode()}")
    except Exception as e:
        print(f"Discord Error: {e}")