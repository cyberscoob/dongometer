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

# Matrix indexer cache
_indexer_cache = {'count': None, 'timestamp': 0}
_metrics_cache = {'data': None, 'timestamp': 0}

def get_indexer_metrics():
    """Get message counts from MongoDB indexer for last 5min/10min/hour"""
    global _metrics_cache
    
    # Return cached if recent (5 seconds)
    if _metrics_cache['data'] is not None:
        if time.time() - _metrics_cache['timestamp'] < 5:
            return _metrics_cache['data']
    
    try:
        import subprocess
        import json
        
        now = datetime.now()
        five_min_ago = (now - timedelta(minutes=5)).timestamp() * 1000
        ten_min_ago = (now - timedelta(minutes=10)).timestamp() * 1000
        hour_ago = (now - timedelta(hours=1)).timestamp() * 1000
        
        # Query MongoDB for recent events
        query = f"""
        var fiveMin = db.events.countDocuments({{"origin_server_ts": {{$gt: {int(five_min_ago)}}}}});
        var tenMin = db.events.countDocuments({{"origin_server_ts": {{$gt: {int(ten_min_ago)}}}}});
        var hour = db.events.countDocuments({{"origin_server_ts": {{$gt: {int(hour_ago)}}}}});
        print(JSON.stringify({{fiveMin: fiveMin, tenMin: tenMin, hour: hour}}));
        """
        
        result = subprocess.run(
            ['mongosh', '--quiet', 
             'mongodb://mongo:27017/matrix_index', 
             '--eval', query],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            # Parse the JSON output
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{'):
                    data = json.loads(line)
                    _metrics_cache['data'] = data
                    _metrics_cache['timestamp'] = time.time()
                    return data
        return None
    except Exception as e:
        print(f"Indexer metrics error: {e}")
        return None

def get_indexer_count():
    """Get total message count from Matrix indexer MongoDB"""
    global _indexer_cache
    
    # Return cached value if recent
    if _indexer_cache['count'] is not None:
        if time.time() - _indexer_cache['timestamp'] < 60:
            return _indexer_cache['count']
    
    try:
        import subprocess
        # Try mongosh directly (inside doghouse container, mongo is at hostname 'mongo')
        result = subprocess.run(
            ['mongosh', '--quiet', 
             'mongodb://mongo:27017/matrix_index', 
             '--eval', 'db.events.countDocuments()'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            count = int(result.stdout.strip())
            _indexer_cache['count'] = count
            _indexer_cache['timestamp'] = time.time()
            return count
        return None
        
    except Exception:
        # MongoDB not available
        return None

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
    
    # APOCALYPSE MODE — ALL LIMITERS REMOVED
    # Try to get metrics from MongoDB indexer first
    indexer_data = get_indexer_metrics()
    
    if indexer_data:
        # Use MongoDB as source of truth
        recent_msgs = indexer_data.get('fiveMin', 0)
        recent_doors = indexer_data.get('tenMin', 0) // 2  # Estimate doors as half
    else:
        # Fallback to in-memory deques
        recent_msgs = sum(1 for t in metrics['chat_velocity'] 
                         if now - t < timedelta(minutes=5))
        recent_doors = sum(1 for t in metrics['door_events'] 
                          if now - t < timedelta(minutes=10))
    
    score += recent_msgs * 2  # NO CAP
    score += recent_doors * 5  # NO CAP
    
    hour = now.hour
    if 0 <= hour < 6:
        score += 20
    elif 18 <= hour < 24:
        score += 15
    elif 12 <= hour < 18:
        score += 10
    else:
        score += 5
    
    # PIZZA SCALING UNLEASHED — logarithmic growth for infinite chaos
    if metrics['pizza_count'] > 0:
        # Logarithmic scaling: every 10x pizzas adds +50 chaos
        import math
        pizza_bonus = min(metrics['pizza_count'] * 2, 10)  # Base +10
        if metrics['pizza_count'] > 10000:
            pizza_bonus += math.log10(metrics['pizza_count']) * 50  # Scaling bonus
        score += pizza_bonus
    
    # NO MAX CAP — CHAOS IS UNLIMITED
    return score

class DongometerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.serve_dashboard()
        elif path == '/manifold':
            self.serve_manifold()
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
    
    def serve_manifold(self):
        html = open('/home/scoob/dongometer/templates/manifold.html').read() if os.path.exists('/home/scoob/dongometer/templates/manifold.html') else '<h1>Dong Manifold</h1>'
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
        
        # Get metrics from indexer or fallback to memory
        indexer_data = get_indexer_metrics()
        if indexer_data:
            chat_5m = indexer_data.get('fiveMin', 0)
            chat_1h = indexer_data.get('hour', 0)
            door_10m = indexer_data.get('tenMin', 0) // 2  # Estimate
        else:
            chat_5m = sum(1 for t in metrics['chat_velocity'] 
                         if now - t < timedelta(minutes=5))
            chat_1h = len(metrics['chat_velocity'])
            door_10m = sum(1 for t in metrics['door_events'] 
                          if now - t < timedelta(minutes=10))
        
        # Check for PIZZAPOCALYPSE (>10k pizzas breaks reality) — UNLIMITED
        if metrics['pizza_count'] > 10000:
            score = score * 2.0  # 100% chaos boost, NO CAP
        
        # Determine status based on UNLIMITED chaos score
        if status is None:
            if score <= 20:
                status = '😴 CALM — The donghouse sleeps'
            elif score <= 40:
                status = '⚡ ACTIVE — Normal operations'
            elif score <= 60:
                status = '🍕 CHAOTIC — Pizza\'s here'
            elif score <= 80:
                status = '👿 DEMONIC — Hardin needs a grader'
            elif score <= 100:
                status = '☠️ APOCALYPTIC — Gigglesgate 2.0'
            elif score <= 200:
                status = '🔥 TRUE APOCALYPSE — The donghouse is no more'
            elif score <= 500:
                status = '🌌 COSMIC HORROR — Physics has left the building'
            elif score <= 1000:
                status = '💀 MULTIVERSE COLLAPSE — All timelines converge to pizza'
            elif score < 42069:
                status = '☠️🍕 HEAT DEATH OF UNIVERSE — Entropy is pizza now 🍕☠️'
            else:
                status = '🌿 FENTHOUSE — Folding in the infinite 🌿 (Chaos maxed at funny number)'
        
        # Get Matrix indexer count if available
        indexer_count = get_indexer_count()
        
        data = {
            'chaos_score': round(score, 1),
            'chat_velocity_5min': chat_5m,
            'chat_velocity_1hour': chat_1h,
            'door_events_10min': door_10m,
            'pizza_count': metrics['pizza_count'],
            'last_updated': metrics['last_updated'],
            'status': status,
            'matrix_indexer_messages': indexer_count
        }
        self.send_json(data)
    
    def handle_event(self, data):
        event_type = data.get('type')
        value = data.get('value', 1)
        
        now = datetime.now()
        
        if event_type == 'chat_message':
            metrics['chat_velocity'].append(now)
        elif event_type in ('door_open', 'door_close'):
            # Honor the value parameter for mass door events
            for _ in range(min(value, 100000)):  # Cap at 100k per request for safety
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
