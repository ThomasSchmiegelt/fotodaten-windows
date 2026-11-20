#!/usr/bin/env bash
# Startet Bildermacher 1.0 und oeffnet den Browser.
#
#   ./start.sh            -> http://127.0.0.1:7860
#   ./start.sh 8080       -> anderer Port
#   QWEN_HOST=0.0.0.0 ./start.sh   -> auch aus dem LAN erreichbar
#
# Eingerichtet wird vorher mit ./einrichten.sh (dieser Ordner, portabel).
# Beenden: Strg+C in diesem Terminal oder "Programm beenden" in der Oberflaeche.
set -euo pipefail
cd "$(dirname "$0")"

PY="./qwen_bild/bin/python"
if [ ! -x "$PY" ]; then
  echo "Noch nicht eingerichtet -- bitte zuerst ./einrichten.sh ausfuehren." >&2
  exit 1
fi

# Eigene Einstellungen dieses Rechners (QWEN_IMAGE_REVISION, QWEN_HOST ...)
# stehen in lokal.env -- nicht im Repository.
[ -f ./lokal.env ] && . ./lokal.env

QWEN_PORT="${1:-${QWEN_PORT:-7860}}"
QWEN_HOST="${QWEN_HOST:-127.0.0.1}"
export QWEN_PORT QWEN_HOST
QWEN_LOCAL="${QWEN_HOST/0.0.0.0/127.0.0.1}"

# Alles im Ordner: Modelle unter daten/hf, Gewichte und Einstellungen unter
# modelle/yolo -- beim Programm, nicht im Benutzerprofil.
export HF_HOME="./daten/hf"
export YOLO_CONFIG_DIR="./modelle/yolo/einstellungen"

# Das Bildmodell rechnet nur lokal, wenn einrichten.sh mit "lokal" die Marke
# daten/bildmodell_lokal.txt gelegt hat; sonst nie auf der eigenen Karte.
if [ -f ./daten/bildmodell_lokal.txt ]; then
  export QWEN_IMAGE_REVISION="${QWEN_IMAGE_REVISION:-790c92633540aa0cb11d9abf19eb46d861714758}"
else
  export QWEN_NUR_CLOUD=1
fi

# Modelle ueber normales HTTP laden. Der Xet-Weg von Hugging Face blieb an
# manchen Rechnern bei 0 Byte stehen, HTTP lief.
export HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
# Python ueberall in UTF-8.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# CUDA wirklich nur noetig, wenn lokal gerechnet wird.
if [ -z "${QWEN_NUR_CLOUD:-}" ]; then
  "$PY" - <<'PY' || { echo "PyTorch findet keine CUDA-GPU." >&2; exit 1; }
import sys, torch
sys.exit(0 if torch.cuda.is_available() else 1)
PY
fi

"$PY" webui/server.py &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' INT TERM EXIT

# Browser oeffnen, sobald der Server antwortet.
URL="http://${QWEN_LOCAL}:${QWEN_PORT}"
for _ in $(seq 1 40); do
  if "$PY" -c "import socket,sys; s=socket.socket(); s.settimeout(.3); \
sys.exit(s.connect_ex(('$QWEN_LOCAL', $QWEN_PORT)))" 2>/dev/null; then
    command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1 &
    break
  fi
  sleep 0.25
done

wait $SERVER
