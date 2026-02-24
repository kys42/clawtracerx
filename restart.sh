#!/bin/bash
pkill -f "port 8901" 2>/dev/null
pkill -f "ctrace web" 2>/dev/null
pkill -f "ctrace\.py web" 2>/dev/null
sleep 0.5
nohup ctrace web --host 0.0.0.0 --port 8901 >> ~/.openclaw/tools/ocmon/web.log 2>&1 &
echo "ctrace restarted (pid $!)"
