import boto3
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import html
import time
import random

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ['TABLE_NAME']
DISCORD_WEBHOOK_URL = os.environ['DISCORD_WEBHOOK_URL']
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
RSS_URL = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"
AI_MODEL = "llama-3.3-70b-versatile"

def safe_request(url, data=None, headers=None, method='POST', timeout=30):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req_headers = headers or {}
            if 'User-Agent' not in req_headers:
                req_headers['User-Agent'] = 'AWS-News-Bot/1.0 (https://github.com/dipen674/aws_news_bot)'
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"Request failed (Attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait:.2f}s...")
            if attempt == max_retries - 1: raise
            time.sleep(wait)

def lambda_handler(event, context):
    is_weekly = event.get('weekly', False)
    
    try:
        rss_data = safe_request(RSS_URL, method='GET').encode('utf-8')
    except Exception as e:
        print(f"RSS Error: {e}")
        return {'statusCode': 500, 'body': "RSS feed unreachable"}
        
    root = ET.fromstring(rss_data)
    items = root.findall(".//item")
    
    if is_weekly:
        return handle_weekly_highlight(items)

    processed = 0
    table = dynamodb.Table(TABLE_NAME)
    
    for item in items:
        if processed >= 5: break
        
        title = item.find("title").text
        # RSS <link> can be tricky in ElementTree — get tail or use guid as fallback
        link_tag = item.find("link")
        link = (link_tag.text or link_tag.tail or '').strip() if link_tag is not None else ''
        if not link:
            link = item.find("guid").text or ''
        guid = item.find("guid").text
        desc = clean_text(item.find("description").text)
        
        print(f"Item: title={title[:60]}, link={link[:80]}, guid={guid[:60]}")
        
        # Dup check ensures we only post NEW stories
        dup = table.get_item(Key={'article_id': guid})
        if 'Item' in dup:
            print(f"Skipping (already processed): {title[:60]}")
            continue
            
        print(f"Analyzing news item: {title}")
        ai = query_groq(title, desc)
        
        if not ai:
            print("Groq failed to analyze news item")
            continue
        
        print(f"AI response: {json.dumps(ai)[:300]}")
            
        send_to_discord(title, ai, link)
        
        table.put_item(Item={'article_id': guid, 'processed_at': str(datetime.now()), 'title': title})
        processed += 1
        time.sleep(2)
        
    return {'statusCode': 200, 'body': json.dumps(f'Processed {processed} news')}

def handle_weekly_highlight(items):
    # Take the top 15 most recent items for the week
    recent_news = []
    for i in items[:15]:
        recent_news.append(f"- {i.find('title').text} (ID: {i.find('guid').text})")
    
    prompt = f"""You are a Master AWS Cloud Architect. From this week's AWS news, pick the ONE single most impactful update for developers.
    NEWS LIST:
    {chr(10).join(recent_news)}
    
    Explain why it's the 'Weekly Champion' and provide a simplified summary + Terraform snippet.
    
    Respond ONLY with valid JSON (no markdown):
    {{
      "champion_title": "The Title of the Winning Update",
      "reason_for_winning": "Why this beats everything else this week (1 sentence).",
      "summary": "Full high-level simplified summary (3 sentences).",
      "terraform_snippet": "A relevant 5-7 line Terraform snippet or config example (N/A if not applicable)."
    }}"""
    
    ai = call_groq_api(prompt)
    if ai:
        send_weekly_to_discord(ai)
        return {'statusCode': 200, 'body': "Weekly Highlight posted"}
    return {'statusCode': 500, 'body': "Weekly Highlight failed"}

def clean_text(text):
    if not text: return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\n\s*\n', '\n', text).strip()

def query_groq(title, content):
    prompt = f"""You are a Senior Cloud Architect. 
Summarize this AWS news in a HIGH-LEVEL and SIMPLIFIED way for a busy developer.
CATEGORIES: [Compute, Storage, Networking, Database, Security, AI/ML, Serverless, DevTools, Analytics]

TITLE: {title}
CONTENT: {content[:5000]}

Respond ONLY with valid JSON (no markdown):
{{
  "category": "Pick the closest category from the list above.",
  "high_level_summary": "A 2-sentence max, simple explanation.",
  "core_benefit": "The #1 reason to care (1 sentence).",
  "terraform_snippet": "A 5-line Terraform snippet if applicable, otherwise 'N/A'."
}}"""
    return call_groq_api(prompt)

def call_groq_api(prompt):
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are an Enterprise Cloud Architect. Respond ONLY in valid JSON with a strictly professional, technical tone. Do not use layman analogies."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1, "max_tokens": 800
    }
    
    try:
        raw = safe_request("https://api.groq.com/openai/v1/chat/completions",
                          data=json.dumps(payload).encode('utf-8'),
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json", "User-Agent": "AWS-Bot/1.0"})
        result = json.loads(raw)
        content = result['choices'][0]['message']['content'].strip()
        if '```' in content:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match: content = match.group(1)
        return json.loads(content)
    except Exception as e:
        print(f"Groq API Error: {e}")
        return None

def send_to_discord(title, ai, link):
    category = ai.get('category', 'General')
    
    # Guard: Discord rejects empty field values
    core_benefit = (ai.get('core_benefit') or 'N/A')[:1024]
    fields = [
        {"name": "🚀 Why It Matters", "value": core_benefit, "inline": False}
    ]
    
    snippet = ai.get('terraform_snippet')
    if snippet and snippet.strip() not in ('N/A', '', 'null'):
        # Discord field value limit is 1024 chars; code block uses ~10 chars overhead
        snippet_trimmed = snippet.strip()[:1000]
        fields.append({"name": "🛠️ Terraform Snippet", "value": f"```hcl\n{snippet_trimmed}\n```", "inline": False})
    
    summary = (ai.get('high_level_summary') or 'See link for details.')[:2048]
    
    payload = {
        "username": "AWS News Bot",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/10061/10061805.png",
        "embeds": [{
            "title": f"[{category}] {title[:240]}",
            "description": f"{summary}\n\n[📖 Read More]({link})",
            "url": link, "color": 16753920, "fields": fields,
            "footer": {"text": "Concise Technical Briefing • " + datetime.utcnow().strftime("%Y-%m-%d")}
        }]
    }
    try:
        payload_json = json.dumps(payload)
        print(f"Sending Discord payload ({len(payload_json)} bytes)")
        safe_request(DISCORD_WEBHOOK_URL, data=payload_json.encode('utf-8'), headers={'Content-Type': 'application/json'})
        print(f"Discord post SUCCESS: {title[:80]}")
    except Exception as e:
        print(f"Discord send FAILED for '{title[:80]}': {e}")
        # Print payload so we can see exactly what was rejected
        print(f"Failed payload: {json.dumps(payload)[:1000]}")
        raise

def send_weekly_to_discord(ai):
    fields = [{"name": "🏆 Why it's the Champion", "value": ai.get('reason_for_winning', 'N/A'), "inline": False}]
    
    snippet = ai.get('terraform_snippet')
    if snippet and snippet != 'N/A':
        fields.append({"name": "🏗️ Implementation Draft", "value": f"```hcl\n{snippet}\n```", "inline": False})
    
    payload = {
        "username": "AWS Executive Brief",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3201/3201211.png",
        "embeds": [{
            "title": f"⭐ Weekly Architect Update: {ai.get('champion_title')}",
            "description": f"{ai.get('summary')}",
            "color": 15548997, "fields": fields,
            "footer": {"text": "The Best of AWS This Week • " + datetime.utcnow().strftime("%Y-%m-%d")}
        }]
    }
    safe_request(DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})