"""Den Browser oeffnen, sobald der Server antwortet. Fuer start.bat.

Unter Linux erledigt das start.sh mit einer Schleife und xdg-open; die
Windows-Stapeldatei kann weder warten noch pruefen, ob ein Port offen ist.
"""

import os
import socket
import time
import webbrowser

host = os.environ.get("QWEN_HOST", "127.0.0.1").replace("0.0.0.0", "127.0.0.1")
port = int(os.environ.get("QWEN_PORT", "7860"))

for _ in range(240):                       # hoechstens eine Minute
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex((host, port)) == 0:
            webbrowser.open(f"http://{host}:{port}")
            break
    time.sleep(0.25)
