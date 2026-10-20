"""Ein Foto vorbehandeln, bevor ein img2img-Modell in der Cloud es nachmalt.

Z Image Turbo (franconia.ai) malt die Vorlage nach dem Prompt neu. Mit
wenig Staerke bleibt das Foto stehen, aber dann wirkt auch der Prompt kaum;
mit viel Staerke wirkt er, und es steht ein anderes Auto da. Gemessen am
blauen BMW, Staerke 0,4 (so viel erlaubt ein bewahrter Bereich, siehe
fotodaten.STAERKE_BEWAHREN): alle zehn Kamerapositionen und alle neun Lichter
ergaben dasselbe Foto, nur das Kennzeichen war verwuerfelt. Und rot wurde
das Auto nicht einmal bei 0,7.

Deshalb wird hier vorher von Hand gemacht, was das Modell nicht kann, und
das Modell gleicht es nur noch an -- es macht aus einer Fotomontage ein
Foto:

    kamera   perspektivisch verzogen, beschnitten oder gekippt. Dieselbe
             Abbildung gilt fuer Maske und Boden, die Box wandert also exakt mit.
    farbe    die vorherrschende bunte Flaeche (die Karosserie) im Zielton,
             oder die gemalte Lackflaeche -- die braucht ein unbuntes Auto
    boden    die gemalte Bodenflaeche mit einem Bild des Untergrunds
    licht    Farbton, Kontrast und Lichtverlauf, Rueckleuchten bleiben hell

In dieser Reihenfolge: die Farbe sucht die bunteste Flaeche, bevor gruenes
Gras dazukommt; das Licht kommt zuletzt und faellt auch auf den neuen Boden.

Alles ist bestimmt -- dieselbe Belegung ergibt dasselbe Bild. Das braucht
`auftraege.run_fotodaten`: es rechnet die Vorlage ein zweites Mal, um aus ihr
die Originalpixel einzusetzen.
"""

import os
import threading

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Die Untergrundbilder entstehen einmal je Sorte und werden wiederverwendet.
BODEN_ORDNER = os.path.join(ROOT, "modelle", "untergrund")

_sperre = threading.Lock()


# --- Kamera -------------------------------------------------------------
#
# Je Position vier Punkte im Foto, die zu den Ecken des neuen Bildes werden
# (oben links, oben rechts, unten rechts, unten links), in Anteilen der
# Bildkante. Alle Punkte liegen im Foto -- so bleibt kein leerer Rand, den
# das Modell bei wenig Staerke nicht fuellen koennte. "weit" und "hochkant"
# gehen so nicht (es fehlte Bild bzw. das Format wechselte) und bleiben dem
# Prompt ueberlassen; "gerade" ist das Foto selbst.

def _schraeg(d: float, links: bool) -> list:
    # Die nahe Seite erscheint groesser: auf ihrer Seite wird weniger Foto
    # auf dieselbe Hoehe gezogen.
    p = [(d, 0.6 * d), (1, 0), (1, 1), (d, 1 - 0.6 * d)]
    return p if links else [(1 - x, y) for x, y in (p[1], p[0], p[3], p[2])]


KAMERA = {
    "linksleicht": _schraeg(0.07, True),
    "rechtsleicht": _schraeg(0.07, False),
    "linksschraeg": _schraeg(0.16, True),
    "rechtsschraeg": _schraeg(0.16, False),
    # Bodennah: unten naeher, also unten vergroessert. Erhoeht umgekehrt.
    "tief": [(0, 0), (1, 0), (0.92, 1), (0.08, 1)],
    "erhoeht": [(0.08, 0), (0.92, 0), (1, 1), (0, 1)],
    "gekipptlinks": "kipp+",
    "gekipptrechts": "kipp-",
    "nah": "nah",
}
KIPPWINKEL = 4.0     # Grad
NAH = 0.68           # Anteil der Bildkante, der bei "nah" bleibt


def _kamera_punkte(groesse: tuple, art, mitte: tuple | None) -> list | None:
    """Die vier Fotopunkte in Pixeln, die zu den Bildecken werden."""
    b, h = groesse
    if isinstance(art, list):
        return [(x * b, y * h) for x, y in art]
    if art == "nah":
        mx, my = mitte or (b / 2, h / 2)
        bb, hh = NAH * b, NAH * h
        x0 = min(max(0, mx - bb / 2), b - bb)
        y0 = min(max(0, my - hh / 2), h - hh)
        return [(x0, y0), (x0 + bb, y0), (x0 + bb, y0 + hh), (x0, y0 + hh)]
    if art in ("kipp+", "kipp-"):
        a = np.radians(KIPPWINKEL if art == "kipp+" else -KIPPWINKEL)
        # So weit hineinzoomen, dass das gedrehte Rechteck ganz im Foto liegt.
        z = np.cos(abs(a)) + max(b / h, h / b) * np.sin(abs(a))
        c, s = np.cos(a), np.sin(a)
        ecken = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
        return [(b / 2 + (c * x - s * y) / z, h / 2 + (s * x + c * y) / z) for x, y in ecken]
    return None


