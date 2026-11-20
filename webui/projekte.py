"""Projekte: getrennte Ablagen fuer getrennte Vorhaben.

Ein Projekt ist ein Verzeichnis, das alles zu einem Vorhaben zusammenhaelt:

    projekte/<schluessel>/
        bilder/          erzeugte Bilder und Videos
        vorlagen/        hochgeladene Referenzbilder (spaeter)
        bausteine.json   Personen, Orte, Gegenstaende (spaeter)
        projekt.json     Name, angelegt, Notiz

Eine Ausnahme: das Projekt **Allgemein** zeigt weiter auf das alte `outputs/`.
Die Bilder, die dort schon liegen, sollen nicht umziehen muessen -- ein
Verschieben von tausenden Dateien waere ein unnoetiges Risiko fuer nichts.

Welches Projekt aktiv ist, steht in `projekte/aktiv.txt` und ueberlebt damit
einen Neustart.
"""

import json
import os
import re
import shutil
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WURZEL = os.path.join(ROOT, "projekte")
ALT = os.path.join(ROOT, "outputs")
ALLGEMEIN = "allgemein"
MERKER = os.path.join(WURZEL, "aktiv.txt")

# Schluessel werden zu Verzeichnisnamen, deshalb eng gefasst.
SCHLUESSEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


def _schluessel(name: str) -> str:
    """Aus einem Anzeigenamen einen unbedenklichen Verzeichnisnamen machen."""
    # Umlaute zuerst, dann zerlegen: sonst hat NFKD das "ü" schon in u plus
    # Trema aufgeteilt, die Ersetzung greift ins Leere und aus Mueller wird
    # Muller.
    roh = (name or "").strip().lower()
    for auf, ab in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        roh = roh.replace(auf, ab)
    roh = "".join(z for z in unicodedata.normalize("NFKD", roh)
                  if not unicodedata.combining(z))
    roh = re.sub(r"[^a-z0-9]+", "-", roh).strip("-")[:40]
    return roh or f"projekt-{int(time.time())}"


def _pruefen(schluessel: str) -> str:
    """Schluessel werden zu Pfaden: alles ausser Allgemein und dem
    Schluesselmuster (etwa "../x") wird abgelehnt, sonst Pfad-Ausbruch."""
    if schluessel != ALLGEMEIN and not SCHLUESSEL.fullmatch(schluessel or ""):
        raise ValueError(f"ungueltiger Projektschluessel: {schluessel!r}")
    return schluessel


def ordner(schluessel: str) -> str:
    """Das Datenverzeichnis eines Projekts -- fuer alles ausser den Bildern.

    Auch Allgemein bekommt hier eines, obwohl seine Bilder in `outputs/`
    liegen: die Bausteine brauchen einen Platz, und `outputs/` soll nur
    Bilder enthalten.
    """
    pfad = os.path.join(WURZEL, _pruefen(schluessel))
    os.makedirs(pfad, exist_ok=True)
    return pfad


def bilder(schluessel: str) -> str:
    """Das Bildverzeichnis eines Projekts. Legt es bei Bedarf an."""
    _pruefen(schluessel)
    pfad = ALT if schluessel == ALLGEMEIN else os.path.join(WURZEL, schluessel, "bilder")
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _lies_namen(schluessel: str) -> str:
    if schluessel == ALLGEMEIN:
        return "Allgemein"
    try:
        with open(os.path.join(WURZEL, schluessel, "projekt.json"), encoding="utf-8") as fh:
            return json.load(fh).get("name") or schluessel
    except (OSError, json.JSONDecodeError):
        return schluessel


def liste() -> list[dict]:
    """Alle Projekte, Allgemein zuerst, dann die uebrigen nach Namen."""
    eintraege = [{"key": ALLGEMEIN, "label": "Allgemein",
                  "bilder": _zaehle(bilder(ALLGEMEIN))}]
    if os.path.isdir(WURZEL):
        for name in sorted(os.listdir(WURZEL)):
            pfad = os.path.join(WURZEL, name)
            if (name == ALLGEMEIN or not os.path.isdir(pfad)
                    or not SCHLUESSEL.fullmatch(name)):
                continue
            eintraege.append({"key": name, "label": _lies_namen(name),
                              "bilder": _zaehle(os.path.join(pfad, "bilder"))})
    return eintraege


def _zaehle(ordner: str) -> int:
    try:
        return sum(1 for f in os.listdir(ordner) if f.endswith(".png"))
    except OSError:
        return 0


def aktiv() -> str:
    """Das aktive Projekt. Ohne Merker oder bei einem verschwundenen
    Verzeichnis faellt es auf Allgemein zurueck."""
    try:
        with open(MERKER, encoding="utf-8") as fh:
            gemerkt = fh.read().strip()
    except OSError:
        return ALLGEMEIN
    if gemerkt == ALLGEMEIN or (SCHLUESSEL.fullmatch(gemerkt)
                                and os.path.isdir(os.path.join(WURZEL, gemerkt))):
        return gemerkt
    return ALLGEMEIN


def waehlen(schluessel: str) -> bool:
    if schluessel != ALLGEMEIN and not os.path.isdir(os.path.join(WURZEL, schluessel)):
        return False
    os.makedirs(WURZEL, exist_ok=True)
    with open(MERKER, "w", encoding="utf-8") as fh:
        fh.write(schluessel)
    return True


def anlegen(name: str) -> dict:
    """Legt ein Projekt an und macht es aktiv. Ein schon vergebener
    Schluessel bekommt eine Zahl angehaengt."""
    basis = _schluessel(name)
    schluessel, n = basis, 2
    while schluessel == ALLGEMEIN or os.path.isdir(os.path.join(WURZEL, schluessel)):
        schluessel, n = f"{basis}-{n}", n + 1
    os.makedirs(os.path.join(WURZEL, schluessel, "bilder"), exist_ok=True)
    os.makedirs(os.path.join(WURZEL, schluessel, "vorlagen"), exist_ok=True)
    with open(os.path.join(WURZEL, schluessel, "projekt.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"name": (name or "").strip() or schluessel,
                   "angelegt": time.strftime("%Y-%m-%d %H:%M"), "notiz": ""},
                  fh, ensure_ascii=False, indent=2)
    waehlen(schluessel)
    return {"key": schluessel, "label": _lies_namen(schluessel), "bilder": 0}


def umbenennen(schluessel: str, name: str) -> bool:
    """Nur der Anzeigename aendert sich. Der Schluessel bleibt, sonst muesste
    das Verzeichnis mitwandern und alle Pfade waeren ungueltig."""
    if schluessel == ALLGEMEIN or not SCHLUESSEL.fullmatch(schluessel or ""):
        return False
    datei = os.path.join(WURZEL, schluessel, "projekt.json")
    if not os.path.isfile(datei):
        return False
    with open(datei, encoding="utf-8") as fh:
        daten = json.load(fh)
    daten["name"] = (name or "").strip() or schluessel
    with open(datei, "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=2)
    return True


def loeschen(schluessel: str) -> bool:
    """Loescht das ganze Projektverzeichnis samt Bildern -- endgueltig.

    Allgemein laesst sich nicht loeschen: dort liegen die Bilder aus der Zeit
    vor den Projekten, und der Ordner ist nicht Teil von `projekte/`.
    """
    if schluessel == ALLGEMEIN or not SCHLUESSEL.fullmatch(schluessel or ""):
        return False
    pfad = os.path.join(WURZEL, schluessel)
    if not os.path.isdir(pfad):
        return False
    shutil.rmtree(pfad)
    if aktiv() == schluessel:
        waehlen(ALLGEMEIN)
    return True
