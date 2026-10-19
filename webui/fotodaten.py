"""Trainingsdaten aus echten Fotos: Varianten erzeugen und gleich labeln.

Der Weg vom eigenen Foto zum Datensatz in einem Auftrag:

    echte Fotos ──► Varianten je Foto ──► Box je Bild ──► Datensatz
    (eins oder       Farbe, Untergrund,     Qwen3-VL +       Original und
    viele)           Kamera, Licht —        Grounding DINO   Varianten, YOLO
                     einzeln und            (oder die Box    und COCO, dazu
                     kombiniert             von Hand)        attribute.csv

Was sich je Bild aendert, sagt ein **Plan** -- keine Wuerfelei auf gut
Glueck, sondern abgezaehlt:

    einzeln     jede gewaehlte Achse allein, jeder ihrer Werte genau einmal,
                alles andere wie im Foto. Zeigt sauber, was eine Achse tut.
    kombiniert  alle gewaehlten Achsen zugleich, `anzahl` Bilder je Foto.
                Ausgewogen: jeder Wert kommt gleich oft dran, bevor sich
                einer wiederholt, und keine Kombination doppelt, solange
                es noch freie gibt.
    beides      erst einzeln, dann kombiniert.
    alle        das volle Kreuzprodukt -- bei vier Achsen schnell tausende,
                deshalb nach oben begrenzt (MAX_ALLE).

Das Original selbst geht mit in den Datensatz und ist das wertvollste Bild
darin: ein echtes Foto. Ist seine Box von Hand gezogen, wird es sofort
aufgenommen; sonst prueft es dieselbe Kette wie jede Variante.

Benannt wird so, dass Original und Varianten eines Fotos zusammenbleiben:

    <stempel>_foto03_00_original.png
    <stempel>_foto03_07_seed1234.png

`detektor._gruppe` liest die ersten beiden Teile -- ein Foto und alles, was
daraus entstand, landet beim Training geschlossen in train oder in val.
Sonst mess die Validierung nur, wie gut das Modell den Zwilling eines
Trainingsbildes wiedererkennt.
"""

import itertools
import random

from PIL import Image, ImageOps

from kataloge import AXIS_OFF, variant_axes

# Die Achsen, die ein Foto-Datensatz sinnvoll variiert, in der Reihenfolge
# der Oberflaeche. Stil fehlt mit Absicht: er steht fest auf Foto --
# gezeichnete Stile schaden einem Detektor fuer echte Fotos.
ACHSEN = {
    "paint":    "Farbe",
    "scene":    "Untergrund / Umgebung",
    "angle":    "Kameraposition",
    "light":    "Licht",
    "palette":  "Farbstimmung",
    "device":   "Kameraart",
    "material": "Werkstoff",
}
ARTEN = ("einzeln", "kombiniert", "beides", "alle")
MAX_ALLE = 500
MAX_JE_FOTO = 500
# Echte Fotos werden auf hoechstens diese Kante gebracht, bevor sie
# Vorlage und Datensatzbild werden.
FOTO_KANTE = 2048


def tabellen(subject: str) -> dict:
    """Je Achse die erlaubten Werte fuer diese Motivart."""
    alle = variant_axes(subject)
    return {k: alle[k] for k in ACHSEN if k in alle}


def katalog(subject: str) -> dict:
    """Fuer die Oberflaeche: je Achse Schluessel und Anzeigename."""
    return {k: [{"key": s, "label": v[0]} for s, v in t.items()]
            for k, t in tabellen(subject).items()}


def _saubere_achsen(achsen: dict, subject: str) -> dict:
    """Nur bekannte Achsen und Werte; eine leere Liste heisst: alle Werte."""
    erlaubt = tabellen(subject)
    raus = {}
    for feld, werte in (achsen or {}).items():
        if feld not in erlaubt:
            continue
        if werte in (True, "alle", "*") or werte == []:
            werte = list(erlaubt[feld])
        werte = [w for w in dict.fromkeys(werte or []) if w in erlaubt[feld]]
        if werte:
            raus[feld] = werte
    return raus


def _aus(subject: str) -> dict:
    """Alle Varianten-Achsen dieser Motivart auf 'unveraendert'."""
    return {k: AXIS_OFF for k in variant_axes(subject)}


