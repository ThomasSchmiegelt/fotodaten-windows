"""Geschichten in Baenden: mehrere Erzaehlungen je Projekt, fortsetzbar.

Eine **Geschichte** hat einen Namen und die globalen Vorgaben, die fuer alles
gelten: Stil, Welt, Wirklichkeitsgrad, Sprachmodell. Sie besteht aus
**Baenden**. Jeder Band hat seine eigene Idee, sein Inhaltsverzeichnis und
seine Prompts -- aber er erbt die Vorgaben und weiss, was vorher geschah.

    projekte/<projekt>/geschichten/<schluessel>.json

Warum nicht ein Band je Datei: die Vorgaben gehoeren der Geschichte, nicht
dem Band. Sie zweimal zu halten hiesse, sie frueher oder spaeter zweimal zu
aendern.
"""

import copy
import json
import os
import re
import tempfile
import threading
import time

import projekte

# Was zur Geschichte gehoert und fuer jeden Band gilt.
GLOBAL = ("stil", "welt", "fiktion", "alter", "modell",
          # Wer die Prosa schreibt: Art der Stimme, aus wessen Sicht, und
          # eine frei geschriebene Beschreibung. Fehlen sie, erzaehlt
          # niemand Bestimmtes -- so wie in allen Geschichten bisher.
          "erzaehler", "erzaehler_wer", "erzaehler_text")
# Was je Band eigen ist.
BAND = ("idee", "kurz", "titel", "zeilen", "prompts",
        # Anfang und Ende stehen fest, bevor die Mitte entsteht; die
        # Abschnitte sind die Stuecke der Vorlage samt Ueberschrift.
        "anfang", "ende", "kapitel")


# Lesen-aendern-schreiben kommt aus mehreren Threads; ohne Sperre gewinnt der
# letzte Schreiber und die Aenderung des anderen ist weg. Reentrant, weil
# fassung_holen() fassung_sichern() ruft.
_SPERRE = threading.RLock()


def _gesperrt(fn):
    def innen(*a, **k):
        with _SPERRE:
            return fn(*a, **k)
    innen.__name__, innen.__doc__ = fn.__name__, fn.__doc__
    return innen


def _ordner(projekt: str) -> str:
    pfad = os.path.join(projekte.ordner(projekt), "geschichten")
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _datei(projekt: str, schluessel: str) -> str:
    return os.path.join(_ordner(projekt), f"{schluessel}.json")


def liste(projekt: str) -> list[dict]:
    """Alle Geschichten eines Projekts, zuletzt geaenderte zuerst."""
    raus = []
    for name in os.listdir(_ordner(projekt)):
        if not name.endswith(".json"):
            continue
        g = lesen(projekt, name[:-5])
        if g:
            raus.append({"schluessel": g["schluessel"], "name": g["name"],
                         "baende": len(g.get("baende") or []),
                         "geaendert": g.get("geaendert", "")})
    return sorted(raus, key=lambda x: x["geaendert"], reverse=True)


def lesen(projekt: str, schluessel: str) -> dict:
    if not projekte.SCHLUESSEL.fullmatch(schluessel or ""):
        return {}
    try:
        with open(_datei(projekt, schluessel), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}


def _schreiben(projekt: str, g: dict) -> dict:
    g["geaendert"] = time.strftime("%Y-%m-%d %H:%M")
    ziel = _datei(projekt, g["schluessel"])
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ziel), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(g, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ziel)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return g


@_gesperrt
def anlegen(projekt: str, name: str, globale: dict | None = None) -> dict:
    """Eine neue Geschichte mit erstem, noch leerem Band."""
    basis = projekte._schluessel(name)
    schluessel, n = basis, 2
    while os.path.isfile(_datei(projekt, schluessel)):
        schluessel, n = f"{basis}-{n}", n + 1
    g = {"schluessel": schluessel, "name": (name or "").strip() or schluessel,
         **{k: (globale or {}).get(k) for k in GLOBAL},
         "baende": [{"nr": 1, **{k: None for k in BAND}}]}
    return _schreiben(projekt, g)


