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

# Die Wahl in der Oberflaeche (Kopfzeile › Sprachmodelle) geht den
# Umgebungsvariablen vor. MODEL und GROSS bleiben die Namen, unter denen die
# Module fragen -- umgelenkt wird an einer Stelle, in `rufen`. So muss keine
# der vielen Aufrufstellen wissen, dass sich das Modell aendern kann.
WAHL_DATEI = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "sprachmodelle.json")


def _wahl_lesen() -> dict:
    try:
        with open(WAHL_DATEI, encoding="utf-8") as fh:
            roh = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: str(v) for k, v in roh.items()
            if k in ("klein", "gross", "pi_provider", "pi_modell") and v}


_wahl = _wahl_lesen()


def gewaehlt(rolle: str) -> str:
    """Das Modell fuer "klein" (deuten, uebersetzen) oder "gross" (erzaehlen)."""
    return _wahl.get(rolle) or (GROSS if rolle == "gross" else MODEL)


def wahl() -> dict:
    return {"klein": gewaehlt("klein"), "gross": gewaehlt("gross"),
            "pi_provider": _wahl.get("pi_provider", ""),
            "pi_modell": _wahl.get("pi_modell", "")}


def waehlen(neu: dict) -> dict:
    """Neue Wahl uebernehmen und sichern. Leer heisst: zurueck zur Vorgabe."""
    for k in ("klein", "gross", "pi_provider", "pi_modell"):
        if k in neu:
            wert = str(neu[k] or "").strip()
            if wert:
                _wahl[k] = wert
            else:
                _wahl.pop(k, None)
    with open(WAHL_DATEI, "w", encoding="utf-8") as fh:
        json.dump(_wahl, fh, ensure_ascii=False, indent=2)
    return wahl()


def _umlenken(name: str | None) -> str:
    if not name or name == MODEL:
        return gewaehlt("klein")
    if name == GROSS:
        return gewaehlt("gross")
    return name


def installiert(timeout: float = 3) -> list[str]:
    """Die Modelle, die Ollama vorliegen hat."""
    with urllib.request.urlopen(OLLAMA.rstrip("/") + "/api/tags", timeout=timeout) as r:
        return sorted(m["name"] for m in json.load(r).get("models", []))


def entladen(model: str | None = None) -> None:
    """Gibt ein gehaltenes Modell frei. Danach hat das Bildmodell wieder Platz."""
    if cloud.aktiv("sprache"):
        return          # in der Cloud liegt nichts auf der eigenen Karte
    antwort({"model": _umlenken(model or GROSS), "keep_alive": 0,
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
    body = {"stream": False, "think": False, "keep_alive": 0, **body}
    body["model"] = _umlenken(body.get("model"))
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
    except (TimeoutError, OSError, ValueError, KeyError, TypeError) as fehler:
        # Zeitueberschreitung beim Lesen oder eine Antwort ohne
        # message.content -- die Aufrufer fangen nur RuntimeError.
        raise RuntimeError(f"Ollama-Antwort unbrauchbar: {fehler}")


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
        return {"available": False, "model": gewaehlt("klein"), "reason": f"Ollama unter {OLLAMA} nicht erreichbar"}
    modell = gewaehlt("klein")
    if modell not in names:
        return {"available": False, "model": modell,
                "reason": f"Modell {modell} fehlt – `ollama pull {modell}`"}
    return {"available": True, "model": modell, "reason": ""}
