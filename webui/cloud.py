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
FELDER = ("aktiv", "url", "schluessel", "modell", "groesse", "art", "staerke")

# Wie das Bildmodell eine Vorlage versteht. "anweisung": ein Bearbeitungs-
# modell (gpt-image, Qwen-Image-Edit) liest "faerbe das Auto rot, lass die
# Kupplung" als Auftrag. "beschreibung": ein Text-zu-Bild-Modell im img2img-
# Betrieb (Z-Image Turbo bei franconia.ai) malt die Vorlage nach dem Prompt
# neu -- es braucht eine Beschreibung des *Zielbildes* und eine Staerke, wie
# weit es sich von der Vorlage entfernen darf.
ARTEN = ("anweisung", "beschreibung")
# Vorlagen gehen hoechstens so gross hinaus, und immer in Vielfachen von 16:
# franconia.ai lehnt alles andere ab ("Breite und Hoehe muessen ein
# Vielfaches von 16 sein"), andere Anbieter stoert es nicht.
VORLAGE_KANTE = 1536

# Bekannte Anbieter: ein Klick fuellt Adresse und Modelle.
VORLAGEN = {
    "franconia": {"label": "franconia.ai", "url": "https://api.franconia.ai/v1",
                  "sprache": "Qwen 3.8 27B", "bild": "Z Image Turbo",
                  "groesse": "genau", "art": "beschreibung", "staerke": 0.7},
    "openai": {"label": "OpenAI", "url": "https://api.openai.com/v1",
               "sprache": "gpt-4.1-mini", "bild": "gpt-image-1",
               "groesse": "openai", "art": "anweisung"},
}

# Groesse beim Bildmodell. "genau" schickt die Kantenlaengen, die auch das
# lokale Modell rechnen wuerde. Die OpenAI-Bildmodelle nehmen aber nur drei
# feste Formate -- "openai" waehlt das naechstliegende. "auto" ueberlaesst
# es dem Anbieter.
GROESSEN = ("genau", "openai", "auto")
OPENAI_FORMATE = ((1024, 1024), (1536, 1024), (1024, 1536))

_sperre = threading.Lock()


def _leer() -> dict:
    return {p: {"aktiv": False, "url": "", "schluessel": "", "modell": "",
                "groesse": "genau", "art": "anweisung", "staerke": 0.6}
            for p in PLAETZE}


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
            if eintrag.get("art") in ARTEN:
                ziel["art"] = eintrag["art"]
            if "staerke" in eintrag:
                try:
                    ziel["staerke"] = max(0.1, min(1.0, float(eintrag["staerke"])))
                except (TypeError, ValueError):
                    pass
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
# Wie oft ein Aufruf wiederholt wird, wenn der Anbieter ausfaellt oder
# drosselt, und wie lange dazwischen gewartet wird (Sekunden). Gemessen an
# franconia.ai: mitten in einer Serie antwortete der Dienst eine Weile gar
# nicht -- ohne Wiederholung brach daran der ganze Auftrag ab.
WARTEN = (5, 15, 40)
VORUEBERGEHEND = (429, 502, 503, 504)


def _einmal(e: dict, pfad: str, daten: bytes, art: str, timeout: int) -> dict:
    """Ein POST. Fehler als RuntimeError; .warten sagt, ob ein neuer Versuch lohnt."""
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
        neu = RuntimeError(f"Cloud-Modell meldet {fehler.code}: {str(text)[:300]}")
        if fehler.code in VORUEBERGEHEND:
            # Bei 429 sagt der Anbieter selbst, wann es wieder geht.
            try:
                neu.warten = float(fehler.headers.get("Retry-After") or 0) or True
            except ValueError:
                neu.warten = True
        raise neu
    except urllib.error.URLError as fehler:
        neu = RuntimeError(f"Kein Kontakt zu {e['url']} ({fehler.reason})")
        neu.warten = True
        raise neu
    except (TimeoutError, ConnectionError) as fehler:
        neu = RuntimeError(f"{e['url']} antwortet nicht innerhalb von {timeout} s"
                           if isinstance(fehler, TimeoutError)
                           else f"Verbindung zu {e['url']} abgebrochen ({fehler})")
        neu.warten = True
        raise neu


