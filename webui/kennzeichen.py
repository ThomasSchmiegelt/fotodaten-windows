"""Deutsche Kennzeichen erzeugen und in ein Foto einsetzen.

Das Bildmodell verwuerfelt jede Schrift -- aus "M DI 380E" wird "Wp vaitle
pein". Ein Detektor fuer die Kupplung lernte dann, dass ueber ihr immer
Buchstabensalat steht. Deshalb kommt in jedes Bild ein glaubhaftes, aber
zufaelliges Kennzeichen: nach dem Rechnen eingesetzt, wie die Kupplung.
Nebenbei verschwindet das echte Kennzeichen aus dem Datensatz.

Die Schrift wird gesetzt, nicht aus einem Foto geschnitten:

    vorlage   ein echtes Schild ohne Schrift -- EU-Feld, weisse Flaeche mit
              ihrem Licht, dazu Plakette und Siegel als eigene Ausschnitte.
              Einmal aus einem Foto gebaut (`vorlage_bauen`), liegt in
              webui/kennzeichen/.
    zufall    Ortskennung, Erkennungsbuchstaben, Zahl, wahlweise E oder H --
              nach den Regeln der FZV (hoechstens acht Zeichen, keine
              fuehrende Null, keine verbotenen Kombinationen).
    zeichnen  die Zeichen in Bahnschrift (Windows, nach DIN 1451) schmal und
              leicht gepraegt auf die Vorlage. Die echte FE-Schrift ist
              aehnlich, aber nicht frei.
    einsetzen in vier Ecken im Foto, perspektivisch verzogen. Licht und
              Farbstich kommen vom alten Schild an derselben Stelle: dessen
              Schrift wird herausgerechnet, uebrig bleibt, wie hell die
              weisse Flaeche dort ist -- auch ein Schatten quer darueber.
"""

import json
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kennzeichen")
SCHRIFT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "bahnschrift.ttf")

# Groesse der Vorlage in Pixeln. Das Seitenverhaeltnis ist das gemessene der
# sichtbaren Flaeche im Halter (5,25), nicht das amtliche 520 x 110 mm: der
# Halter deckt oben und unten einen Streifen ab.
BREITE, HOEHE = 1050, 200

# Ortskennungen in Bayern -- das Siegel der Vorlage ist das bayerische.
ORTE = ("A AB AIC AN AÖ AS BA BGL BT CHA CO DAH DEG DGF DON ED EBE EI ER ERH "
        "FFB FRG FS FÜ GAP GZ HAS HO IN KC KE KEH KG KT KU LA LAU LI LIF LL M "
        "MB MIL MM MN MSP MÜ N NEA NES NM NU OA OAL PA PAF PAN R REG RH RO SAD "
        "SR STA SW TIR TÖL TS WEN WM WÜ WUN").split()
BUCHSTABEN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VERBOTEN = {"HJ", "KZ", "NS", "SA", "SS"}
# HU-Plakette: die Farbe wechselt jaehrlich, alle sechs Jahre dieselbe.
# Farbton in Grad, Saettigung, Helligkeit -- auf die blaue Vorlage gelegt.
PLAKETTEN = {"gruen": (125, 0.8, 0.85), "orange": (28, 0.95, 1.0), "blau": None,
             "gelb": (52, 0.95, 1.1), "braun": (25, 0.7, 0.6), "rosa": (330, 0.55, 1.1)}


# --- Zufall ---------------------------------------------------------------

def zufall(rng: random.Random) -> dict:
    """Ein gueltiges Kennzeichen in seinen Teilen."""
    while True:
        ort = rng.choice(ORTE)
        buchst = "".join(rng.choice(BUCHSTABEN) for _ in range(rng.choice((1, 2, 2))))
        if buchst in VERBOTEN or (ort + buchst)[-2:] in VERBOTEN:
            continue
        zusatz = rng.choices(("", "E", "H"), (0.83, 0.12, 0.05))[0]
        frei = 8 - len(ort) - len(buchst) - len(zusatz)
        if frei < 1:
            continue
        # Echte Schilder tragen meist drei oder vier Ziffern.
        stellen = rng.choices(range(1, min(4, frei) + 1), (1, 3, 6, 8)[:min(4, frei)])[0]
        zahl = str(rng.randint(10 ** (stellen - 1), 10 ** stellen - 1))
        return {"ort": ort, "buchstaben": buchst, "zahl": zahl, "zusatz": zusatz,
                "plakette": rng.choice(list(PLAKETTEN))}


