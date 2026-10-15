"""Cloud-Modelle ueber eine OpenAI-kompatible Schnittstelle.

Zwei Plaetze, jeder fuer sich ein- und ausschaltbar:

    sprache   statt Ollama: uebersetzen, Seitenprompts, Bilder beschreiben
    bild      statt Qwen-Image auf der eigenen Karte

"OpenAI-kompatibel" heisst: `POST <url>/chat/completions`,
`<url>/images/generations` und `<url>/images/edits` mit einem Bearer-Schluessel.
Das sprechen OpenAI selbst, OpenRouter, Mistral, DeepSeek, Together, vLLM,
LiteLLM und viele mehr -- eingetragen wird nur die Basisadresse, etwa
`https://api.openai.com/v1`.

Die Einstellungen liegen in `einstellungen.json` neben dem Programm, mit
Rechten nur fuer den Besitzer. Die Datei steht in `.gitignore`: ein
Schluessel im Repository waere ein veroeffentlichter Schluessel.
"""

import base64
import io
import json
import os
import threading
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, "einstellungen.json")

PLAETZE = ("sprache", "bild")
FELDER = ("aktiv", "url", "schluessel", "modell", "groesse")

# Groesse beim Bildmodell. "genau" schickt die Kantenlaengen, die auch das
# lokale Modell rechnen wuerde. Die OpenAI-Bildmodelle nehmen aber nur drei
# feste Formate -- "openai" waehlt das naechstliegende. "auto" ueberlaesst
# es dem Anbieter.
GROESSEN = ("genau", "openai", "auto")
OPENAI_FORMATE = ((1024, 1024), (1536, 1024), (1024, 1536))

_sperre = threading.Lock()


def _leer() -> dict:
    return {p: {"aktiv": False, "url": "", "schluessel": "", "modell": "",
                "groesse": "genau"} for p in PLAETZE}


def lesen() -> dict:
    """Die Einstellungen, mit Schluessel. Nur fuer den Server selbst."""
    daten = _leer()
    try:
        with open(DATEI, encoding="utf-8") as fh:
            roh = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return daten
    for platz in PLAETZE:
        eintrag = roh.get(platz) if isinstance(roh, dict) else None
        if isinstance(eintrag, dict):
            for feld in FELDER:
                if feld in eintrag:
                    daten[platz][feld] = eintrag[feld]
    return daten


def oeffentlich() -> dict:
    """Die Einstellungen fuer die Seite: der Schluessel nur als Andeutung.

    Er geht nie zurueck an den Browser -- nur, ob einer hinterlegt ist, und
    seine letzten vier Zeichen, damit man ihn wiedererkennt.
    """
    daten = lesen()
    for platz in PLAETZE:
        s = str(daten[platz].pop("schluessel") or "")
        daten[platz]["schluessel_da"] = bool(s)
        daten[platz]["schluessel_ende"] = s[-4:] if len(s) > 8 else ""
    return daten


def schreiben(neu: dict) -> dict:
    """Einstellungen uebernehmen. Ein leerer Schluessel laesst den alten stehen.

    Zum Loeschen des Schluessels gibt es `schluessel_loeschen`.
    """
    with _sperre:
        daten = lesen()
        for platz in PLAETZE:
            eintrag = (neu or {}).get(platz)
            if not isinstance(eintrag, dict):
                continue
            ziel = daten[platz]
            if "aktiv" in eintrag:
                ziel["aktiv"] = bool(eintrag["aktiv"])
            for feld in ("url", "modell"):
                if feld in eintrag:
                    ziel[feld] = str(eintrag[feld] or "").strip()
            if eintrag.get("groesse") in GROESSEN:
                ziel["groesse"] = eintrag["groesse"]
            if str(eintrag.get("schluessel") or "").strip():
                ziel["schluessel"] = str(eintrag["schluessel"]).strip()
            if eintrag.get("schluessel_loeschen"):
                ziel["schluessel"] = ""
        # Erst anlegen mit 0600, dann schreiben: der Schluessel soll keinen
        # Augenblick fuer andere lesbar auf der Platte liegen.
        fd = os.open(DATEI, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, ensure_ascii=False, indent=2)
        os.chmod(DATEI, 0o600)
    return oeffentlich()


def aktiv(platz: str) -> dict | None:
    """Die Einstellungen eines Platzes, wenn er eingeschaltet und vollstaendig ist."""
    e = lesen()[platz]
    if e["aktiv"] and e["url"] and e["modell"]:
        return e
    return None


