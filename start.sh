#!/bin/bash
cd /home/scoob/dongometer
exec python3 simple_app.py > /tmp/dongometer.log 2>&1
