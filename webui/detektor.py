"""Einen Detektor auf dem eigenen Datensatz trainieren, ansehen, ausprobieren.

Das Modell ist **D-FINE** (Apache 2.0) aus `transformers`. Vorher stand hier
Ultralytics YOLO -- das steht unter AGPL-3.0, und Ultralytics zaehlt die
trainierten Gewichte mit dazu: ein damit trainierter Detektor waere selbst
AGPL oder braeuchte deren kostenpflichtige Lizenz. D-FINE ist so genau wie
ein YOLO derselben Groesse, seine Gewichte sind frei, und es braucht keine
zweite Umgebung -- `transformers` ist ohnehin da.

Gerechnet wird in einem eigenen Prozess (`detektor_lauf.py`), damit die Karte
am Ende bestimmt wieder frei ist. Ein Training ist ein Auftrag in der
Warteschlange wie jedes Bild.

Ablage je Projekt:

    projekte/<p>/datensatz/train.txt, val.txt     die Aufteilung
    projekte/<p>/detektor/<lauf>/
        gewichte/            das trainierte Modell (save_pretrained)
        ergebnisse.csv       je Epoche Verlust und Kennzahlen
        einstellungen.json   womit trainiert wurde
        val_vorhersagen.jpg  vier Validierungsbilder: gruen Wahrheit, rot Vorhersage
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time

import datensatz
import projekte

HIER = os.path.dirname(os.path.abspath(__file__))
SKRIPT = os.path.join(HIER, "detektor_lauf.py")

MODELLE = {"dfine-nano": ("ustc-community/dfine-nano-coco",
                          "Nano -- schnell, fuer den Anfang"),
           "dfine-small": ("ustc-community/dfine-small-coco",
                           "Small -- genauer, rund doppelt so lange"),
           "dfine-medium": ("ustc-community/dfine-medium-coco",
                            "Medium -- noch genauer, braucht viele Bilder")}
LAUF = re.compile(r"\d{8}-\d{6}_dfine-(?:nano|small|medium)")
BILD = re.compile(r"[\w.\-]+\.(?:png|jpg)")


def ordner(projekt: str) -> str:
    pfad = os.path.join(projekte.ordner(projekt), "detektor")
    os.makedirs(pfad, exist_ok=True)
    return pfad


# --- Aufteilung -----------------------------------------------------------
def _gruppe(datei: str) -> str:
    """Bilder eines Auftrags gehoeren zusammen in train oder in val.

    Varianten eines Laufs aehneln sich -- verteilt auf beide Seiten, mess
    die Validierung nur, wie gut das Modell den Nachbarn wiedererkennt.
    """
    teile = datei.split("_")
    return "_".join(teile[:2]) if len(teile) > 2 else datei


def _wert(text: str) -> float:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def aufteilen(projekt: str, val_anteil: float) -> dict:
    """Aufgenommene Bilder in train und val teilen -- stabil ueber den Namen.

    Dieselbe Gruppe landet bei jedem Lauf auf derselben Seite, auch wenn
    neue Bilder dazukommen. Sonst wanderten Bilder zwischen train und val,
    und zwei Laeufe waeren nicht vergleichbar. train.txt und val.txt gehen
    zusaetzlich auf die Platte: dieselbe Aufteilung fuer andere Werkzeuge.
    """
    wurzel = datensatz.wurzel(projekt)
    eintraege = sorted((e for e in datensatz.eintraege(projekt)
                        if e.get("status") == "ok" and e.get("box")),
                       key=lambda e: e["datei"])
    if len(eintraege) < 2:
        raise RuntimeError("Fuer ein Training braucht es mindestens zwei "
                           "aufgenommene Bilder im Datensatz")
    gruppen = sorted({_gruppe(e["datei"]) for e in eintraege})
    hinweis = ""
    if len(gruppen) > 1:
        val_gruppen = {g for g in gruppen if _wert(g) < val_anteil}
        # Mindestens eine Gruppe auf jeder Seite.
        if not val_gruppen:
            val_gruppen = {min(gruppen, key=_wert)}
        if val_gruppen == set(gruppen):
            val_gruppen.discard(max(gruppen, key=_wert))
        val = [e for e in eintraege if _gruppe(e["datei"]) in val_gruppen]
    else:
        val = [e for e in eintraege if _wert(e["datei"]) < val_anteil] or eintraege[:1]
        hinweis = ("Alle Bilder stammen aus einem Auftrag -- die Validierung "
                   "ist darum zu optimistisch.")
    train = [e for e in eintraege if e not in val]
    for name, liste in (("train.txt", train), ("val.txt", val)):
        with open(os.path.join(wurzel, name), "w", encoding="utf-8") as fh:
            fh.write("".join(os.path.join(wurzel, "images", e["datei"]) + "\n"
                             for e in liste))
    return {"train": train, "val": val, "hinweis": hinweis,
            "bilder": os.path.join(wurzel, "images")}


# --- Training -------------------------------------------------------------
def trainieren(projekt: str, modell: str, epochen: int, bildgroesse: int,
               val_anteil: float, melden, abbrechen) -> dict:
    """Ein Training als eigener Prozess.

    `melden(text, ist, von)` bekommt den Fortschritt aus ergebnisse.csv,
    `abbrechen()` sagt, ob der Benutzer gestoppt hat.
    """
    if modell not in MODELLE:
        raise RuntimeError(f"Unbekanntes Modell: {modell}")
    teilung = aufteilen(projekt, val_anteil)
    name = time.strftime("%Y%m%d-%H%M%S") + "_" + modell
    ziel = os.path.join(ordner(projekt), name)
    os.makedirs(ziel)
    einstellungen = {"modell": modell, "quelle": MODELLE[modell][0],
                     "epochen": epochen, "bildgroesse": bildgroesse,
                     "train": len(teilung["train"]), "val": len(teilung["val"]),
                     "hinweis": teilung["hinweis"],
                     "klassen": datensatz.klassen(projekt)}
    with open(os.path.join(ziel, "einstellungen.json"), "w", encoding="utf-8") as fh:
        json.dump(einstellungen, fh, ensure_ascii=False, indent=1)
    auftrag = os.path.join(ziel, "auftrag.json")
    with open(auftrag, "w", encoding="utf-8") as fh:
        json.dump({"modell": MODELLE[modell][0], "epochen": epochen,
                   "bildgroesse": bildgroesse, "ziel": ziel,
                   "bilder": teilung["bilder"], "klassen": einstellungen["klassen"],
                   "train": teilung["train"], "val": teilung["val"]}, fh)

    protokoll = os.path.join(ziel, "protokoll.txt")
    with open(protokoll, "w", encoding="utf-8") as log:
        prozess = subprocess.Popen([sys.executable, SKRIPT, "trainieren", auftrag],
                                   cwd=HIER, stdout=log, stderr=subprocess.STDOUT)
        while prozess.poll() is None:
            if abbrechen():
                prozess.terminate()
                try:
                    prozess.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    prozess.kill()
                break
            zeilen = _ergebnisse(os.path.join(ziel, "ergebnisse.csv"))
            if zeilen:
                z = zeilen[-1]
                melden(f"Detektor trainiert · Epoche {z['epoche']}/{epochen} · "
                       f"mAP50 {z['map50']:.3f}", z["epoche"], epochen)
            else:
                melden("Detektor wird vorbereitet (Grundmodell laden)", 0, epochen)
            time.sleep(3)
    if prozess.returncode not in (0, None) and not abbrechen():
        with open(protokoll, encoding="utf-8", errors="replace") as fh:
            ende = [z for z in fh.read().strip().splitlines() if z.strip()]
        raise RuntimeError("Das Training ist abgebrochen: "
                           + (ende[-1] if ende else str(prozess.returncode)))
    return {"lauf": name, "train": len(teilung["train"]),
            "val": len(teilung["val"]), "hinweis": teilung["hinweis"]}


def _zahl(text) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _ergebnisse(pfad: str) -> list[dict]:
    try:
        with open(pfad, encoding="utf-8") as fh:
            roh = list(csv.DictReader(fh))
    except OSError:
        return []
    return [{"epoche": int(_zahl(z.get("epoch"))),
             "verlust": _zahl(z.get("train/loss")),
             "praezision": _zahl(z.get("metrics/precision(B)")),
             "trefferquote": _zahl(z.get("metrics/recall(B)")),
             "map50": _zahl(z.get("metrics/mAP50(B)")),
             "map50_95": _zahl(z.get("metrics/mAP50-95(B)"))} for z in roh]


def laeufe(projekt: str) -> list[dict]:
    """Alle Trainingslaeufe eines Projekts, der neueste zuerst."""
    raus = []
    for name in sorted(os.listdir(ordner(projekt)), reverse=True):
        pfad = os.path.join(ordner(projekt), name)
        if not LAUF.fullmatch(name) or not os.path.isdir(pfad):
            continue
        zeilen = _ergebnisse(os.path.join(pfad, "ergebnisse.csv"))
        try:
            with open(os.path.join(pfad, "einstellungen.json"), encoding="utf-8") as fh:
                einstellungen = json.load(fh)
        except (OSError, json.JSONDecodeError):
            einstellungen = {}
        gewichte = os.path.join(pfad, "gewichte")
        raus.append({
            "name": name, "zeilen": zeilen,
            "beste": max(zeilen, key=lambda z: z["map50_95"]) if zeilen else None,
            "einstellungen": einstellungen,
            "gewichte": gewichte if os.path.isfile(
                os.path.join(gewichte, "config.json")) else "",
            "bilder": sorted(b for b in os.listdir(pfad) if BILD.fullmatch(b)),
        })
    return raus


def bildpfad(projekt: str, lauf: str, datei: str) -> str | None:
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") or not LAUF.fullmatch(lauf or "") \
            or not BILD.fullmatch(datei or ""):
        return None
    pfad = os.path.join(ordner(projekt), lauf, datei)
    return pfad if os.path.isfile(pfad) else None


# --- Ausprobieren ---------------------------------------------------------
def erkennen(projekt: str, lauf: str, bild_bytes: bytes, schwelle: float = 0.25) -> list[dict]:
    """Ein trainiertes Modell auf ein Bild loslassen -- auf der CPU.

    Die CPU, weil das in ein paar Sekunden erledigt ist und so neben einem
    laufenden Bildauftrag geht, ohne ihm die Karte streitig zu machen.
    """
    if not LAUF.fullmatch(lauf or ""):
        raise RuntimeError("Unbekannter Lauf")
    gewichte = os.path.join(ordner(projekt), lauf, "gewichte")
    if not os.path.isfile(os.path.join(gewichte, "config.json")):
        raise RuntimeError("Dieser Lauf hat keine fertigen Gewichte")
    eingabe = os.path.join(ordner(projekt), "probe_eingabe.png")
    with open(eingabe, "wb") as fh:
        fh.write(bild_bytes)
    aus = subprocess.run([sys.executable, SKRIPT, "erkennen", gewichte, eingabe,
                          str(schwelle)], capture_output=True, text=True,
                         timeout=180, cwd=HIER)
    if aus.returncode != 0:
        raise RuntimeError("Erkennung fehlgeschlagen: "
                           + (aus.stderr.strip().splitlines() or ["?"])[-1])
    return json.loads(aus.stdout.strip().splitlines()[-1])
