#!/usr/bin/env bash
# Beendet den Bildermacher-Server, wenn er laeuft.
set -euo pipefail
cd "$(dirname "$0")"
if pkill -f "qwen_bild/bin/python webui/server.py"; then
  echo "Server gestoppt."
else
  echo "Kein laufender Server gefunden."
fi
sleep 1
pkill -f "bash ./start.sh" 2>/dev/null || true
