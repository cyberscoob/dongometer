#!/usr/bin/env python3
"""
Discord → Dongometer Webhook Integration
Simple HTTP-based, no discord.py required
"""
import os
import re
import requests
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

DONGOMETER_URL = os.getenv('DONGOMETER_URL', 'http://localhost:5000/api/event')

def send_event(event_type, value=1, details=""):
    """Send to Dongometer"""
    try:
        requests.post(
            DONGOMETER_URL,
            json={"type": event_type, "value": value, "details": details},
            timeout=2
        )
    except Exception as e:
        print(f"[Dongometer] Error: {e}")

def process_discord_message(username, content, channel):
    """Process Discord message and update Dongometer"""
    content_lower = content.lower()
    
    # Pizza detection
    pizza_count = len(re.findall(r'pizza|🍕', content_lower))
    if pizza_count > 0:
        send_event("pizza", pizza_count, f"{username} in #{channel}")
        print(f"[Dongometer] 🍕 +{pizza_count} from {username}")
    
    # Door detection
    if re.search(r'door.*open|door.*unlock|🚪', content_lower):
        send_event("door_open", 1, f"{username}: {content[:30]}")
        print(f"[Dongometer] 🚪 from {username}")
    
    # Chat velocity (always)
    chaos_boost = 2 if any(k in content_lower for k in ['chaos', 'dong', 'apocalyptic', 'hardin']) else 1
    send_event("chat_message", chaos_boost, f"{username} in #{channel}")

# Webhook receiver for Discord
class DiscordWebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_POST(self):
        if self.path == '/discord-webhook':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len).decode()
            
            try:
                data = json.loads(body)
                process_discord_message(
                    data.get('username', 'unknown'),
                    data.get('content', ''),
                    data.get('channel', 'general')
                )
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                self.send_error(400)
        else:
            self.send_error(404)

if __name__ == "__main__":
    # Test mode
    print("[Dongometer Discord] Testing...")
    process_discord_message("shaggy", "pizza is here! 🍕", "donghouse")
    print("[Dongometer Discord] Test complete")
    
    # Start webhook listener on port 5001
    print("[Dongometer Discord] Webhook listener on port 5001")
    server = HTTPServer(('0.0.0.0', 5001), DiscordWebhookHandler)
    server.serve_forever()