def _koeffizienten(groesse: tuple, punkte: list) -> tuple:
    """PIL-PERSPECTIVE: Bildpunkt -> Fotopunkt, aus den vier Ecken."""
    b, h = groesse
    ziel = [(0, 0), (b, 0), (b, h), (0, h)]
    a, r = [], []
    for (x, y), (u, v) in zip(ziel, punkte):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); r.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); r.append(v)
    return tuple(np.linalg.solve(np.array(a, float), np.array(r, float)))


def kamera_ecken(groesse: tuple, position: str | None, mitte: tuple | None,
                 ecken: list | None) -> list | None:
    """Wohin Punkte des Fotos mit der Kameraposition wandern -- etwa die vier
    Ecken des Kennzeichens. Die Abbildung von `kamera` geht vom neuen Bild
    ins Foto; hier braucht es die Umkehrung."""
    if not ecken or position not in KAMERA:
        return ecken
    punkte = _kamera_punkte(groesse, KAMERA[position], mitte)
    if not punkte:
        return ecken
    k = _koeffizienten(groesse, punkte)
    umgekehrt = np.linalg.inv(np.array([[k[0], k[1], k[2]], [k[3], k[4], k[5]],
                                        [k[6], k[7], 1.0]]))
    raus = []
    for x, y in ecken:
        u, v, w = umgekehrt @ np.array([x, y, 1.0])
        raus.append((u / w, v / w))
    return raus


def kamera(bilder: list, position: str | None, mitte: tuple | None = None) -> list:
    """Dieselbe Kameraposition fuer Foto und Masken (None bleibt None).

    `mitte` ist die Mitte des Objekts -- dorthin geht "nah".
    """
    if position not in KAMERA or not bilder or bilder[0] is None:
        return bilder
    groesse = bilder[0].size
    punkte = _kamera_punkte(groesse, KAMERA[position], mitte)
    if not punkte:
        return bilder
    k = _koeffizienten(groesse, punkte)
    return [None if bild is None else bild.transform(
        groesse, Image.PERSPECTIVE, k,
        Image.BICUBIC if bild.mode == "RGB" else Image.BILINEAR)
        for bild in bilder]


# --- Farbe --------------------------------------------------------------
#
# Je Farbe: Farbton in Grad (None = unbunt), Faktor Saettigung, Faktor
# Helligkeit, Zuschlag Helligkeit. Was fehlt (etwa "neon"), bleibt dem
# Prompt ueberlassen.

FARBTOENE = {
    "rot": (0, 1.0, 1.0, 0), "weiss": (None, 0.06, 1.1, 50),
    "schwarz": (None, 0.1, 0.22, 0), "silber": (None, 0.06, 1.0, 10),
    "dunkelgrau": (None, 0.06, 0.5, 0), "matt": (None, 0.05, 0.6, 0),
    "dunkelgruen": (135, 1.0, 0.55, 0), "beige": (38, 0.35, 1.1, 20),
    "gelb": (52, 1.0, 1.15, 20), "orange": (28, 1.0, 1.1, 10),
    "dunkelblau": (225, 1.0, 0.55, 0), "bordeaux": (348, 0.9, 0.55, 0),
    "pink": (325, 0.9, 1.05, 10), "tuerkis": (178, 1.0, 1.0, 0),
    "limette": (85, 1.0, 1.1, 10), "lila": (280, 0.9, 0.8, 0),
    "knallorange": (22, 1.0, 1.15, 20), "neongruen": (110, 1.0, 1.15, 20),
    "neonpink": (320, 1.0, 1.15, 20),
}
# Mindestanteil der vorherrschenden bunten Farbe am Bild. Darunter ist die
# Karosserie unbunt (weiss, schwarz, silber) und laesst sich am Farbton nicht
# finden -- dann bleibt das Foto, wie es ist, ausser der Lack ist gemalt.
FARBE_ANTEIL = 0.04
# Fuer die gemalte Lackflaeche: der Zielton als feste Farbe, aus derselben
# Tabelle -- Saettigung und Helligkeit eines mittleren Lacks mal den Faktoren.
LACK_SATT, LACK_HELL = 230, 200