# --- Aufruf --------------------------------------------------------------
def _anfrage(e: dict, pfad: str, daten: bytes, art: str, timeout: int) -> dict:
    """Ein POST an den Anbieter. Fehler kommen als RuntimeError mit Klartext."""
    kopf = {"Content-Type": art}
    if e.get("schluessel"):
        kopf["Authorization"] = f"Bearer {e['schluessel']}"
    anfrage = urllib.request.Request(e["url"].rstrip("/") + pfad, daten, kopf)
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            return json.load(antwort)
    except urllib.error.HTTPError as fehler:
        text = fehler.read().decode("utf-8", "replace")
        try:
            text = json.loads(text)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError(f"Cloud-Modell meldet {fehler.code}: {str(text)[:300]}")
    except urllib.error.URLError as fehler:
        raise RuntimeError(f"Kein Kontakt zu {e['url']} ({fehler.reason})")
    except TimeoutError:
        raise RuntimeError(f"{e['url']} antwortet nicht innerhalb von {timeout} s")


def _bildart(b64: str) -> str:
    """Den Medientyp eines base64-Bildes an seinen ersten Zeichen erkennen."""
    if b64.startswith("/9j/"):
        return "image/jpeg"
    if b64.startswith("UklGR"):
        return "image/webp"
    return "image/png"


def chat(body: dict, timeout: int = 180) -> str:
    """Eine Ollama-Anfrage an das Cloud-Sprachmodell weiterreichen.

    Alle Stellen im Programm bauen ihre Anfragen im Ollama-Format. Hier wird
    daraus eine OpenAI-Anfrage: Bilder als Daten-URL im Inhalt,
    `num_predict` als `max_tokens`, `format: json` als `response_format`.
    Zurueck kommt der Antworttext, wie ihn Ollama auch liefern wuerde.
    """
    e = aktiv("sprache")
    if not e:
        raise RuntimeError("Kein Cloud-Sprachmodell eingestellt")
    nachrichten = []
    for m in body.get("messages") or []:
        bilder = m.get("images") or []
        inhalt = m.get("content") or ""
        if bilder:
            inhalt = [{"type": "text", "text": inhalt}] + [
                {"type": "image_url",
                 "image_url": {"url": f"data:{_bildart(b)};base64,{b}"}}
                for b in bilder]
        nachrichten.append({"role": m.get("role") or "user", "content": inhalt})

    optionen = body.get("options") or {}
    anfrage = {"model": e["modell"], "messages": nachrichten}
    if "temperature" in optionen:
        anfrage["temperature"] = optionen["temperature"]
    if optionen.get("num_predict"):
        # Ollama zaehlt knapp, weil das lokale Modell nicht laut denkt. Ein
        # Cloud-Modell, das vorher ueberlegt, braucht dafuer Luft -- sonst
        # bricht die Antwort mitten im JSON ab.
        anfrage["max_tokens"] = max(int(optionen["num_predict"]), 256) * 4
    if body.get("format") == "json":
        anfrage["response_format"] = {"type": "json_object"}

    try:
        roh = _anfrage(e, "/chat/completions", json.dumps(anfrage).encode("utf-8"),
                       "application/json", timeout)
    except RuntimeError as fehler:
        # Nicht jeder Anbieter nimmt alles: neuere OpenAI-Modelle wollen
        # `max_completion_tokens` und keine Temperatur, manche kennen
        # `response_format` nicht. Einmal ohne die strittigen Teile.
        if " 400:" not in str(fehler):
            raise
        anfrage.pop("temperature", None)
        anfrage.pop("response_format", None)
        if "max_tokens" in anfrage:
            anfrage["max_completion_tokens"] = anfrage.pop("max_tokens")
        roh = _anfrage(e, "/chat/completions", json.dumps(anfrage).encode("utf-8"),
                       "application/json", timeout)
    inhalt = _inhalt(roh)
    if not inhalt.strip() and ("max_tokens" in anfrage
                               or "max_completion_tokens" in anfrage):
        # Ein Modell, das erst ueberlegt, kann das ganze Budget dafuer
        # verbrauchen und mit leerer Antwort enden. Einmal mit viel Luft --
        # ganz ohne Grenze denkt manches Modell, bis die Zeit um ist.
        feld = "max_tokens" if "max_tokens" in anfrage else "max_completion_tokens"
        anfrage[feld] = 8192
        inhalt = _inhalt(_anfrage(e, "/chat/completions",
                                  json.dumps(anfrage).encode("utf-8"),
                                  "application/json", timeout))
    return inhalt


