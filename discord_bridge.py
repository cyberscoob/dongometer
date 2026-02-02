#!/usr/bin/env python3
"""
Discord Bridge for Dongometer
Integrates with OpenClaw's existing Discord channel
"""
import os
import re
import json
import urllib.request
import urllib.error

DONGOMETER_URL = os.getenv('DONGOMETER_URL', 'http://localhost:5000/api/event')

# Discord config from environment
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

PIZZA_PATTERN = re.compile(r'pizza|🍕', re.IGNORECASE)
DOOR_PATTERN = re.compile(r'door.*(?:open|unlock|opened)|🚪', re.IGNORECASE)
CHAOS_KEYWORDS = ['chaos', 'dong', 'apocalyptic', 'gigglesgate', 'hardin needs']

def send_to_dongometer(event_type, value=1, details=""):
    """Send event to Dongometer API using stdlib only"""
    try:
        data = json.dumps({
            "type": event_type,
            "value": value,
            "details": details
        }).encode('utf-8')
        
        req = urllib.request.Request(
            DONGOMETER_URL,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Content-Length': str(len(data))
            }
        )
        
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Dongometer] API error: {e}")
        return None

def on_discord_message(message_obj):
    """
    Call this from OpenClaw's Discord message handler
    message_obj should have: author, content, channel
    """
    author = str(message_obj.get('author', 'unknown'))
    content = message_obj.get('content', '')
    channel = message_obj.get('channel', 'general')
    content_lower = content.lower()
    
    events = []
    
    # Pizza count
    pizza_matches = len(PIZZA_PATTERN.findall(content_lower))
    if pizza_matches > 0:
        result = send_to_dongometer("pizza", pizza_matches, f"{author} in #{channel}")
        events.append(f"🍕+{pizza_matches}")
    
    # Door events
    if DOOR_PATTERN.search(content_lower):
        send_to_dongometer("door_open", 1, f"{author}: {content[:40]}")
        events.append("🚪")
    
    # Chat velocity (always count, boost for chaos words)
    chaos_boost = 2 if any(kw in content_lower for kw in CHAOS_KEYWORDS) else 1
    send_to_dongometer("chat_message", chaos_boost, f"{author} in #{channel}")
    
    return events

# For testing
if __name__ == "__main__":
    # Simulate messages
    test_msgs = [
        {"author": "shaggy", "content": "pizza is here! 🍕🍕", "channel": "donghouse"},
        {"author": "aerospice", "content": "door opened for the pizza guy", "channel": "general"},
        {"author": "clawdad", "content": "this is total chaos right now", "channel": "officers"},
    ]
    
    for msg in test_msgs:
        events = on_discord_message(msg)
        print(f"[Test] {msg['author']}: {events}")
