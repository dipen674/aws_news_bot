import boto3
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import html
import time

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['TABLE_NAME']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
RSS_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
AI_MODEL = "llama-3.3-70b-versatile"

def lambda_handler(event, context):
    try:
        with urllib.request.urlopen(RSS_URL, timeout=10) as response:
            rss_data = response.read()
    except Exception as e:
        print(f"RSS Error: {e}")
        return
        
    root = ET.fromstring(rss_data)
    items = root.findall(".//item")
    
    processed = 0
    table = dynamodb.Table(TABLE_NAME)
    
    for item in items:
        if processed >= 1: break
        
        title = item.find("title").text
        link = item.find("link").text
        guid = item.find("guid").text
        desc = clean_text(item.find("description").text)
        
        # Dup check ensures we only post NEW stories
        dup = table.get_item(Key={'article_id': guid})
        if 'Item' in dup: continue
            
        print(f"Analyzing news item with Senior AI: {title}")
        ai = query_groq(title, desc)
        
        if not ai:
            print("Groq failed to analyze news item")
            continue
            
        send_to_discord(title, desc, ai, link)
        
        table.put_item(Item={'article_id': guid, 'processed_at': str(datetime.now()), 'title': title})
        processed += 1
        time.sleep(3)
        
    return {'statusCode': 200, 'body': json.dumps(f'Processed {processed} news')}

def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\n\s*\n', '\n', text).strip()

def query_groq(title, content):
    prompt = f"""You are a funny Technical Bard / Architect. 
Tell me the EPIC story of this AWS News using VERY SIMPLE everyday English.
I want to laugh, but I MUST know every technical detail (names, domains, version numbers).

TITLE: {title}
CONTENT: {content[:5000]}

Respond ONLY with valid JSON (no markdown):
{{
  "friendly_summary": "The Epic Tale (Very Simple English): A funny, happy story of what happened. List all specific names/numbers from the text.",
  "devops_impact": "The Technical Plot Twist: How this makes our life easier tomorrow (Simple English).",
  "real_use_case": "The Quest: A funny, practical example of using this hero at work.",
  "key_takeaway": "The Ancient Wisdom: The #1 simple secret to remember."
}}"""

    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a funny technical storyteller. Respond ONLY in valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }
    
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json", "User-Agent": "AWS-News-Bot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            raw = result['choices'][0]['message']['content'].strip()
            if '```' in raw:
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
                if match: raw = match.group(1)
            return json.loads(raw)
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

def send_to_discord(title, desc, ai, link):
    fields = []
    final_desc = ai.get('friendly_summary') if ai else desc[:500] + "..."

    if ai:
        fields.append({"name": "\n\n🎭  The Technical Plot Twist", "value": f"{ai.get('devops_impact', 'N/A')}\n\u200b", "inline": False})
        fields.append({"name": "\n\n🎯  The Practical Quest", "value": f"{ai.get('real_use_case', 'N/A')}\n\u200b", "inline": False})
        fields.append({"name": "\n\n💡  The Ancient Wisdom", "value": f"{ai.get('key_takeaway', 'N/A')}\n\u200b", "inline": False})
    
    payload = {
        "username": "AWS Storyteller",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/10061/10061805.png",
        "embeds": [{
            "title": f"📜 {title[:250]}",
            "description": f"{final_desc}\n\n[📖 Read The Sacred Texts]({link})",
            "url": link,
            "color": 16753920,
            "fields": fields,
            "footer": {"text": "A Refreshing Technical Tale • " + datetime.utcnow().strftime("%Y-%m-%d")}
        }]
    }
    
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'AWS-News-Bot/1.0'})
    with urllib.request.urlopen(req):
        print("Posted to Discord")