def _inhalt(roh: dict) -> str:
    try:
        return roh["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Das Cloud-Sprachmodell hat keine Antwort geliefert")


def _groesse(e: dict, breite: int, hoehe: int) -> str:
    art = e.get("groesse") or "genau"
    if art == "auto":
        return "auto"
    if art == "openai":
        verhaeltnis = breite / hoehe
        b, h = min(OPENAI_FORMATE, key=lambda f: abs(f[0] / f[1] - verhaeltnis))
        return f"{b}x{h}"
    return f"{breite}x{hoehe}"


def _formular(felder: dict, dateien: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    """multipart/form-data von Hand -- urllib kann es nicht selbst."""
    grenze = uuid.uuid4().hex
    teile = []
    for name, wert in felder.items():
        teile.append(f'--{grenze}\r\nContent-Disposition: form-data; '
                     f'name="{name}"\r\n\r\n{wert}\r\n'.encode("utf-8"))
    for name, dateiname, inhalt in dateien:
        teile.append(f'--{grenze}\r\nContent-Disposition: form-data; '
                     f'name="{name}"; filename="{dateiname}"\r\n'
                     f'Content-Type: image/png\r\n\r\n'.encode("utf-8"))
        teile.append(inhalt + b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode("utf-8"))
    return b"".join(teile), f"multipart/form-data; boundary={grenze}"


def bild(prompt: str, breite: int, hoehe: int, vorlagen: list | None = None,
         timeout: int = 300):
    """Ein Bild vom Cloud-Bildmodell. Mit Vorlagen ueber /images/edits.

    Seed und negativer Prompt gibt es in der Schnittstelle nicht -- ein
    Cloud-Bild ist darum nicht wiederholbar wie ein lokales.
    """
    from PIL import Image

    e = aktiv("bild")
    if not e:
        raise RuntimeError("Kein Cloud-Bildmodell eingestellt")
    groesse = _groesse(e, breite, hoehe)
    if vorlagen:
        dateien = []
        for i, v in enumerate(vorlagen):
            puffer = io.BytesIO()
            v.save(puffer, format="PNG")
            dateien.append(("image[]" if len(vorlagen) > 1 else "image",
                            f"vorlage{i + 1}.png", puffer.getvalue()))
        daten, art = _formular({"model": e["modell"], "prompt": prompt,
                                "size": groesse, "n": "1"}, dateien)
        roh = _anfrage(e, "/images/edits", daten, art, timeout)
    else:
        roh = _anfrage(e, "/images/generations",
                       json.dumps({"model": e["modell"], "prompt": prompt,
                                   "size": groesse, "n": 1}).encode("utf-8"),
                       "application/json", timeout)
    try:
        eintrag = roh["data"][0]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Das Cloud-Bildmodell hat kein Bild geliefert")
    if eintrag.get("b64_json"):
        inhalt = base64.b64decode(eintrag["b64_json"])
    elif eintrag.get("url"):
        with urllib.request.urlopen(eintrag["url"], timeout=timeout) as r:
            inhalt = r.read()
    else:
        raise RuntimeError("Das Cloud-Bildmodell hat kein Bild geliefert")
    return Image.open(io.BytesIO(inhalt)).convert("RGB")


def pruefen(platz: str) -> dict:
    """Ein kurzer Probeaufruf: stimmen Adresse, Schluessel und Modell?

    Beim Sprachmodell ein Wort, beim Bildmodell nur die Modellliste -- ein
    Probebild kostet Geld.
    """
    if platz not in PLAETZE:
        return {"ok": False, "meldung": "Unbekannter Platz"}
    e = aktiv(platz)
    if not e:
        return {"ok": False, "meldung": "Nicht eingeschaltet oder unvollstaendig"}
    try:
        if platz == "sprache":
            text = chat({"messages": [{"role": "user", "content": "Antworte nur mit: ok"}],
                         "options": {"num_predict": 5}}, timeout=60)
            return {"ok": True, "meldung": f"Antwort: {text.strip()[:60]}"}
        anfrage = urllib.request.Request(
            e["url"].rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {e['schluessel']}"} if e["schluessel"] else {})
        with urllib.request.urlopen(anfrage, timeout=30) as r:
            namen = [m.get("id") for m in json.load(r).get("data", [])]
        if namen and e["modell"] not in namen:
            return {"ok": False, "meldung": f"Erreichbar, aber {e['modell']} steht "
                                            "nicht in der Modellliste"}
        return {"ok": True, "meldung": "Erreichbar, Modell vorhanden"}
    except Exception as fehler:
        return {"ok": False, "meldung": str(fehler)[:300]}
