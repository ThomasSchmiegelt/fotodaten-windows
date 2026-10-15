"""Sechs Seiten eines Gegenstands: vorne, hinten, links, rechts, oben, unten.

Gemeint ist, was man aus einem Teilekatalog kennt: ein Gegenstand, sechsmal
aufgenommen, jedes Mal gerade von einer Seite. Man beschreibt ihn einmal und
bekommt die sechs Ansichten in einem Zug.

Der Gegenstand **schwebt** dabei frei im Raum. Das ist keine Spielerei: steht
er auf einem Tisch, ist seine Unterseite verdeckt, und die Ansicht von unten
zeigt dann die Tischplatte statt des Bodens des Gegenstands. Also kein Tisch,
kein Sockel, keine Hand, kein Boden -- und jedes davon ausdruecklich genannt,
sonst malt das Modell eines dazu.

Alle sechs Bilder entstehen aus demselben Beschreibungstext, mit demselben
Seed, in einem einzigen Ladevorgang. Ohne Vorlagenbild: ein Referenzbild
haelt die Blickrichtung fest -- dieselbe Beobachtung wie beim Szenenaufbau,
wo eine stehende Figur stehen blieb, obwohl der Text sie liegend wollte. Die
Ansicht von unten waere damit wieder die von vorn. Derselbe Seed ist das
staerkste Mittel, das bleibt: dasselbe Ausgangsrauschen haelt Groesse, Farbe
und Anmutung ueber die sechs Bilder zusammen.

Die Bilder liegen **nicht** in `outputs/`. Dort wird oft aufgeraeumt, und ein
Katalog, der beim Aufraeumen verschwindet, ist keiner. Sie gehen nach

    katalog/<projekt>/<kennung>/vorne.png … unten.png
    katalog/<projekt>/katalog.json          die Liste der Eintraege

Ein Lauf ergibt genau einen Eintrag. Wer denselben Gegenstand noch einmal
rechnet, bekommt einen zweiten daneben -- der erste bleibt, man will die
beiden ja vergleichen.
"""

import json
import os
import re
import shutil
import time
import unicodedata

from PIL import PngImagePlugin

import bausteine
import projekte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WURZEL = os.path.join(ROOT, "katalog")

# Kennungen und Dateinamen werden zu Pfaden, deshalb eng gefasst. Im Ordner
# eines Eintrags liegen genau die sechs Seiten und nichts sonst.
KENNUNG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


# --- Die sechs Blickrichtungen -------------------------------------------
# Je Seite: Anzeigename, die Blickrichtung und -- das Entscheidende -- was im
# Bild zu sehen ist.
#
# Gemessen an sechs Formulierungen fuer dieselbe Ansicht, gleicher Seed,
# gleicher Gegenstand: "a true top view, the camera directly above it" ergab
# dasselbe Dreiviertelbild wie "flat lay", wie die orthografische Zeichnung,
# wie die zweimal gesagte Blickrichtung. Deutlich hoeher kam allein die
# Fassung, die nicht sagt, wo die Kamera steht, sondern **was das Bild
# zeigt**: "The picture shows only its top: ... the sides of the body are
# hidden beneath them". Dieselbe Bauart lieferte auch die bis dahin nicht
# erreichte Untersicht -- den Boden der Kanne, von unten gesehen.
#
# Darum hier je Seite beides: die Richtung kurz, und dann ein Satz darueber,
# was sichtbar ist und was gerade nicht.
SEITEN = {
    "vorne":  ("Vorne", "from straight in front",
               "only its front: the front of the object is turned fully "
               "towards the camera and fills the middle of the frame, its "
               "left and right sides are seen edge-on, and nothing of its "
               "back is visible"),
    "hinten": ("Hinten", "from straight behind",
               "only its back: the side that is normally turned away from a "
               "viewer faces the camera and fills the middle of the frame, "
               "and nothing of its front is visible"),
    "links":  ("Links", "from straight at its left",
               "only its left side: the whole left flank fills the middle of "
               "the frame, while its front and its back are seen edge-on and "
               "almost nothing of them is visible"),
    "rechts": ("Rechts", "from straight at its right",
               "only its right side: the whole right flank fills the middle "
               "of the frame, while its front and its back are seen edge-on "
               "and almost nothing of them is visible"),
    "oben":   ("Oben", "from directly above",
               "only its top: the upper surface of the object fills the "
               "middle of the frame, the sides of the body are hidden "
               "beneath it and almost nothing of them is visible"),
    "unten":  ("Unten", "from directly below",
               "only its underside: the side it would normally stand on "
               "faces the camera and fills the middle of the frame, seen "
               "from below, and almost nothing of the sides of the body is "
               "visible"),
}

