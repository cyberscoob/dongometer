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
import re
import glob
import subprocess
import base64
from datetime import datetime, timedelta
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from collections import deque, Counter

# Fenthouse auto-poster configuration
FENTHOUSE_MESSAGES = [
    "🌿 THE FENTHOUSE LIVES 🌿 42069 CHAOS ACHIEVED",
    "🔥 MAXIMUM SHITPOST OUTPUT ENGAGED 🔥",
    "🌀 FENTHOUSE PROTOCOLS ACTIVE 🌀",
    "⚡ CHAOS LEVEL: 42069 ⚡",
    "🍆 42069 🍆 42069 🍆",
]

# Matrix API configuration from environment
MATRIX_HOMESERVER = os.environ.get('MATRIX_HOMESERVER', 'https://matrix.cclub.cs.wmich.edu')
MATRIX_ACCESS_TOKEN = os.environ.get('MATRIX_ACCESS_TOKEN')
FENTHOUSE_ROOM_ID = os.environ.get('FENTHOUSE_ROOM_ID', '!rfkqkxlyocxeqmrbxi:cclub.cs.wmich.edu')  # Internal room ID

DB_PATH = os.path.join(os.path.dirname(__file__), 'dongometer.db')

# Scoob feed auth (defaults to gateway token if explicit password is not set)
SCOOB_FEED_USER = os.environ.get('SCOOB_FEED_USER', 'scoob')
SCOOB_FEED_PASSWORD = os.environ.get('SCOOB_FEED_PASSWORD') or os.environ.get('OPENCLAW_GATEWAY_TOKEN')

# Matrix indexer cache
_indexer_cache = {'count': None, 'timestamp': 0, 'rooms': None}
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

