"""Retusche: eine Stelle im Bild nachbessern, der Rest bleibt pixelgenau.

Qwen-Image 2.1 hat keinen Masken-Eingang -- beim Bearbeiten zeichnet es
immer das ganze Bild neu, und auch was nicht gemeint war, verschiebt sich
ein wenig. Deshalb geht die Retusche einen Umweg:

1. Um die gemalte Maske wird ein quadratischer Ausschnitt gelegt, mit Rand,
   damit das Modell sieht, wozu die Stelle gehoert.
2. Nur dieser Ausschnitt geht ins Modell. Die Engine liest ihn in voller
   Aufloesung -- ein Mund, der im Ganzkoerperbild 150 Pixel breit ist,
   bekommt so tausend. Daran liegen schiefe Laecheln und Flecken meistens.
3. Das Ergebnis wird auf die Groesse des Ausschnitts zurueckgerechnet, in
   der Farbe an die Umgebung angeglichen und nur innerhalb der Maske, mit
   weicher Kante, ins Original gesetzt.

Hier steht nur Bildarbeit ohne Grafikkarte. Den Auftrag fuehrt
`auftraege.run_retusche` aus.
"""

import numpy as np
from PIL import Image, ImageFilter

# Was jeder Retusche-Anweisung angehaengt wird. Ohne den Satz aendert das
# Modell gern mit, was es fuer verbesserungswuerdig haelt -- am ehesten das
# Gesicht selbst.
ZUSATZ = ("Change only what is described. Keep the identity, skin tone, "
          "lighting, colors, sharpness and framing exactly the same.")

# Fertige Anweisungen fuer die Schnellwahl im Reiter. Englisch, damit sie
# ohne Uebersetzung ankommen; die Seite zeigt die deutschen Namen.
VORLAGEN = {
    "haut": ("Haut glätten, Fleck weg",
             "Remove the red spot and any blemish. The skin there is clean "
             "and even, with the same natural texture and tone as the "
             "surrounding skin."),
    "laecheln": ("Lächeln gerade",
                 "A natural, symmetrical smile: both corners of the mouth at "
                 "the same height, lips and teeth even and well formed."),
    "augen": ("Augen klar",
              "Both eyes clear, symmetrical and looking in the same "
              "direction, with natural irises and catchlights."),
    "haende": ("Hand richtig",
               "An anatomically correct hand with five fingers, natural "
               "proportions and joints."),
    "weg": ("Gegenstand entfernen",
            "Remove the object in this area and fill it with the background "
            "that would naturally be behind it."),
}


def maske_lesen(maske: Image.Image, groesse: tuple[int, int]) -> Image.Image:
    """Die Maske als Graustufen in Bildgroesse. Gemalt ist, was nicht leer ist.

    Die Seite schickt die Malschicht als PNG mit Durchsichtigkeit -- dort
    zaehlt der Alphakanal. Eine Maske aus GIMP oder von Hand ist dagegen
    weiss auf schwarz.
    """
    if maske.mode in ("RGBA", "LA") or "transparency" in maske.info:
        grau = maske.convert("RGBA").getchannel("A")
    else:
        grau = maske.convert("L")
    if grau.size != groesse:
        grau = grau.resize(groesse, Image.NEAREST)
    return grau.point(lambda v: 255 if v > 20 else 0)


def ausschnitt(maske: Image.Image, rand: float = 0.6,
               mindestens: int = 384) -> tuple[int, int, int, int] | None:
    """Der Ausschnitt um die Maske, oder None ohne Maske.

    `rand` ist der Anteil der Maskengroesse, der auf jeder Seite dazukommt.
    Das Quadrat wird ins Bild geschoben statt abgeschnitten; nur wenn das Bild
    selbst schmaler ist, wird es in dieser Richtung kuerzer -- die Engine
    folgt dann dem Seitenverhaeltnis des Ausschnitts.
    """
    box = maske.getbbox()
    if not box:
        return None
    breite, hoehe = maske.size
    l, o, r, u = box
    seite = max(r - l, u - o)
    seite = int(max(seite * (1 + 2 * rand), mindestens))
    sw, sh = min(seite, breite), min(seite, hoehe)
    mx, my = (l + r) / 2, (o + u) / 2
    x0 = int(round(min(max(mx - sw / 2, 0), breite - sw)))
    y0 = int(round(min(max(my - sh / 2, 0), hoehe - sh)))
    return x0, y0, x0 + sw, y0 + sh


def weiche_maske(maske: Image.Image, kante: int) -> Image.Image:
    """Die Maske etwas erweitert und weichgezeichnet.

    Erweitert, damit die volle Wirkung die ganze gemalte Flaeche deckt und
    erst ausserhalb ausblendet -- sonst bliebe am Rand des Flecks ein Rest.
    """
    if kante <= 0:
        return maske
    groesser = maske.filter(ImageFilter.MaxFilter(2 * (kante // 2) + 1))
    return groesser.filter(ImageFilter.GaussianBlur(kante / 2))


def farbe_angleichen(neu: Image.Image, alt: Image.Image,
                     maske: Image.Image) -> Image.Image:
    """Mittlere Farbe des neuen Ausschnitts an die des alten angleichen.

    Gemessen wird ausserhalb der Maske, wo beide dasselbe zeigen sollen.
    Das Bearbeiten verschiebt Helligkeit und Farbton oft um ein paar Werte;
    im ganzen Bild faellt das nicht auf, eingesetzt in ein anderes schon.
    """
    a = np.asarray(alt.convert("RGB"), dtype=np.float32)
    n = np.asarray(neu.convert("RGB"), dtype=np.float32)
    aussen = np.asarray(maske, dtype=np.uint8) < 128
    if aussen.sum() < 500:
        return neu.convert("RGB")
    versatz = a[aussen].mean(axis=0) - n[aussen].mean(axis=0)
    return Image.fromarray(np.clip(n + versatz, 0, 255).astype(np.uint8))


def einsetzen(original: Image.Image, ergebnis: Image.Image,
              maske: Image.Image, box: tuple[int, int, int, int],
              kante: int = 16) -> Image.Image:
    """Das bearbeitete Quadrat nur innerhalb der Maske ins Original setzen."""
    breite, hoehe = box[2] - box[0], box[3] - box[1]
    alt = original.crop(box)
    neu = ergebnis.convert("RGB").resize((breite, hoehe), Image.LANCZOS)
    teil = maske.crop(box)
    neu = farbe_angleichen(neu, alt, weiche_maske(teil, kante * 2))
    fertig = original.copy()
    # Ein durchsichtiges Original behaelt seinen Alphakanal; ersetzt wird
    # nur die Farbe.
    if fertig.mode == "RGBA":
        alpha = fertig.getchannel("A")
        fertig = fertig.convert("RGB")
        fertig.paste(neu, box[:2], weiche_maske(teil, kante))
        fertig.putalpha(alpha)
        return fertig
    fertig = fertig.convert("RGB")
    fertig.paste(neu, box[:2], weiche_maske(teil, kante))
    return fertig


def anweisung(text: str) -> str:
    """Der Prompt fuers Modell: Benutzertext und der feste Zusatz."""
    text = (text or "").strip()
    if text and not text.endswith((".", "!")):
        text += "."
    return f"{text} {ZUSATZ}".strip()