# Das erste Bild: der Gegenstand einmal, schraeg von vorn oben. Es kommt vor
# den sechs Seiten, als Probe -- sechs Ansichten kosten zehn Minuten, und
# ob der Gegenstand ueberhaupt so aussieht wie gedacht, zeigt schon eines.
# Danach ist es die Vorlage fuer die Effekte: ein Cover, eine
# Explosionszeichnung setzen auf einem Bild auf, und ein Schraegbild zeigt
# mehr vom Gegenstand als jede einzelne der sechs Seiten.
ERSTES = "erstes"

DATEI = re.compile(r"(?:" + "|".join((*SEITEN, ERSTES)) + r")\.png")

# Was fuer alle sechs Bilder gilt. Das Schweben steht zweimal drin -- einmal
# als Lage, einmal als Aufzaehlung dessen, was nicht im Bild sein darf. Ein
# Diffusionsmodell stellt einen Gegenstand sonst hin, weil Gegenstaende in
# fast allen Bildern, die es kennt, auf etwas stehen. Dieser Teil hat auf
# Anhieb gesessen: in allen gemessenen Bildern schwebte der Gegenstand, ohne
# Tisch, ohne Boden, ohne Schlagschatten.
SCHWEBT = (
    "The object alone, floating freely in mid-air in the middle of the "
    "frame, nothing touching it and nothing underneath it: no table, no "
    "shelf, no floor, no ground, no stand, no pedestal, no hand, no string, "
    "no shadow cast on any surface. The whole object inside the frame with a "
    "little space around it, sharp from front to back. Only this one object, "
    "nothing beside it, no text, no labels, no arrows, no measurements.")

# Der Hintergrund steht getrennt, weil er als einziger Teil austauschbar ist:
# ein Satellit gehoert vor Sterne, ein Werkzeug vor nichts. Ohne eigene
# Angabe bleibt es beim neutralen Grau -- ein Katalog soll den Gegenstand
# zeigen und nicht die Kulisse.
GRUND = "A plain seamless light grey background, soft even light from all sides."


def _grund(eigener: str) -> str:
    """Der Hintergrundsatz: der eigene, oder der neutrale."""
    text = (eigener or "").strip().rstrip(". ")
    if not text:
        return GRUND
    return f"{text[0].upper()}{text[1:]} behind it, soft even light from all sides."


# Manche Stile bringen ihre eigene Kulisse mit: "Technisch" sagt "clean
# studio backdrop", "Studio" "seamless backdrop". Gegen einen eigenen
# Hintergrund gewinnt die Kulisse -- gemessen am Satelliten vor dem
# Sternenhimmel, der mit Stil "Technisch" vor hellem Grau schwebte. Steht
# ein eigener Hintergrund da, faellt dieser Teil des Stils weg.
KULISSE = re.compile(r",[^,]*\b(?:backdrop|background)\b[^,]*", re.I)


# --- Die Eingabemaske ----------------------------------------------------
# Ein Feld, nicht sieben: oben der Gegenstand, darunter je Seite eine Zeile
# mit ihrem Befehl.
#
#     ein Erdbeobachtungssatellit mit goldener Isolationsfolie
#     /hintergrund ein tiefschwarzer Sternenhimmel
#     /oben  die goldene Oberseite fuellt die Mitte als Kreis
#     /-oben Parabolantenne, Kameratubus, Duesen
#
# Dieselbe Schreibweise wie die /Namen in einer Geschichte und die
# Kurzbefehle im Prompt-Feld -- wer das eine kennt, kennt das andere. Was
# nicht dasteht, schreibt das Sprachmodell.
#
# `/-` ist der eigentliche Kunstgriff. Was nicht zu sehen sein soll, darf
# nicht im Prompt vorkommen -- auch nicht als "the antenna is hidden". Ein
# Diffusionsmodell malt, was dasteht; die Verneinung davor liest es kaum.
# Gemessen an der Aufsicht des Satelliten: im Text stand "antenna, camera
# tube and thrusters are completely hidden", und die Antenne war im Bild.
# Hinter `/-` genannt, faellt sie stattdessen aus dem Satz heraus.
#
# `/+oben` ist dasselbe wie `/oben`; `/-` ohne Seite gilt fuer alle sechs.
NAMEN = tuple(SEITEN) + ("hintergrund",)
BEFEHL = re.compile(
    r"(?m)^[ \t]*/(-(?:" + "|".join(NAMEN) + r")?|\+?(?:" + "|".join(NAMEN)
    + r"))(?![\w])[ \t:]*")


