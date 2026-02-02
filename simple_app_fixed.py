#!/usr/bin/env python3
"""
The Dongometer - FIXED VERSION
Fenthouse lock support added
"""
import os
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from collections import deque

DB_PATH = os.path.join(os.path.dirname(__file__), 'dongometer.db')

metrics = {
    'chat_velocity': deque(maxlen=100),
    'door_events': deque(maxlen=50),
    'pizza_count': 0,
    'last_updated': None,
    'chaos_score': 0.0,
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metric_type TEXT NOT NULL,
            value REAL,
            details TEXT
        )
    ''')
    conn.commit()
    conn.close()

def calculate_chaos_score():
    score = 0.0
    now = datetime.now()
    
    # Check for Fenthouse lock
    try:
        if os.path.exists('/tmp/dongometer_lock'):
            with open('/tmp/dongometer_lock', 'r') as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    lock_time = int(lines[0].strip())
                    duration = int(lines[1].strip())
                    if now.timestamp() < lock_time + duration:
                        return 42069.0
    except:
        pass
    
    # Normal calculation
    recent_msgs = sum(1 for t in metrics['chat_velocity'] 
                     if now - t < timedelta(minutes=5))
    score += min(recent_msgs * 2, 40)
    
    recent_doors = sum(1 for t in metrics['door_events'] 
                      if now - t < timedelta(minutes=10))
    score += min(recent_doors * 5, 30)
    
    hour = now.hour
    if 0 <= hour < 6:
        score += 20
    elif 18 <= hour < 24:
        score += 15
    elif 12 <= hour < 18:
        score += 10
    else:
        score += 5
    
    if metrics['pizza_count'] > 0:
        score += min(metrics['pizza_count'] * 2, 10)
    
    return min(score, 100)

class DongometerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.serve_dashboard()
        elif path == '/api/metrics':
            self.serve_metrics()
        else:
            self.send_error(404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/event':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                self.handle_event(data)
            except json.JSONDecodeError:
                self.send_error(400)
        else:
            self.send_error(404)
    
    def serve_dashboard(self):
        html = open('/home/scoob/dongometer/templates/dashboard.html').read() if os.path.exists('/home/scoob/dongometer/templates/dashboard.html') else '<h1>Dongometer</h1>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_metrics(self):
        score = calculate_chaos_score()
        metrics['chaos_score'] = score
        metrics['last_updated'] = datetime.now().isoformat()
        
        now = datetime.now()
        
        # Check for Fenthouse lock
        status = None
        try:
            if os.path.exists('/tmp/dongometer_lock'):
                with open('/tmp/dongometer_lock', 'r') as f:
                    lines = f.readlines()
                    if len(lines) >= 3:
                        lock_time = int(lines[0].strip())
                        duration = int(lines[1].strip())
                        lock_status = lines[2].strip()
                        if now.timestamp() < lock_time + duration:
                            status = lock_status
        except:
            pass
        
        chat_5m = sum(1 for t in metrics['chat_velocity'] 
                     if now - t < timedelta(minutes=5))
        door_10m = sum(1 for t in metrics['door_events'] 
                      if now - t < timedelta(minutes=10))
        
        if status is None:
            if score <= 20:
                status = '😴 CALM — The donghouse sleeps'
            elif score <= 40:
                status = '⚡ ACTIVE — Normal operations'
            elif score <= 60:
                status = '🍕 CHAOTIC — Pizza\'s here'
            elif score <= 80:
                status = '👿 DEMONIC — Hardin needs a grader'
            else:
                status = '☠️ APOCALYPTIC — Gigglesgate 2.0'
        
        data = {
            'chaos_score': round(score, 1),
            'chat_velocity_5min': chat_5m,
            'door_events_10min': door_10m,
            'pizza_count': metrics['pizza_count'],
            'last_updated': metrics['last_updated'],
            'status': status
        }
        self.send_json(data)
    
    def handle_event(self, data):
        event_type = data.get('type')
        value = data.get('value', 1)
        
        now = datetime.now()
        
        if event_type == 'chat_message':
            metrics['chat_velocity'].append(now)
        elif event_type in ('door_open', 'door_close'):
            metrics['door_events'].append(now)
        elif event_type == 'pizza':
            metrics['pizza_count'] += value
        elif event_type == 'reset_pizza':
            metrics['pizza_count'] = 0
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO events (metric_type, value, details) VALUES (?, ?, ?)',
            (event_type, value, data.get('details', ''))
        )
        conn.commit()
        conn.close()
        
        self.send_json({'success': True, 'chaos_score': calculate_chaos_score()})
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == '__main__':
    init_db()
    server = HTTPServer(('0.0.0.0', 5000), DongometerHandler)
    print("🍆 The Dongometer is live on http://localhost:5000")
    server.serve_forever()
