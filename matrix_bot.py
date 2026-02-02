#!/usr/bin/env python3
"""
Matrix bot integration for The Dongometer
Posts events when it detects chat activity
"""
import requests
import json
from datetime import datetime

DONGOMETER_URL = "http://localhost:5000/api/event"

def record_chat_message(username, room="general"):
    """Record a chat message to the dongometer"""
    try:
        requests.post(DONGOMETER_URL, json={
            "type": "chat_message",
            "value": 1,
            "details": f"Message from {username} in {room}"
        }, timeout=2)
    except Exception as e:
        print(f"Failed to record chat: {e}")

def record_door_event(event_type="open", source="sensor"):
    """Record a door event"""
    try:
        requests.post(DONGOMETER_URL, json={
            "type": f"door_{event_type}",
            "value": 1,
            "details": f"Door {event_type} via {source}"
        }, timeout=2)
    except Exception as e:
        print(f"Failed to record door: {e}")

def record_pizza(count=1, topping="unknown"):
    """Record pizza arrival"""
    try:
        requests.post(DONGOMETER_URL, json={
            "type": "pizza",
            "value": count,
            "details": f"Pizza with {topping}"
        }, timeout=2)
    except Exception as e:
        print(f"Failed to record pizza: {e}")

# Example usage for Matrix bot integration:
# When a message is received:
# record_chat_message(event.sender, room.name)

# When door opens/closes:
# record_door_event("open", "mqtt_sensor")

# When pizza arrives:
# record_pizza(3, "pepperoni")