def _anfrage(e: dict, pfad: str, daten: bytes, art: str, timeout: int) -> dict:
    """Ein POST an den Anbieter, mit Wiederholung bei voruebergehenden Fehlern.

    Wiederholt wird bei Zeitueberschreitung, abgebrochener Verbindung, 429
    (Anfragelimit) und 502/503/504 (Modell gerade nicht da). Ein 400 oder 401
    wird nicht besser, wenn man es noch einmal versucht -- der kommt sofort.
    """
    import sys
    import time
    for versuch, pause in enumerate((*WARTEN, None), start=1):
        try:
            return _einmal(e, pfad, daten, art, timeout)
        except RuntimeError as fehler:
            warten = getattr(fehler, "warten", None)
            if not warten or pause is None:
                raise
            pause = warten if isinstance(warten, float) else pause
            print(f"Cloud: {fehler} -- neuer Versuch {versuch + 1} in {pause:.0f} s",
                  file=sys.stderr, flush=True)
            time.sleep(pause)


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


def _vorlage(bild):
    """Eine Vorlage zum Versand: RGB, hoechstens VORLAGE_KANTE, Kanten /16."""
    from PIL import Image
    bild = bild.convert("RGB")
    f = min(1.0, VORLAGE_KANTE / max(bild.size))
    b = max(16, int(bild.size[0] * f) // 16 * 16)
    h = max(16, int(bild.size[1] * f) // 16 * 16)
    if (b, h) != bild.size:
        bild = bild.resize((b, h), Image.LANCZOS)
    return bild


# Anbieter, die die Zusatzfelder abgelehnt haben -- danach ohne sie.
_ohne_zusatz: set = set()


def bild(prompt: str, breite: int, hoehe: int, vorlagen: list | None = None,
         timeout: int = 300, seed: int | None = None, schritte: int | None = None):
    """Ein Bild vom Cloud-Bildmodell. Mit Vorlagen ueber /images/edits.

    Seed, Schrittzahl und -- bei einem Beschreibungs-Modell -- die img2img-
    Staerke gehen als Zusatzfelder mit. Die OpenAI-Schnittstelle kennt sie
    nicht, vLLM-Omni (franconia.ai) reicht sie an das Modell durch: dort ist
    ein Cloud-Bild dann wiederholbar wie ein lokales. Lehnt ein Anbieter die
    Felder ab (400), geht derselbe Aufruf einmal ohne sie, und dieser
    Anbieter bekommt sie danach nicht mehr.
    """
    from PIL import Image

    e = aktiv("bild")
    if not e:
        raise RuntimeError("Kein Cloud-Bildmodell eingestellt")
    groesse = _groesse(e, breite, hoehe)
    zusatz = {}
    if e["url"] not in _ohne_zusatz:
        if seed is not None:
            zusatz["seed"] = int(seed) % 2 ** 32
        if schritte:
            zusatz["num_inference_steps"] = int(schritte)
        if vorlagen and e.get("art") == "beschreibung":
            zusatz["strength"] = float(e.get("staerke") or 0.6)

    def senden(mit: dict):
        if vorlagen:
            dateien = []
            for i, v in enumerate(vorlagen):
                puffer = io.BytesIO()
                _vorlage(v).save(puffer, format="PNG")
                dateien.append(("image[]" if len(vorlagen) > 1 else "image",
                                f"vorlage{i + 1}.png", puffer.getvalue()))
            daten, art = _formular({"model": e["modell"], "prompt": prompt,
                                    "size": groesse, "n": "1", **mit}, dateien)
            return _anfrage(e, "/images/edits", daten, art, timeout)
        return _anfrage(e, "/images/generations",
                        json.dumps({"model": e["modell"], "prompt": prompt,
                                    "size": groesse, "n": 1, **mit}).encode("utf-8"),
                        "application/json", timeout)

    try:
        roh = senden(zusatz)
    except RuntimeError as fehler:
        if not zusatz or " 400:" not in str(fehler):
            raise
        _ohne_zusatz.add(e["url"])
        roh = senden({})
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
