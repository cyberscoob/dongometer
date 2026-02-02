#!/bin/bash
# Start The Dongometer
cd /home/scoob/dongometer
source venv/bin/activate 2>/dev/null || echo "No venv, using system Python"
python3 app.py
