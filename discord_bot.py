#!/usr/bin/env python3
"""
Discord Bot for The Dongometer
Monitors Discord messages and sends events to Dongometer API
"""
import os
import re
import requests
import asyncio
from datetime import datetime

# Discord bot token from environment
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DONGOMETER_URL = os.getenv('DONGOMETER_URL', 'http://localhost:5000/api/event')

# Import discord.py if available, otherwise use webhook style
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    print("[Dongometer] discord.py not installed, using webhook fallback")

# Keyword patterns
PIZZA_PATTERNS = [
    r'\bpizza\b', r'\b🍕\b', r'pizzas', r'pizzatime',
]

DOOR_PATTERNS = [
    r'\bdoor\s+open\b', r'\bdoor\s+opened\b', 
    r'\bdoor\s+unlock\b', r'🚪',
]

CHAOS_KEYWORDS = [
    'chaos', 'dong', 'apocalyptic', 'gigglesgate',
    'hardin needs', 'demonic', 'shadow president'
]

def send_to_dongometer(event_type, value=1, details=""):
    """Send event to Dongometer API"""
    try:
        resp = requests.post(
            DONGOMETER_URL,
            json={
                "type": event_type,
                "value": value,
                "details": details
            },
            timeout=3
        )
        return resp.json()
    except Exception as e:
        print(f"[Dongometer Discord] Error: {e}")
        return None

def analyze_message(content, author, channel):
    """Analyze message and send appropriate events"""
    content_lower = content.lower()
    events = []
    
    # Pizza detection
    pizza_count = 0
    for pattern in PIZZA_PATTERNS:
        matches = re.findall(pattern, content_lower)
        pizza_count += len(matches)
    
    if pizza_count > 0:
        result = send_to_dongometer(
            "pizza", 
            pizza_count,
            f"{author} in #{channel}: {content[:50]}"
        )
        events.append(f"pizza+{pizza_count}")
    
    # Door detection
    for pattern in DOOR_PATTERNS:
        if re.search(pattern, content_lower):
            send_to_dongometer(
                "door_open",
                1,
                f"{author}: {content[:50]}"
            )
            events.append("door")
            break
    
    # Chat velocity (always record)
    chaos_boost = 1
    for keyword in CHAOS_KEYWORDS:
        if keyword in content_lower:
            chaos_boost = 2
            events.append("chaos_boost")
            break
    
    send_to_dongometer(
        "chat_message",
        chaos_boost,
        f"{author} in #{channel}"
    )
    
    return events

# Discord.py bot implementation
if DISCORD_AVAILABLE:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f'[Dongometer Discord] Logged in as {bot.user}')
        print(f'[Dongometer Discord] Connected to Dongometer at {DONGOMETER_URL}')
    
    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        
        # Process message
        events = analyze_message(
            message.content,
            str(message.author),
            message.channel.name
        )
        
        if events:
            print(f"[Dongometer Discord] {message.author}: {events}")
        
        await bot.process_commands(message)
    
    @bot.command(name='pizza')
    async def pizza_cmd(ctx, count: int = 1):
        """Manually record pizza"""
        result = send_to_dongometer("pizza", count, f"Manual command by {ctx.author}")
        if result:
            await ctx.send(f"🍕 Pizza count +{count}! Chaos level: {result.get('chaos_score', '?')}")
    
    @bot.command(name='chaos')
    async def chaos_cmd(ctx):
        """Get current chaos level"""
        try:
            resp = requests.get(DONGOMETER_URL.replace('/api/event', '/api/metrics'), timeout=3)
            data = resp.json()
            await ctx.send(f"🍆 **Dongometer**: Chaos Level {data['chaos_score']}/100\nStatus: {data['status']}")
        except Exception as e:
            await ctx.send(f"❌ Can't reach Dongometer: {e}")
    
    @bot.command(name='door')
    async def door_cmd(ctx, action: str = "open"):
        """Record door event"""
        result = send_to_dongometer(f"door_{action}", 1, f"Manual by {ctx.author}")
        await ctx.send(f"🚪 Door {action} recorded!")
    
    def run_bot():
        if not DISCORD_TOKEN:
            print("[Dongometer Discord] Error: DISCORD_BOT_TOKEN not set")
            return
        bot.run(DISCORD_TOKEN)

# Simple webhook-based version (no discord.py)
else:
    def run_webhook_listener():
        """Fallback: Use Discord webhooks instead of bot"""
        print("[Dongometer Discord] Webhook mode not implemented")
        print("[Dongometer Discord] Install discord.py: pip install discord.py")

# Main entry
if __name__ == "__main__":
    if DISCORD_AVAILABLE:
        run_bot()
    else:
        print("[Dongometer Discord] Please install discord.py")
        print("[Dongometer Discord] Then set DISCORD_BOT_TOKEN environment variable")
