#!/usr/bin/env bash
# Startet Bildermacher 1.0 und oeffnet den Browser.
#
#   ./start.sh            -> http://127.0.0.1:7860
#   ./start.sh 8080       -> anderer Port
#   QWEN_HOST=0.0.0.0 ./start.sh   -> auch aus dem LAN erreichbar
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="./qwen_bild/bin/python"
export QWEN_PORT="${1:-${QWEN_PORT:-7860}}"
export QWEN_HOST="${QWEN_HOST:-127.0.0.1}"
URL="http://${QWEN_HOST/0.0.0.0/127.0.0.1}:${QWEN_PORT}"

if [ ! -x "$PYTHON" ]; then
  echo "Virtuelle Umgebung 'qwen_bild' nicht gefunden." >&2
  exit 1
fi

"$PYTHON" - <<'PY' || { echo "PyTorch findet keine CUDA-GPU." >&2; exit 1; }
import sys, torch
sys.exit(0 if torch.cuda.is_available() else 1)
PY

"$PYTHON" webui/server.py &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' INT TERM EXIT

# Warten bis der Server antwortet, dann Browser oeffnen.
for _ in $(seq 1 40); do
  if "$PYTHON" -c "import socket,sys; s=socket.socket(); s.settimeout(.3); sys.exit(s.connect_ex(('${QWEN_HOST/0.0.0.0/127.0.0.1}', ${QWEN_PORT})))" 2>/dev/null; then
    command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1 &
    break
  fi
  sleep 0.25
done

wait $SERVER
