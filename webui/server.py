"""Kleiner HTTP-Server fuer die Qwen-Image-2.1 Oberflaeche (nur Standardbibliothek).

Start:  ./start.sh          bzw.  ./qwen_bild/bin/python webui/server.py
Dann:   http://127.0.0.1:7860
"""

import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (  # noqa: E402
    ASPECT_RATIOS, LOKAL, MAX_REFERENCES, REFERENCE_TOKEN_BUDGET, dimensions_for,
)
# Die eigentliche Arbeit steht in auftraege.py -- hier nur Routen und Start.
from auftraege import (  # noqa: E402
    current, decode, einreihen, engine, entfernen, leeren, melden, uebersicht,
    verschieben,
)
import projekte  # noqa: E402
import bausteine  # noqa: E402
import bewertung  # noqa: E402
import baender  # noqa: E402
import geschichte  # noqa: E402
import sprache as chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402
import cloud  # noqa: E402
import datensatz  # noqa: E402
import detektor  # noqa: E402
import fotodaten  # noqa: E402
import sechsseiten  # noqa: E402
import retusche  # noqa: E402
import vervielfaeltigen  # noqa: E402
from kataloge import (  # noqa: E402
    AXIS_OFF, EFFECTS, EINSTELLUNGEN, FOLGEN, GEZEICHNET, GROUP_ACTIONS,
    MIMIK, PAINT_TARGET, WESEN,
    catalog, overrides,
    parse_command,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEITE = os.path.join(HERE, "seite")
# Der Gespraechsverlauf der Freitexteingabe. Ein Benutzer, ein Gespraech --
# das Programm laeuft ohnehin nur fuer einen. Abgeschnitten, damit ein langer
# Nachmittag den Systemtext nicht aus dem Fenster draengt.
gespraech: list[dict] = []
GESPRAECH_LAENGE = 12
HOST = os.environ.get("QWEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("QWEN_PORT", "7860"))
SAFE_NAME = re.compile(r"[\w.\-]+\.(png|jsonl|mp4)")
WINDOWS = os.name == "nt"


def _gimp_suchen() -> str:
    """Der GIMP-Befehl. Unter Windows steht GIMP nicht im Suchpfad.

    Der Installer legt es unter "C:\\Program Files\\GIMP 3\\bin" ab, die
    ausfuehrbare Datei heisst nach der Version (gimp-3.exe, gimp-3.2.exe).
    Die Konsolenfassung oeffnet kein Fenster und faellt deshalb heraus.
    """
    if os.environ.get("QWEN_GIMP"):
        return os.environ["QWEN_GIMP"]
    if not WINDOWS:
        return "gimp"
    import glob
    for wurzel in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                   os.environ.get("LOCALAPPDATA", "") + r"\Programs"):
        treffer = sorted(p for p in glob.glob(os.path.join(wurzel, "GIMP*", "bin", "gimp*.exe"))
                         if "console" not in os.path.basename(p).lower()
                         and re.fullmatch(r"gimp(-\d+(\.\d+)*)?\.exe",
                                          os.path.basename(p).lower()))
        if treffer:
            return treffer[-1]
    return "gimp"


# Fester Befehl, keine Shell: der Aufruf kann nur eine Datei aus outputs/ oeffnen.
GIMP_CMD = _gimp_suchen()



def _source_state() -> dict[str, str]:
    """Pruefsummen der Python-Dateien, die der Server beim Start geladen hat."""
    state = {}
    # Auch die Unterverzeichnisse: seit der Aufteilung liegen Kataloge und
    # Sprachanbindung in eigenen Paketen, und eine Aenderung dort faellt sonst
    # durch -- der Server liefe mit altem Code, ohne es zu melden.
    for wurzel, ordner, dateien in os.walk(HERE):
        ordner[:] = [o for o in ordner if o != "__pycache__"]
        for name in sorted(dateien):
            if not name.endswith(".py"):
                continue
            pfad = os.path.join(wurzel, name)
            with open(pfad, "rb") as fh:
                schluessel = os.path.relpath(pfad, HERE)
                state[schluessel] = hashlib.sha256(fh.read()).hexdigest()[:12]
    return state


# Beim Start festgehalten. Python laedt Module genau einmal -- wer danach eine
# Datei aendert, sieht die Aenderung erst nach einem Neustart. Das ist schon
# mehrfach fuer einen Programmfehler gehalten worden, deshalb meldet es der
# Server jetzt von sich aus.
SOURCE_AT_START = _source_state()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # ruhiger Log
        if "/api/status" not in (self.path or ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- Helfer -----------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _nur_hier(self) -> bool:
        """Kommt die Anfrage vom Rechner des Servers selbst?

        Bei QWEN_HOST=0.0.0.0 haengt die Oberflaeche im Netz. Was dort etwas
        anrichtet -- GIMP starten, Bilder loeschen, den Server abschalten --
        bleibt deshalb dem eigenen Rechner vorbehalten.
        """
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _bausteinbilder(self, params: dict):
        """Die Musterbilder der genannten Bausteine als Datenzeilen.

        Zurueck kommt die Liste, oder ein Fehlerpaar fuer `_json`, wenn ein
        Baustein noch kein Bild hat -- ohne Bild ist nichts zusammenzusetzen,
        und ein stillschweigend ausgelassener Baustein faellt erst im
        fertigen Bild auf.
        """
        kennungen = [str(k) for k in (params.get("bausteine") or []) if k]
        if not kennungen:
            return []
        projekt = projekte.aktiv()
        ordner = projekte.bilder(projekt)
        nach_id = {b["id"]: b for b in bausteine.liste(projekt)}
        # "bild" ist das Musterbild, "bild_augen" die Grossaufnahme.
        feld = "bild_augen" if params.get("baustein_feld") == "bild_augen" \
            else "bild"
        geladen, fehlt = [], []
        for kennung in kennungen:
            b = nach_id.get(kennung) or {}
            datei = str(b.get(feld) or "")
            pfad = os.path.join(ordner, datei)
            if not SAFE_NAME.fullmatch(datei) or not os.path.isfile(pfad):
                fehlt.append(b.get("name") or kennung)
                continue
            with open(pfad, "rb") as fh:
                geladen.append("data:image/png;base64,"
                               + base64.b64encode(fh.read()).decode())
        if fehlt:
            return (400, {"error": "Noch kein Musterbild bei: "
                          + ", ".join(fehlt)
                          + " \u2014 erst mit \u25a3 eines erzeugen."})
        return geladen

    def _bild_aus_anfrage(self):
        """Das Bild aus dem Anfragerumpf, als PNG-Bytes fuers Sprachmodell.

        Gibt bei einem Fehler stattdessen (Code, Meldung) zurueck -- der
        Aufrufer erkennt das am Tupel. Das Sprachmodell darf nicht waehrend
        eines Auftrags laufen, beide wollen dieselbe Grafikkarte.
        """
        if engine.lock.locked():
            return 409, {"error": "Es laeuft gerade ein Auftrag"}
        params = self._body()
        if params is None:
            return 400, {"error": "ungueltiges JSON"}
        if not params.get("image"):
            return 400, {"error": "Kein Bild"}
        try:
            roh = decode(params["image"])
        except Exception as exc:
            return 400, {"error": f"Bild nicht lesbar: {exc}"}
        puffer = io.BytesIO()
        roh.convert("RGB").save(puffer, format="PNG")
        return puffer.getvalue()

    @staticmethod
    def _prompt_im_bild(pfad: str) -> str:
        """Der Prompt aus dem PNG. Jedes erzeugte Bild traegt ihn bei sich."""
        try:
            with Image.open(pfad) as im:
                return str(im.text.get("qwen_prompt") or "")
        except (OSError, ValueError):
            return ""

    def _body(self):
        """Der JSON-Rumpf der Anfrage, oder None wenn er nicht lesbar ist."""
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def _output_path(self, name):
        """Pfad in outputs/ -- oder None, wenn der Name nicht sauber ist."""
        if not SAFE_NAME.fullmatch(name):
            return None
        path = os.path.join(projekte.bilder(projekte.aktiv()), name)
        return path if os.path.isfile(path) else None

    # -- Routen -----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path in ("/", "/index.html"):
            with open(os.path.join(SEITE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")

        if path.startswith("/bilder/"):
            # Ein Bild aus einem *benannten* Projekt. /outputs/ loest nur im
            # aktiven auf; der Katalog zeigt aber alle.
            teile = path[len("/bilder/"):].split("/", 1)
            if len(teile) != 2:
                return self._json(404, {"error": "not found"})
            schluessel, name = teile
            if not projekte.SCHLUESSEL.fullmatch(schluessel) \
                    or not SAFE_NAME.fullmatch(name):
                return self._json(404, {"error": "not found"})
            datei = os.path.join(projekte.bilder(schluessel), name)
            if not os.path.isfile(datei):
                return self._json(404, {"error": "not found"})
            art = mimetypes.guess_type(datei)[0] or "application/octet-stream"
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(), art)

        if path.startswith("/katalog/"):
            # Die Bilder einer Sechs-Seiten-Ansicht. Sie liegen bewusst
            # ausserhalb von outputs/ -- dort wird oft aufgeraeumt -- und
            # brauchen deshalb ihren eigenen Weg nach draussen.
            teile = path[len("/katalog/"):].split("/")
            if len(teile) != 3:
                return self._json(404, {"error": "not found"})
            datei = sechsseiten.bildpfad(*teile)
            if not datei:
                return self._json(404, {"error": "not found"})
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(), "image/png")

        if path.startswith("/detektor/"):
            # Beispielbilder eines Trainingslaufs.
            teile = path[len("/detektor/"):].split("/")
            datei = detektor.bildpfad(*teile) if len(teile) == 3 else None
            if not datei:
                return self._json(404, {"error": "not found"})
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(),
                                  "image/png" if datei.endswith(".png") else "image/jpeg")

        if path.startswith("/datensatz/"):
            # Die Bilder des Trainingsdatensatzes: aufgenommen, zu pruefen
            # oder verworfen -- jeder Teil gegen sein Muster geprueft.
            teile = path[len("/datensatz/"):].split("/")
            datei = datensatz.bildpfad(*teile) if len(teile) == 3 else None
            if not datei:
                return self._json(404, {"error": "not found"})
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(), "image/png")

        if path.startswith("/seite/"):
            # Aufbau, Aussehen und Verhalten der Oberflaeche liegen getrennt.
            # Nur schlichte Namen, keine Verzeichniswechsel.
            name = path[len("/seite/"):]
            if not re.fullmatch(r"[\w.\-]+\.(css|js)", name):
                return self._json(404, {"error": "not found"})
            datei = os.path.join(SEITE, name)
            if not os.path.isfile(datei):
                return self._json(404, {"error": "not found"})
            art = "text/css" if name.endswith(".css") else "text/javascript"
            with open(datei, "rb") as fh:
                return self._send(200, fh.read(), f"{art}; charset=utf-8")

        if path == "/api/status":
            status = engine.snapshot()
            status["results"] = list(current["files"])
            status["error"] = current["error"]
            status["translated"] = dict(current["translated"])
            status["stage"] = current["stage"]
            status["fortschritt"] = dict(current["fortschritt"])
            status["video"] = current["video"]
            status["gelesen"] = dict(current["gelesen"])
            status["tor"] = list(current["tor"])
            status["gliederung"] = list(current["gliederung"])
            status["expose"] = dict(current["expose"])
            status["bau"] = dict(current["bau"])
            status["seiten"] = dict(current["seiten"])
            status["nummer"] = current["nummer"]
            status["titel"] = current["titel"]
            status.update(uebersicht())
            status["projekt"] = projekte.aktiv()
            status["bausteine"] = bausteine.liste(projekte.aktiv())
            # Solange noch etwas wartet, ist die Oberflaeche nicht fertig --
            # sonst hoerte sie nach dem ersten Auftrag auf nachzufragen.
            status["busy"] = status["busy"] or bool(status["wartend"])
            return self._json(200, status)

        if path == "/api/info":
            info = catalog()
            info["aspects"] = list(ASPECT_RATIOS)
            info["sizes"] = {a: dimensions_for(a, 1024) for a in ASPECT_RATIOS}
            info["max_references"] = MAX_REFERENCES
            info["reference_token_budget"] = REFERENCE_TOKEN_BUDGET
            info["chat"] = chat.available()
            info["axis_off"] = AXIS_OFF
            info["paint_target"] = PAINT_TARGET
            info["gimp"] = {"available": bool(shutil.which(GIMP_CMD)), "command": GIMP_CMD}
            # Ohne torch/diffusers (die portable Fassung) geht nur die Cloud.
            info["lokal"] = LOKAL
            now = _source_state()
            changed = sorted(k for k in set(now) | set(SOURCE_AT_START)
                             if now.get(k) != SOURCE_AT_START.get(k))
            info["source"] = {"stale": bool(changed), "changed": changed}
            info["projekte"] = projekte.liste()
            info["bausteine"] = bausteine.liste(projekte.aktiv())
            info["wesen"] = [{"key": k, "label": v[0]} for k, v in WESEN.items()]
            info["bausteinarten"] = [{"key": k, "label": v}
                                     for k, v in bausteine.ARTEN.items()]
            info["mimik"] = [{"key": k, "label": v[0]} for k, v in MIMIK.items()]
            info["gross"] = chat.GROSS
            info["freigaben"] = [{"key": k, "label": v[0]}
                                 for k, v in chat.FREIGABEN.items()]
            info["erzaehler"] = [{"key": k, "label": v[0]}
                                 for k, v in chat.ERZAEHLER.items()]
            # Folgen: mehrere Szenen mit festen Einstellungen in einem Zug.
            info["folgen"] = [{"key": k, "label": v[0], "schritte": v[1]}
                              for k, v in FOLGEN.items()]
            # Welche Stile gezeichnet sind, entscheidet der Katalog. Die Seite
            # rechnet sonst mit einer zweiten Liste, die auseinanderlaeuft.
            info["gezeichnet"] = sorted(GEZEICHNET)
            info["welten"] = [{"key": k, "label": v[0]}
                              for k, v in chat.WELTEN.items()]
            # "luecke" ist der Name dessen, was in die Klammer gehoert --
            # bei "augen" die Spiegelung, bei "decke" die Hoehe. Die Seite
            # macht daraus ein eigenes kleines Feld je Szene.
            info["einstellungen"] = [
                {"key": k, "label": v["label"], "paar": "gegentext" in v,
                 "luecke": next(iter(v.get("vorgabe") or {}), "")}
                for k, v in EINSTELLUNGEN.items()]
            info["projekt"] = projekte.aktiv()
            info["katalogseiten"] = [{"key": k, "label": v[0]}
                                     for k, v in sechsseiten.SEITEN.items()]
            info["demo"] = demo.available()
            info["kulissen"] = [{"key": k, "label": v[0]}
                                for k, v in demo.KULISSEN.items()]
            info["ablaeufe"] = [
                {"key": k, "label": v["label"],
                 "bilder": ablauf.anzahl_bilder(v["bauen"]("auto", None)),
                 "erzeugt": ablauf.zu_erzeugen(v["bauen"]("auto", None)),
                 "bloecke": v["bauen"]("auto", None)}
                for k, v in ablauf.ABLAEUFE.items()]
            info["retusche"] = [{"key": k, "label": v[0], "text": v[1]}
                                for k, v in retusche.VORLAGEN.items()]
            return self._json(200, info)

        if path == "/api/bewertung":
            # Die Noten des Projekts, dazu die daraus gemerkten Prompts.
            projekt = projekte.aktiv()
            return self._json(200, {**bewertung.lesen(projekt),
                                    "gemerkte": bewertung.gemerkte(projekt)})

        if path == "/api/gallery":
            files = sorted(
                (f for f in os.listdir(projekte.bilder(projekte.aktiv()))
                 if f.endswith(".png")), reverse=True
            )
            return self._json(200, {"files": files[:120]})

        if path == "/api/meta":
            name = (parse_qs(url.query).get("file") or [""])[0]
            target = self._output_path(name)
            if not target:
                return self._json(404, {"error": "not found"})
            with Image.open(target) as im:
                meta = {k[5:]: v for k, v in im.text.items() if k.startswith("qwen_")}
                meta["size"] = list(im.size)
            return self._json(200, meta)

        if path == "/api/zip":
            names = (parse_qs(url.query).get("files") or [""])[0].split(",")
            paths = [(n, self._output_path(n)) for n in names if n]
            paths = [(n, p) for n, p in paths if p]
            if not paths:
                return self._json(404, {"error": "keine Bilder"})
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
                for name, target in paths:
                    zf.write(target, name)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="qwen-serie.zip"')
            self.send_header("Content-Length", str(buf.tell()))
            self.end_headers()
            return self.wfile.write(buf.getvalue())

        if path.startswith("/outputs/"):
            target = self._output_path(os.path.basename(path))
            if not target:
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as fh:
                return self._send(200, fh.read(), ctype)

        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/cancel":
            # Ohne Angabe: den laufenden Auftrag stoppen. Mit "nummer": einen
            # wartenden aus der Liste nehmen. Mit "alles": die Liste leeren,
            # der laufende bleibt.
            params = self._body() or {}
            if params.get("alles"):
                return self._json(200, {"ok": True, "entfernt": leeren()})
            if params.get("nummer"):
                weg = entfernen(int(params["nummer"]))
                return self._json(200 if weg else 404, {"ok": weg})
            engine.cancel()
            return self._json(200, {"ok": True})

        if path == "/api/verschieben":
            params = self._body() or {}
            weg = verschieben(int(params.get("nummer") or 0),
                              -1 if params.get("richtung") == "hoch" else 1)
            return self._json(200 if weg else 404, {"ok": weg})

        if path == "/api/video":
            # Aus ausgewaehlten Bildern ein Video mit weichen Uebergaengen.
            # Die Standzeit ergibt sich aus der Wunschlaenge -- mehr muss man
            # nicht angeben.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            namen = [os.path.basename(str(n)) for n in (params.get("files") or [])]
            pfade = [p for p in (self._output_path(n) for n in namen) if p]
            if len(pfade) < 2:
                return self._json(400, {"error": "Mindestens zwei Bilder auswaehlen"})
            if not demo.available()["video"]:
                return self._json(501, {"error": "ffmpeg fehlt"})
            dauer = max(2.0, min(float(params.get("duration") or 20), 600.0))
            ziel = os.path.join(projekte.bilder(projekte.aktiv()),
                                datetime.now().strftime("%Y%m%d-%H%M%S") + "_film.mp4")
            try:
                demo.baue_video(pfade, ziel, gesamtdauer=dauer)
            except Exception as exc:
                return self._json(500, {"error": f"ffmpeg scheiterte: {exc}"})
            return self._json(200, {"ok": True, "video": os.path.basename(ziel),
                                    "bilder": len(pfade), "dauer": dauer})

        if path == "/api/geschichten":
            # Mehrere Geschichten je Projekt, jede in Baenden. Die Vorgaben
            # gehoeren der Geschichte, die Gliederung dem Band.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            was = params.get("tu")
            schluessel = str(params.get("schluessel") or "")

            if was == "liste":
                return self._json(200, {"geschichten": baender.liste(projekt)})
            if was == "anlegen":
                g = baender.anlegen(projekt, str(params.get("name") or ""),
                                    params.get("globale") or {})
                return self._json(200, g)
            if was == "lesen":
                g = baender.lesen(projekt, schluessel)
                return self._json(200 if g else 404, g or {"error": "nicht gefunden"})
            if was == "speichern":
                g = baender.speichern(projekt, schluessel, params.get("stand") or {})
                return self._json(200 if g else 404, g or {"error": "nicht gefunden"})
            if was == "band":
                g = baender.band_anlegen(projekt, schluessel)
                return self._json(200 if g else 404, g or {"error": "nicht gefunden"})
            if was == "loeschen":
                gut = baender.loeschen(projekt, schluessel)
                return self._json(200 if gut else 404, {"ok": gut})

            # Fassungen: der Stand eines Bandes zu einem Zeitpunkt. Damit
            # laesst sich ein neuer Autor gefahrlos ausprobieren -- die
            # bisherige Arbeit liegt daneben und kommt auf Wunsch zurueck.
            nr = int(params.get("band") or 1)
            if was == "fassungen":
                return self._json(200, {"fassungen":
                                        baender.fassungen(projekt, schluessel, nr)})
            if was == "sichern":
                f = baender.fassung_sichern(projekt, schluessel, nr,
                                            str(params.get("name") or ""))
                return self._json(200 if f else 404,
                                  {"fassung": f} if f else {"error": "nicht gefunden"})
            if was == "holen":
                g = baender.fassung_holen(projekt, schluessel, nr,
                                          int(params.get("index") or 0))
                return self._json(200 if g else 404, g or {"error": "nicht gefunden"})
            if was == "fassung_weg":
                gut = baender.fassung_loeschen(projekt, schluessel, nr,
                                               int(params.get("index") or 0))
                return self._json(200 if gut else 404, {"ok": gut})
            return self._json(400, {"error": "unbekannte Aktion"})

        if path == "/api/expose":
            # Zuerst: worum geht es, welcher Stil, welche Welt. Der Stil gilt
            # danach fuer alle Szenen.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            if not (params.get("idee") or "").strip():
                return self._json(400, {"error": "Keine Idee"})
            # "fiktion" darf fehlen -- dann entscheidet das Modell selbst.
            fiktion = params.get("fiktion")
            vorher = ""
            if params.get("schluessel"):
                g = baender.lesen(projekte.aktiv(), str(params["schluessel"]))
                if g:
                    vorher = baender.vorgeschichte(g, int(params.get("band") or 1))
            auftrag = einreihen("expose", {
                "idee": str(params["idee"]), "fiktion": fiktion,
                "vorher": vorher,
                "anzahl": int(params.get("anzahl") or 0),
                "alter": str(params.get("alter") or ""),
                "modell": str(params.get("modell") or "") or None})
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/gliederung":
            # Das Inhaltsverzeichnis: je Zeile eine Szene, /Name verweist auf
            # einen Baustein. Eingereiht statt sofort ausgefuehrt, weil das
            # grosse Modell die Grafikkarte belegt.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            alle = bausteine.liste(projekt)
            zeilen = geschichte.zeilen_lesen(params.get("zeilen") or [], alle,
                                             bewertung.nach_namen(projekt))
            if not zeilen:
                return self._json(400, {"error": "Keine Szene im Inhaltsverzeichnis"})
            auftrag = einreihen("prompts", {
                "zeilen": zeilen, "stil": str(params.get("stil") or ""),
                # "nummern" sind die Szenen der Geschichte, die hier neu
                # geschrieben werden. Dann stehen in "zeilen" auch nur diese.
                "nummern": [int(n) for n in (params.get("nummern") or [])
                            if str(n).isdigit()],
                "welt": str(params.get("welt") or ""),
                "kurz": str(params.get("kurz") or ""),
                "fiktion": params.get("fiktion"),
                "alter": str(params.get("alter") or ""),
                "schluessel": str(params.get("schluessel") or "") or None,
                "band": int(params.get("band") or 1),
                "modell": str(params.get("modell") or "") or None,
                "prosa": bool(params.get("prosa"))})
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"],
                                    "zeilen": [{"text": z["text"], "ort": z["ort"],
                                                "einstellung": z["einstellung"],
                                                "spiegelung": z["spiegelung"],
                                                "teile": [t["name"] for t in z["teile"]]}
                                               for z in zeilen]})

        if path == "/api/aufbau":
            # Eine ganze Geschichte in eine Gliederung verwandeln. Zwei
            # Stufen: erst Rahmen und Abschnitte, dann die Szenen.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            phase = str(params.get("phase") or "rahmen")
            if phase == "rahmen" and not str(params.get("text") or "").strip():
                return self._json(400, {"error": "Keine Geschichte und keine Idee"})
            auftrag = einreihen("aufbau", {
                "phase": phase,
                "text": str(params.get("text") or ""),
                "kurz": str(params.get("kurz") or ""),
                "welt": str(params.get("welt") or ""),
                "stil": str(params.get("stil") or ""),
                "fiktion": params.get("fiktion"),
                "alter": str(params.get("alter") or ""),
                "anzahl": int(params.get("anzahl") or 12),
                "anfang": str(params.get("anfang") or ""),
                "ende": str(params.get("ende") or ""),
                "kapitel": params.get("kapitel") or [],
                "modell": str(params.get("modell") or "") or None})
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/prosa":
            # Der Text zu jeder Szene, als eigener Schritt vor den Bausteinen.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            if not (params.get("zeilen") or []):
                return self._json(400, {"error": "Keine Szene"})
            # Wer vorkommt und was er ist, geht mit: eine Androidin soll
            # im Text nicht wie ein Mensch beschrieben werden.
            projekt = projekte.aktiv()
            auftrag = einreihen("prosa", {
                "zeilen": params.get("zeilen") or [],
                "figuren": geschichte.besetzung(
                    params.get("zeilen") or [], bausteine.liste(projekt),
                    bewertung.nach_namen(projekt)),
                "nummern": [int(n) for n in (params.get("nummern") or [])
                            if str(n).isdigit()],
                "kurz": str(params.get("kurz") or ""),
                "welt": str(params.get("welt") or ""),
                "alter": str(params.get("alter") or ""),
                "fiktion": params.get("fiktion"),
                # Wer die Prosa schreibt. Fehlt die Angabe, bleibt es beim
                # neutralen Erzaehler -- so wie es bisher war.
                "erzaehler": chat.erzaehlerstimme(
                    params.get("erzaehler"),
                    str(params.get("erzaehler_wer") or ""),
                    str(params.get("erzaehler_text") or "")),
                "modell": str(params.get("modell") or "") or None})
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/ergaenzen":
            # Fehlende Zeilen nachschreiben lassen. Die vorhandenen bleiben,
            # wie sie sind -- nachgereicht wird nur, was fehlt.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            fehlt = int(params.get("fehlt") or 0)
            if fehlt < 1:
                return self._json(400, {"error": "Es fehlt keine Szene"})
            auftrag = einreihen("ergaenzen", {
                "zeilen": params.get("zeilen") or [], "fehlt": fehlt,
                "kurz": str(params.get("kurz") or ""),
                "welt": str(params.get("welt") or ""),
                "stil": str(params.get("stil") or ""),
                "fiktion": params.get("fiktion"),
                "modell": str(params.get("modell") or "") or None})
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/szenen":
            # Aus Gliederung plus geschriebenen Prompts die Ablaufbloecke.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            alle = {b["id"]: b for b in bausteine.liste(projekt)}
            # Dieselbe Zerlegung wie beim Prompt-Schreiben. Frueher stand hier
            # eine eigene, die auf Felder wartete, die die Seite gar nicht
            # schickt -- die Kameraeinstellung fiel damit still unter den Tisch.
            gemerkt = bewertung.nach_namen(projekt)
            zeilen = geschichte.zeilen_lesen(params.get("zeilen") or [],
                                             list(alle.values()), gemerkt)
            stil = str(params.get("stil") or "")
            szenen = geschichte.gliederung_zu_szenen(
                zeilen, params.get("prompts") or [], list(alle.values()), stil)
            # Alle Bausteine der Szenen, nicht nur je einer pro Art: eine
            # zweite Person fiel sonst still heraus, und die Szene beschrieb
            # nur eine von zweien, die einander ansehen.
            gebraucht = []
            for s in szenen:
                gebraucht += (s.get("teile")
                              or [s["person"], s["ort"], s["gegenstand"]])
            benutzt = [alle[k] for k in dict.fromkeys(gebraucht) if k in alle]
            bloecke = geschichte.zu_bloecken(szenen, benutzt, gemerkt)
            je_szene = [int(z.get("bilder") or 1)
                        for z in (params.get("zeilen") or [])]
            if any(n > 1 for n in je_szene):
                geschichte.mit_streuung(bloecke, je_szene, stil,
                                        int(params.get("seed") or 42))
            return self._json(200, {
                "szenen": szenen, "bloecke": bloecke,
                # Was jede Szene an fertigem Bildprompt ergibt -- mit der
                # Beschreibung der Figur statt ihres Namens. Die Oberflaeche
                # zeigte bisher den Text des Sprachmodells, und in dem steht
                # der Name; das sah aus wie ein Fehler und war keiner.
                "je_szene": geschichte.je_szene(szenen, benutzt, gemerkt),
                "bilder": sum(len(b["bausteine"]) for b in bloecke),
                "startbild": geschichte.startbild(szenen, benutzt)})

        if path == "/api/geschichte":
            # Handlung -> Szenen -> Bloecke, wie der Ablauf-Reiter sie kennt.
            # Erzeugt wird hier noch nichts; das entscheidet die Oberflaeche.
            if engine.lock.locked():
                return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            text = (params.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "Keine Handlung"})
            projekt = projekte.aktiv()
            alle = {b["id"]: b for b in bausteine.liste(projekt)}
            gewaehlt = [alle[k] for k in (params.get("ids") or []) if k in alle]
            if not gewaehlt:
                return self._json(400, {"error":
                    "Erst Bausteine anhaken, die vorkommen sollen"})
            erg = chat.geschichte(text, gewaehlt, int(params.get("anzahl") or 8))
            if not erg["szenen"]:
                return self._json(502, {"error": erg["hinweis"]})
            return self._json(200, {
                "szenen": erg["szenen"],
                "hinweis": erg["hinweis"],
                "bloecke": geschichte.zu_bloecken(erg["szenen"], gewaehlt),
                "startbild": geschichte.startbild(erg["szenen"], gewaehlt)})

        if path == "/api/baustein":
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            was = params.get("tu")

            if was == "speichern":
                return self._json(200, bausteine.speichern(projekt, params.get("baustein") or {}))
            if was == "loeschen":
                kennung = str(params.get("id") or "")
                # Vor dem Loeschen die Namen holen: danach gibt es sie nicht
                # mehr, und in den Szenen stuende der Verweis weiter da --
                # als blosses Wort, das ins Leere zeigt.
                weg = next((bausteine.namen(b) for b in bausteine.liste(projekt)
                            if b.get("id") == kennung), [])
                gut = bausteine.loeschen(projekt, kennung)
                zeilen = 0
                if gut:
                    for name in weg:
                        zeilen += baender.verweis_entfernen(projekt, name)
                return self._json(200 if gut else 404,
                                  {"ok": gut, "zeilen": zeilen})
            if was == "prompt":
                # Deutsche Beschreibung -> englischer Prompt mit Luecken.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                text = (params.get("text") or "").strip()
                if not text:
                    return self._json(400, {"error": "Keine Beschreibung"})
                melden("Der Prompt wird geschrieben")
                erg = chat.baustein_prompt(text, str(params.get("art") or "person"))
                melden("")
                erg["prompt"], erg["variablen"] = bausteine.ohne_leere_luecken(
                    erg["prompt"], erg["variablen"])
                if not erg["prompt"]:
                    return self._json(502, {"error":
                        "Das Sprachmodell hat keinen Prompt geliefert."})
                return self._json(200, erg)
            if was == "zusammenfuehren":
                # Zwei Bausteine, eine Figur. Der eine geht im anderen auf,
                # und alle Geschichten des Projekts nennen ab jetzt den
                # bleibenden Namen.
                erg = bausteine.zusammenfuehren(projekt,
                                                str(params.get("von") or ""),
                                                str(params.get("nach") or ""))
                if not erg:
                    return self._json(404, {"error": "Baustein nicht gefunden"})
                zeilen = baender.verweis_umbenennen(projekt, erg["alter_name"],
                                                    erg["neuer_name"])
                return self._json(200, {"ziel": erg["ziel"], "zeilen": zeilen,
                                        "alter_name": erg["alter_name"]})

            if was == "auffrischen":
                # Personen aus der Zeit vor der Trennung: Gesicht und Kleidung
                # standen damals im allgemeinen Prompt oder in einer Luecke.
                # Hier werden sie herausgeloest -- ohne neu zu formulieren.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                offen = [b for b in bausteine.liste(projekt)
                         if b.get("art") == "person"
                         and not ((b.get("gesicht") or "").strip()
                                  and (b.get("kleidung") or "").strip())]
                if not offen:
                    return self._json(200, {"neu": [], "hinweis":
                        "Alle Personen haben schon Gesicht und Kleidung."})
                frisch = []
                for i, b in enumerate(offen, 1):
                    melden(f"Person {i} von {len(offen)}: {b['name']}", i, len(offen))
                    # Was frueher in {kleidung} steckte, gehoert mit in den
                    # Text, sonst faellt es beim Trennen unter den Tisch.
                    ganz = bausteine.einsetzen(b.get("prompt") or "",
                                               b.get("variablen") or {})
                    teile = chat.person_teilen(ganz)
                    if not teile:
                        continue
                    b = dict(b)
                    b["prompt"] = teile["prompt"]
                    b["gesicht"] = (b.get("gesicht") or "").strip() or teile["gesicht"]
                    b["kleidung"] = (b.get("kleidung") or "").strip() or teile["kleidung"]
                    # Die Luecken sind jetzt eingesetzt, also weg damit.
                    b["variablen"] = {}
                    frisch.append(bausteine.speichern(projekt, b))
                melden("")
                return self._json(200, {"neu": frisch, "hinweis": ""})

            if was == "pruefen":
                # Kostet nichts: kein Sprachmodell, nur Nachsehen. Deshalb
                # auch kein Puls und keine Warteschlange.
                zeilen = params.get("zeilen") or []
                alle = bausteine.liste(projekt)
                funde = geschichte.pruefen(zeilen, alle,
                                           bewertung.nach_namen(projekt))
                return self._json(200, {"funde": funde,
                                        "szenen": len([z for z in zeilen
                                                       if str(z.get("text") or "").strip()])})

            if was == "vorschlagen":
                # Alles, was die Geschichte mit /Name verlangt und noch nicht
                # gibt, gleich anlegen -- mit einem geschriebenen Prompt, den
                # der Benutzer danach abaendert. Ein leeres Feld hilft
                # niemandem, ein Vorschlag schon.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                zeilen = [str(z.get("text") or "") if isinstance(z, dict) else str(z)
                          for z in (params.get("zeilen") or [])]
                da = bausteine.liste(projekt)
                offen = geschichte.offene_verweise(zeilen, da)[:40]
                if not offen:
                    return self._json(200, {"neu": [], "hinweis":
                        "Alle erwaehnten Bausteine gibt es schon."})
                # Was der Benutzer selbst erklaert hat -- /Susi "weisse Frau"
                # --, schlaegt die Vermutung des Sprachmodells. Er hat es ja
                # gerade hingeschrieben.
                erklaert = {}
                for z in zeilen:
                    for name, text in geschichte.definitionen(z)[1].items():
                        erklaert[name.lower()] = text
                melden(f"{len(offen)} Bausteine werden eingeordnet", 0, len(offen) + 1)
                geraten = chat.bausteine_raten(offen, "\n".join(zeilen))
                neu, unklar = [], []
                for i, e in enumerate(geraten, 1):
                    melden(f"Baustein {i} von {len(geraten)}: {e['name']}",
                           i, len(geraten) + 1)
                    if not e["art"]:
                        # Lieber nichts anlegen als das Falsche: ein
                        # Gegenstand als Person bekaeme Gesicht und Kleidung.
                        unklar.append(e["name"])
                        continue
                    e["beschreibung"] = (erklaert.get(e["name"].lower())
                                         or e["beschreibung"])
                    fertig = chat.baustein_prompt(e["beschreibung"] or e["name"],
                                                  e["art"])
                    if not fertig.get("prompt"):
                        continue
                    # Eine Luecke ohne Vorgabe ist in einem Vorschlag eine
                    # Falle: sie faellt erst im fertigen Bild auf.
                    text_fertig, werte = bausteine.ohne_leere_luecken(
                        fertig["prompt"], fertig.get("variablen") or {})
                    neu.append(bausteine.speichern(projekt, {
                        "art": e["art"], "name": e["name"],
                        "prompt": text_fertig,
                        "gesicht": fertig.get("gesicht") or "",
                        "kleidung": fertig.get("kleidung") or "",
                        "variablen": werte}))
                melden("")
                return self._json(200, {"neu": neu, "unklar": unklar,
                    "hinweis": ("Nicht eingeordnet, bitte von Hand anlegen: "
                                + ", ".join(unklar)) if unklar else ""})

            if was == "teilprompt":
                # Gesicht oder Kleidung einzeln: der Benutzer hat das Feld
                # von Hand auf Deutsch gefuellt und will es englisch zurueck.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                feld = str(params.get("feld") or "")
                text = (params.get("text") or "").strip()
                if not text:
                    return self._json(400, {"error": "Keine Beschreibung"})
                melden(f"Der Prompt für {feld} wird geschrieben")
                fertig = chat.teil_prompt(feld, text,
                                          str(params.get("person") or ""))
                melden("")
                if not fertig:
                    return self._json(502, {"error":
                        "Das Sprachmodell hat keinen Prompt geliefert."})
                return self._json(200, {"text": fertig})

            if was == "katalog":
                # Was in einer Geschichte mit /Name erwaehnt wird, aber noch
                # nicht angelegt ist, gehoert sichtbar dazu: es ist eine
                # Arbeitsanweisung, keine Luecke zum Uebersehen.
                fehlend = []
                for pj in projekte.liste():
                    vorhanden = bausteine.liste(pj["key"])
                    zeilen = []
                    for eintrag in baender.liste(pj["key"]):
                        g = baender.lesen(pj["key"], eintrag["schluessel"])
                        for b in g.get("baende") or []:
                            zeilen += b.get("zeilen") or []
                    for n in geschichte.offene_verweise(zeilen, vorhanden):
                        fehlend.append({"name": n, "projekt": pj["key"],
                                        "projektname": pj["label"]})
                return self._json(200, {"bausteine": bausteine.katalog(),
                                        "projekte": projekte.liste(),
                                        "fehlend": fehlend})
            if was == "kopieren":
                if not self._nur_hier():
                    return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
                erg = bausteine.kopieren(str(params.get("von") or ""),
                                         str(params.get("nach") or ""),
                                         str(params.get("id") or ""))
                if not erg:
                    return self._json(404, {"error":
                        "Baustein nicht gefunden oder schon im Zielprojekt"})
                return self._json(200, erg)

            if was == "vorschlaege":
                # Zehn verschiedene Hosen fuer die Luecke {hose}. Ohne das
                # Umfeld schlaegt das Modell etwas vor, das nicht zur Person
                # passt.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                werte = chat.luecken_vorschlaege(
                    str(params.get("luecke") or ""),
                    str(params.get("umfeld") or ""),
                    int(params.get("anzahl") or 10))
                if not werte:
                    return self._json(502, {"error":
                        "Das Sprachmodell hat nichts vorgeschlagen."})
                return self._json(200, {"werte": werte})

            if was == "zusammensetzen":
                alle = {b["id"]: b for b in bausteine.liste(projekt)}
                teile = [alle[k] for k in (params.get("ids") or []) if k in alle]
                if params.get("augen") and len(teile) == 1:
                    # Die Grossaufnahme der Augen: allein aus dem Gesicht,
                    # ohne Kleidung, ohne Ort, ohne Freistellung.
                    fertig = bausteine.augen_prompt(teile[0],
                                                    params.get("werte") or {})
                    fertig = bausteine.mit_stil(fertig,
                                                str(params.get("stil") or ""))
                    if not fertig:
                        return self._json(400, {"error":
                            "Erst eine Gesichtsbeschreibung eintragen."})
                    return self._json(200, {"prompt": fertig, "vorlage": ""})
                fertig = bausteine.zusammensetzen(teile, params.get("werte") or {})
                # Das Musterbild eines einzelnen Bausteins zeigt ihn ganz und
                # vor nichts. Sobald mehrere zusammenkommen, ist es eine Szene
                # und kein Muster mehr.
                if params.get("freistellen") and len(teile) == 1:
                    fertig = bausteine.freigestellt(fertig, teile[0].get("art"))
                # Der Stil kommt zuletzt. Bringt der Baustein einen eigenen
                # mit, steht der schon im Text -- dann nicht noch einmal.
                if not (len(teile) == 1 and (teile[0].get("stil") or "").strip()):
                    fertig = bausteine.mit_stil(fertig,
                                                str(params.get("stil") or ""))
                return self._json(200, {
                    "prompt": fertig,
                    # Dieselbe Mischung mit offenen Luecken -- so wird sie als
                    # Szene gespeichert und bleibt wiederverwendbar.
                    "vorlage": bausteine.vorlage(teile)})
            return self._json(400, {"error": "unbekannte Aktion"})

        if path == "/api/szenenbau":
            # Eine Szene in Stufen bauen: Kulisse, Posen, Spiegelung,
            # Zusammensetzen. Der Bauplan entsteht im Auftrag selbst -- das
            # Sprachmodell braucht ein paar Sekunden, und die gehoeren in
            # den Fortschritt, nicht in eine haengende Antwort.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            if not (params.get("text") or "").strip():
                return self._json(400, {"error": "Keine Beschreibung"})
            projekt = projekte.aktiv()
            alle = {b["id"] for b in bausteine.liste(projekt)}
            gewaehlt = [k for k in (params.get("bausteine") or []) if k in alle]
            if not gewaehlt:
                return self._json(400, {"error":
                    "Erst Bausteine angeben, die vorkommen sollen"})
            params["bausteine"] = gewaehlt
            auftrag = einreihen("szenenbau", params)
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/sechsseiten":
            # Ein Gegenstand, sechsmal gerade von einer Seite -- und der
            # Katalog, in dem die Eintraege liegen. Die Bilder gehen nicht
            # nach outputs/, deshalb hat der Reiter seine eigene Liste.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            was = params.get("tu")

            if was == "liste":
                # Der ganze Katalog, nicht nur das aktive Projekt: wer einen
                # Gegenstand einmal von sechs Seiten hat, soll ihn im
                # naechsten Vorhaben wiederfinden.
                return self._json(200, {"katalog": sechsseiten.katalog(),
                                        "seiten": [{"key": k, "label": v[0]}
                                                   for k, v in sechsseiten.SEITEN.items()],
                                        "projekt": projekt})
            if was == "vorschlag":
                # Erst anschauen, dann rechnen: das Sprachmodell schreibt den
                # ganzen Satz Befehle, der Benutzer bessert nach. Ungesehen
                # ins Bild gehen zu lassen, was es sich ausgedacht hat, kostet
                # bei sechs Bildern zehn Minuten, bis der Fehler sichtbar wird.
                if engine.lock.locked():
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                roh = str(params.get("text") or "").strip()
                # Nach dem ersten Bild schreibt das Sprachmodell die Ansichten
                # zu genau dem Gegenstand, der darin steckt -- und laesst den
                # Gegenstandstext stehen. Neu ausformuliert waere er ein
                # anderer Gegenstand als der im Bild.
                vorher = sechsseiten.eintrag(
                    str(params.get("eintrag_projekt") or projekt),
                    str(params.get("eintrag") or "")) \
                    if params.get("eintrag") else None
                fest = (vorher or {}).get("prompt") or ""
                if not roh and not fest:
                    return self._json(400, {"error": "Bitte den Gegenstand beschreiben"})
                # Was schon dasteht, bleibt: der Vorschlag fuellt nur die
                # Luecken. Wer eine Seite selbst geschrieben hat, will sie
                # nicht ueberschrieben sehen.
                eigen = sechsseiten.lies_eingabe(roh)
                melden("Das Sprachmodell schreibt den Vorschlag")
                plan = chat.seiten_plan(fest or eigen["allgemein"] or roh,
                                        str(params.get("modell") or "") or None)
                melden("")
                if not plan["sichten"]:
                    return self._json(502, {"error":
                        "Das Sprachmodell hat nichts geliefert."})
                return self._json(200, {"text": sechsseiten.als_eingabe(
                    fest or plan["gegenstand"] or eigen["allgemein"],
                    {**plan["sichten"], **eigen["sichten"]},
                    {**plan["ohne"], **eigen["ohne"]},
                    eigen["hintergrund"]
                    or (vorher or {}).get("hintergrund") or "")})

            if was == "loeschen":
                # Loescht Bilder auf der Platte -- wie beim Projekt nur vom
                # Rechner des Servers aus.
                if not self._nur_hier():
                    return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
                gut = sechsseiten.loeschen(
                    str(params.get("projekt") or projekt),
                    str(params.get("id") or ""))
                return self._json(200 if gut else 404, {"ok": gut})

            if not (params.get("text") or "").strip() \
                    and not params.get("gegenstand") \
                    and not params.get("eintrag"):
                return self._json(400, {"error":
                    "Bitte den Gegenstand beschreiben oder einen Baustein waehlen"})
            auftrag = einreihen("sechsseiten", params)
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/detektor":
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            was = params.get("tu") or "liste"
            if was == "liste":
                z = datensatz.uebersicht(projekt)["zahlen"]
                return self._json(200, {"projekt": projekt,
                                        "modelle": [{"key": k, "label": v[1]}
                                                    for k, v in detektor.MODELLE.items()],
                                        "aufgenommen": z.get("ok", 0),
                                        "laeufe": detektor.laeufe(projekt)})
            if was == "starten":
                auftrag = einreihen("detektor", params)
                return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})
            if was == "ausprobieren":
                try:
                    bild = decode(params.get("bild") or "")
                    puffer = io.BytesIO()
                    bild.convert("RGB").save(puffer, format="PNG")
                    boxen = detektor.erkennen(projekt, str(params.get("lauf") or ""),
                                          puffer.getvalue(),
                                          float(params.get("schwelle") or 0.25))
                except Exception as exc:
                    return self._json(400, {"error": str(exc)})
                return self._json(200, {"boxen": boxen, "breite": bild.size[0],
                                        "hoehe": bild.size[1]})
            return self._json(400, {"error": "unbekannt"})

        if path == "/api/fotodaten":
            # Echte Fotos zu Trainingsdaten -- siehe fotodaten.py. "katalog"
            # liefert die Achsen der Motivart, "plan" zaehlt vorab, wie viele
            # Bilder entstehen, "starten" reiht den Auftrag ein.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            was = params.get("tu") or "katalog"
            subject = params.get("subject") or "fahrzeug"
            if was == "katalog":
                wolke = cloud.aktiv("bild")
                return self._json(200, {"achsen": fotodaten.katalog(subject),
                                        "namen": fotodaten.namen(subject),
                                        "wirkung": fotodaten.WIRKUNG_CLOUD
                                        if wolke and wolke.get("art") == "beschreibung"
                                        else {},
                                        "arten": list(fotodaten.ARTEN),
                                        "max_alle": fotodaten.MAX_ALLE,
                                        "cloud": bool(cloud.aktiv("bild")),
                                        "lokal": LOKAL})
            try:
                belegung = fotodaten.plan(params.get("achsen") or {},
                                          params.get("art") or "beides",
                                          int(params.get("anzahl") or 12), 0, subject)
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            if was == "plan":
                return self._json(200, {"je_foto": len(belegung),
                                        "beispiele": belegung[:6]})
            if was == "starten":
                fotos = [f for f in (params.get("fotos") or []) if f.get("bild")]
                if not fotos:
                    return self._json(400, {"error": "Bitte mindestens ein Foto wählen"})
                if not str(params.get("klasse") or "").strip():
                    return self._json(400, {"error": "Bitte eine Klasse angeben, z. B. anhaengerkupplung"})
                if "paint" in (params.get("achsen") or {}) \
                        and not str(params.get("paint_target") or "").strip():
                    return self._json(400, {"error": "Die Farbachse braucht ein Ziel — "
                                            "was soll umgefärbt werden, z. B. „die Karosserie“"})
                if not LOKAL and not cloud.aktiv("bild"):
                    return self._json(400, {"error": "Kein Bildmodell: bitte unter "
                                            "Cloud-Modelle eines eintragen und einschalten"})
                nummer = einreihen("fotodaten", params)["nummer"]
                return self._json(202, {"ok": True, "nummer": nummer,
                                        "bilder": len(belegung) * len(fotos)})
            return self._json(400, {"error": "unbekannt"})

        if path == "/api/datensatz":
            # Die Pruefliste: ansehen, aufnehmen, verwerfen, Box neu setzen.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            if (params.get("tu") or "liste") == "liste":
                return self._json(200, {**datensatz.uebersicht(projekt),
                                        "projekt": projekt,
                                        "umgebungen": vervielfaeltigen.UMGEBUNGEN})
            if params.get("tu") == "vervielfaeltigen":
                if not datensatz.originale(projekt):
                    return self._json(400, {"error": "Noch kein aufgenommenes Bild mit "
                                            "Box -- erst Basisbilder erzeugen und prüfen"})
                nummer = einreihen("vervielfaeltigen", params)["nummer"]
                return self._json(202, {"ok": True, "nummer": nummer})
            if params.get("tu") == "setzen":
                e = datensatz.setzen(projekt, str(params.get("datei") or ""),
                                     str(params.get("status") or ""),
                                     params.get("box"))
                if not e:
                    return self._json(400, {"error": "Das ging nicht -- ohne Box "
                                            "laesst sich kein Bild aufnehmen"})
                return self._json(200, e)
            return self._json(400, {"error": "unbekannt"})

        if path == "/api/cloud":
            # Cloud-Modelle: lesen, speichern, ausprobieren. Der Schluessel
            # geht nie an die Seite zurueck. Speichern nur vom eigenen
            # Rechner -- im Netz koennte sonst jeder die Bilder ueber ein
            # fremdes Konto umleiten.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            was = params.get("tu") or "lesen"
            if was == "lesen":
                return self._json(200, {**cloud.oeffentlich(),
                                        "vorlagen": cloud.VORLAGEN})
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            if was == "speichern":
                return self._json(200, cloud.schreiben(params.get("einstellungen") or {}))
            if was == "pruefen":
                if engine.lock.locked() and params.get("platz") == "sprache" \
                        and not cloud.aktiv("sprache"):
                    return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
                return self._json(200, cloud.pruefen(str(params.get("platz") or "")))
            return self._json(400, {"error": "unbekannt"})

        if path == "/api/projekt":
            # Anlegen, wechseln, umbenennen, loeschen. Alles am eigenen
            # Rechner: ein Projekt zu loeschen nimmt Bilder mit.
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            was = params.get("tu")
            schluessel = str(params.get("key") or "")
            if was == "anlegen":
                neu_p = projekte.anlegen(str(params.get("name") or ""))
                return self._json(200, {"ok": True, "projekt": neu_p,
                                        "aktiv": projekte.aktiv()})
            if was == "waehlen":
                gut = projekte.waehlen(schluessel)
                return self._json(200 if gut else 404,
                                  {"ok": gut, "aktiv": projekte.aktiv()})
            if was == "umbenennen":
                gut = projekte.umbenennen(schluessel, str(params.get("name") or ""))
                return self._json(200 if gut else 404, {"ok": gut})
            if was == "loeschen":
                # Ein laufender Auftrag schreibt womoeglich gerade dorthin.
                if engine.lock.locked():
                    return self._json(409, {"error":
                        "Erst abwarten: es laeuft ein Auftrag"})
                gut = projekte.loeschen(schluessel)
                return self._json(200 if gut else 404,
                                  {"ok": gut, "aktiv": projekte.aktiv()})
            return self._json(400, {"error": "unbekannte Aktion"})

        if path == "/api/bild-lesen":
            # Die kurze Fassung: wer ist zu sehen. Fuer den Ablauf-Reiter, wo
            # die Beschreibung in die Bewahrungsklauseln wandert und nicht als
            # ganzer Bildprompt gebraucht wird.
            bild = self._bild_aus_anfrage()
            if isinstance(bild, tuple):
                return self._json(*bild)
            return self._json(200, chat.bild_lesen(bild))

        if path == "/api/bild-prompt":
            # Rueckwaerts: aus einem mitgebrachten Bild den Prompt schreiben.
            # Wie beim Chat nicht waehrend eines Auftrags -- Ollama und das
            # Bildmodell wuerden sich um die Grafikkarte streiten.
            bild = self._bild_aus_anfrage()
            if isinstance(bild, tuple):
                return self._json(*bild)
            ergebnis = chat.bild_zu_prompt(bild)
            if not ergebnis["prompt"]:
                return self._json(502, {"error":
                    "Das Sprachmodell hat keinen Prompt geliefert."})
            return self._json(200, ergebnis)

        if path == "/api/delete":
            # Loescht eine Datei auf dem Rechner des Servers -- wie beim
            # GIMP-Aufruf nur von dort aus erlaubt.
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            ziel = self._output_path(os.path.basename(params.get("file") or ""))
            if not ziel:
                return self._json(404, {"error": "Bild nicht gefunden"})
            try:
                os.remove(ziel)
            except OSError as exc:
                return self._json(500, {"error": f"liess sich nicht loeschen: {exc}"})
            # Die Note gehoert zum Bild. Ein gemerkter Prompt ueberlebt es
            # aber -- der steckt dann in bewertung.json und nicht mehr im PNG.
            name = os.path.basename(ziel)
            if not bewertung.lesen(projekte.aktiv())["bilder"].get(name, {}).get("name"):
                bewertung.loeschen(projekte.aktiv(), name)
            return self._json(200, {"ok": True, "file": name})

        if path == "/api/bewertung":
            # Note, Notiz und Name eines Bildes. Der Prompt wird aus dem PNG
            # mitgenommen: das Bild darf spaeter weg, der gute Prompt bleibt.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            projekt = projekte.aktiv()
            if params.get("tu") == "verbessern":
                return self._json(200, bewertung.verbessern(
                    projekt, params.get("was") or "", params.get("text") or ""))
            datei = os.path.basename(str(params.get("file") or ""))
            if not self._output_path(datei):
                return self._json(404, {"error": "Bild nicht gefunden"})
            prompt = str(params.get("prompt") or "")
            if not prompt and params.get("name"):
                prompt = self._prompt_im_bild(self._output_path(datei))
            return self._json(200, bewertung.setzen(
                projekt, datei, note=params.get("note"),
                notiz=params.get("notiz"), name=params.get("name"),
                prompt=prompt))

        if path == "/api/shutdown":
            if not self._nur_hier():
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            # Erst antworten, dann abschalten: sonst sieht die Seite nur einen
            # abgebrochenen Aufruf und meldet einen Fehler.
            self._json(200, {"ok": True})
            engine.cancel()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return None

        if path == "/api/open-in-gimp":
            # Startet ein Programm auf dem Rechner des Servers. Deshalb nur von
            # dort aus erreichbar -- bei QWEN_HOST=0.0.0.0 koennte sonst jeder
            # im Netz GIMP-Fenster aufpoppen lassen.
            if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                return self._json(403, {"error": "Nur vom Rechner des Servers aus"})
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            target = self._output_path(os.path.basename(params.get("file") or ""))
            if not target:
                return self._json(404, {"error": "Bild nicht gefunden"})
            if not shutil.which(GIMP_CMD):
                return self._json(501, {"error": f"{GIMP_CMD} ist nicht installiert"})
            if not WINDOWS and not (os.environ.get("DISPLAY")
                                    or os.environ.get("WAYLAND_DISPLAY")):
                return self._json(501, {"error":
                    "Der Server sieht keine Anzeige. start.sh aus einer Desktop-Sitzung starten."})
            try:
                # Losgeloest vom Server: GIMP soll weiterlaufen, wenn das
                # Konsolenfenster des Servers geschlossen wird.
                eigen = ({"creationflags": subprocess.DETACHED_PROCESS
                          | subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS
                         else {"start_new_session": True})
                subprocess.Popen(
                    [GIMP_CMD, target], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, **eigen)
            except OSError as exc:
                return self._json(500, {"error": f"GIMP liess sich nicht starten: {exc}"})
            return self._json(200, {"ok": True})

        if path == "/api/demo":
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            auftrag = einreihen("demo", params)
            return self._json(202, {"ok": True, "nummer": auftrag["nummer"]})

        if path == "/api/retusche":
            # Eine Stelle nachbessern: Bild aus der Galerie (per Name) oder
            # hochgeladen, dazu die gemalte Maske. Geprueft wird hier, damit
            # ein leerer Pinselstrich nicht erst in der Warteschlange scheitert.
            params = self._body()
            if params is None:
                return self._json(400, {"error": "ungueltiges JSON"})
            if params.get("datei"):
                pfad = self._output_path(os.path.basename(str(params["datei"])))
                if not pfad:
                    return self._json(404, {"error": "Bild nicht gefunden"})
                params["pfad"] = pfad
            elif not params.get("bild"):
                return self._json(400, {"error": "Kein Bild gewählt"})
            if not params.get("maske"):
                return self._json(400, {"error": "Bitte die Stelle mit dem Pinsel markieren"})
            try:
                gemalt = decode(params["maske"])
                if not retusche.maske_lesen(gemalt, gemalt.size).getbbox():
                    return self._json(400, {"error": "Bitte die Stelle mit dem Pinsel markieren"})
            except Exception as exc:
                return self._json(400, {"error": f"Maske nicht lesbar: {exc}"})
            if not str(params.get("prompt") or "").strip():
                return self._json(400, {"error": "Bitte sagen, was an der Stelle anders werden soll"})
            nummer = einreihen("retusche", params)["nummer"]
            return self._json(202, {"ok": True, "nummer": nummer})

        if path == "/api/chat":
            # Mit Gedaechtnis: der Verlauf liegt beim Server, damit ein
            # Nachsatz wie "und jetzt noch einen Hut dazu" weiss, worauf er
            # sich bezieht. Ein Benutzer, ein Gespraech -- das Programm
            # laeuft ohnehin nur fuer einen.
            length = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                return self._json(400, {"error": f"ungueltiges JSON: {exc}"})
            if params.get("neu"):
                gespraech.clear()
                return self._json(200, {"ok": True, "verlauf": []})
            text = (params.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "Kein Text"})
            # Das Sprachmodell belegt selbst GPU-Speicher; solange das Bildmodell
            # rechnet, ist daneben kein Platz.
            if engine.lock.locked():
                return self._json(409, {"error": "Es laeuft gerade ein Auftrag"})
            try:
                plan = chat.interpret(text, int(params.get("has_images") or 0),
                                      verlauf=list(gespraech))
            except RuntimeError as exc:
                return self._json(502, {"error": str(exc)})
            gespraech.append({"role": "user", "content": text})
            # Das Modell bekommt seine eigene Antwort als JSON zurueck -- so
            # weiss es beim naechsten Satz, was gerade eingestellt ist.
            gespraech.append({"role": "assistant",
                              "content": json.dumps(plan, ensure_ascii=False)})
            del gespraech[:-GESPRAECH_LAENGE]
            plan["verlauf"] = [{"wer": m["role"], "was": m["content"][:400]}
                               for m in gespraech]
            return self._json(200, plan)

        if path != "/api/generate":
            return self._json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", 0))
        try:
            params = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            return self._json(400, {"error": f"ungueltiges JSON: {exc}"})

        refs = params.get("images") or []

        # Musterbilder von Bausteinen als Vorlage. Wer mehrere Personen in
        # einem Bild will, hat sie meist schon als Baustein mit Musterbild
        # angelegt -- dieselben Bilder noch einmal von Hand hochzuladen ist
        # Arbeit ohne Gewinn. Sie stehen vor den hochgeladenen: bei "Figur in
        # eine Szene setzen" ist das erste Bild die Szene.
        holen = self._bausteinbilder(params)
        if isinstance(holen, tuple):
            return self._json(*holen)
        if holen:
            refs = holen + list(refs)
            params["images"] = refs

        # Getippter Kurzbefehl: Er ist die ausdrueckliche Absicht, seine
        # Einstellungen setzen sich deshalb gegen die Regler durch. Wird ein
        # Effekt dagegen im Menue gewaehlt, hat die Oberflaeche die Regler
        # bereits sichtbar umgestellt.
        typed, rest = parse_command(params.get("prompt", ""))
        if typed:
            params["prompt"] = rest
            params["effect"] = typed
            params.update(overrides(EFFECTS[typed]))

        spec = EFFECTS.get(params.get("effect") or "", {})
        mode = params.get("mode") or "t2i"
        has_text = bool(params.get("prompt", "").strip())
        if not has_text and not spec and not params.get("form") \
                and mode not in ("gruppe", "person", "varianten"):
            return self._json(400, {"error": "Prompt ist leer"})
        if spec.get("needs_image") and not refs:
            return self._json(400, {
                "error": f"„{spec['label']}\u201c braucht ein Bild \u2013 bitte eines hochladen"})
        if len(refs) > MAX_REFERENCES:
            return self._json(400, {"error": f"Hoechstens {MAX_REFERENCES} Referenzbilder"})
        if mode in ("edit", "person", "varianten") and not refs:
            return self._json(400, {"error": "Bitte ein Referenzbild hochladen"})
        if mode == "gruppe":
            act = GROUP_ACTIONS.get(params.get("action") or "zusammen") or GROUP_ACTIONS["zusammen"]
            if len(refs) < act["min"]:
                return self._json(400, {"error":
                    f"„{act['label']}“ braucht mindestens {act['min']} Referenzbild(er)"})
            if params.get("action") == "entfernen" and not has_text:
                return self._json(400, {"error": "Bitte beschreiben, wer entfernt werden soll"})

        # Kameraeinstellung und Spiegelung, dieselben wie hinter dem
        # Rueckwaertsschraegstrich in der Geschichte -- hier als eigene
        # Felder, damit sich in Text->Bild sauber angeben laesst, was zu
        # sehen ist und was sich darin spiegelt. Ein Paar wie "Blick hinaus"
        # ergibt zwei Prompts und damit zwei Auftraege; die laufen in einem
        # Ladevorgang durch, weil sie sich sonst in nichts unterscheiden.
        texte = [params.get("prompt", "")]
        if str(params.get("einstellung") or "") and has_text:
            texte = geschichte.mit_einstellung(
                params["prompt"], str(params["einstellung"]),
                str(params.get("spiegelung") or ""),
                bewertung.nach_namen(projekte.aktiv()))

        nummern = []
        for text in texte:
            eigener = dict(params, prompt=text)
            nummern.append(einreihen("generate", eigener)["nummer"])
        return self._json(202, {"ok": True, "nummer": nummern[0],
                                "nummern": nummern})