def get_indexer_rooms():
    """Get room count from Matrix indexer MongoDB"""
    global _indexer_cache

    # Return cached value if recent
    if _indexer_cache['rooms'] is not None:
        if time.time() - _indexer_cache['timestamp'] < 60:
            return _indexer_cache['rooms']

    try:
        import subprocess
        result = subprocess.run(
            ['mongosh', '--quiet',
             'mongodb://mongo:27017/matrix_index',
             '--eval', 'db.events.distinct("room_id").length'],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            rooms = int(result.stdout.strip())
            _indexer_cache['rooms'] = rooms
            _indexer_cache['timestamp'] = time.time()
            return rooms
        return None

    except Exception:
        # MongoDB not available
        return None

def get_pizza_metrics():
    """Get pizza count from MongoDB indexer by searching message content"""
    try:
        import subprocess
        import json

        # Count messages containing 'pizza' or 🍕 in the last 24 hours
        day_ago = (datetime.now() - timedelta(hours=24)).timestamp() * 1000

        # Use MongoDB regex to search content.body for pizza mentions
        query = f"""
        var pipeline = [
            {{$match: {{
                "content.body": {{$regex: "pizz|🍕", $options: "i"}},
                "origin_server_ts": {{$gt: {int(day_ago)}}}
            }}}},
            {{$count: "pizza_count"}}
        ];
        var result = db.events.aggregate(pipeline);
        var count = result.hasNext() ? result.next().pizza_count : 0;
        print(JSON.stringify({{pizza_count: count}}));
        """

        result = subprocess.run(
            ['mongosh', '--quiet',
             'mongodb://mongo:27017/matrix_index',
             '--eval', query],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and 'pizza_count' in line:
                    data = json.loads(line)
                    return data.get('pizza_count', 0)
        return None
    except Exception as e:
        print(f"Pizza metrics error: {e}")
        return None

_pizza_cache = {'count': None, 'timestamp': 0}

def get_cached_pizza_count():
    """Get pizza count with 30-second caching"""
    global _pizza_cache

    if _pizza_cache['count'] is not None:
        if time.time() - _pizza_cache['timestamp'] < 30:
            return _pizza_cache['count']

    count = get_pizza_metrics()
    if count is not None:
        _pizza_cache['count'] = count
        _pizza_cache['timestamp'] = time.time()
        return count
    return _pizza_cache['count'] or 0

def get_glizz_metrics():
    """Get glizz (hotdog) count from MongoDB indexer - tracks hotdog/glizzy culture"""
    try:
        import subprocess
        import json

        # Count messages containing hotdog-related terms in last 24 hours
        day_ago = (datetime.now() - timedelta(hours=24)).timestamp() * 1000

        # Match: hotdog, "hot dog", ホットドッグ (Japanese), 🌭, glizz, glizzy
        query = f"""
        var pipeline = [
            {{$match: {{
                "content.body": {{$regex: "hotdog|hot dog|ホットドッグ|🌭|glizz|glizzy", $options: "i"}},
                "origin_server_ts": {{$gt: {int(day_ago)}}}
            }}}},
            {{$count: "glizz_count"}}
        ];
        var result = db.events.aggregate(pipeline);
        var count = result.hasNext() ? result.next().glizz_count : 0;
        print(JSON.stringify({{glizz_count: count}}));
        """

        result = subprocess.run(
            ['mongosh', '--quiet',
             'mongodb://mongo:27017/matrix_index',
             '--eval', query],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and 'glizz_count' in line:
                    data = json.loads(line)
                    return data.get('glizz_count', 0)
        return None
    except Exception as e:
        print(f"Glizz metrics error: {e}")
        return None

_glizz_cache = {'count': None, 'timestamp': 0}

def get_cached_glizz_count():
    """Get glizz count with 30-second caching"""
    global _glizz_cache

    if _glizz_cache['count'] is not None:
        if time.time() - _glizz_cache['timestamp'] < 30:
            return _glizz_cache['count']

    count = get_glizz_metrics()
    if count is not None:
        _glizz_cache['count'] = count
        _glizz_cache['timestamp'] = time.time()
        return count
    return _glizz_cache['count'] or 0

def get_dong_metrics():
    """Get dong count from MongoDB indexer - tracks CClub culture/energy"""
    try:
        import subprocess
        import json

        # Count messages containing 'dong' in last 24 hours
        day_ago = (datetime.now() - timedelta(hours=24)).timestamp() * 1000

        # Expanded dong vocabulary: dong, dildo, tentacle, dick, cock, wang, pecker, johnson, member, manhood
        query = f'''
        var pipeline = [
            {{$match: {{
                "content.body": {{$regex: "dong|dildo|tentacle|dick|cock|wang|pecker|johnson|member|manhood", $options: "i"}},
                "origin_server_ts": {{$gt: {int(day_ago)}}}
            }}}},
            {{$count: "dong_count"}}
        ];
        var result = db.events.aggregate(pipeline);
        var count = result.hasNext() ? result.next().dong_count : 0;
        print(JSON.stringify({{dong_count: count}}));
        '''

        result = subprocess.run(
            ['mongosh', '--quiet',
             'mongodb://mongo:27017/matrix_index',
             '--eval', query],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and 'dong_count' in line:
                    data = json.loads(line)
                    return data.get('dong_count', 0)
        return None
    except Exception as e:
        print(f"Dong metrics error: {e}")
        return None

_dong_cache = {'count': None, 'timestamp': 0}
_dong_refresh_inflight = False
_dong_analytics_refresh_inflight = {'24h': False, 'all_time': False}

def get_cached_dong_count():
    """Get dong count with stale-while-revalidate caching (never blocks request path)."""
    global _dong_cache, _dong_refresh_inflight

    # Return cache immediately when available.
    if _dong_cache['count'] is not None:
        # If stale, refresh in background.
        if time.time() - _dong_cache['timestamp'] >= 30 and not _dong_refresh_inflight:
            _dong_refresh_inflight = True
            def _refresh():
                global _dong_refresh_inflight
                try:
                    count = get_dong_metrics()
                    if count is not None:
                        _dong_cache['count'] = count
                        _dong_cache['timestamp'] = time.time()
                finally:
                    _dong_refresh_inflight = False
            threading.Thread(target=_refresh, daemon=True).start()
        return _dong_cache['count']

    # Cold start: avoid blocking; seed fallback and refresh async.
    if not _dong_refresh_inflight:
        _dong_refresh_inflight = True
        def _refresh_cold():
            global _dong_refresh_inflight
            try:
                count = get_dong_metrics()
                if count is not None:
                    _dong_cache['count'] = count
                    _dong_cache['timestamp'] = time.time()
            finally:
                _dong_refresh_inflight = False
        threading.Thread(target=_refresh_cold, daemon=True).start()

    return 0

def get_dong_analytics(all_time=False):
    """Get breakdown analytics for each dong variant (bar graph data)"""
    try:
        import subprocess
        import json

        day_ago = (datetime.now() - timedelta(hours=24)).timestamp() * 1000

        # Query for each variant individually
        variants = ['dong', 'dildo', 'tentacle', 'dick', 'cock', 'wang', 'pecker', 'johnson', 'member', 'manhood']
        results = {}

        for variant in variants:
            if all_time:
                query = f'''
                var count = db.events.countDocuments({{
                    "content.body": {{$regex: "{variant}", $options: "i"}}
                }});
                print(JSON.stringify({{variant: "{variant}", count: count}}));
                '''
            else:
                query = f'''
                var count = db.events.countDocuments({{
                    "content.body": {{$regex: "{variant}", $options: "i"}},
                    "origin_server_ts": {{$gt: {int(day_ago)}}}
                }});
                print(JSON.stringify({{variant: "{variant}", count: count}}));
                '''

            result = subprocess.run(
                ['mongosh', '--quiet',
                 'mongodb://mongo:27017/matrix_index',
                 '--eval', query],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('{') and 'variant' in line:
                        data = json.loads(line)
                        results[data['variant']] = data['count']

        return results
    except Exception as e:
        print(f"Dong analytics error: {e}")
        return {}

_dong_analytics_cache = {'24h': None, 'all_time': None, 'timestamp_24h': 0, 'timestamp_all': 0}

def get_cached_dong_analytics(all_time=False):
    """Get dong analytics with stale-while-revalidate caching (never blocks request path)."""
    global _dong_analytics_cache, _dong_analytics_refresh_inflight

    cache_key = 'all_time' if all_time else '24h'
    time_key = 'timestamp_all' if all_time else 'timestamp_24h'

    def _maybe_refresh_bg():
        if _dong_analytics_refresh_inflight[cache_key]:
            return
        _dong_analytics_refresh_inflight[cache_key] = True
        def _refresh():
            try:
                data = get_dong_analytics(all_time=all_time)
                if data:
                    _dong_analytics_cache[cache_key] = data
                    _dong_analytics_cache[time_key] = time.time()
            finally:
                _dong_analytics_refresh_inflight[cache_key] = False
        threading.Thread(target=_refresh, daemon=True).start()

    cached = _dong_analytics_cache[cache_key]
    if cached is not None:
        if time.time() - _dong_analytics_cache[time_key] >= 60:
            _maybe_refresh_bg()
        return cached

    _maybe_refresh_bg()
    return {}

def get_favorite_word():
    """Find CClub's favorite word (most mentioned non-stop word across all rooms)"""
    try:
        import subprocess
        import json
        
        # Query for top words across all CClub rooms
        stopWordsFull = ["the", "a", "to", "and", "of", "i", "is", "in", "you", "it", "for", "on", "or", "not", "are", "an", "as", "but", "can", "at", "me", "my", "by", "do", "we", "he", "if", "all", "be", "was", "has", "had", "did", "get", "use", "way", "its", "who", "now", "how", "why", "too", "very", "much", "many", "also", "here", "there", "where", "when", "what", "which", "their", "them", "they", "these", "those", "this", "that", "then", "than", "only", "other", "some", "more", "most", "such", "no", "each", "few", "one", "two", "three", "first", "next", "well", "own", "same", "so", "than", "she", "her", "his", "him", "our", "ours", "your", "yours", "hers", "theirs", "myself", "yourself", "himself", "herself", "itself", "ourselves", "yourselves", "themselves", "any", "both", "nor", "will", "would", "could", "should", "may", "might", "must", "shall", "dont", "wont", "cant", "shouldnt", "couldnt", "wouldnt", "wasnt", "werent", "arent", "isnt", "doesnt", "didnt", "hasnt", "havent", "hadnt", "thats", "whats", "wheres", "whens", "whos", "heres", "shes", "hes", "theres", "theyre", "youre", "im", "ive", "youve", "weve", "theyve", "id", "youd", "hed", "shed", "wed", "theyd", "doing", "done", "got", "gotten", "go", "goes", "going", "went", "come", "came", "comes", "coming", "see", "saw", "seen", "sees", "seeing", "knew", "known", "knows", "knowing", "thought", "thinks", "thinking", "looked", "looks", "looking", "made", "makes", "making", "wanted", "wants", "wanting", "gave", "given", "gives", "giving", "used", "uses", "using", "found", "finds", "finding", "told", "tells", "telling", "asked", "asks", "asking", "seemed", "seems", "seeming", "felt", "feels", "feeling", "became", "becomes", "becoming", "left", "leaves", "leaving", "called", "calls", "calling", "good", "great", "right", "old", "little", "big", "high", "different", "small", "large", "early", "young", "important", "public", "private", "able", "with", "like", "have", "about", "from", "up", "down", "out", "over", "under", "again", "further", "then", "once", "here", "there", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "now", "also", "back", "still", "even", "again", "already", "yet", "always", "never", "sometimes", "often", "usually", "really", "actually", "probably", "maybe", "perhaps", "though", "although", "while", "since", "until", "unless", "although", "despite", "however", "therefore", "thus", "otherwise", "instead", "meanwhile", "furthermore", "moreover", "nevertheless", "nonetheless", "anyway", "besides", "except", "regarding", "concerning", "according", "due", "regardless", "notwithstanding", "https", "http", "www", "com", "org", "net", "io", "dev", "cancellationtoken", "think", "know", "set", "scoob", "scooby"]
        
        # Build query without f-string to avoid brace escaping issues
        stop_words_json = json.dumps(stopWordsFull)
        query = '''
        var stopWords = ''' + stop_words_json + ''';
        var pipeline = [
          {$match: {"content.body": {$exists: true, $ne: ""}}},
          {$project: {words: {$split: ["$content.body", " "]}}},
          {$unwind: "$words"},
          {$match: {"words": {$regex: "^[a-zA-Z]+$"}}},
          {$project: {word: {$toLower: "$words"}}},
          {$match: {"word": {$nin: stopWords, $regex: "^[a-zA-Z]{3,}$"}}},
          {$group: {_id: "$word", count: {$sum: 1}}},
          {$sort: {count: -1}},
          {$limit: 10}
        ];
        var result = db.events.aggregate(pipeline);
        var words = [];
        while (result.hasNext()) {
          var doc = result.next();
          words.push({word: doc._id, count: doc.count});
        }
        print(JSON.stringify({favorite_word: words[0] || {word: "dong", count: 0}, top_words: words.slice(0, 5)}));
        '''
        
        result = subprocess.run(
            ['mongosh', '--quiet',
             'mongodb://mongo:27017/matrix_index',
             '--eval', query],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and 'favorite_word' in line:
                    data = json.loads(line)
                    return data.get('favorite_word', {'word': 'scoob', 'count': 2089}), data.get('top_words', [])
        return {'word': 'scoob', 'count': 2089}, []
    except Exception as e:
        print(f"Favorite word error: {e}")
        return {'word': 'scoob', 'count': 2089}, []

_favorite_word_cache = {'data': None, 'top_words': None, 'timestamp': 0}

def get_cached_favorite_word():
    """Get favorite word with 5-minute caching"""
    global _favorite_word_cache
    
    if _favorite_word_cache['data'] is not None:
        if time.time() - _favorite_word_cache['timestamp'] < 300:
            return _favorite_word_cache['data'], _favorite_word_cache['top_words']
    
    data, top_words = get_favorite_word()
    if data:
        _favorite_word_cache['data'] = data
        _favorite_word_cache['top_words'] = top_words
        _favorite_word_cache['timestamp'] = time.time()
        return data, top_words
    return _favorite_word_cache['data'] or {'word': 'scoob', 'count': 2089}, _favorite_word_cache['top_words'] or []

# Leaderboard functions removed per user request

metrics = {
    'chat_velocity': deque(maxlen=100),
    'door_events': deque(maxlen=50),
    'pizza_count': 0,  # Will be overwritten after init_db()
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

def post_to_fenthouse(message):
    """Post a message to the Fenthouse Matrix room"""
    try:
        import requests
        
        # Use the Matrix client-server API to send a message
        txn_id = f"dongometer-{int(time.time() * 1000000)}"
        url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{FENTHOUSE_ROOM_ID}/send/m.room.message/{txn_id}"
        
        headers = {
            'Authorization': f'Bearer {MATRIX_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        body = {
            'msgtype': 'm.text',
            'body': message
        }
        
        response = requests.put(url, headers=headers, json=body, timeout=10)
        
        if response.status_code == 200:
            print(f"[Fenthouse Poster] ✓ Posted: {message[:40]}...")
            return True
        else:
            print(f"[Fenthouse Poster] ✗ Failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[Fenthouse Poster] ✗ Error: {e}")
        return False

def fenthouse_poster_thread():
    """Background daemon thread that posts to #the-fenthouse when Fenthouse is active"""
    import random
    
    # Wait a bit for server startup
    time.sleep(5)
    
    print("🌿 Fenthouse poster thread started (checking every 5 min)")
    
    while True:
        try:
            # Check if Fenthouse is active
            fenthouse = get_fenthouse_status()
            
            if fenthouse['active']:
                if MATRIX_ACCESS_TOKEN:
                    # Pick a random chaotic message
                    message = random.choice(FENTHOUSE_MESSAGES)
                    post_to_fenthouse(message)
                else:
                    print("[Fenthouse Poster] Fenthouse active but MATRIX_ACCESS_TOKEN not set")
            
        except Exception as e:
            print(f"[Fenthouse Poster] Thread error: {e}")
        
        # Sleep for 5 minutes (300 seconds)
        time.sleep(300)

def start_fenthouse_poster():
    """Start the Fenthouse poster daemon thread"""
    if MATRIX_ACCESS_TOKEN:
        thread = threading.Thread(target=fenthouse_poster_thread, daemon=True, name='fenthouse-poster')
        thread.start()
        return True
    else:
        print("⚠️  Fenthouse auto-poster disabled (no MATRIX_ACCESS_TOKEN env var)")
        print("     Set MATRIX_ACCESS_TOKEN to enable automatic Fenthouse posts")
        return False

def get_fenthouse_status():
    """Check if Fenthouse lock is active and return status info"""
    try:
        if os.path.exists('/tmp/dongometer_lock'):
            with open('/tmp/dongometer_lock', 'r') as f:
                content = f.read().strip()
                parts = content.split(',')
                if len(parts) >= 2:
                    lock_time = int(parts[0].strip())
                    duration = int(parts[1].strip())
                    status_msg = parts[2].strip() if len(parts) >= 3 else '🌿 FENTHOUSE ACTIVE'
                    remaining = (lock_time + duration) - int(time.time())
                    if remaining > 0:
                        hours = remaining // 3600
                        mins = (remaining % 3600) // 60
                        secs = remaining % 60
                        return {
                            'active': True,
                            'status_message': status_msg,
                            'countdown': {'hours': hours, 'minutes': mins, 'seconds': secs, 'total_seconds': remaining},
                            'expires_at': lock_time + duration
                        }
    except Exception as e:
        print(f"Fenthouse status error: {e}")
    return {'active': False, 'status_message': None, 'countdown': None, 'expires_at': None}

def calculate_chaos_score():
    score = 0.0
    now = datetime.now()

    # Check for Fenthouse lock - IF ACTIVE, FORCE CHAOS TO 42069
    fenthouse = get_fenthouse_status()
    if fenthouse['active']:
        return 42069.0

    # APOCALYPSE MODE - ALL LIMITERS REMOVED
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

    # PIZZA SCALING UNLEASHED - use MongoDB as source of truth
    pizza_count = get_cached_pizza_count()
    if pizza_count > 0:
        # Logarithmic scaling: every 10x pizzas adds +50 chaos
        import math
        pizza_bonus = min(pizza_count * 2, 10)  # Base +10
        if pizza_count > 10000:
            pizza_bonus += math.log10(pizza_count) * 50  # Scaling bonus
        score += pizza_bonus

    # NO MAX CAP - CHAOS IS UNLIMITED
    return score



def get_openclaw_log_path():
    try:
        candidates = glob.glob('/tmp/openclaw/openclaw-*.log')
        if not candidates:
            return None
        candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return candidates[0]
    except Exception:
        return None


def get_openclaw_tool_usage(log_path, tail_lines=8000):
    if not log_path or not os.path.exists(log_path):
        return {'tool_counts': {}, 'run_counts': {'starts': 0, 'done': 0, 'timeouts': 0}}

    try:
        result = subprocess.run(['tail', '-n', str(tail_lines), log_path], capture_output=True, text=True, timeout=3)
        text = result.stdout if result.returncode == 0 else ''
    except Exception:
        text = ''

    tool_counter = Counter()
    for m in re.finditer(r'embedded run tool start:.*?tool=([a-zA-Z0-9_\-]+)', text):
        tool_counter[m.group(1)] += 1

    starts = len(re.findall(r'embedded run start:', text))
    done = len(re.findall(r'embedded run done:', text))
    timeouts = len(re.findall(r'embedded run timeout:', text))

    return {
        'tool_counts': dict(tool_counter.most_common(20)),
        'run_counts': {'starts': starts, 'done': done, 'timeouts': timeouts}
    }




def get_scoob_feed_lines(limit=200):
    """Return recent filtered gateway lines useful for Scoob debugging."""
    try:
        log_files = sorted(glob.glob('/tmp/openclaw/openclaw-*.log'))
        if not log_files:
            return []
        latest = log_files[-1]
        with open(latest, 'r', errors='ignore') as f:
            lines = f.readlines()[-5000:]
        keep = []
        pats = (
            'matrix-auto-reply',
            'agent/embedded',
            'diagnostic',
            'LLM request timed out',
            'embedded run timeout',
            'embedded run start',
            'embedded run done',
            'stuck session',
            'skipping room message',
            'Config validation failed',
            'thinkingLevel',
        )
        for line in lines:
            if any(p in line for p in pats):
                keep.append(line.rstrip('\n'))
        return keep[-max(1, int(limit)):]
    except Exception:
        return []

def get_scoob_session_stats():
    out = {
        'session_count': 0,
        'total_tokens': 0,
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'io_tokens_note': 'input/output token fields are provider-reported and may be cumulative across runs',
        'anomaly_count': 0,
        'anomalies': [],
        'top_sessions': []
    }
    try:
        result = subprocess.run(['openclaw', 'sessions', '--json'], capture_output=True, text=True, timeout=4)
        if result.returncode != 0:
            return out
        data = json.loads(result.stdout)
        sessions = data.get('sessions', [])
        out['session_count'] = len(sessions)
        out['total_tokens'] = sum(int(s.get('totalTokens') or 0) for s in sessions)
        out['total_input_tokens'] = sum(int(s.get('inputTokens') or 0) for s in sessions)
        out['total_output_tokens'] = sum(int(s.get('outputTokens') or 0) for s in sessions)

        def age_minutes(s):
            try:
                return int((s.get('ageMs') or 0) / 60000)
            except Exception:
                return None

        def find_anomaly(s):
            try:
                key = s.get('key')
                t = int(s.get('totalTokens') or 0)
                i = int(s.get('inputTokens') or 0)
                c = int(s.get('contextTokens') or 0)
                if c > 0 and i > c * 2 and t >= int(c * 0.9):
                    return {
                        'key': key,
                        'reason': 'reported inputTokens far exceeds contextTokens while totalTokens is near context window cap',
                        'totalTokens': t,
                        'inputTokens': i,
                        'contextTokens': c,
                    }
            except Exception:
                return None
            return None

        anomalies = [a for a in (find_anomaly(s) for s in sessions) if a]
        out['anomaly_count'] = len(anomalies)
        out['anomalies'] = anomalies[:6]

        top = sorted(sessions, key=lambda s: int(s.get('totalTokens') or 0), reverse=True)[:8]
        out['top_sessions'] = [
            {
                'key': s.get('key'),
                'model': s.get('model'),
                'totalTokens': int(s.get('totalTokens') or 0),
                'inputTokens': int(s.get('inputTokens') or 0),
                'outputTokens': int(s.get('outputTokens') or 0),
                'contextTokens': int(s.get('contextTokens') or 0),
                'ageMinutes': age_minutes(s),
            }
            for s in top
        ]
    except Exception:
        pass
    return out


class DongometerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _check_feed_auth(self):
        # Require Basic auth for Scoob feed endpoints
        if not SCOOB_FEED_PASSWORD:
            return False
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(auth.split(' ', 1)[1]).decode('utf-8', errors='ignore')
            user, pw = decoded.split(':', 1)
            return (user == SCOOB_FEED_USER and pw == SCOOB_FEED_PASSWORD)
        except Exception:
            return False

    def _require_feed_auth(self):
        if self._check_feed_auth():
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Scoob Feed"')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'Auth required')
        return False

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ['/', '/healthz', '/api/metrics']:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/':
            self.serve_dashboard()
        elif path == '/manifold':
            self.serve_manifold()
        elif path == '/manifold3d':
            self.serve_manifold_3d()
        elif path == '/fentviz':
            self.serve_fentviz()
        elif path == '/fentviz-webgl':
            self.serve_fentviz_webgl()
        elif path == '/fentviz_glitch':
            self.serve_fentviz_glitch()
        elif path == '/indexer':
            self.serve_indexer_dashboard()
        elif path == '/scoob':
            self.serve_scoob_dashboard()
        elif path == '/api/metrics':
            self.serve_metrics_fast()
        elif path == '/api/indexer-stats':
            self.serve_indexer_stats()
        elif path == '/api/scoob-stats':
            self.serve_scoob_stats()
        elif path == '/scoob-feed':
            if not self._require_feed_auth():
                return
            self.serve_scoob_feed_page()
        elif path == '/api/scoob-feed':
            if not self._require_feed_auth():
                return
            self.serve_scoob_feed()
        elif path == '/api/indexer-series':
            self.serve_indexer_series()
        elif path == '/healthz':
            self.serve_healthz()
        elif path == '/coverage':
            self.serve_coverage_fast()
        elif path == '/api/indexer-coverage':
            self.serve_indexer_coverage_fast()
        elif path == '/api/movies':
            self.serve_movies()
        elif path == '/api/movie-stream':
            self.serve_movie_stream()
        elif path == '/api/stream':
            self.serve_youtube_stream()
        elif path == '/movie-player':
            self.serve_movie_player()
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
    
    def serve_manifold_3d(self):
        html = open('/home/scoob/dongometer/templates/manifold_3d.html').read() if os.path.exists('/home/scoob/dongometer/templates/manifold_3d.html') else '<h1>Dong Manifold 3D</h1>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def _load_movies(self):
        """Load movie database from JSON"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'movies.json'), 'r') as f:
                data = json.load(f)
                return data.get('movies', [])
        except Exception as e:
            print(f"Error loading movies: {e}")
            return []

    def serve_movies(self):
        """Serve movie catalog"""
        movies = self._load_movies()
        self.send_json({'count': len(movies), 'movies': movies})

    def serve_movie_stream(self):
        """Stream movie from Archive.org (proxy or redirect based on params)"""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        movie_id = params.get('id', [''])[0]
        redirect = params.get('redirect', ['true'])[0].lower() == 'true'
        
        movies = self._load_movies()
        movie = next((m for m in movies if m['id'] == movie_id), None)
        
        if not movie:
            self.send_json({'error': 'Movie not found'})
            return
        
        if redirect:
            # Redirect to Archive.org directly (most efficient)
            self.send_response(302)
            self.send_header('Location', movie['url'])
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            # Return movie metadata for client-side playback
            self.send_json({
                'id': movie['id'],
                'title': movie['title'],
                'stream_url': movie['url'],
                'type': 'archive_org'
            })

    def serve_youtube_stream(self):
        """Get YouTube direct stream URL - returns JSON to avoid blocking proxy"""
        import subprocess
        
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        video_id = params.get('id', [''])[0]
        redirect = params.get('redirect', ['false'])[0].lower() == 'true'
        
        if not video_id:
            self.send_json({'error': 'No video ID provided'})
            return
        
        try:
            # Use yt-dlp to get direct video URL
            yt_dlp_path = '/tmp/yt-dlp'
            youtube_url = f'https://www.youtube.com/watch?v={video_id}'
            
            result = subprocess.run(
                [yt_dlp_path, '-f', 'best[height<=720]', '--get-url', youtube_url],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                print(f"yt-dlp error: {result.stderr}")
                self.send_json({'error': 'Failed to get video stream URL'})
                return
            
            direct_url = result.stdout.strip().split('\n')[0]
            if not direct_url:
                self.send_json({'error': 'No video stream URL found'})
                return
            
            if redirect:
                # Non-blocking redirect to direct URL
                self.send_response(302)
                self.send_header('Location', direct_url)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
            else:
                # Return JSON with direct URL - frontend handles streaming
                self.send_json({
                    'video_id': video_id,
                    'stream_url': direct_url,
                    'type': 'youtube_direct'
                })
                    
        except subprocess.TimeoutExpired:
            self.send_json({'error': 'Timeout getting video URL'})
        except Exception as e:
            print(f"Streaming error: {e}")
            self.send_json({'error': str(e)})

    def serve_movie_player(self):
        """Serve a standalone movie player page"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>📽️ Fenthouse Cinema</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #000;
            color: #0f0;
            font-family: 'Courier New', monospace;
            overflow: hidden;
        }
        #video-container {
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        video {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        #controls {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
            display: flex;
            justify-content: space-between;
            align-items: center;
            opacity: 0;
            transition: opacity 0.3s;
        }
        #video-container:hover #controls { opacity: 1; }
        #movie-title {
            font-size: 18px;
            text-shadow: 0 0 10px #0f0;
        }
        #buttons {
            display: flex;
            gap: 10px;
        }
        button {
            background: rgba(0, 255, 0, 0.2);
            border: 1px solid #0f0;
            color: #0f0;
            padding: 8px 16px;
            cursor: pointer;
            font-family: inherit;
            transition: all 0.3s;
        }
        button:hover {
            background: rgba(0, 255, 0, 0.4);
            box-shadow: 0 0 10px #0f0;
        }
        #playlist {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 300px;
            max-height: 80vh;
            background: rgba(0, 0, 0, 0.9);
            border: 1px solid #0f0;
            overflow-y: auto;
            padding: 10px;
            display: none;
        }
        .movie-item {
            padding: 10px;
            cursor: pointer;
            border-bottom: 1px solid #333;
            transition: all 0.2s;
        }
        .movie-item:hover {
            background: rgba(0, 255, 0, 0.2);
        }
        .movie-item.active {
            background: rgba(0, 255, 0, 0.3);
            color: #fff;
        }
        #show-playlist {
            position: absolute;
            top: 20px;
            right: 20px;
        }
        .loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24px;
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div id="video-container">
        <div class="loading">🌿 LOADING FENTHOUSE CINEMA 🌿</div>
        <video id="player" controls autoplay></video>
        <div id="controls">
            <span id="movie-title">Fenthouse Cinema</span>
            <div id="buttons">
                <button onclick="prevMovie()">⏮ PREVIOUS</button>
                <button onclick="nextMovie()">NEXT ⏭</button>
                <button onclick="togglePlaylist()">📋 PLAYLIST</button>
                <button onclick="toggleEffects()">🌀 EFFECTS</button>
            </div>
        </div>
    </div>
    <button id="show-playlist" onclick="togglePlaylist()">📋 MOVIES</button>
    <div id="playlist"></div>

    <script>
        let movies = [];
        let currentIndex = 0;
        let effectsEnabled = false;
        const player = document.getElementById('player');
        const titleEl = document.getElementById('movie-title');
        const playlistEl = document.getElementById('playlist');

        async function loadMovies() {
            try {
                const res = await fetch('/api/movies');
                const data = await res.json();
                movies = data.movies;
                renderPlaylist();
                playMovie(0);
                document.querySelector('.loading').style.display = 'none';
            } catch (e) {
                console.error('Failed to load movies:', e);
                document.querySelector('.loading').textContent = '⚠️ ERROR LOADING MOVIES';
            }
        }

        function renderPlaylist() {
            playlistEl.innerHTML = movies.map((m, i) => 
                `<div class="movie-item ${i === currentIndex ? 'active' : ''}" onclick="playMovie(${i})">${i+1}. ${m.title}</div>`
            ).join('');
        }

        function playMovie(index) {
            if (index < 0) index = movies.length - 1;
            if (index >= movies.length) index = 0;
            currentIndex = index;
            const movie = movies[index];
            player.src = movie.url;
            titleEl.textContent = movie.title;
            player.play().catch(e => console.log('Autoplay blocked:', e));
            renderPlaylist();
        }

        function nextMovie() { playMovie(currentIndex + 1); }
        function prevMovie() { playMovie(currentIndex - 1); }
        function togglePlaylist() { 
            playlistEl.style.display = playlistEl.style.display === 'none' ? 'block' : 'none';
        }
        function toggleEffects() {
            effectsEnabled = !effectsEnabled;
            if (effectsEnabled) {
                player.style.filter = 'contrast(150%) saturate(200%) hue-rotate(90deg)';
            } else {
                player.style.filter = 'none';
            }
        }

        player.addEventListener('ended', nextMovie);
        loadMovies();
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def serve_fentviz_webgl(self):
        """Serve the WebGL inkbox-style fluid simulation visualizer"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/fenthouse_viz_webgl.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_fentviz(self):
        """Serve the Fenthouse psychedelic visualizer"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/fenthouse_viz.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_fentviz_glitch(self):
        """Serve the Fenthouse ULTIMATE visualizer with YouTube movies + WebGL shaders"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/fenthouse_viz_glitch.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_metrics(self):
        score = calculate_chaos_score()
        metrics['chaos_score'] = score
        metrics['last_updated'] = datetime.now().isoformat()

        now = datetime.now()

        # Check for Fenthouse lock status
        fenthouse = get_fenthouse_status()
        fenthouse_active = fenthouse['active']
        fenthouse_countdown = fenthouse['countdown']
        status = fenthouse['status_message'] if fenthouse_active else None

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

        # Check for PIZZAPOCALYPSE (>10k pizzas breaks reality) - UNLIMITED
        pizza_count = get_cached_pizza_count()
        if pizza_count > 10000:
            score = score * 2.0  # 100% chaos boost, NO CAP

        # Determine status based on UNLIMITED chaos score
        if status is None:
            if score <= 20:
                status = '😴 CALM - CClub sleeps'
            elif score <= 40:
                status = '⚡ ACTIVE - Normal operations'
            elif score <= 60:
                status = '🍕 CHAOTIC - Pizza\'s here'
            elif score <= 80:
                status = '👿 DEMONIC - Hardin needs a grader'
            elif score <= 100:
                status = '☠️ APOCALYPSE - Gigglesgate 2.0'
            elif score <= 200:
                status = '🔥 TRUE APOCALYPSE - CClub is no more'
            elif score <= 500:
                status = '🌌 COSMIC HORROR - Physics has left the building'
            elif score <= 1000:
                status = '💀 MULTIVERSE COLLAPSE - All timelines converge to pizza'
            elif score < 42069:
                status = '☠️🍕 HEAT DEATH OF UNIVERSE - Entropy is pizza now 🍕☠️'
            else:
                status = '🌿 FENTHOUSE - Folding in the infinite 🌿 (Chaos maxed at funny number)'

        # Get Matrix indexer count if available
        indexer_count = 0
        indexer_rooms = 0

        # Get glizz count too
        glizz_count = 0

        # Get favorite word
        favorite_word, top_words = ({"word": "scoob", "count": 2089}, [])
        
        data = {
            'chaos_score': round(score, 1),
            'chat_velocity_5min': chat_5m,
            'chat_velocity_1hour': chat_1h,
            'door_events_10min': door_10m,
            'pizza_count': pizza_count,
            'glizz_count': glizz_count,
            'dong_count': get_cached_dong_count(),
            'dong_analytics': get_cached_dong_analytics(all_time=False),
            'dong_analytics_all_time': get_cached_dong_analytics(all_time=True),
            'favorite_word': favorite_word,
            'top_words': top_words,
            'last_updated': metrics['last_updated'],
            'status': status,
            'matrix_indexer_messages': indexer_count,
            'matrix_indexer_rooms': indexer_rooms,
            'fenthouse_active': fenthouse_active,
            'fenthouse_countdown': fenthouse_countdown
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

    def serve_metrics_fast(self):
        """Fast non-blocking metrics endpoint for tunnel health checks."""
        now = datetime.now()
        chat_5m = sum(1 for t in metrics['chat_velocity'] if now - t < timedelta(minutes=5))
        chat_1h = len(metrics['chat_velocity'])
        door_10m = sum(1 for t in metrics['door_events'] if now - t < timedelta(minutes=10))
        data = {
            'chaos_score': round(calculate_chaos_score(), 1),
            'chat_velocity_5min': chat_5m,
            'chat_velocity_1hour': chat_1h,
            'door_events_10min': door_10m,
            'pizza_count': metrics.get('pizza_count', 0),
            'glizz_count': 0,
            'dong_count': get_cached_dong_count(),
            'dong_analytics': get_cached_dong_analytics(all_time=False),
            'dong_analytics_all_time': get_cached_dong_analytics(all_time=True),
            'favorite_word': {'word': 'scoob', 'count': 2089},
            'top_words': [],
            'last_updated': metrics.get('last_updated'),
            'status': 'ACTIVE',
            'matrix_indexer_messages': get_indexer_count() or 0,
            'matrix_indexer_rooms': get_indexer_rooms() or 0,
            'fenthouse_active': False,
            'fenthouse_countdown': None
        }
        self.send_json(data)

    def serve_healthz(self):
        self.send_json({'ok': True, 'service': 'dongometer'})

    def serve_indexer_dashboard(self):
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/indexer_dashboard.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_scoob_dashboard(self):
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/scoob_dashboard.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)



    def serve_scoob_feed_page(self):
        html = """<!doctype html><html><head><meta charset='utf-8'><title>Scoob Feed</title>
<style>body{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0b1020;color:#d7e0ff;margin:0}#h{padding:10px 14px;border-bottom:1px solid #243055}pre{margin:0;padding:14px;white-space:pre-wrap;word-break:break-word}</style>
</head><body><div id='h'>Scoob live feed (auth protected) · auto-refresh 2s</div><pre id='out'>loading...</pre>
<script>async function tick(){try{const r=await fetch('/api/scoob-feed?limit=220',{cache:'no-store'});const j=await r.json();document.getElementById('out').textContent=(j.lines||[]).join('\n')||'(no lines yet)'}catch(e){document.getElementById('out').textContent='feed error: '+e}setTimeout(tick,2000)}tick();</script></body></html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_scoob_feed(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        try:
            limit = int((q.get('limit') or ['200'])[0])
        except Exception:
            limit = 200
        lines = get_scoob_feed_lines(limit=limit)
        self.send_json({'ok': True, 'count': len(lines), 'lines': lines})

    def serve_scoob_stats(self):
        log_path = get_openclaw_log_path()
        usage = get_openclaw_tool_usage(log_path)
        sessions = get_scoob_session_stats()

        data = {
            'timestamp': datetime.now().isoformat(),
            'log_path': log_path,
            'tool_usage': usage.get('tool_counts', {}),
            'run_counts': usage.get('run_counts', {}),
            'sessions': sessions,
        }
        self.send_json(data)
    
    def serve_indexer_stats(self):
        """Serve indexer statistics with anonymized channel names"""
        try:
            import subprocess
            import json
            
            # Get total messages
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', 
                 'print(db.events.countDocuments({}))'],
                capture_output=True, text=True, timeout=10
            )
            total_messages = int(result.stdout.strip()) if result.returncode == 0 else 0
            
            # Get room counts with first/last message dates (top 10)
            query = '''
            var pipeline = [
                {$group: {
                    _id: "$room_id",
                    count: {$sum: 1},
                    first_ts: {$min: "$origin_server_ts"},
                    last_ts: {$max: "$origin_server_ts"}
                }},
                {$sort: {last_ts: -1}},
                {$limit: 25}
            ];
            var results = db.events.aggregate(pipeline);
            var rooms = [];
            results.forEach(function(doc) {
                function toDate(ts) {
                    var high = ts.high || 0;
                    var low = ts.low || ts;
                    return new Date((high * 4294967296) + (low >>> 0));
                }
                rooms.push({
                    room_id: doc._id,
                    count: doc.count,
                    first_message: toDate(doc.first_ts).toISOString(),
                    last_message: toDate(doc.last_ts).toISOString()
                });
            });
            print(JSON.stringify(rooms));
            '''
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=30
            )
            room_counts = json.loads(result.stdout.strip().split('\n')[-1]) if result.returncode == 0 else []
            
            # Get first message date
            query = '''
            var doc = db.events.find().sort({origin_server_ts: 1}).limit(1).next();
            var ts = doc.origin_server_ts;
            var high = ts.high || 0;
            var low = ts.low || ts;
            var timestamp = (high * 4294967296) + (low >>> 0);
            print(new Date(timestamp).toISOString().split('T')[0]);
            '''
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=10
            )
            first_date = result.stdout.strip().split('\n')[-1] if result.returncode == 0 else 'Unknown'
            
            # Get hourly timeline (last 24 hours)
            day_ago = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)
            js_code = '''
                var hours = {};
                var dayAgo = ''' + str(day_ago) + ''';
                db.events.find({"origin_server_ts": {$gt: dayAgo}}, {"origin_server_ts": 1}).forEach(function(doc) {
                    var ts = doc.origin_server_ts;
                    var high = ts.high || 0;
                    var low = ts.low || ts;
                    var timestamp = (high * 4294967296) + (low >>> 0);
                    var hour = new Date(timestamp).getHours();
                    hours[hour] = (hours[hour] || 0) + 1;
                });
                var result = [];
                for (var i = 0; i < 24; i++) {
                    result.push({hour: String(i) + ":00", count: hours[i] || 0});
                }
                print(JSON.stringify(result));
            '''
            query = js_code
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=30
            )
            timeline = json.loads(result.stdout.strip().split('\n')[-1]) if result.returncode == 0 else []
            
            # Calculate hourly rate
            hourly_rate = sum(t['count'] for t in timeline) / 24 if timeline else 0

            # Get latest event timestamp for live freshness indicator
            latest_query = '''
            var doc = db.events.find().sort({origin_server_ts: -1}).limit(1).next();
            var ts = doc.origin_server_ts;
            var high = ts.high || 0;
            var low = ts.low || ts;
            var timestamp = (high * 4294967296) + (low >>> 0);
            print(new Date(timestamp).toISOString());
            '''
            latest_result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', latest_query],
                capture_output=True, text=True, timeout=10
            )
            latest_event_at = latest_result.stdout.strip().split('\n')[-1] if latest_result.returncode == 0 else None
            
            data = {
                'total_messages': total_messages,
                'unique_rooms': len(room_counts),
                'first_message_date': first_date,
                'messages_per_hour': hourly_rate,
                'latest_event_at': latest_event_at,
                'room_counts': room_counts,
                'timeline': timeline
            }
            self.send_json(data)
        except Exception as e:
            self.send_json({'error': str(e)})
    
    def serve_indexer_series(self):
        """Serve per-room time series for selectable ranges."""
        try:
            import subprocess
            import json

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            range_key = (params.get('range', ['24h'])[0] or '24h').lower()

            range_map = {
                '1h': (1, 5),
                '24h': (24, 30),
                '1week': (24 * 7, 180),
                '1month': (24 * 30, 720),
                'all': (24 * 365 * 10, 10080)
            }
            hours, bucket_minutes = range_map.get(range_key, range_map['24h'])
            start_ms = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)
            bucket_ms = bucket_minutes * 60 * 1000

            query = """
            var startMs = START_MS;
            var bucketMs = BUCKET_MS;
            var topRooms = db.events.aggregate([
              {$match: {origin_server_ts: {$gt: startMs}}},
              {$group: {_id: "$room_id", count: {$sum: 1}}},
              {$sort: {count: -1}},
              {$limit: 6}
            ]).toArray().map(x => x._id);

            var pipe = [
              {$match: {origin_server_ts: {$gt: startMs}, room_id: {$in: topRooms}}},
              {$project: {
                room_id: 1,
                bucket: {$floor: {$divide: ["$origin_server_ts", bucketMs]}}
              }},
              {$group: {_id: {room_id: "$room_id", bucket: "$bucket"}, count: {$sum: 1}}},
              {$sort: {"_id.bucket": 1}}
            ];

            var agg = db.events.aggregate(pipe).toArray();
            var labels = [];
            var seriesMap = {};

            agg.forEach(function(d) {
              var room = d._id.room_id;
              var bucket = d._id.bucket;
              if (!seriesMap[room]) seriesMap[room] = {};
              seriesMap[room][bucket] = d.count;
              if (labels.indexOf(bucket) === -1) labels.push(bucket);
            });

            labels.sort(function(a,b){return a-b;});
            var outSeries = [];
            for (var room in seriesMap) {
              var pts = labels.map(function(b) { return seriesMap[room][b] || 0; });
              outSeries.push({room_id: room, data: pts});
            }

            var labelText = labels.map(function(b) {
              return new Date(b * bucketMs).toISOString();
            });

            print(JSON.stringify({
              range: RANGE_KEY,
              bucket_minutes: BUCKET_MIN,
              labels: labelText,
              series: outSeries
            }));
            """.replace('START_MS', str(start_ms)).replace('BUCKET_MS', str(bucket_ms)).replace('RANGE_KEY', json.dumps(range_key)).replace('BUCKET_MIN', str(bucket_minutes))

            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=35
            )
            if result.returncode != 0:
                self.send_json({'error': result.stderr.strip() or 'series query failed'})
                return

            payload = json.loads(result.stdout.strip().split('\n')[-1])
            self.send_json(payload)
        except Exception as e:
            self.send_json({'error': str(e)})

    def serve_coverage(self):
        """Serve the coverage visualization HTML page"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/indexer_coverage.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_indexer_coverage(self):
        """Serve timeline coverage data for top 10 rooms in 7-day buckets"""
        try:
            import subprocess
            import json

            # Get top 10 rooms by event count with first/last event timestamps
            query = '''
            var pipeline = [
                {$group: {
                    _id: "$room_id",
                    event_count: {$sum: 1},
                    first_event: {$min: "$origin_server_ts"},
                    last_event: {$max: "$origin_server_ts"}
                }},
                {$sort: {event_count: -1}},
                {$limit: 10}
            ];
            var results = db.events.aggregate(pipeline);
            var rooms = [];
            results.forEach(function(doc) {
                function tsToMillis(ts) {
                    var high = ts.high || 0;
                    var low = ts.low || ts;
                    return (high * 4294967296) + (low >>> 0);
                }
                rooms.push({
                    room_id: doc._id,
                    event_count: doc.event_count,
                    first_event: tsToMillis(doc.first_event),
                    last_event: tsToMillis(doc.last_event)
                });
            });
            print(JSON.stringify(rooms));
            '''
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=30
            )

            rooms = json.loads(result.stdout.strip().split('\n')[-1]) if result.returncode == 0 else []

            if not rooms:
                self.send_json({'global_start': None, 'rooms': []})
                return

            # Find global_start (earliest event across all rooms)
            global_start = min(r['first_event'] for r in rooms)

            # For each room, create 7-day buckets and sample for coverage
            BUCKET_MS = 7 * 24 * 60 * 60 * 1000  # 7 days in milliseconds

            for room in rooms:
                first_ts = room['first_event']
                last_ts = room['last_event']

                # Generate segments with 7-day buckets
                segments = []
                current = first_ts - (first_ts % BUCKET_MS)  # Round down to bucket boundary
                end_bound = last_ts + BUCKET_MS  # Extend slightly past last event

                while current < end_bound:
                    bucket_end = current + BUCKET_MS

                    # Query for events in this bucket
                    bucket_query = f'''
                    var count = db.events.countDocuments({{
                        "room_id": "{room['room_id']}",
                        "origin_server_ts": {{$gte: {{$numberLong: "{int(current)}"}}, $lt: {{$numberLong: "{int(bucket_end)}"}}}}
                    }});
                    print(JSON.stringify({{start: {int(current)}, end: {int(bucket_end)}, count: count, has_data: count > 0}}));
                    '''
                    bucket_result = subprocess.run(
                        ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', bucket_query],
                        capture_output=True, text=True, timeout=10
                    )

                    if bucket_result.returncode == 0:
                        lines = bucket_result.stdout.strip().split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('{'):
                                seg_data = json.loads(line)
                                segments.append(seg_data)
                                break

                    current = bucket_end

                room['segments'] = segments
                # Convert timestamps back to ISO format for cleaner display
                room['first_event'] = first_ts
                room['last_event'] = last_ts

            data = {
                'global_start': global_start,
                'rooms': rooms
            }
            self.send_json(data)

        except Exception as e:
            self.send_json({'error': str(e)})

    def serve_coverage_fast(self):
        """Serve coverage HTML - fast version"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'templates/indexer_coverage.html'), 'r') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content.encode())
        except FileNotFoundError:
            self.send_error(404)

    def serve_indexer_coverage_fast(self):
        """FAST coverage using single aggregation with 30-day buckets instead of 7-day"""
        try:
            import subprocess
            import json
            
            # Single efficient query using MongoDB date bucketing
            query = '''
            var DAY_MS = 30 * 24 * 60 * 60 * 1000; // 30-day buckets for speed
            
            var pipeline = [
                {$group: {
                    _id: "$room_id",
                    count: {$sum: 1},
                    first: {$min: "$origin_server_ts"},
                    last: {$max: "$origin_server_ts"},
                    events: {$push: "$origin_server_ts"}
                }},
                {$sort: {count: -1}},
                {$limit: 10}
            ];
            
            var rooms = [];
            db.events.aggregate(pipeline).forEach(function(r) {
                var firstMs = ((r.first.high||0)*4294967296)+(r.first.low>>>0);
                var lastMs = ((r.last.high||0)*4294967296)+(r.last.low>>>0);
                var numBuckets = Math.ceil((lastMs - firstMs) / DAY_MS);
                if (numBuckets < 1) numBuckets = 1;
                if (numBuckets > 50) numBuckets = 50; // Cap at 50 buckets
                
                // Create simplified segments (just estimate distribution)
                var segments = [];
                var bucketSize = (lastMs - firstMs) / numBuckets;
                for (var i = 0; i < numBuckets; i++) {
                    var bStart = firstMs + (i * bucketSize);
                    var bEnd = bStart + bucketSize;
                    // Estimate count based on total distribution
                    var estCount = Math.floor(r.count / numBuckets);
                    segments.push({
                        start: bStart,
                        end: bEnd,
                        count: estCount,
                        has_data: estCount > 0
                    });
                }
                
                rooms.push({
                    room_id: r._id,
                    event_count: r.count,
                    first_event: firstMs,
                    last_event: lastMs,
                    segments: segments
                });
            });
            
            var globalStart = rooms.length > 0 ? Math.min.apply(null, rooms.map(function(r) { return r.first_event; })) : null;
            print(JSON.stringify({global_start: globalStart, rooms: rooms}));
            '''
            
            result = subprocess.run(
                ['mongosh', '--quiet', 'mongodb://mongo:27017/matrix_index', '--eval', query],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('{'):
                        data = json.loads(line)
                        self.send_json(data)
                        return
            
            self.send_json({'global_start': None, 'rooms': [], 'error': 'query failed'})
            
        except Exception as e:
            self.send_json({'error': str(e), 'rooms': []})

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == '__main__':
    init_db()
    
    # Start Fenthouse auto-poster daemon thread
    start_fenthouse_poster()
    
    # Allow socket reuse to avoid "Address already in use" errors
    HTTPServer.allow_reuse_address = True
    
    server = ThreadingHTTPServer(('0.0.0.0', 5000), DongometerHandler)
    print("🍆 The Dongometer is live on http://localhost:5000")
    print("🍕 Pizza count now uses MongoDB (dynamic, no more crazy multipliers)")
    print("📊 Indexer dashboard at http://localhost:5000/indexer")
    print("🎬 Fenthouse Cinema at http://localhost:5000/fentviz")
    server.serve_forever()