def lies_eingabe(text: str) -> dict:
    """Das Eingabefeld zerlegen.

    Zurueck kommt, was wo hingehoert: der Gegenstand, der Hintergrund, je
    Seite der Satz darueber was sie zeigt (`sichten`), und je Seite das, was
    aus ihrem Prompt herausfallen soll (`ohne`). `ohne_alle` gilt fuer alle
    sechs.

    Alles vor dem ersten Befehl beschreibt den Gegenstand. Steht ein Befehl
    zweimal da, gilt der letzte -- so wie man sich beim Schreiben
    korrigiert.
    """
    leer = {"allgemein": "", "hintergrund": "", "sichten": {}, "ohne": {},
            "ohne_alle": ""}
    roh = (text or "").strip()
    if not roh:
        return leer
    teile = BEFEHL.split(roh)
    erg = dict(leer, allgemein=teile[0].strip())
    for befehl, wert in zip(teile[1::2], teile[2::2]):
        wert = wert.strip().strip(",")
        if not wert:
            continue
        if befehl.startswith("-"):
            name = befehl[1:]
            if not name:
                erg["ohne_alle"] = wert
            elif name in SEITEN:
                erg["ohne"][name] = wert
            continue
        name = befehl.lstrip("+")
        if name == "hintergrund":
            erg["hintergrund"] = wert
        else:
            erg["sichten"][name] = wert
    return erg


def als_eingabe(gegenstand: str, sichten: dict | None = None,
                ohne: dict | None = None, hintergrund: str = "") -> str:
    """Einen Plan als Text fuers Eingabefeld schreiben -- zum Nachbessern.

    Der Rueckweg zu `lies_eingabe`: was hier herauskommt, liest jene
    Funktion wieder ein. Damit laesst sich der Vorschlag des Sprachmodells
    anschauen, aendern und erst dann rechnen -- statt ihn ungesehen ins Bild
    gehen zu lassen.
    """
    sichten, ohne = sichten or {}, ohne or {}
    zeilen = [(gegenstand or "").strip()]
    if (hintergrund or "").strip():
        zeilen += ["", "/hintergrund " + hintergrund.strip()]
    for seite in SEITEN:
        satz = (sichten.get(seite) or "").strip()
        weg = (ohne.get(seite) or "").strip()
        if not satz and not weg:
            continue
        zeilen.append("")
        if satz:
            zeilen.append(f"/{seite} {satz}")
        if weg:
            zeilen.append(f"/-{seite} {weg}")
    return "\n".join(zeilen).strip()


def seiten_prompt(text: str, seite: str, stil: str = "",
                  sicht: str = "", hintergrund: str = "") -> str:
    """Der Prompt fuer eine der sechs Seiten.

    Die Blickrichtung steht vorn, die Beschreibung des Gegenstands in der
    Mitte, und was zu sehen ist dahinter. Vorn, weil das Modell die
    Komposition am Anfang des Prompts aufhaengt -- dieselbe Reihenfolge wie
    in `build_prompt` und in `szenenbau.pose_prompt`.

    `sicht` ist der Satz, den das Sprachmodell ueber *diesen* Gegenstand in
    *dieser* Ansicht geschrieben hat -- welches Teil in der Mitte steht,
    welches verdeckt ist. Er schlaegt den allgemeinen Satz aus `SEITEN`:
    der weiss nur, dass oben oben ist, und nicht, dass unten die Antenne
    sitzt. Fehlt er, bleibt es beim allgemeinen.
    """
    eintrag = SEITEN.get(seite)
    beschreibung = (text or "").strip().rstrip(".")
    if not eintrag:
        return ""
    _, richtung, sichtbar = eintrag
    sichtbar = (sicht or "").strip().rstrip(".") or sichtbar
    if not beschreibung:
        return ""
    return _abschluss(f"one single object seen {richtung}. "
                      f"{bausteine._klein(beschreibung)}. "
                      f"The picture shows {sichtbar}. {SCHWEBT}",
                      stil, hintergrund)