class _Server(ThreadingHTTPServer):
    """Unter Windows den Port fuer sich allein.

    Python setzt SO_REUSEADDR. Unter Linux verhindert das einen zweiten
    Start trotzdem, unter Windows aber erlaubt es mehreren Prozessen
    denselben Port -- die Anfragen landen dann mal hier, mal dort. Gemessen:
    ein Auftrag lief im alten Server mit altem Code, waehrend der neue nichts
    davon wusste. SO_EXCLUSIVEADDRUSE macht den zweiten Start zu einem
    klaren Fehler.
    """

    allow_reuse_address = not WINDOWS

    def server_bind(self):
        if WINDOWS:
            import socket
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    try:
        server = _Server((HOST, PORT), Handler)
    except OSError as fehler:
        print(f"Port {PORT} ist belegt -- laeuft schon ein Server? Dann einfach "
              f"http://{HOST.replace('0.0.0.0', '127.0.0.1')}:{PORT} oeffnen, "
              f"oder mit einem anderen Port starten: start.bat 7861\n({fehler})",
              file=sys.stderr)
        sys.exit(1)
    print(f"Qwen-Image WebUI laeuft auf http://{HOST}:{PORT}  (Strg+C zum Beenden)")
    print(f"Bilder landen in {projekte.bilder(projekte.aktiv())}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    else:
        # serve_forever() kehrt nur zurueck, wenn /api/shutdown es angehalten hat.
        print("ueber die Oberflaeche beendet")
    server.server_close()


if __name__ == "__main__":
    main()
