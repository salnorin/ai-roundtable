#!/usr/bin/env bash
# Start AI Roundtable (if not running) and open it in the browser.
cd "$(dirname "$0")"
PORT="${ROUNDTABLE_PORT:-8765}"
if ! curl -fs "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
  nohup python3 server.py >server.log 2>&1 &
  for i in $(seq 1 20); do curl -fs "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1 && break; sleep 0.3; done
fi
[ "$1" = "--no-browser" ] || xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 &