def _lack(bild: Image.Image, flaeche: Image.Image, wahl: str) -> Image.Image:
    """Die gemalte Lackflaeche in `wahl`, gleich welche Farbe sie hatte.

    Ein silbernes Auto hat keinen Farbton, den man drehen koennte. Deshalb
    wird hier nur die Helligkeit des Fotos behalten -- Woelbung, Schatten,
    Tropfen -- und mit dem Zielton multipliziert. Was heller ist als der
    Lack im Mittel (Spiegelungen), laeuft gegen Weiss und bleibt Glanz.
    """
    ton, f_satt, f_hell, plus = FARBTOENE[wahl]
    satt = 0 if ton is None else min(255, LACK_SATT * f_satt)
    hell = min(255, LACK_HELL * f_hell + plus)
    grund = np.asarray(Image.new("HSV", (1, 1), (round((ton or 0) * 255 / 360),
                                                 round(satt), round(hell))).convert("RGB"),
                       np.float32)[0, 0]
    m = np.asarray(flaeche.convert("L"), np.float32) / 255
    alt = np.asarray(bild, np.float32)
    lum = _hell(alt)
    mittel = float(np.median(lum[m > 0.5])) if (m > 0.5).any() else 128.0
    rel = (lum / max(mittel, 1.0))[..., None]
    neu = np.where(rel <= 1, grund * rel,
                   grund + (255 - grund) * np.clip(rel - 1, 0, 1))
    b, h = bild.size
    weich = np.asarray(flaeche.convert("L").filter(
        ImageFilter.GaussianBlur(max(1, round(0.002 * max(b, h))))), np.float32)[..., None] / 255
    return Image.fromarray(np.clip(alt * (1 - weich) + neu * weich, 0, 255).astype(np.uint8))


def farbe(bild: Image.Image, wahl: str | None,
          flaeche: Image.Image | None = None) -> Image.Image:
    """Die vorherrschende bunte Flaeche des Fotos in `wahl` umfaerben --
    oder die gemalte Lackflaeche `flaeche`, wenn es sie gibt.

    Der bewahrte Bereich wird mit umgefaerbt -- `fotodaten.bewahren` setzt
    ihn danach aus dieser Vorlage ein, und so hat sein Rand schon die neue
    Farbe. Die Kupplung selbst ist schwarz und bleibt es.
    """
    if wahl not in FARBTOENE:
        return bild
    bild = bild.convert("RGB")
    if flaeche is not None and flaeche.getbbox():
        return _lack(bild, flaeche, wahl)
    ton, f_satt, f_hell, plus = FARBTOENE[wahl]
    hsv = np.asarray(bild.convert("HSV")).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    bunt = (s > 90) & (v > 40)
    zahl, _ = np.histogram(h[bunt], bins=32, range=(0, 256))
    if zahl.max() < FARBE_ANTEIL * h.size:
        return bild
    mitte = (zahl.argmax() + 0.5) * 8
    abstand = np.abs(((h - mitte + 128) % 256) - 128)
    wahl_flaeche = Image.fromarray(((abstand < 16) & (s > 60) & (v > 25)).astype(np.uint8) * 255)
    # Einzelne Pixel (Spiegelungen im Glas) weg, dann weich auslaufen.
    wahl_flaeche = wahl_flaeche.filter(ImageFilter.MedianFilter(5)).filter(
        ImageFilter.GaussianBlur(2))
    a = np.asarray(wahl_flaeche, dtype=np.float32) / 255
    neu = hsv.copy()
    if ton is not None:
        neu[..., 0] = ton * 255 / 360
    neu[..., 1] = np.clip(s * f_satt, 0, 255)
    neu[..., 2] = np.clip(v * f_hell + plus, 0, 255)
    neu = np.asarray(Image.fromarray(neu.astype(np.uint8), "HSV").convert("RGB"),
                     dtype=np.float32)
    alt = np.asarray(bild, dtype=np.float32)
    return Image.fromarray(np.clip(alt * (1 - a[..., None]) + neu * a[..., None],
                                   0, 255).astype(np.uint8))


# --- Boden --------------------------------------------------------------
#
# Den Untergrund kann das Modell bei wenig Staerke nicht tauschen, und von
# selbst laesst sich nicht sicher sagen, was Boden ist. Deshalb malt man ihn
# im Editor an (zweiter Pinsel). Hinein kommt ein Bild der Sorte -- einmal
# vom Cloud-Bildmodell gemalt und in modelle/untergrund/ abgelegt --, mit
# der groben Helligkeit des Fotos multipliziert: der Schatten unter dem Auto
# bleibt.

