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
        
        # Intentional pacing to stay under 15 RPM
        if processed_count < 3:
            import time
            time.sleep(5)
        
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
    """Summarizes AWS news with a friendly, simple DevOps focus"""
    if not GEMINI_API_KEY:
        return None

    prompt = f"""
    You are a friendly Senior DevOps Architect. 
    Explain this new AWS announcement in VERY SIMPLE, friendly English. 
    Imagine you are chatting with a junior dev who is a bit overwhelmed.

    TITLE: {title}
    CONTENT: {content[:8000]}
    
    RESPONSE FORMAT (STRICT JSON ONLY):
    {{
        "friendly_summary": "A 2-3 sentence very simple and exciting explanation of what this news is.",
        "devops_impact": "How this actually makes our lives easier as engineers.",
        "key_takeaway": "The one technical 'pro-tip' to remember.",
        "worth_it": "Yes/No/Maybe + a simple reason (max 5 words)."
    }}
    """

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.4}
    }
    
    max_retries = 5
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(api_url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                
                json_text = raw_text.strip()
                if json_text.startswith("```"):
                    json_text = re.sub(r'^```(?:json)?\n?|\n?```$', '', json_text, flags=re.MULTILINE)
                
                return json.loads(json_text)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"News AI Rate Limit (429). Attempt {attempt + 1}. Waiting 15s...")
                import time
                time.sleep(15)
                if attempt == max_retries: raise
            else:
                raise
        except Exception as e:
            print(f"AI News Analysis Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                import time
                time.sleep(3)
            else:
                raise
    return None

def send_to_discord(title, full_description, ai_analysis, link):
    embed_fields = []
    
    # Use AI summary for the main description if available
    final_description = ""
    if ai_analysis and ai_analysis.get('friendly_summary'):
        final_description = ai_analysis['friendly_summary']
    else:
        # Fallback to truncated RSS desc only if AI fails
        final_description = full_description[:300] + "..."

    # 🧠 AI Insight Fields with improved vertical spacing
    if ai_analysis:
        embed_fields.append({
            "name": "\n⚙️ DevOps Impact",
            "value": f"{ai_analysis.get('devops_impact', 'N/A')}\n\u200b",
            "inline": False
        })
        embed_fields.append({
            "name": "💡 Key Takeaway",
            "value": f"{ai_analysis.get('key_takeaway', 'N/A')}\n\u200b",
            "inline": False
        })
        embed_fields.append({
            "name": "🚀 Deployment Recommendation",
            "value": f"{ai_analysis.get('worth_it', 'N/A')}\n\u200b",
            "inline": False
        })
    
    payload = {
        "username": "AWS Tech Curator",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/10061/10061805.png",
        "embeds": [
            {
                "title": title[:256],
                "description": f"{final_description}\n\n[📖 Read Official Documentation]({link})",
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