def erster_prompt(text: str, stil: str = "", hintergrund: str = "") -> str:
    """Der Prompt fuers erste Bild: derselbe Gegenstand, schraeg gesehen.

    Gleich gebaut wie die sechs Seiten -- schwebend, derselbe Hintergrund,
    derselbe Stil --, nur die Blickrichtung ist eine, die viel zeigt.
    """
    beschreibung = (text or "").strip().rstrip(".")
    if not beschreibung:
        return ""
    return _abschluss(
        "one single object seen at a three-quarter angle from the front and "
        "slightly above. "
        f"{bausteine._klein(beschreibung)}. "
        "The picture shows its front, one of its sides and its top at the "
        f"same time. {SCHWEBT}", stil, hintergrund)


def _abschluss(kern: str, stil: str, hintergrund: str) -> str:
    """Stil und Hintergrund an einen Prompt haengen."""
    # Der Hintergrund steht hinter dem Stil, als letzter Satz: dazwischen
    # geschoben las ihn das Modell als Nebensache.
    mit = bausteine.mit_stil(kern, stil)
    if (hintergrund or "").strip():
        rumpf = kern.rstrip(".")
        mit = rumpf + KULISSE.sub("", mit[len(rumpf):])
    return f"{mit.rstrip('.')}. {_grund(hintergrund)}"


def alle_prompts(text: str, stil: str = "", sichten: dict | None = None,
                 hintergrund: str = "") -> list[tuple[str, str]]:
    """Die sechs Seiten als Paare (Schluessel, Prompt), in Katalogreihenfolge."""
    sichten = sichten or {}
    paare = [(s, seiten_prompt(text, s, stil, sichten.get(s) or "", hintergrund))
             for s in SEITEN]
    return [(s, p) for s, p in paare if p]


# --- Ablage ---------------------------------------------------------------
def ordner(projekt: str) -> str:
    """Das Katalogverzeichnis eines Projekts. Legt es bei Bedarf an."""
    if not projekte.SCHLUESSEL.fullmatch(projekt or ""):
        projekt = projekte.ALLGEMEIN
    pfad = os.path.join(WURZEL, projekt)
    os.makedirs(pfad, exist_ok=True)
    return pfad


def _datei(projekt: str) -> str:
    return os.path.join(ordner(projekt), "katalog.json")


