# Matrix Integration for Dongometer

## Quick Setup

### 1. OpenClaw Integration

Add to your OpenClaw Matrix message handler:

```python
# In your OpenClaw message handler (where Matrix messages are processed)
import sys
sys.path.insert(0, '/home/scoob/dongometer')
from matrix_bridge import on_matrix_message

def handle_matrix_message(event):
    # Your existing message handling...
    
    # Also send to Dongometer
    on_matrix_message({
        'sender': event.sender,
        'content': {'body': event.content.body},
        'room_id': event.room_id
    })
```

### 2. Environment Variables (Already Set)

```bash
MATRIX_HOMESERVER=https://cclub.cs.wmich.edu
MATRIX_USER_ID=@scooby:cclub.cs.wmich.edu
MATRIX_PASSWORD=***  # You have this
DONGOMETER_URL=http://localhost:5000/api/event
```

### 3. Test It

```bash
cd /home/scoob/dongometer
python3 matrix_bridge.py
```

## Auto-Detection

**Saying these in #donghouse auto-updates Dongometer:**

| Phrase | Effect |
|--------|--------|
| "pizza", "🍕" | +count per occurrence |
| "door open", "🚪" | Door event |
| "chaos", "dong", "apocalyptic" | 2x message weight |
| "hardin needs" | Chaos boost |
| "gigglesgate" | Chaos boost |

## Current Status

After test messages:
- 🍕 Pizza count: **13**
- Chaos Score: **37.0** (⚡ ACTIVE)

## One-Line Integration

If you just want to add it to your existing handler:

```python
# At the top of your OpenClaw Matrix handler file
exec(open('/home/scoob/dongometer/quick_matrix_hook.py').read())
```

🍆📊
