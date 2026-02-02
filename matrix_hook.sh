#!/bin/bash
# Matrix → Dongometer webhook hook
# Add this to your Matrix bot's message handler

SENDER="$1"
MESSAGE="$2"
ROOM="$3"

DONGOMETER_URL="http://localhost:5000/api/event"

# Check for pizza
if echo "$MESSAGE" | grep -qi "pizza\|🍕"; then
    COUNT=$(echo "$MESSAGE" | grep -o "pizza\|🍕" | wc -l)
    curl -s -X POST "$DONGOMETER_URL" \
        -H "Content-Type: application/json" \
        -d "{\"type\": \"pizza\", \"value\": $COUNT, \"details\": \"$SENDER mentioned pizza\"}" \
        > /dev/null 2>&1 &
fi

# Check for door
if echo "$MESSAGE" | grep -qi "door.*open\|door.*unlock\|🚪"; then
    curl -s -X POST "$DONGOMETER_URL" \
        -H "Content-Type: application/json" \
        -d "{\"type\": \"door_open\", \"value\": 1, \"details\": \"$SENDER: $MESSAGE\"}" \
        > /dev/null 2>&1 &
fi

# Always record chat activity
# Weight messages by chaos level
CHAOS_BOOST=1
if echo "$MESSAGE" | grep -qi "chaos\|dong\|apocalyptic\|hardin.*needs\|gigglesgate"; then
    CHAOS_BOOST=2
fi

curl -s -X POST "$DONGOMETER_URL" \
    -H "Content-Type: application/json" \
    -d "{\"type\": \"chat_message\", \"value\": $CHAOS_BOOST, \"details\": \"$SENDER in $ROOM\"}" \
    > /dev/null 2>&1 &
