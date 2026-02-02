#!/usr/bin/env python3
"""
The Dongometer - Simple version using only stdlib
No Flask required
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

# In-memory metrics
metrics = {
    'chat_velocity': deque(maxlen=100),
    'door_events': deque(maxlen=50),
    'pizza_count': 0,
    'last_updated': None,
    'chaos_score': 0.0,
}

def init_db():
    """Initialize SQLite database"""
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hourly_stats (
            hour DATETIME PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            door_opens INTEGER DEFAULT 0,
            chaos_score REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def calculate_chaos_score():
    """Calculate chaos score 0-100 (or 42069 for Fenthouse mode)"""
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
    
    # Chat velocity (0-40 points)
    recent_msgs = sum(1 for t in metrics['chat_velocity'] 
                     if now - t < timedelta(minutes=5))
    score += min(recent_msgs * 2, 40)
    
    # Door activity (0-30 points)
    recent_doors = sum(1 for t in metrics['door_events'] 
                      if now - t < timedelta(minutes=10))
    score += min(recent_doors * 5, 30)
    
    # Time factor (0-20 points)
    hour = now.hour
    if 0 <= hour < 6:
        score += 20
    elif 18 <= hour < 24:
        score += 15
    elif 12 <= hour < 18:
        score += 10
    else:
        score += 5
    
    # Pizza bonus (0-10 points)
    if metrics['pizza_count'] > 0:
        score += min(metrics['pizza_count'] * 2, 10)
    
    return min(score, 100)

class DongometerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.serve_dashboard()
        elif path == '/api/metrics':
            self.serve_metrics()
        elif path == '/api/history':
            self.serve_history()
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
        html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>🍆 THE DONGOMETER 🍆</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Courier New', monospace; 
            background: #0a0a1a; 
            color: #fff; 
            text-align: center;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            overflow-x: hidden;
        }
        h1 { 
            color: #ff00ff; 
            text-shadow: 0 0 20px #ff00ff, 0 0 40px #ff00ff;
            font-size: 2.5em;
            margin-bottom: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        .subtitle { 
            color: #888; 
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        .chaos-score { 
            font-size: 7em; 
            font-weight: bold; 
            margin: 20px 0;
            transition: all 0.3s ease;
            text-shadow: 0 0 30px currentColor;
        }
        .status-text {
            font-size: 1.5em;
            padding: 15px 30px;
            border-radius: 10px;
            display: inline-block;
            margin: 20px 0;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .metrics {
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 20px;
            margin: 30px 0;
        }
        .metric { 
            background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
            border: 1px solid rgba(255,255,255,0.1);
            padding: 25px 35px;
            border-radius: 15px;
            min-width: 140px;
            backdrop-filter: blur(10px);
            transition: transform 0.3s ease;
        }
        .metric:hover {
            transform: translateY(-5px);
        }
        .metric-value { 
            font-size: 2.5em; 
            font-weight: bold;
            margin-bottom: 5px;
        }
        .metric-label {
            font-size: 0.9em;
            color: #888;
            text-transform: uppercase;
        }
        
        /* Chaos levels */
        .calm { 
            color: #00ff88; 
            text-shadow: 0 0 20px #00ff88;
        }
        .calm .status-text { background: rgba(0,255,136,0.2); border: 1px solid #00ff88; }
        
        .active { 
            color: #ffff00; 
            text-shadow: 0 0 20px #ffff00;
            animation: glow 3s infinite;
        }
        .active .status-text { background: rgba(255,255,0,0.2); border: 1px solid #ffff00; }
        
        .chaotic { 
            color: #ff8800; 
            text-shadow: 0 0 30px #ff8800;
            animation: shake 0.5s infinite, glow 2s infinite;
        }
        .chaotic .status-text { 
            background: rgba(255,136,0,0.3); 
            border: 1px solid #ff8800;
            animation: shake 0.3s infinite;
        }
        
        .demonic { 
            color: #ff0088; 
            text-shadow: 0 0 40px #ff0088, 0 0 80px #ff0088;
            animation: violent-shake 0.2s infinite, red-flash 1s infinite;
        }
        .demonic .status-text { 
            background: rgba(255,0,136,0.4); 
            border: 2px solid #ff0088;
            animation: shake 0.15s infinite;
        }
        
        .apocalyptic { 
            color: #ff0000; 
            text-shadow: 0 0 50px #ff0000, 0 0 100px #ff0000, 0 0 150px #ff0000;
            animation: violent-shake 0.1s infinite, fire-colors 0.5s infinite, glow 0.3s infinite;
        }
        .apocalyptic .status-text { 
            background: rgba(255,0,0,0.5); 
            border: 3px solid #ff0000;
            animation: shake 0.1s infinite, fire-colors 0.8s infinite;
        }
        
        /* Animations */
        @keyframes glow {
            0%, 100% { text-shadow: 0 0 20px currentColor; }
            50% { text-shadow: 0 0 60px currentColor, 0 0 100px currentColor; }
        }
        @keyframes shake {
            0%, 100% { transform: translate(0, 0) rotate(0deg); }
            25% { transform: translate(2px, 1px) rotate(0.5deg); }
            50% { transform: translate(-1px, -2px) rotate(-0.5deg); }
            75% { transform: translate(-2px, 1px) rotate(0.3deg); }
        }
        @keyframes violent-shake {
            0% { transform: translate(0, 0) rotate(0deg) scale(1); }
            20% { transform: translate(-3px, 2px) rotate(-1deg) scale(1.02); }
            40% { transform: translate(3px, -2px) rotate(1deg) scale(0.98); }
            60% { transform: translate(-2px, -3px) rotate(-0.5deg) scale(1.01); }
            80% { transform: translate(2px, 3px) rotate(0.5deg) scale(0.99); }
            100% { transform: translate(0, 0) rotate(0deg) scale(1); }
        }
        @keyframes fire-colors {
            0% { color: #ff0000; }
            33% { color: #ff4400; }
            66% { color: #ff8800; }
            100% { color: #ff0000; }
        }
        @keyframes red-flash {
            0%, 100% { background-color: rgba(255,0,0,0.1); }
            50% { background-color: rgba(255,0,0,0.3); }
        }
        
        /* Fire particles for apocalyptic */
        .fire-container {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: -1;
            opacity: 0;
            transition: opacity 0.5s;
        }
        .fire-container.active {
            opacity: 0.3;
        }
        .particle {
            position: absolute;
            width: 4px;
            height: 4px;
            background: #ff4400;
            border-radius: 50%;
            animation: rise 2s infinite;
        }
        @keyframes rise {
            0% { transform: translateY(100vh) scale(0); opacity: 0; }
            50% { opacity: 1; }
            100% { transform: translateY(-100px) scale(1.5); opacity: 0; }
        }
    </style>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍆</text></svg>">
</head>
<body>
    <div class="fire-container" id="fire"></div>
    
    <h1>🍆 THE DONGOMETER 🍆</h1>
    <div class="subtitle">Real-time Donghouse Chaos Metrics</div>
    
    <div id="main-container">
        <div class="chaos-score" id="score">0.0</div>
        <div class="status-text" id="status">Loading...</div>
        
        <div class="metrics">
            <div class="metric">
                <div class="metric-value" id="chat5">0</div>
                <div class="metric-label">Messages (5m)</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="door10">0</div>
                <div class="metric-label">Door Events (10m)</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="pizza">0</div>
                <div class="metric-label">🍕 Pizza Count</div>
            </div>
        </div>
    </div>
    
    <script>
        let lastChaos = 0;
        let fireInterval;
        
        function createFireParticles() {
            const fire = document.getElementById('fire');
            fire.innerHTML = '';
            for(let i=0; i<50; i++) {
                const p = document.createElement('div');
                p.className = 'particle';
                p.style.left = Math.random() * 100 + '%';
                p.style.animationDelay = Math.random() * 2 + 's';
                p.style.animationDuration = (1 + Math.random() * 2) + 's';
                fire.appendChild(p);
            }
        }
        
        async function update() {
            try {
                const r = await fetch('/api/metrics');
                const d = await r.json();
                const score = d.chaos_score.toFixed(1);
                
                // Update score
                document.getElementById('score').textContent = score;
                
                // Determine chaos class
                let chaosClass = 'calm';
                if(d.chaos_score >= 81) chaosClass = 'apocalyptic';
                else if(d.chaos_score >= 61) chaosClass = 'demonic';
                else if(d.chaos_score >= 41) chaosClass = 'chaotic';
                else if(d.chaos_score >= 21) chaosClass = 'active';
                
                // Apply class to body for full-screen effects
                document.body.className = chaosClass;
                document.getElementById('main-container').className = chaosClass;
                
                // Fire particles for apocalyptic
                const fire = document.getElementById('fire');
                if(d.chaos_score >= 81) {
                    if(!fireInterval) {
                        createFireParticles();
                        fire.classList.add('active');
                        fireInterval = true;
                    }
                } else {
                    fire.classList.remove('active');
                    fireInterval = false;
                }
                
                // Status
                document.getElementById('status').textContent = d.status;
                
                // Metrics
                document.getElementById('chat5').textContent = d.chat_velocity_5min;
                document.getElementById('door10').textContent = d.door_events_10min;
                document.getElementById('pizza').textContent = d.pizza_count;
                
                // Alert on level up
                if(d.chaos_score >= 81 && lastChaos < 81) {
                    document.getElementById('status').textContent = '☠️ APOCALYPSE DETECTED ☠️';
                }
                
                lastChaos = d.chaos_score;
            } catch(e) {}
        }
        
        update();
        setInterval(update, 5000);
        createFireParticles();
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_metrics(self):
        metrics['chaos_score'] = calculate_chaos_score()
        metrics['last_updated'] = datetime.now().isoformat()
        
        now = datetime.now()
        
        # Check for Fenthouse lock first
        status = None
        try:
            import os
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
        
        # Dynamic status based on actual metrics (if not locked)
        score = metrics['chaos_score']
        pizza = metrics['pizza_count']
        
        if status is None:
            if score <= 20:
                status = '😴 CALM — The donghouse sleeps'
            elif score <= 40:
            if chat_5m > 10:
                status = '⚡ ACTIVE — Chat velocity rising'
            else:
                status = '⚡ ACTIVE — Normal operations'
            elif score <= 60:
            if pizza > 0:
                status = '🍕 CHAOTIC — Pizza\'s here'
            elif chat_5m > 20:
                status = '🗣️ CHAOTIC — Chat is fire'
            elif door_10m > 2:
                status = '🚪 CHAOTIC — Door activity high'
            else:
                status = '🔥 CHAOTIC — Chaos building'
            elif score <= 80:
            if pizza > 3:
                status = '👿 DEMONIC — Too much pizza'
            else:
                status = '👿 DEMONIC — Hardin needs a grader'
            else:
            status = '☠️ APOCALYPTIC — Gigglesgate 2.0'
        
        data = {
            'chaos_score': round(score, 1),
            'chat_velocity_5min': chat_5m,
            'chat_velocity_1hour': len(metrics['chat_velocity']),
            'door_events_10min': door_10m,
            'pizza_count': pizza,
            'last_updated': metrics['last_updated'],
            'status': status
        }
        self.send_json(data)
    
    def serve_history(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM hourly_stats 
            WHERE hour > datetime('now', '-24 hours')
            ORDER BY hour DESC
        ''')
        rows = [dict(zip([c[0] for c in cursor.description], row)) 
                for row in cursor.fetchall()]
        conn.close()
        self.send_json(rows)
    
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
        
        # Store in DB
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