@_gesperrt
def speichern(projekt: str, schluessel: str, daten: dict) -> dict:
    """Vorgaben und einen Band ablegen.

    `daten["band"]` ist die Nummer; fehlt sie, gilt der letzte. Nur bekannte
    Felder wandern in die Datei -- was die Seite sonst mitschickt, nicht.
    """
    g = lesen(projekt, schluessel)
    if not g:
        return {}
    for k in GLOBAL:
        if k in daten:
            g[k] = daten[k]
    if daten.get("name"):
        g["name"] = str(daten["name"]).strip()[:60]

    baende = g.setdefault("baende", [{"nr": 1}])
    nr = int(daten.get("band") or baende[-1].get("nr", 1))
    band = next((b for b in baende if b.get("nr") == nr), None)
    if band is None:
        band = {"nr": nr}
        baende.append(band)
    for k in BAND:
        if k in daten:
            band[k] = daten[k]
    return _schreiben(projekt, g)


# --- Fassungen ------------------------------------------------------------
# Eine Fassung ist der Stand eines Bandes zu einem Zeitpunkt: die Zeilen mit
# ihrer Prosa, die geschriebenen Prompts und die Erzaehlstimme. Sie kostet
# nichts als Text und ist der Grund, warum man einen neuen Autor gefahrlos
# ausprobieren kann -- die alte Fassung liegt daneben.
FASSUNG = ("zeilen", "prompts", "kurz", "titel", "anfang", "ende", "kapitel")
STIMME = ("erzaehler", "erzaehler_wer", "erzaehler_text")


def _band(g: dict, nr: int) -> dict | None:
    return next((b for b in g.get("baende") or [] if b.get("nr") == nr), None)


@_gesperrt
def fassung_sichern(projekt: str, schluessel: str, nr: int,
                    name: str = "") -> dict:
    """Den jetzigen Stand eines Bandes als Fassung ablegen."""
    g = lesen(projekt, schluessel)
    band = _band(g, nr) if g else None
    if not band:
        return {}
    wann = time.strftime("%Y-%m-%d %H:%M")
    eintrag = {"name": (name or "").strip()[:60] or f"Fassung vom {wann}",
               "wann": wann,
               **{k: copy.deepcopy(band.get(k)) for k in FASSUNG},
               **{k: g.get(k) for k in STIMME}}
    band.setdefault("fassungen", []).append(eintrag)
    _schreiben(projekt, g)
    return eintrag


def fassungen(projekt: str, schluessel: str, nr: int) -> list[dict]:
    """Nur Name und Zeitpunkt -- der Inhalt waere zu viel fuer eine Liste."""
    g = lesen(projekt, schluessel)
    band = _band(g, nr) if g else None
    return [{"nr": i, "name": f.get("name"), "wann": f.get("wann"),
             "zeilen": len(f.get("zeilen") or []),
             "erzaehler": f.get("erzaehler") or ""}
            for i, f in enumerate(band.get("fassungen") or [])] if band else []


@_gesperrt
def fassung_holen(projekt: str, schluessel: str, nr: int, index: int) -> dict:
    """Eine Fassung zurueckholen. Der jetzige Stand wird vorher gesichert.

    Ohne diese Sicherung waere das Zurueckholen selbst ein Verlust -- man
    haette den neuen Stand weggeworfen, um den alten zu bekommen.
    """
    g = lesen(projekt, schluessel)
    band = _band(g, nr) if g else None
    if not band:
        return {}
    liste = band.get("fassungen") or []
    if not 0 <= index < len(liste):
        return {}
    fassung_sichern(projekt, schluessel, nr, "vor dem Zurückholen")
    g = lesen(projekt, schluessel)
    band = _band(g, nr)
    alt = (band.get("fassungen") or [])[index]
    for k in FASSUNG:
        band[k] = copy.deepcopy(alt.get(k))
    for k in STIMME:
        if alt.get(k) is not None:
            g[k] = alt[k]
    _schreiben(projekt, g)
    return g


@_gesperrt
def fassung_loeschen(projekt: str, schluessel: str, nr: int,
                     index: int) -> bool:
    g = lesen(projekt, schluessel)
    band = _band(g, nr) if g else None
    liste = (band or {}).get("fassungen") or []
    if not 0 <= index < len(liste):
        return False
    del liste[index]
    _schreiben(projekt, g)
    return True


