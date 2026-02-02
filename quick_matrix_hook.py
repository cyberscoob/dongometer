# One-line Matrix → Dongometer integration
# Add this to your OpenClaw Matrix message handler:
# exec(open('/home/scoob/dongometer/quick_matrix_hook.py').read())

import sys
import os
sys.path.insert(0, '/home/scoob/dongometer')

from matrix_bridge import on_matrix_message, process_matrix_message

# Store original handler if exists
_original_handler = globals().get('handle_matrix_message')

def handle_matrix_message(event):
    # Send to Dongometer
    try:
        sender = getattr(event, 'sender', str(event.get('sender', 'unknown')))
        content = getattr(event, 'content', event.get('content', {}))
        body = getattr(content, 'body', content.get('body', ''))
        room = getattr(event, 'room_id', event.get('room_id', '#unknown'))
        
        process_matrix_message(sender, body, room)
    except Exception as e:
        pass  # Don't break message handling
    
    # Call original handler if exists
    if _original_handler:
        return _original_handler(event)

print("[Dongometer] Matrix hook installed - pizza tracking active 🍕")