def plan(achsen: dict, art: str = "beides", anzahl: int = 12, seed: int = 0,
         subject: str = "fahrzeug") -> list[dict]:
    """Die Belegung je Bild: eine Liste von dicts Achse -> Schluessel.

    Jede Belegung nennt *alle* Achsen der Motivart. Was nicht gewaehlt ist,
    steht auf AXIS_OFF -- sonst wuerfelte die Engine dort weiter, und neben
    der Farbe wanderte unbemerkt auch der Hintergrund.
    """
    achsen = _saubere_achsen(achsen, subject)
    if not achsen:
        raise ValueError("Bitte mindestens eine Achse mit mindestens einem Wert wählen")
    art = art if art in ARTEN else "beides"
    rng = random.Random(seed)
    grund = {**_aus(subject), "style": "foto"}
    raus = []

    if art in ("einzeln", "beides"):
        for feld, werte in achsen.items():
            for w in werte:
                raus.append({**grund, feld: w})

    if art in ("kombiniert", "beides"):
        felder = list(achsen)
        moeglich = 1
        for w in achsen.values():
            moeglich *= len(w)
        # Je Achse ein gemischter Stapel, der erst leer wird, bevor sich ein
        # Wert wiederholt. Doppelte Kombinationen werden neu gezogen, solange
        # es noch unbenutzte gibt.
        stapel = {f: [] for f in felder}

        def ziehen(f):
            if not stapel[f]:
                stapel[f] = list(achsen[f])
                rng.shuffle(stapel[f])
            return stapel[f].pop()

        gesehen = set()
        for _ in range(max(0, int(anzahl))):
            for _versuch in range(20):
                wahl = tuple(ziehen(f) for f in felder)
                if wahl not in gesehen or len(gesehen) >= moeglich:
                    break
            gesehen.add(wahl)
            raus.append({**grund, **dict(zip(felder, wahl))})

    if art == "alle":
        felder = list(achsen)
        alle = list(itertools.product(*(achsen[f] for f in felder)))
        if len(alle) > MAX_ALLE:
            alle = rng.sample(alle, MAX_ALLE)
        raus = [{**grund, **dict(zip(felder, wahl))} for wahl in alle]

    return raus[:MAX_JE_FOTO]


def vorbereiten(bild: Image.Image) -> Image.Image:
    """Ein echtes Foto als Vorlage: aufrecht, RGB, nicht riesig.

    Handyfotos liegen oft quer in der Datei und tragen die Drehung nur als
    EXIF-Vermerk. Ohne `exif_transpose` saehe das Bildmodell das Auto auf
    der Seite liegen -- und die Box stimmte nicht zum angezeigten Bild.
    """
    bild = ImageOps.exif_transpose(bild).convert("RGB")
    f = FOTO_KANTE / max(bild.size)
    if f < 1:
        bild = bild.resize((round(bild.size[0] * f), round(bild.size[1] * f)),
                           Image.LANCZOS)
    return bild


# --- Bewahren: einen gemalten Bereich aus dem Original einsetzen ------------
#
# Ein img2img-Modell (Z Image Turbo) zeichnet das ganze Bild neu, auch die
# Kupplung -- "alles ausser der Kupplung" kann es nicht. Eine Box um die
# Kupplung hilft nicht: sie enthielte auch ein Stueck Auto, und das soll sich
# ja aendern. Deshalb wird die Kupplung selbst ausgemalt, und nach dem
# Rechnen kommen genau diese Pixel aus dem Original zurueck ins neue Bild.
#
# Das Bild verrutscht dabei leicht -- img2img haelt den Aufbau, aber nicht
# pixelgenau. `ausrichten` sucht die Stelle, an der die Kupplung jetzt sitzt:
# Kantenbild des Originals um die Maske gegen das Kantenbild der Variante,
# normierte Korrelation in einem Fenster von +-8 % der Bildgroesse. Kanten
# statt Farben, weil sich die Farben ja gerade aendern sollen.

LAGE_SICHER = 0.35        # darunter: eingesetzt, aber auf die Pruefliste
SUCHFENSTER = 0.08        # Anteil der Bildkante, um den gesucht wird
ANALYSE = 320             # Kante, auf der gesucht wird


def maske_lesen(bild: Image.Image, groesse: tuple) -> Image.Image | None:
    """Die gemalte Maske in Fotogroesse, 0/255. None, wenn nichts gemalt ist."""
    import retusche
    maske = retusche.maske_lesen(ImageOps.exif_transpose(bild), groesse)
    return maske if maske.getbbox() else None


