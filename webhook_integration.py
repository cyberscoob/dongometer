#!/usr/bin/env python3
"""
Dongometer Webhook Integration
Called by Matrix bot when keywords detected
"""
import requests
import re
from datetime import datetime

DONGOMETER_URL = "http://localhost:5000/api/event"

# Keyword patterns
PIZZA_PATTERNS = [
    r'\bpizza\b',
    r'\b🍕\b',
    r'pizzas',
    r'pizzatime',
]

DOOR_PATTERNS = [
    r'\bdoor\s+open\b',
    r'\bdoor\s+opened\b',
    r'\bdoor\s+unlock\b',
    r'🚪',
]

CHAOS_PATTERNS = [
    r'\bchaos\b',
    r'\bdong\b',
    r'\bgigglesgate\b',
    r'\bapocalyptic\b',
    r'\bhardin\s+needs',
]

def send_event(event_type, value=1, details=""):
    """Send event to Dongometer"""
    try:
        resp = requests.post(
            DONGOMETER_URL,
            json={"type": event_type, "value": value, "details": details},
            timeout=2
        )
        return resp.json()
    except Exception as e:
        print(f"[Dongometer] Failed to send event: {e}")
        return None

def process_matrix_message(sender, message, room="#donghouse"):
    """
    Process a Matrix message and update Dongometer if keywords found.
    Call this from your Matrix bot's message handler.
    """
    message_lower = message.lower()
    events_triggered = []
    
    # Check for pizza
    for pattern in PIZZA_PATTERNS:
        if re.search(pattern, message_lower):
            # Count occurrences
            count = len(re.findall(pattern, message_lower))
            result = send_event("pizza", count, f"{sender} mentioned pizza in {room}")
            events_triggered.append(f"pizza+{count}")
            break
    
    # Check for door events
    for pattern in DOOR_PATTERNS:
        if re.search(pattern, message_lower):
            result = send_event("door_open", 1, f"{sender}: {message[:50]}")
            events_triggered.append("door")
            break
    
    # Check for chaos indicators (just log chat velocity)
    send_event("chat_message", 1, f"{sender} in {room}")
    
    # Boost chaos for certain keywords
    for pattern in CHAOS_PATTERNS:
        if re.search(pattern, message_lower):
            # Extra chaos point
            send_event("chat_message", 2, f"CHAOS BOOST: {sender} said {pattern}")
            events_triggered.append("chaos_boost")
            break
    
    return events_triggered

def record_door_sensor(event_type="open", source="sensor"):
    """Called by door sensor/webhook"""
    return send_event(
        f"door_{event_type}", 
        1, 
        f"Door {event_type} via {source} at {datetime.now().isoformat()}"
    )

def record_pizza_arrival(count=1, topping="unknown", source="manual"):
    """Record pizza arrival"""
    return send_event(
        "pizza", 
        count, 
        f"{count} pizza(s) - {topping} ({source})"
    )

# Example usage for testing
if __name__ == "__main__":
    # Test pizza detection
    print("Testing pizza detection...")
    result = process_matrix_message("shaggy", "Pizza is here! 🍕🍕🍕")
    print(f"Triggered: {result}")
    
    # Test door
    print("\nTesting door detection...")
    result = process_matrix_message("aerospice", "door opened for pizza")
    print(f"Triggered: {result}")
    
    # Test chaos
    print("\nTesting chaos detection...")
    result = process_matrix_message("clawdad", "this is total chaos right now")
    print(f"Triggered: {result}")
