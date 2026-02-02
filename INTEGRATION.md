# Dongometer Integration Guide

## Quick Start: Webhook Style (Option 2)

### 1. Matrix Bot Integration

Add this to your Matrix bot's message handler:

```python
# At the top of your bot file
from webhook_integration import process_matrix_message

# In your message handler
def on_message(event):
    sender = event.sender
    message = event.content.body
    room = event.room_id
    
    # Send to Dongometer
    triggered = process_matrix_message(sender, message, room)
    if triggered:
        print(f"[Dongometer] Events: {triggered}")
```

### 2. Shell Script Hook (Alternative)

Use `matrix_hook.sh` from any script:

```bash
# Call when message received
./matrix_hook.sh "@shaggy:cclub.cs.wmich.edu" "pizza is here!" "#donghouse"
```

### 3. Auto-Detect Keywords

**Pizza Detection:**
- "pizza" → +1 per occurrence
- "🍕" emoji → +1 per emoji
- "pizzatime" → +1

**Door Detection:**
- "door open" / "door opened" / "door unlock"
- "🚪" emoji

**Chaos Boost (2x message weight):**
- "chaos", "dong", "apocalyptic"
- "hardin needs" (grader desperation)
- "gigglesgate"

### 4. Door Sensor Webhook

Physical door sensor → POST to Dongometer:

```bash
curl -X POST http://localhost:5000/api/event \
  -d '{"type": "door_open", "details": "RFID badge scan"}'
```

### 5. Pizza Button (Physical or Chat Command)

```bash
# Big increment
curl -X POST http://localhost:5000/api/event \
  -d '{"type": "pizza", "value": 9001, "details": "aerospice chaos protocol"}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard HTML |
| `/api/metrics` | GET | Current chaos data JSON |
| `/api/event` | POST | Record event |
| `/api/history` | GET | Historical data |

## Event Types

- `chat_message` - General chat activity
- `pizza` - Pizza arrival/count
- `door_open` - Door opened
- `door_close` - Door closed
- `reset_pizza` - Reset counter (morning after)

## Testing

```bash
# Test pizza
curl -X POST http://localhost:5000/api/event \
  -d '{"type": "pizza", "value": 3}'

# Check result
curl http://localhost:5000/api/metrics
```

## Port Exposure

The Dongometer runs on port 5000. To expose externally:

```bash
# Option A: Port forward
ssh -L 5000:localhost:5000 doghouse

# Option B: Reverse proxy (nginx/traefik)
# Proxy /dongometer → localhost:5000

# Option C: Firewall
sudo ufw allow 5000/tcp
```

## Docker/Compose Setup (Future)

```yaml
services:
  dongometer:
    build: ./dongometer
    ports:
      - "5000:5000"
    volumes:
      - ./dongometer-data:/data
```

🍆📊
