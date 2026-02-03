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

def get_cached_dong_count():
    """Get dong count with 30-second caching"""
    global _dong_cache

    if _dong_cache['count'] is not None:
        if time.time() - _dong_cache['timestamp'] < 30:
            return _dong_cache['count']

    count = get_dong_metrics()
    if count is not None:
        _dong_cache['count'] = count
        _dong_cache['timestamp'] = time.time()
        return count
    return _dong_cache['count'] or 0

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
    """Get dong analytics with 60-second caching"""
    global _dong_analytics_cache
    
    cache_key = 'all_time' if all_time else '24h'
    time_key = 'timestamp_all' if all_time else 'timestamp_24h'
    
    if _dong_analytics_cache[cache_key] is not None:
        if time.time() - _dong_analytics_cache[time_key] < 60:
            return _dong_analytics_cache[cache_key]
    
    data = get_dong_analytics(all_time=all_time)
    if data:
        _dong_analytics_cache[cache_key] = data
        _dong_analytics_cache[time_key] = time.time()
        return data
    return _dong_analytics_cache[cache_key] or {}

def get_favorite_word():
    """Find CClub's favorite word (most mentioned non-stop word across all rooms)"""
    try:
        import subprocess
        import json
        
        # Query for top words across all CClub rooms
        stopWordsFull = ["the", "a", "to", "and", "of", "i", "is", "in", "you", "it", "for", "on", "or", "not", "are", "an", "as", "but", "can", "at", "me", "my", "by", "do", "we", "he", "if", "all", "be", "was", "has", "had", "did", "get", "use", "way", "its", "who", "now", "how", "why", "too", "very", "much", "many", "also", "here", "there", "where", "when", "what", "which", "their", "them", "they", "these", "those", "this", "that", "then", "than", "only", "other", "some", "more", "most", "such", "no", "each", "few", "one", "two", "three", "first", "next", "well", "own", "same", "so", "than", "she", "her", "his", "him", "our", "ours", "your", "yours", "hers", "theirs", "myself", "yourself", "himself", "herself", "itself", "ourselves", "yourselves", "themselves", "any", "both", "nor", "will", "would", "could", "should", "may", "might", "must", "shall", "dont", "wont", "cant", "shouldnt", "couldnt", "wouldnt", "wasnt", "werent", "arent", "isnt", "doesnt", "didnt", "hasnt", "havent", "hadnt", "thats", "whats", "wheres", "whens", "whos", "heres", "shes", "hes", "theres", "theyre", "youre", "im", "ive", "youve", "weve", "theyve", "id", "youd", "hed", "shed", "wed", "theyd", "doing", "done", "got", "gotten", "go", "goes", "going", "went", "come", "came", "comes", "coming", "see", "saw", "seen", "sees", "seeing", "knew", "known", "knows", "knowing", "thought", "thinks", "thinking", "looked", "looks", "looking", "made", "makes", "making", "wanted", "wants", "wanting", "gave", "given", "gives", "giving", "used", "uses", "using", "found", "finds", "finding", "told", "tells", "telling", "asked", "asks", "asking", "seemed", "seems", "seeming", "felt", "feels", "feeling", "became", "becomes", "becoming", "left", "leaves", "leaving", "called", "calls", "calling", "good", "great", "right", "old", "little", "big", "high", "different", "small", "large", "early", "young", "important", "public", "private", "able", "with", "like", "have", "about", "from", "up", "down", "out", "over", "under", "again", "further", "then", "once", "here", "there", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "now", "also", "back", "still", "even", "again", "already", "yet", "always", "never", "sometimes", "often", "usually", "really", "actually", "probably", "maybe", "perhaps", "though", "although", "while", "since", "until", "unless", "although", "despite", "however", "therefore", "thus", "otherwise", "instead", "meanwhile", "furthermore", "moreover", "nevertheless", "nonetheless", "anyway", "besides", "except", "regarding", "concerning", "according", "due", "regardless", "notwithstanding", "https", "http", "www", "com", "org", "net", "io", "dev"]
        
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

        # Check for Fenthouse lock and calculate countdown
        status = None
        fenthouse_countdown = None
        try:
            if os.path.exists('/tmp/dongometer_lock'):
                with open('/tmp/dongometer_lock', 'r') as f:
                    lines = f.readlines()
                    if len(lines) >= 3:
                        lock_time = int(lines[0].strip())
                        duration = int(lines[1].strip())
                        lock_status = lines[2].strip()
                        expires_at = lock_time + duration
                        remaining = expires_at - int(now.timestamp())
                        if remaining > 0:
                            status = lock_status
                            hours = remaining // 3600
                            mins = (remaining % 3600) // 60
                            secs = remaining % 60
                            fenthouse_countdown = {'hours': hours, 'minutes': mins, 'seconds': secs, 'total_seconds': remaining}
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
        indexer_count = get_indexer_count()
        indexer_rooms = get_indexer_rooms()

        # Get glizz count too
        glizz_count = get_cached_glizz_count()

        # Get favorite word
        favorite_word, top_words = get_cached_favorite_word()
        
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
    print("🍕 Pizza count now uses MongoDB (dynamic, no more crazy multipliers)")
    server.serve_forever()