def text(teile: dict) -> str:
    return f"{teile['ort']}-{teile['buchstaben']} {teile['zahl']}{teile['zusatz']}"


# --- Vorlage --------------------------------------------------------------

def _hom(ausgabe: list, eingabe: list) -> tuple:
    """PIL-PERSPECTIVE-Koeffizienten: Ausgabepunkt -> Eingabepunkt."""
    a, r = [], []
    for (x, y), (u, v) in zip(ausgabe, eingabe):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); r.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); r.append(v)
    return tuple(np.linalg.solve(np.array(a, float), np.array(r, float)))


def _rechteck(b=BREITE, h=HOEHE) -> list:
    return [(0, 0), (b, 0), (b, h), (0, h)]


def ordnen(ecken: list) -> list:
    """Vier Punkte in der Reihenfolge oben links, oben rechts, unten rechts,
    unten links -- egal, in welcher sie geklickt wurden."""
    p = [tuple(map(float, e)) for e in ecken]
    oben = sorted(sorted(p, key=lambda e: e[1])[:2])
    unten = sorted(sorted(p, key=lambda e: e[1])[2:])
    return [oben[0], oben[1], unten[1], unten[0]]


def gerade(bild: Image.Image, ecken: list, b=BREITE, h=HOEHE) -> Image.Image:
    """Das Schild aus dem Foto, gerade gezogen auf b x h."""
    return bild.convert("RGB").transform((b, h), Image.PERSPECTIVE,
                                         _hom(_rechteck(b, h), ordnen(ecken)), Image.BICUBIC)


