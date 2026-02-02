#!/bin/bash
# Dongometer runner with auto-restart

cd /home/scoob/dongometer

while true; do
    echo "[$(date)] Starting Dongometer..."
    python3 -u simple_app.py 2>&1 | tee -a dongometer.log
    echo "[$(date)] Dongometer crashed, restarting in 3s..."
    sleep 3
done
