#!/usr/bin/env python3
"""
The Dongometer - Real-time Donghouse Chaos Metrics
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from collections import deque
import threading
import time

app = Flask(__name__)

# Configuration
DB_PATH = os.path.join(os.path.dirname(__file__), 'dongometer.db')
MAX_HISTORY = 1000  # Keep last 1000 events

# In-memory metrics (recent data)
metrics = {
    'chat_velocity': deque(maxlen=100),  # Messages per minute
    'door_events': deque(maxlen=50),     # Door open/close events
    'pizza_count': 0,
    'last_updated': None,
    'chaos_score': 0.0,  # 0-100 calculated score
}

def init_db():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Events table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            metric_type TEXT NOT NULL,
            value REAL,
            details TEXT
        )
    ''')
    
    # Hourly aggregates
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

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_chaos_score():
    """Calculate a chaos score based on recent activity"""
    score = 0.0
    
    # Chat velocity factor (0-40 points)
    if len(metrics['chat_velocity']) > 0:
        recent_msgs = sum(1 for t in metrics['chat_velocity'] 
                         if datetime.now() - t < timedelta(minutes=5))
        score += min(recent_msgs * 2, 40)
    
    # Door activity factor (0-30 points)
    if len(metrics['door_events']) > 0:
        recent_doors = sum(1 for t in metrics['door_events'] 
                          if datetime.now() - t < timedelta(minutes=10))
        score += min(recent_doors * 5, 30)
    
    # Time of day factor (0-20 points) - more chaotic at night
    hour = datetime.now().hour
    if 0 <= hour < 6:  # Late night
        score += 20
    elif 18 <= hour < 24:  # Evening
        score += 15
    elif 12 <= hour < 18:  # Afternoon
        score += 10
    else:  # Morning
        score += 5
    
    # Pizza bonus (0-10 points)
    if metrics['pizza_count'] > 0:
        score += min(metrics['pizza_count'] * 2, 10)
    
    return min(score, 100)

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/metrics')
def get_metrics():
    """Get current metrics as JSON"""
    # Update chaos score
    metrics['chaos_score'] = calculate_chaos_score()
    metrics['last_updated'] = datetime.now().isoformat()
    
    return jsonify({
        'chaos_score': round(metrics['chaos_score'], 1),
        'chat_velocity_5min': sum(1 for t in metrics['chat_velocity'] 
                                  if datetime.now() - t < timedelta(minutes=5)),
        'chat_velocity_1hour': len(metrics['chat_velocity']),
        'door_events_10min': sum(1 for t in metrics['door_events'] 
                                 if datetime.now() - t < timedelta(minutes=10)),
        'door_events_total': len(metrics['door_events']),
        'pizza_count': metrics['pizza_count'],
        'last_updated': metrics['last_updated'],
        'status': 'operational' if metrics['chaos_score'] > 0 else 'dormant'
    })

@app.route('/api/event', methods=['POST'])
def record_event():
    """Record a new event"""
    data = request.json
    event_type = data.get('type')
    value = data.get('value', 1)
    details = data.get('details', '')
    
    now = datetime.now()
    
    # Update in-memory metrics
    if event_type == 'chat_message':
        metrics['chat_velocity'].append(now)
    elif event_type == 'door_open':
        metrics['door_events'].append(now)
    elif event_type == 'door_close':
        metrics['door_events'].append(now)
    elif event_type == 'pizza':
        metrics['pizza_count'] += value
    elif event_type == 'reset_pizza':
        metrics['pizza_count'] = 0
    
    # Store in database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO events (metric_type, value, details) VALUES (?, ?, ?)',
        (event_type, value, details)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'chaos_score': calculate_chaos_score()})

@app.route('/api/history')
def get_history():
    """Get historical data"""
    hours = request.args.get('hours', 24, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM hourly_stats 
        WHERE hour > datetime('now', '-{} hours')
        ORDER BY hour DESC
    '''.format(hours))
    
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in rows])

@app.route('/api/leaderboard')
def get_leaderboard():
    """Get chaos leaderboard (most active times)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT hour, chaos_score, message_count, door_opens
        FROM hourly_stats
        ORDER BY chaos_score DESC
        LIMIT 10
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in rows])

def background_aggregator():
    """Background thread to aggregate hourly stats"""
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # Get current hour
            now = datetime.now()
            hour = now.replace(minute=0, second=0, microsecond=0)
            
            # Count events in last hour
            msg_count = sum(1 for t in metrics['chat_velocity'] 
                           if now - t < timedelta(hours=1))
            door_count = sum(1 for t in metrics['door_events'] 
                            if now - t < timedelta(hours=1))
            chaos = calculate_chaos_score()
            
            # Upsert hourly stats
            cursor.execute('''
                INSERT INTO hourly_stats (hour, message_count, door_opens, chaos_score)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(hour) DO UPDATE SET
                    message_count = excluded.message_count,
                    door_opens = excluded.door_opens,
                    chaos_score = excluded.chaos_score
            ''', (hour, msg_count, door_count, chaos))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Aggregator error: {e}")
        
        time.sleep(300)  # Run every 5 minutes

if __name__ == '__main__':
    init_db()
    
    # Start background aggregator
    aggregator_thread = threading.Thread(target=background_aggregator, daemon=True)
    aggregator_thread.start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
