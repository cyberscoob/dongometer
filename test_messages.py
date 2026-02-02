#!/usr/bin/env python3
"""Test message counting for Dongometer"""
import urllib.request
import json
import time

def send_event(event_type, value=1, details=""):
    data = json.dumps({"type": event_type, "value": value, "details": details}).encode()
    req = urllib.request.Request(
        'http://localhost:5000/api/event',
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_metrics():
    try:
        with urllib.request.urlopen('http://localhost:5000/api/metrics', timeout=2) as resp:
            return json.loads(resp.read().decode())
    except:
        return None

print("Testing Dongometer message counting...")
print("="*50)

# Check initial state
m = get_metrics()
if m:
    print(f"Initial: messages(5m)={m['chat_velocity_5min']}, chaos={m['chaos_score']}")
else:
    print("Dongometer not running! Start it first: python3 simple_app.py")
    exit(1)

# Simulate 5 messages
print("\nSending 5 chat messages...")
for i in range(5):
    result = send_event("chat_message", 1, f"Test message {i+1}")
    print(f"  Message {i+1}: chaos={result.get('chaos_score') if result else 'error'}")
    time.sleep(0.1)

# Check result
time.sleep(0.5)
m = get_metrics()
print(f"\nAfter 5 messages: messages(5m)={m['chat_velocity_5min']}, chaos={m['chaos_score']}")
print(f"Status: {m['status']}")

print("\n" + "="*50)
print("To auto-count Matrix messages, add this to OpenClaw's message handler:")
print("""
import sys
sys.path.insert(0, '/home/scoob/dongometer')
from matrix_bridge import process_matrix_message

# In your message handler:
process_matrix_message(event.sender, event.content.body, event.room_id)
""")
