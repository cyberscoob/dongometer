#!/usr/bin/env python3
"""
Matrix Bridge for The Dongometer
Uses environment Matrix creds to listen and track chaos
"""
import os
import re
import json
import urllib.request
import urllib.error
import threading
import time
from datetime import datetime

# Matrix config from environment
MATRIX_HOMESERVER = os.getenv('MATRIX_HOMESERVER', 'https://cclub.cs.wmich.edu')
MATRIX_USER_ID = os.getenv('MATRIX_USER_ID', '@scooby:cclub.cs.wmich.edu')
MATRIX_PASSWORD = os.getenv('MATRIX_PASSWORD')
MATRIX_ROOM = os.getenv('DONGOMETER_ROOM', '!pYoawuzxaFxYhOVtjN:cclub.cs.wmich.edu')  # #donghouse

DONGOMETER_URL = os.getenv('DONGOMETER_URL', 'http://localhost:5000/api/event')

# Patterns
PIZZA_PATTERN = re.compile(r'pizza|🍕', re.IGNORECASE)
DOOR_PATTERN = re.compile(r'door.*(?:open|unlock|opened)|🚪', re.IGNORECASE)
CHAOS_KEYWORDS = ['chaos', 'dong', 'apocalyptic', 'gigglesgate', 'hardin needs', 'demonic', 'shadow president']

def send_to_dongometer(event_type, value=1, details=""):
    """Send event to Dongometer"""
    try:
        data = json.dumps({
            "type": event_type,
            "value": value,
            "details": details
        }).encode('utf-8')
        
        req = urllib.request.Request(
            DONGOMETER_URL,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[Dongometer Matrix] Error: {e}")
        return None

def process_matrix_message(sender, content, room):
    """Process Matrix message and update Dongometer"""
    content_lower = content.lower()
    sender_name = sender.split(':')[0].replace('@', '')
    
    # Pizza
    pizza_count = len(PIZZA_PATTERN.findall(content_lower))
    if pizza_count > 0:
        send_to_dongometer("pizza", pizza_count, f"{sender_name} in {room}")
        print(f"[Dongometer] 🍕 +{pizza_count} from {sender_name}")
    
    # Door
    if DOOR_PATTERN.search(content_lower):
        send_to_dongometer("door_open", 1, f"{sender_name}: {content[:40]}")
        print(f"[Dongometer] 🚪 from {sender_name}")
    
    # Chat velocity (always count)
    chaos_boost = 2 if any(kw in content_lower for kw in CHAOS_KEYWORDS) else 1
    send_to_dongometer("chat_message", chaos_boost, f"{sender_name} in {room}")

# For integration with existing Matrix handler
def on_matrix_message(event):
    """
    Call this from OpenClaw's Matrix message handler
    event should have: sender, content, room_id
    """
    process_matrix_message(
        event.get('sender', '@unknown:cclub.cs.wmich.edu'),
        event.get('content', {}).get('body', ''),
        event.get('room_id', '#unknown')
    )

# Direct Matrix sync (if we want standalone)
def matrix_sync_loop():
    """Direct Matrix sync - polls for messages"""
    print(f"[Dongometer Matrix] Syncing with {MATRIX_HOMESERVER}")
    print(f"[Dongometer Matrix] Room: {MATRIX_ROOM}")
    print(f"[Dongometer Matrix] User: {MATRIX_USER_ID}")
    print("[Dongometer Matrix] Note: Using direct sync - integrate into OpenClaw for better results")
    
    # Would need full Matrix client implementation
    # Better to integrate with existing OpenClaw Matrix handler
    pass

# Test
if __name__ == "__main__":
    test_msgs = [
        {"sender": "@shaggy:cclub.cs.wmich.edu", "content": {"body": "pizza is here! 🍕🍕"}, "room_id": "#donghouse"},
        {"sender": "@aerospice:cclub.cs.wmich.edu", "content": {"body": "door opened for pizza"}, "room_id": "#donghouse"},
        {"sender": "@clawdad:cclub.cs.wmich.edu", "content": {"body": "chaos level rising"}, "room_id": "#donghouse"},
    ]
    
    for msg in test_msgs:
        on_matrix_message(msg)
    
    print("\n[Dongometer Matrix] Test complete. Integrate on_matrix_message() into OpenClaw handler.")