def _kanten(bild: Image.Image, f: int):
    import numpy as np
    g = np.asarray(bild.convert("L").resize(
        (max(1, bild.size[0] // f), max(1, bild.size[1] // f)), Image.BILINEAR),
        dtype=np.float32)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    return gx + gy


def ausrichten(original: Image.Image, maske: Image.Image,
               variante: Image.Image) -> tuple[int, int, float]:
    """Wohin ist der gemalte Bereich in der Variante gewandert? (dx, dy, Guete).

    Alle drei Bilder in derselben Groesse. Guete ist die Korrelation der
    Kantenbilder, 1 hiesse deckungsgleich.
    """
    import numpy as np
    breite, hoehe = original.size
    f = max(1, round(max(breite, hoehe) / ANALYSE))
    x1, y1, x2, y2 = maske.getbbox()
    rand = 0.25 * max(x2 - x1, y2 - y1)
    p = [max(0, int((x1 - rand) / f)), max(0, int((y1 - rand) / f)),
         min(breite // f, int((x2 + rand) / f) + 1), min(hoehe // f, int((y2 + rand) / f) + 1)]
    a = _kanten(original, f)[p[1]:p[3], p[0]:p[2]]
    b = _kanten(variante, f)
    a = a - a.mean()
    na = np.sqrt((a * a).sum()) or 1.0
    r = max(1, int(SUCHFENSTER * max(breite, hoehe) / f))
    beste = (0, 0, -1.0)
    for oy in range(-r, r + 1):
        for ox in range(-r, r + 1):
            ya, xa = p[1] + oy, p[0] + ox
            if ya < 0 or xa < 0 or ya + a.shape[0] > b.shape[0] or xa + a.shape[1] > b.shape[1]:
                continue
            w = b[ya:ya + a.shape[0], xa:xa + a.shape[1]]
            w = w - w.mean()
            wert = float((a * w).sum() / (na * (np.sqrt((w * w).sum()) or 1.0)))
            if wert > beste[2]:
                beste = (ox * f, oy * f, wert)
    return beste


def bewahren(original: Image.Image, maske: Image.Image, variante: Image.Image,
             licht: bool = True) -> tuple[Image.Image, list, float]:
    """Den gemalten Bereich aus dem Original in die Variante setzen.

    Zurueck: das Bild, die Box des eingesetzten Bereichs (in Pixeln der
    Variante) und die Guete der Ausrichtung.

    `licht` gleicht die Helligkeit an die Variante an -- sonst stuende eine
    taghelle Kupplung in einer Neonnacht. Gemessen wird die Helligkeit des
    ganzen Bildes, nicht die Umgebung der Maske: die Umgebung ist das Auto,
    und das wechselt ja absichtlich die Farbe. Begrenzt auf 0,6 bis 1,4.
    """
    from PIL import ImageFilter, ImageStat
    variante = variante.convert("RGB")
    if original.size != variante.size:
        original = original.resize(variante.size, Image.LANCZOS)
        maske = maske.resize(variante.size, Image.NEAREST)
    dx, dy, guete = ausrichten(original, maske, variante)
    quelle = Image.new("RGB", variante.size)
    quelle.paste(original.convert("RGB"), (dx, dy))
    lage = Image.new("L", variante.size, 0)
    lage.paste(maske, (dx, dy))
    if licht:
        hell = (ImageStat.Stat(variante.convert("L")).mean[0]
                / max(1.0, ImageStat.Stat(original.convert("L")).mean[0]))
        hell = max(0.6, min(1.4, hell))
        quelle = quelle.point(lambda v: min(255, round(v * hell)))
    # Weich ausblenden, aber nach innen: der Rand der Maske soll nicht ein
    # Stueck des alten Autos mitnehmen.
    kante = max(1, round(0.004 * max(variante.size)))
    weich = lage.filter(ImageFilter.MinFilter(2 * kante + 1)).filter(
        ImageFilter.GaussianBlur(kante))
    fertig = variante.copy()
    fertig.paste(quelle, (0, 0), weich)
    box = lage.getbbox()
    return fertig, [box[0], box[1], box[2], box[3]], round(guete, 3)


def verkleinert(bild: Image.Image, kante: int) -> Image.Image:
    """Hoechstens `kante` gross -- etwa damit das Sprachmodell nicht ein
    2048er Foto ansehen muss, um es in zwei Saetzen zu beschreiben."""
    f = kante / max(bild.size)
    if f >= 1:
        return bild
    return bild.resize((round(bild.size[0] * f), round(bild.size[1] * f)), Image.LANCZOS)


def box_umrechnen(box, von: tuple, nach: tuple) -> list | None:
    """Eine Box aus den Pixeln der Anzeige in die des vorbereiteten Fotos."""
    if not box or len(box) != 4:
        return None
    fx, fy = nach[0] / von[0], nach[1] / von[1]
    x1, y1, x2, y2 = (float(v) for v in box)
    x1, x2 = sorted((max(0, min(nach[0], x1 * fx)), max(0, min(nach[0], x2 * fx))))
    y1, y2 = sorted((max(0, min(nach[1], y1 * fy)), max(0, min(nach[1], y2 * fy))))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return [round(x1), round(y1), round(x2), round(y2)]
