#!/usr/bin/env bash
# Beendet den Bildermacher-Server *dieses* Ordners, wenn er laeuft.
#
# Frueher per `pkill -f "qwen_bild/bin/python webui/server.py"` -- das traf
# jede Kopie des Programms auf dem Rechner, die mit derselben relativen
# Befehlszeile lief, also auch einen zweiten Checkout. Jetzt ueber die
# Prozessnummer, die start.sh in server.pid ablegt, und nur wenn der Prozess
# wirklich in diesem Ordner laeuft.
set -euo pipefail
cd "$(dirname "$0")"
HIER="$(pwd -P)"

PID="$(cat server.pid 2>/dev/null || true)"
if [ -n "$PID" ] && [ -d "/proc/$PID" ] \
   && [ "$(readlink -f "/proc/$PID/cwd")" = "$HIER" ] \
   && tr '\0' ' ' < "/proc/$PID/cmdline" | grep -q "webui/server.py"; then
  kill "$PID"
  for _ in $(seq 1 20); do [ -d "/proc/$PID" ] || break; sleep 0.25; done
  rm -f server.pid
  echo "Server gestoppt."
else
  rm -f server.pid
  echo "Kein laufender Server in $HIER gefunden."
fi