def _boden_prompt(text: str) -> str:
    satz = text.replace("standing on ", "").replace("standing in ", "")
    return (f"A photo of the ground: {satz}. Seen at a shallow angle from one "
            "metre height, the surface fills the whole frame and recedes into "
            "the distance, even daylight, nothing else in the picture, no "
            "vehicles, no people, no sky.")


def boden_bild(schluessel: str, text: str) -> Image.Image | None:
    """Das Bild einer Untergrundsorte, beim ersten Mal von der Cloud.

    None ohne Cloud-Bildmodell oder wenn der Anbieter versagt -- dann wirkt
    der Untergrund nur ueber den Prompt.
    """
    pfad = os.path.join(BODEN_ORDNER, f"{schluessel}.png")
    with _sperre:
        if os.path.exists(pfad):
            return Image.open(pfad).convert("RGB")
        import cloud
        if not cloud.aktiv("bild"):
            return None
        try:
            bild = cloud.bild(_boden_prompt(text), 1024, 768, seed=7, schritte=8)
        except RuntimeError:
            return None
        os.makedirs(BODEN_ORDNER, exist_ok=True)
        bild.save(pfad)
        return bild


def boden(bild: Image.Image, flaeche: Image.Image | None,
          untergrund: Image.Image | None) -> Image.Image:
    """Die gemalte Bodenflaeche mit dem Untergrund belegen."""
    if flaeche is None or untergrund is None or not flaeche.getbbox():
        return bild
    bild = bild.convert("RGB")
    b, h = bild.size
    x1, y1, x2, y2 = flaeche.getbbox()
    # Den Untergrund so gross, dass er die Flaeche ganz deckt.
    f = max((x2 - x1) / untergrund.size[0], (y2 - y1) / untergrund.size[1])
    stueck = untergrund.resize((max(1, round(untergrund.size[0] * f)),
                                max(1, round(untergrund.size[1] * f))), Image.LANCZOS)
    lage = Image.new("RGB", bild.size)
    lage.paste(stueck, (x1 - (stueck.size[0] - (x2 - x1)) // 2, y1))
    # Grobe Helligkeit des Fotos: Schatten unter dem Wagen, Licht von vorn.
    r = max(4, round(0.03 * max(b, h)))
    grob = np.asarray(bild.convert("L").filter(ImageFilter.GaussianBlur(r)), np.float32)
    m = np.asarray(flaeche.convert("L"), np.float32) / 255
    mittel = float((grob * m).sum() / max(1.0, m.sum())) or 1.0
    licht = np.clip(grob / mittel, 0.35, 1.5)[..., None]
    neu = np.asarray(lage, np.float32) * licht
    weich = np.asarray(flaeche.convert("L").filter(
        ImageFilter.GaussianBlur(max(1, round(0.003 * max(b, h))))), np.float32)[..., None] / 255
    alt = np.asarray(bild, np.float32)
    return Image.fromarray(np.clip(alt * (1 - weich) + neu * weich, 0, 255).astype(np.uint8))


# --- Licht --------------------------------------------------------------

def _hell(x):
    return x[..., 0] * 0.299 + x[..., 1] * 0.587 + x[..., 2] * 0.114


def _saett(x, s):
    l = _hell(x)[..., None]
    return l + (x - l) * s


def _kontrast(x, k, mitte=0.45):
    return mitte + (x - mitte) * k


def _leuchten(x):
    """Rueckleuchten und Bremslichter: hell und rot. Bleiben im Dunkeln hell."""
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    m = ((r > 0.5) & (r > 1.6 * g) & (r > 1.6 * b)).astype(np.float32)
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(2)), np.float32) / 255
    return m[..., None]


def licht(bild: Image.Image, wahl: str | None) -> Image.Image:
    """Licht und Stimmung von Hand -- das Modell macht daraus ein Foto."""
    if wahl not in LICHTER:
        return bild
    x = np.asarray(bild.convert("RGB"), np.float32) / 255
    h, b = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:b].astype(np.float32)
    xn, yn = xx / b, yy / h
    neu = LICHTER[wahl](x, xn, yn)
    if wahl in DUNKEL:
        k = _leuchten(x)
        neu = neu * (1 - k) + np.maximum(neu, x) * k
    return Image.fromarray((np.clip(neu, 0, 1) * 255).astype(np.uint8))


def _golden(x, xn, yn):
    glut = np.clip(1 - np.hypot(xn, yn * 0.8) / 1.2, 0, 1)[..., None] ** 2
    y = _kontrast(x * [1.15, 1.0, 0.72] * 0.95, 1.1)
    return 1 - (1 - y) * (1 - 0.35 * glut * [1.0, 0.62, 0.22])


