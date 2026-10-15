"""Anbindung an Ollama: Adresse, Modell und der Aufruf selbst.

Alle drei Teile des Pakets sprechen ueber diese Datei mit dem Sprachmodell.
`keep_alive: 0` ist wichtig -- das Sprachmodell gibt die Grafikkarte sofort
wieder frei, sonst fehlt sie dem Bildmodell.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cloud  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("QWEN_CHAT_MODEL", "qwen3.5:4b")
THINK = re.compile(r"<think>.*?</think>", re.S)


# Das grosse Modell fuer die schoepferische Arbeit. Es wiegt 16,5 GB und
# braucht entsprechend lange zum Laden -- fuer eine Reihe von Aufrufen bleibt
# es deshalb geladen und wird erst am Ende freigegeben.
GROSS = os.environ.get("QWEN_CHAT_GROSS", "qwen3.8:27b-mtp-q4_K_M")


def entladen(model: str | None = None) -> None:
    """Gibt ein gehaltenes Modell frei. Danach hat das Bildmodell wieder Platz."""
    if cloud.aktiv("sprache"):
        return          # in der Cloud liegt nichts auf der eigenen Karte
    antwort({"model": model or GROSS, "keep_alive": 0,
             "messages": [{"role": "user", "content": "."}],
             "options": {"num_predict": 1}}, timeout=60)


def rufen(body: dict, timeout: int = 180) -> str:
    """Eine Anfrage im Ollama-Format abschicken, der Antworttext zurueck.

    Ist ein Cloud-Sprachmodell eingeschaltet, geht sie dorthin -- alle
    Stellen im Programm laufen hier durch und merken davon nichts. Fehler
    kommen als RuntimeError mit Klartext.
    """
    if cloud.aktiv("sprache"):
        return THINK.sub("", cloud.chat(body, timeout)).strip()
    body = {"stream": False, "think": False, "keep_alive": 0, "model": MODEL, **body}
    anfrage = urllib.request.Request(
        OLLAMA.rstrip("/") + "/api/chat", json.dumps(body).encode("utf-8"),
        {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            return THINK.sub("", json.load(antwort)["message"]["content"]).strip()
    except urllib.error.HTTPError as fehler:
        detail = fehler.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Ollama meldet {fehler.code}: {detail}")
    except urllib.error.URLError as fehler:
        raise RuntimeError(
            f"Kein Kontakt zu Ollama unter {OLLAMA} ({fehler.reason}). "
            "Laeuft der Dienst?")


def _json(inhalt: str):
    """JSON aus einer Antwort -- auch wenn ein Cloud-Modell es in einen
    Codeblock gesetzt hat."""
    text = inhalt.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def antwort(body: dict, timeout: int = 180) -> dict | str | None:
    """Schickt eine fertige Anfrage ab und gibt die Antwort zurueck.

    Bei `format: "json"` kommt das ausgepackte Objekt, sonst der Text. Faellt
    etwas aus, kommt None -- wer eine Ausnahme braucht, nimmt `rufen`.
    """
    try:
        inhalt = rufen(body, timeout)
    except Exception:
        return None
    if body.get("format") != "json":
        return inhalt
    try:
        return _json(inhalt)
    except json.JSONDecodeError:
        return None


def available(timeout: float = 1.5) -> dict:
    """Ist Ollama erreichbar und liegt das eingestellte Modell vor?"""
    wolke = cloud.aktiv("sprache")
    if wolke:
        return {"available": True, "model": wolke["modell"], "reason": "",
                "cloud": True}
    try:
        with urllib.request.urlopen(OLLAMA.rstrip("/") + "/api/tags", timeout=timeout) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
    except Exception:
        return {"available": False, "model": MODEL, "reason": f"Ollama unter {OLLAMA} nicht erreichbar"}
    if MODEL not in names:
        return {"available": False, "model": MODEL,
                "reason": f"Modell {MODEL} fehlt – `ollama pull {MODEL}`"}
    return {"available": True, "model": MODEL, "reason": ""}