@_gesperrt
def band_anlegen(projekt: str, schluessel: str) -> dict:
    """Den naechsten Band anhaengen. Die Vorgaben gelten weiter."""
    g = lesen(projekt, schluessel)
    if not g:
        return {}
    baende = g.setdefault("baende", [])
    nr = (max((b.get("nr", 0) for b in baende), default=0)) + 1
    baende.append({"nr": nr, **{k: None for k in BAND}})
    return _schreiben(projekt, g)


def loeschen(projekt: str, schluessel: str) -> bool:
    if not projekte.SCHLUESSEL.fullmatch(schluessel or ""):
        return False
    try:
        os.remove(_datei(projekt, schluessel))
        return True
    except OSError:
        return False


def verweis_umbenennen(projekt: str, alt: str, neu: str) -> int:
    """`/Alt` in allen Geschichten des Projekts durch `/Neu` ersetzen.

    Gehoert zum Zusammenfuehren zweier Bausteine: sonst zeigte jede Szene,
    die den alten Namen nennt, ins Leere -- und stuende danach als "noch
    anzulegen" im Katalog.
    """
    if not alt or not neu or alt.lower() == neu.lower():
        return 0
    return _in_allen_zeilen(
        projekt, re.compile(r"/(-?)" + re.escape(alt) + r"(?!\w)", re.I),
        # Funktion statt Vorlagentext: ein Backslash im Namen waere sonst
        # eine Escape-Folge.
        lambda m: "/" + m.group(1) + neu)


# Ein Vorwort und ein Artikel davor fallen beim Entfernen mit: aus "rennt
# durch die /Halle" bliebe sonst "rennt durch die". Dieselbe Liste wie in
# der Seite -- dort wird ein Baustein aus einer einzelnen Szene genommen,
# hier aus allen.
VORWORT = ("durch|in|an|auf|zu|zum|zur|bei|mit|über|unter|vor|hinter|neben"
           "|aus|nach|von|gegen|um|ohne|entlang")
ARTIKEL = ("der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines"
           "|sein|seine|ihr|ihre|ihren|seinen")


def verweis_entfernen(projekt: str, name: str) -> int:
    """`/Name` aus allen Geschichten des Projekts streichen.

    Gehoert zum Loeschen eines Bausteins: sonst bliebe sein Name als blosses
    Wort in der Zeile stehen, liefe ins Leere und stuende beim naechsten
    Durchsehen als "noch anzulegen" da.
    """
    if not name:
        return 0
    muster = re.compile(
        rf"(?:\b(?:{VORWORT})\s+)?(?:\b(?:{ARTIKEL})\s+)?/-?{re.escape(name)}(?!\w)",
        re.I)
    return _in_allen_zeilen(projekt, muster, lambda m: "", entfernen=True)


@_gesperrt
def _in_allen_zeilen(projekt: str, muster, ersatz, entfernen: bool = False) -> int:
    """Ein Muster in allen Szenenzeilen aller Geschichten ersetzen."""
    geaendert = 0
    for eintrag in liste(projekt):
        g = lesen(projekt, eintrag["schluessel"])
        beruehrt = False
        for band in g.get("baende") or []:
            for z in band.get("zeilen") or []:
                text = str(z.get("text") or "")
                neu_text = muster.sub(ersatz, text)
                if entfernen:
                    neu_text = re.sub(r"\s+([,.;!?])", r"\1", neu_text)
                    neu_text = re.sub(r"\s{2,}", " ", neu_text).strip()
                if neu_text != text:
                    z["text"] = neu_text
                    geaendert += 1
                    beruehrt = True
        if beruehrt:
            _schreiben(projekt, g)
    return geaendert


def vorgeschichte(g: dict, bis_nr: int) -> str:
    """Was in den Baenden davor geschah, als Text fuers Sprachmodell.

    Ohne das faengt Band 2 bei null an und erfindet die Figuren neu. Genommen
    wird die Kurzfassung je Band; die Gliederung waere zu lang und die
    Prompts sind englisch.
    """
    stuecke = []
    for b in g.get("baende") or []:
        if b.get("nr", 0) >= bis_nr:
            continue
        kurz = (b.get("kurz") or "").strip()
        if kurz:
            stuecke.append(f"Band {b['nr']}: {kurz}")
    return "\n\n".join(stuecke)
