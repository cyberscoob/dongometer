#!/usr/bin/env python3
"""
Matrix Listener for The Dongometer
Connects directly to Matrix and sends events to Dongometer API
Uses environment variables: MATRIX_HOMESERVER, MATRIX_USER_ID, MATRIX_PASSWORD
"""
import os
import sys
import re
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import ssl

# Matrix config from environment
MATRIX_HOMESERVER = os.getenv('MATRIX_HOMESERVER', 'https://cclub.cs.wmich.edu')
MATRIX_USER_ID = os.getenv('MATRIX_USER_ID')
MATRIX_PASSWORD = os.getenv('MATRIX_PASSWORD')
TARGET_ROOM = os.getenv('DONGOMETER_ROOM', '!pYoawuzxaFxYhOVtjN:cclub.cs.wmich.edu')  # #donghouse

DONGOMETER_URL = os.getenv('DONGOMETER_URL', 'http://localhost:5000/api/event')

# Patterns
PIZZA_PATTERN = re.compile(r'pizz|🍕', re.IGNORECASE)
DOOR_PATTERN = re.compile(r'door.*(?:open|unlock|opened)|🚪', re.IGNORECASE)
CHAOS_KEYWORDS = ['chaos', 'dong', 'apocalyptic', 'gigglesgate', 'hardin needs', 'demonic', 'shadow president']

class MatrixDongometerBot:
    def __init__(self):
        self.access_token = None
        self.user_id = None
        self.next_batch = None
        self.start_time = int(time.time() * 1000)  # Only count messages after this
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
    def matrix_request(self, endpoint, data=None, method="POST", token=None):
        """Make Matrix API request"""
        url = f"{MATRIX_HOMESERVER}/_matrix/client/r0{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        try:
            if data:
                data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            print(f"[Matrix API Error] {e}")
            return None
    
    def dongometer_request(self, event_type, value=1, details=""):
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
            print(f"[Dongometer Error] {e}")
            return None
    
    def login(self):
        """Login to Matrix"""
        print(f"[Matrix] Logging in as {MATRIX_USER_ID}...")
        result = self.matrix_request("/login", {
            "type": "m.login.password",
            "user": MATRIX_USER_ID,
            "password": MATRIX_PASSWORD
        })
        if result and 'access_token' in result:
            self.access_token = result['access_token']
            self.user_id = result.get('user_id', MATRIX_USER_ID)
            print(f"[Matrix] Logged in as {self.user_id}")
            return True
        print("[Matrix] Login failed!")
        return False
    
    def join_room(self, room_id):
        """Join a room"""
        print(f"[Matrix] Joining room {room_id}...")
        result = self.matrix_request(f"/rooms/{room_id}/join", {}, token=self.access_token)
        if result:
            print(f"[Matrix] Joined room")
            return True
        return False
    
    def process_message(self, sender, content, room_id):
        """Process a message and send to Dongometer"""
        if not content or sender == self.user_id:
            return
            
        content_lower = content.lower()
        sender_name = sender.split(':')[0].replace('@', '')
        room_name = room_id.split(':')[0].replace('!', '#')
        
        events = []
        
        # Pizza detection
        pizza_count = len(PIZZA_PATTERN.findall(content_lower))
        # Apply multiplier if active
        try:
            with open("/tmp/dongometer_multiplier", "r") as f:
                multiplier = int(f.read().strip())
                pizza_count *= multiplier
        except:
            pass
        if pizza_count > 0:
            self.dongometer_request("pizza", pizza_count, f"{sender_name} in {room_name}")
            events.append(f"🍕+{pizza_count}")
        
        # Door detection
        if DOOR_PATTERN.search(content_lower):
            self.dongometer_request("door_open", 1, f"{sender_name}: {content[:40]}")
            events.append("🚪")
        
        # Chat velocity (always count)
        chaos_boost = 2 if any(kw in content_lower for kw in CHAOS_KEYWORDS) else 1
        result = self.dongometer_request("chat_message", chaos_boost, f"{sender_name} in {room_name}")
        
        if events or chaos_boost > 1:
            print(f"[Dongometer] {sender_name}: {events} chaos_boost={chaos_boost}")
    
    def poll_messages(self):
        """Poll for new messages"""
        # Initial sync
        print("[Matrix] Starting sync...")
        endpoint = f"/sync?timeout=30000"
        if self.next_batch:
            endpoint += f"&since={self.next_batch}"
        
        result = self.matrix_request(endpoint, method="GET", token=self.access_token)
        if not result:
            return
        
        self.next_batch = result.get('next_batch')
        
        # Process rooms
        rooms = result.get('rooms', {}).get('join', {})
        for room_id, room_data in rooms.items():
            timeline = room_data.get('timeline', {}).get('events', [])
            for event in timeline:
                if event.get('type') == 'm.room.message':
                    # Check timestamp
                    event_ts = event.get('origin_server_ts', 0)
                    current_ts = int(time.time() * 1000)
                    
                    # For first 5 minutes, count all messages (including historical)
                    # After 5 minutes, only count new messages
                    five_minutes_ms = 5 * 60 * 1000
                    within_grace_period = (current_ts - self.start_time) < five_minutes_ms
                    
                    if not within_grace_period and event_ts < self.start_time:
                        continue  # Skip historical messages after grace period
                    
                    content = event.get('content', {}).get('body', '')
                    sender = event.get('sender', '')
                    self.process_message(sender, content, room_id)
    
    def run(self):
        """Main loop"""
        if not MATRIX_USER_ID or not MATRIX_PASSWORD:
            print("[Matrix] Error: MATRIX_USER_ID and MATRIX_PASSWORD must be set")
            print(f"  Current: USER_ID={MATRIX_USER_ID}, PASSWORD={'*' * len(MATRIX_PASSWORD or '')}")
            return
        
        if not self.login():
            return
        
        # Join target room if specified
        if TARGET_ROOM:
            self.join_room(TARGET_ROOM)
        
        print(f"[Matrix] Listening for messages in all connected rooms...")
        print(f"[Dongometer] Sending events to {DONGOMETER_URL}")
        
        while True:
            try:
                self.poll_messages()
            except Exception as e:
                print(f"[Error] {e}")
                time.sleep(5)

if __name__ == "__main__":
    print("🍆 Dongometer Matrix Listener starting...")
    print("=" * 50)
    bot = MatrixDongometerBot()
    bot.run()