def _blau(x, xn, yn):
    himmel = np.clip(1 - yn * 1.6, 0, 1)[..., None]
    return x * [0.5, 0.62, 0.95] * 0.55 + [0.02, 0.04, 0.12] + 0.1 * himmel * [0.2, 0.35, 0.8]


def _mittag(x, xn, yn):
    return _saett(_kontrast(x * 1.05, 1.3), 1.1)


def _studio(x, xn, yn):
    grau = x.reshape(-1, 3).mean(0)
    neutral = x * (grau.mean() / np.maximum(grau, 1e-3))
    rand = 1 - 0.18 * (np.hypot(xn - 0.5, yn - 0.5) ** 2)[..., None]
    return _kontrast((0.5 * x + 0.5 * neutral) * 1.08, 0.85) * rand


def _neon(x, xn, yn):
    l = _hell(x)[..., None]
    links = np.clip(1 - xn * 1.6, 0, 1)[..., None] ** 1.5
    rechts = np.clip(xn * 1.6 - 0.6, 0, 1)[..., None] ** 1.5
    return x * 0.28 + l * (0.9 * links * [0.95, 0.1, 0.8] + 0.9 * rechts * [0.1, 0.85, 1.0])


def _gegenlicht(x, xn, yn):
    schein = np.exp(-((xn - 0.5) ** 2 + (yn + 0.1) ** 2) / 0.18)[..., None]
    y = _kontrast(x * 0.6, 0.9)
    return 1 - (1 - y) * (1 - 0.75 * schein * [1.0, 0.95, 0.85])


def _nebel(x, xn, yn):
    t = (0.15 + 0.5 * np.clip(1 - yn, 0, 1) ** 0.8)[..., None]
    return _saett(x, 0.7) * (1 - t) + t * [0.85, 0.87, 0.9]


def _seitenlicht(x, xn, yn):
    s = np.clip(1 - xn, 0, 1)
    seite = (0.35 + 0.85 * s * s * (3 - 2 * s))[..., None]
    return _kontrast(x * seite, 1.15)


def _bewoelkt(x, xn, yn):
    return _saett(_kontrast(x * [0.97, 1.0, 1.04] * 0.95, 0.85), 0.75)


LICHTER = {"golden": _golden, "blau": _blau, "mittag": _mittag, "studio": _studio,
           "neon": _neon, "gegenlicht": _gegenlicht, "nebel": _nebel,
           "seitenlicht": _seitenlicht, "bewoelkt": _bewoelkt}
DUNKEL = {"blau", "neon", "gegenlicht"}


# --- Alles zusammen -----------------------------------------------------

def anwenden(bild: Image.Image, belegung: dict, maske: Image.Image | None = None,
             bodenflaeche: Image.Image | None = None, untergrund: dict | None = None,
             ecken: list | None = None, lackflaeche: Image.Image | None = None):
    """Foto und Maske fuer eine Belegung (Achse -> Schluessel).

    Zurueck (Vorlage, Maske, Ecken): Maske und die Ecken des Kennzeichens
    haben die Kameraposition mitgemacht.
    `untergrund` ist Schluessel -> Text der Untergrundsorten; ohne gemalte
    Bodenflaeche bleibt der Boden, wie er ist. Ohne gemalte Lackflaeche sucht
    `farbe` die bunteste Flaeche -- ein unbuntes Auto bleibt dann, wie es ist.
    """
    mitte = None
    if maske is not None and maske.getbbox():
        x1, y1, x2, y2 = maske.getbbox()
        mitte = ((x1 + x2) / 2, (y1 + y2) / 2)
    groesse = bild.size
    bild, maske, bodenflaeche, lackflaeche = kamera(
        [bild.convert("RGB"), maske, bodenflaeche, lackflaeche], belegung.get("angle"), mitte)
    ecken = kamera_ecken(groesse, belegung.get("angle"), mitte, ecken)
    bild = farbe(bild, belegung.get("paint"), lackflaeche)
    sorte = belegung.get("scene")
    if bodenflaeche is not None and untergrund and sorte in untergrund:
        bild = boden(bild, bodenflaeche, boden_bild(sorte, untergrund[sorte]))
    bild = licht(bild, belegung.get("light"))
    return bild, maske, ecken


def wirkt(achse: str, wert: str, mit_boden: bool) -> bool:
    """Wird dieser Wert hier vorbehandelt? Sonst wirkt er nur ueber den Prompt."""
    if achse == "angle":
        return wert in KAMERA
    if achse == "paint":
        return wert in FARBTOENE
    if achse == "light":
        return wert in LICHTER
    if achse == "scene":
        return mit_boden
    return False