def _hintergrund(schild: Image.Image) -> Image.Image:
    """Die weisse Flaeche ohne Schrift: dunkle Striche weg, Licht bleibt.

    Ein Strich ist rund 4 % der Breite dick; ein Maximumfilter etwas
    breiter loescht ihn, der Weichzeichner glaettet die Kanten.
    """
    klein = schild.resize((schild.size[0] // 4, schild.size[1] // 4), Image.BILINEAR)
    klein = klein.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(3))
    return klein.resize(schild.size, Image.BICUBIC)


def vorlage_bauen(foto: Image.Image, ecken: list, ordner: str = ORDNER,
                  band: float = 0.0913, plakette: tuple | None = None,
                  siegel: tuple | None = None) -> None:
    """Aus einem Foto mit gut lesbarem Kennzeichen die Vorlage bauen.

    `band` ist die Breite des EU-Felds als Anteil der Schildbreite,
    `plakette` und `siegel` die Kreise (Mitte x, Mitte y, Radius) in Pixeln
    der geraden Vorlage.
    """
    schild = gerade(foto, ecken)
    a = np.asarray(schild, np.float32)
    grund = np.asarray(_hintergrund(schild), np.float32)
    leer = a.copy()
    x0, rand = int(band * BREITE) + 3, 7
    leer[rand:HOEHE - rand, x0:BREITE - rand] = grund[rand:HOEHE - rand, x0:BREITE - rand]
    # Etwas Korn, sonst wirkt die Flaeche wie gemalt.
    rng = np.random.default_rng(1)
    leer[rand:HOEHE - rand, x0:BREITE - rand] += rng.normal(0, 1.6, leer[rand:HOEHE - rand, x0:BREITE - rand].shape)
    os.makedirs(ordner, exist_ok=True)
    Image.fromarray(np.clip(leer, 0, 255).astype(np.uint8)).save(os.path.join(ordner, "vorlage.png"))
    # Die Schriftfarbe: die dunkelsten Pixel der weissen Flaeche.
    flaeche = a[rand:HOEHE - rand, x0:BREITE - rand].reshape(-1, 3)
    hell = flaeche.sum(1)
    farbe = flaeche[hell <= np.percentile(hell, 4)].mean(0)
    info = {"band": band, "farbe": [round(float(v)) for v in farbe]}
    for name, kreis in (("plakette", plakette), ("siegel", siegel)):
        if not kreis:
            continue
        mx, my, r = kreis
        stueck = schild.crop((round(mx - r), round(my - r), round(mx + r), round(my + r))).convert("RGBA")
        maske = Image.new("L", (stueck.size[0] * 4, stueck.size[1] * 4), 0)
        ImageDraw.Draw(maske).ellipse((2, 2, maske.size[0] - 3, maske.size[1] - 3), fill=255)
        stueck.putalpha(maske.resize(stueck.size, Image.LANCZOS))
        stueck.save(os.path.join(ordner, f"{name}.png"))
        info[name] = [mx / BREITE, my / HOEHE, r / HOEHE]
    with open(os.path.join(ordner, "info.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)


_vorrat = {}


def _lade() -> dict | None:
    if "info" not in _vorrat:
        try:
            with open(os.path.join(ORDNER, "info.json"), encoding="utf-8") as fh:
                _vorrat["info"] = json.load(fh)
            _vorrat["vorlage"] = Image.open(os.path.join(ORDNER, "vorlage.png")).convert("RGB")
            for name in ("plakette", "siegel"):
                pfad = os.path.join(ORDNER, f"{name}.png")
                _vorrat[name] = Image.open(pfad).convert("RGBA") if os.path.exists(pfad) else None
            _vorrat["licht"] = np.asarray(_hintergrund(_vorrat["vorlage"]).convert("L"), np.float32)
        except OSError:
            return None
    return _vorrat


def verfuegbar() -> bool:
    return _lade() is not None and os.path.exists(SCHRIFT)


# --- Zeichnen -------------------------------------------------------------

def _schrift(groesse: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(SCHRIFT, groesse)
    f.set_variation_by_axes([470, 75])          # Staerke, Breite (Condensed)
    return f


def _umfaerben(plakette: Image.Image, farbe: str) -> Image.Image:
    werte = PLAKETTEN.get(farbe)
    if not werte:
        return plakette
    ton, satt, hell = werte
    rgb, alpha = plakette.convert("RGB"), plakette.getchannel("A")
    hsv = np.asarray(rgb.convert("HSV")).astype(np.float32)
    bunt = hsv[..., 1] > 80
    hsv[..., 0] = np.where(bunt, ton * 255 / 360, hsv[..., 0])
    hsv[..., 1] = np.where(bunt, hsv[..., 1] * satt, hsv[..., 1])
    hsv[..., 2] = np.where(bunt, np.clip(hsv[..., 2] * hell, 0, 255), hsv[..., 2])
    neu = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGBA")
    neu.putalpha(alpha)
    return neu


def zeichnen(teile: dict) -> Image.Image:
    """Das Schild als Bild in Vorlagengroesse."""
    v = _lade()
    if v is None:
        raise RuntimeError("Keine Kennzeichen-Vorlage in webui/kennzeichen/")
    info = v["info"]
    schild = v["vorlage"].copy()
    hoch = round(0.75 * HOEHE)                  # Hoehe der Grossbuchstaben
    f = _schrift(100)
    g = f.getbbox("H")
    f = _schrift(round(100 * hoch / (g[3] - g[1])))
    oben = round(0.125 * HOEHE) - f.getbbox("H")[1]

    # Die Zeile auf eine eigene Ebene: zu breit, wird sie gestaucht.
    luecke, siegelbreite = round(0.03 * BREITE), round(0.135 * BREITE)
    stuecke = [(teile["ort"], 0), ("", siegelbreite), (teile["buchstaben"], luecke),
               (teile["zahl"] + teile["zusatz"], 0)]
    breiten = [f.getlength(t) if t else 0 for t, _ in stuecke]
    gesamt = round(sum(breiten) + sum(z for _, z in stuecke)) + 4
    ebene = Image.new("L", (gesamt, HOEHE), 0)
    zeichner = ImageDraw.Draw(ebene)
    x, siegel_x = 0, 0
    for (t, zwischen), b in zip(stuecke, breiten):
        if t:
            zeichner.text((x, oben), t, font=f, fill=255)
            x += b
        else:
            siegel_x = x
        x += zwischen
    links = int(info["band"] * BREITE) + round(0.016 * BREITE)
    frei = BREITE - links - round(0.03 * BREITE)
    stauchen = min(1.0, frei / gesamt)
    ebene = ebene.resize((max(1, round(gesamt * stauchen)), HOEHE), Image.LANCZOS)
    # Mittig im freien Feld, wie auf echten Schildern.
    x0 = links + (frei - ebene.size[0]) // 2

    # Gepraegt: oben links ein Hauch heller, unten rechts dunkler.
    farbe = tuple(info["farbe"])
    for dx, dy, ton, deckung in ((-1, -1, (235, 235, 235), 70), (1, 1, (0, 0, 0), 80),
                                 (0, 0, farbe, 255)):
        maske = ebene.point(lambda p, d=deckung: p * d // 255)
        schild.paste(Image.new("RGB", ebene.size, ton), (x0 + dx, dy), maske)

    # Plakette oben, Siegel unten, zwischen Ort und Buchstaben.
    mitte = x0 + round((siegel_x + siegelbreite / 2) * stauchen)
    for name in ("plakette", "siegel"):
        if v.get(name) is None or name not in info:
            continue
        _, my, r = info[name]
        stueck = v[name] if name == "siegel" else _umfaerben(v[name], teile.get("plakette", "blau"))
        groesse = round(2 * r * HOEHE)
        stueck = stueck.resize((groesse, groesse), Image.LANCZOS)
        schild.paste(stueck, (mitte - groesse // 2, round(my * HOEHE) - groesse // 2), stueck)
    return schild


# --- Einsetzen ------------------------------------------------------------

def einsetzen(bild: Image.Image, ecken: list, schild: Image.Image) -> Image.Image:
    """Das Schild in die vier Ecken setzen, im Licht des alten."""
    v = _lade()
    bild = bild.convert("RGB")
    ecken = ordnen(ecken)
    # Licht des alten Schilds an derselben Stelle, ohne seine Schrift.
    alt = gerade(bild, ecken)
    licht = np.asarray(_hintergrund(alt).convert("L"), np.float32)
    verhaeltnis = np.clip(licht / np.maximum(v["licht"], 1.0), 0.2, 2.0)
    a_alt = np.asarray(alt, np.float32).reshape(-1, 3)
    a_vor = np.asarray(v["vorlage"], np.float32).reshape(-1, 3)
    hell_alt = a_alt[a_alt.sum(1) >= np.percentile(a_alt.sum(1), 80)].mean(0)
    hell_vor = a_vor[a_vor.sum(1) >= np.percentile(a_vor.sum(1), 80)].mean(0)
    stich = (hell_alt / hell_alt.mean()) / (hell_vor / hell_vor.mean())
    neu = np.asarray(schild, np.float32) * verhaeltnis[..., None] * stich
    schild = Image.fromarray(np.clip(neu, 0, 255).astype(np.uint8))

    # Vorher auf ungefaehr die Zielgroesse: PIL glaettet beim Verziehen nicht,
    # ein grosses Schild auf wenige Pixel ergaebe Treppen.
    breite = max(np.hypot(ecken[1][0] - ecken[0][0], ecken[1][1] - ecken[0][1]),
                 np.hypot(ecken[2][0] - ecken[3][0], ecken[2][1] - ecken[3][1]))
    f = min(1.0, max(0.05, 1.5 * breite / BREITE))
    sb, sh = max(8, round(BREITE * f)), max(2, round(HOEHE * f))
    schild = schild.resize((sb, sh), Image.LANCZOS)
    verzogen = schild.transform(bild.size, Image.PERSPECTIVE,
                                _hom(ecken, _rechteck(sb, sh)), Image.BICUBIC)
    # Die Maske vierfach fein gezeichnet und verkleinert: glatte Kanten.
    gross = Image.new("L", (bild.size[0] * 4, bild.size[1] * 4), 0)
    ImageDraw.Draw(gross).polygon([(x * 4, y * 4) for x, y in ecken], fill=255)
    maske = gross.resize(bild.size, Image.LANCZOS)
    fertig = bild.copy()
    fertig.paste(verzogen, (0, 0), maske)
    return fertig


def maske(groesse: tuple, ecken: list) -> Image.Image:
    """Die Flaeche des Schilds als Maske -- fuer die Suche nach seiner Lage."""
    m = Image.new("L", groesse, 0)
    ImageDraw.Draw(m).polygon([tuple(e) for e in ordnen(ecken)], fill=255)
    return m