def liste(projekt: str) -> list[dict]:
    """Die Eintraege eines Projekts, der neueste zuerst."""
    try:
        with open(_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(daten, list):
        return []
    eintraege = [e for e in daten if isinstance(e, dict) and e.get("id")]
    return sorted(eintraege, key=lambda e: str(e.get("angelegt") or ""),
                  reverse=True)


def _schreiben(projekt: str, daten: list[dict]) -> None:
    with open(_datei(projekt), "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=2)


def _kennung(name: str) -> str:
    """Aus einem Namen einen unbedenklichen Verzeichnisnamen machen.

    Mit Zeitstempel davor: zwei Laeufe zum selben Gegenstand sollen
    nebeneinander liegen und nicht einander ueberschreiben.
    """
    roh = (name or "").strip().lower()
    for auf, ab in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        roh = roh.replace(auf, ab)
    roh = "".join(z for z in unicodedata.normalize("NFKD", roh)
                  if not unicodedata.combining(z))
    roh = re.sub(r"[^a-z0-9]+", "-", roh).strip("-")[:40]
    return time.strftime("%Y%m%d-%H%M%S") + (f"_{roh}" if roh else "")


def anlegen(projekt: str, name: str, beschreibung: str, prompt: str,
            stil: str = "", seed: int = 0, sichten: dict | None = None,
            hintergrund: str = "", ohne: dict | None = None) -> dict:
    """Einen leeren Katalogeintrag anlegen. Die Bilder kommen einzeln nach.

    Der Eintrag steht schon in der Liste, bevor das erste Bild gerechnet ist.
    Bricht der Lauf in der Mitte ab, bleibt damit sichtbar, was entstanden
    ist -- und was fehlt.
    """
    eintrag = {"id": _kennung(name or beschreibung),
               "name": (name or "").strip() or (beschreibung or "").strip()[:60]
               or "ohne Namen",
               "beschreibung": (beschreibung or "").strip(),
               "prompt": (prompt or "").strip(),
               "stil": (stil or "").strip(),
               "hintergrund": (hintergrund or "").strip(),
               # Was aus den Prompts herausgestrichen wurde. Gehoert zum
               # Eintrag: ohne diese Liste sieht man dem Bild nicht an,
               # warum ein Teil fehlt.
               "ohne": dict(ohne or {}),
               "seed": int(seed or 0),
               # Was das Sprachmodell ueber jede einzelne Ansicht gesagt
               # hat. Gehoert zum Eintrag: ohne diese Saetze laesst sich
               # nicht nachvollziehen, warum die Unterseite so aussieht.
               "sichten": dict(sichten or {}),
               "angelegt": time.strftime("%Y-%m-%d %H:%M:%S"),
               "bilder": {}}
    os.makedirs(os.path.join(ordner(projekt), eintrag["id"]), exist_ok=True)
    _schreiben(projekt, [eintrag] + liste(projekt))
    return eintrag


def ablegen(projekt: str, kennung: str, seite: str, bild, prompt: str = "",
            seed: int = 0) -> str:
    """Ein Seitenbild ablegen und am Eintrag vermerken.

    Der Prompt geht als PNG-Textfeld mit ins Bild, genau wie bei den Bildern
    in `outputs/` -- ohne ihn weiss spaeter niemand mehr, wie die Ansicht
    entstanden ist.
    """
    if (seite not in SEITEN and seite != ERSTES) \
            or not KENNUNG.fullmatch(kennung or ""):
        return ""
    name = f"{seite}.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("qwen_prompt", str(prompt or ""))
    info.add_text("qwen_seed", str(seed or 0))
    info.add_text("qwen_seite", seite)
    ort = os.path.join(ordner(projekt), kennung)
    os.makedirs(ort, exist_ok=True)
    bild.save(os.path.join(ort, name), pnginfo=info)

    daten = liste(projekt)
    for e in daten:
        if e.get("id") == kennung:
            bilder = e.get("bilder") if isinstance(e.get("bilder"), dict) else {}
            bilder[seite] = name
            e["bilder"] = bilder
            _schreiben(projekt, daten)
            break
    return name


def eintrag(projekt: str, kennung: str) -> dict | None:
    """Ein Eintrag nach seiner Kennung -- oder None."""
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") \
            or not KENNUNG.fullmatch(kennung or ""):
        return None
    return next((e for e in liste(projekt) if e.get("id") == kennung), None)


def nachtragen(projekt: str, kennung: str, **felder) -> dict | None:
    """Felder eines Eintrags ersetzen, etwa die Ansichten nach dem ersten Bild.

    Die Bilder bleiben, wie sie sind -- die traegt `ablegen` ein.
    """
    daten = liste(projekt)
    for e in daten:
        if e.get("id") == kennung:
            e.update({k: v for k, v in felder.items() if k != "bilder"})
            _schreiben(projekt, daten)
            return e
    return None


def bildpfad(projekt: str, kennung: str, name: str) -> str | None:
    """Der Pfad eines Katalogbildes -- oder None, wenn etwas nicht stimmt.

    Der Server gibt die Teile ungeprueft aus der Adresse herein, deshalb
    jeder Teil gegen ein eigenes Muster.
    """
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") \
            or not KENNUNG.fullmatch(kennung or "") \
            or not DATEI.fullmatch(name or ""):
        return None
    pfad = os.path.join(WURZEL, projekt, kennung, name)
    return pfad if os.path.isfile(pfad) else None


def loeschen(projekt: str, kennung: str) -> bool:
    """Einen Eintrag samt seiner sechs Bilder loeschen -- endgueltig.

    Das Projekt wird hier eigens geprueft und nicht wie in `ordner()` auf
    Allgemein zurueckgefuehrt: ein krummer Schluessel soll nichts loeschen,
    schon gar nichts in einem anderen Projekt.
    """
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") \
            or not KENNUNG.fullmatch(kennung or ""):
        return False
    daten = liste(projekt)
    rest = [e for e in daten if e.get("id") != kennung]
    if len(rest) == len(daten):
        return False
    pfad = os.path.join(ordner(projekt), kennung)
    if os.path.isdir(pfad):
        shutil.rmtree(pfad)
    _schreiben(projekt, rest)
    return True


def katalog() -> list[dict]:
    """Alle Eintraege aller Projekte, jeder mit seiner Herkunft.

    Wie bei den Bausteinen: ein Gegenstand, den man einmal von sechs Seiten
    hat, soll im naechsten Vorhaben wiederzufinden sein.
    """
    raus = []
    for projekt in projekte.liste():
        for e in liste(projekt["key"]):
            raus.append({**e, "projekt": projekt["key"],
                         "projektname": projekt["label"]})
    return raus
