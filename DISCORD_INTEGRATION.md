# Discord Integration for Dongometer

## Quick Setup (Using Your Existing Discord Bot)

### 1. Environment Variables

Make sure these are set:
```bash
DISCORD_BOT_TOKEN=your_token_here  # You already have this
DONGOMETER_URL=http://localhost:5000/api/event
```

### 2. OpenClaw Integration

Add this to your OpenClaw message handler:

```python
# In your OpenClaw Discord message handler
from dongometer.discord_bridge import on_discord_message

def on_discord_message_received(event):
    # Convert to Dongometer format
    msg = {
        'author': str(event.author),
        'content': event.content,
        'channel': event.channel.name
    }
    
    # Process
    events = on_discord_message(msg)
    if events:
        print(f"[Dongometer] {events}")
```

### 3. Test It

```bash
cd /home/scoob/dongometer
python3 discord_bridge.py
```

This will test with sample messages.

### 4. Run Both Services

Terminal 1 - Dongometer API:
```bash
python3 simple_app.py
```

Terminal 2 - Discord processing (if separate):
```bash
python3 discord_bridge.py  # or integrate into OpenClaw
```

## Auto-Detection Keywords

**Pizza (+count per occurrence):**
- "pizza", "🍕", "pizzas"

**Door Events:**
- "door open", "door opened", "door unlock", "🚪"

**Chaos Boost (2x weight):**
- "chaos", "dong", "apocalyptic"
- "gigglesgate", "hardin needs"

## Bot Commands (Future)

Add to your Discord bot:

```python
!pizza [count]     # Manual pizza count
!chaos             # Show current chaos level
!door [open/close] # Manual door event
```

## Webhook Alternative

If you prefer webhooks over bot integration:

```bash
# Start webhook listener
python3 discord_webhook.py  # listens on port 5001

# Then POST from your existing bot:
curl -X POST http://localhost:5001/discord-webhook \
  -d '{"username": "shaggy", "content": "pizza!", "channel": "donghouse"}'
```

## Files

- `discord_bridge.py` - Main integration module
- `discord_webhook.py` - Webhook listener (no discord.py needed)
- `discord_bot.py` - Full bot implementation (needs discord.py)

🍕🤖
