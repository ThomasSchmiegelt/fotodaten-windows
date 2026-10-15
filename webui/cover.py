"""Ein Titelblatt: welcher Titel, welche Schlagzeilen, welcher Preis.

Der Effekt `/magazine cover` sagt dem Modell, dass ein Heft entstehen soll
-- Titelzeile oben, Schlagzeilen an der Seite, Barcode, Ausgabennummer. Was
darin *steht*, sagt er nicht. Dann erfindet es das Modell, und zwar als
Fantasieschrift: auf dem ersten Satelliten-Cover stand "WALD ARAS" als Titel
und "SRDVIS ZYABRNTS" als Schlagzeile.

Vorgegebenen Text schreibt Qwen-Image dagegen zuverlaessig. Hier steht
deshalb die Umsetzung der Eingabemaske: aus Titel, Zeilen, Ausgabe und Preis
wird ein Satz, der jedes Wort in Anfuehrungszeichen beim Namen nennt.

Der letzte Satz ist der wichtigste: *jedes* Wort auf dem Titelblatt ist
eines der genannten, sonst keines. Ohne ihn fuellt das Modell den freien
Platz weiter mit erfundener Schrift -- auf dem zweiten Versuch stand unter
der richtigen Ausgabennummer noch eine Zeile Kauderwelsch.
"""

import re

# Die Grundlage. Sie ersetzt die feste Anweisung des Effekts, statt sie zu
# ergaenzen: jene verlangt einen Barcode, und die Maske darf ihn abwaehlen.
GRUNDLAGE = ("Turn this into a glossy magazine cover in A4 portrait format, "
             "professional editorial layout with generous white space. The "
             "photograph from the reference image is the cover image and "
             "stays exactly as it is.")

# Ohne diesen Satz erfindet das Modell weitere Schrift, wo Platz ist.
NUR_DIESE = ("Every word on the cover is one of the words given above and "
             "there is no other text anywhere on it: no extra headline, no "
             "strapline, no caption, no fake lettering.")


def _wort(text, laenge: int = 90) -> str:
    """Ein Stueck Text, so wie es im Bild stehen soll.

    Anfuehrungszeichen fliegen heraus -- der Prompt setzt selbst welche, und
    ein zweites Paar mittendrin zerlegt die Anweisung an der falschen
    Stelle.
    """
    sauber = re.sub(r"[\"“”„]", "", str(text or ""))
    return re.sub(r"\s+", " ", sauber).strip()[:laenge]


def _aufzaehlung(stuecke: list[str]) -> str:
    """a, b and c -- englisch, mit "and" vor dem letzten."""
    if len(stuecke) == 1:
        return stuecke[0]
    return ", ".join(stuecke[:-1]) + " and " + stuecke[-1]


def gefuellt(felder: dict | None) -> bool:
    """Steht in der Maske ueberhaupt etwas?

    Eine leere Maske darf die Anweisung nicht bauen: sie wuerde sagen, auf
    dem Titelblatt stehe kein Wort, und das Heft kaeme ohne Schrift heraus.
    """
    felder = felder or {}
    return bool(_wort(felder.get("titel"))
                or [z for z in (felder.get("zeilen") or []) if _wort(z)])


def anweisung(felder: dict, rest: str = "") -> str:
    """Aus den Feldern der Maske die vollstaendige Anweisung fuers Titelblatt."""
    felder = felder or {}
    titel = _wort(felder.get("titel"), 40)
    unter = _wort(felder.get("untertitel"), 70)
    zeilen = [z for z in (_wort(x) for x in (felder.get("zeilen") or [])) if z][:6]
    ausgabe = _wort(felder.get("ausgabe"), 30)
    preis = _wort(felder.get("preis"), 20)

    saetze = [GRUNDLAGE]
    if titel:
        saetze.append(f'The masthead across the top reads "{titel}" in large '
                      f'letters.')
    if unter:
        saetze.append(f'A smaller line directly under the masthead reads '
                      f'"{unter}".')
    if zeilen:
        # Die erste ist die Schlagzeile: ein Titelblatt hat eine grosse und
        # ein paar kleine, nicht fuenf gleich grosse.
        saetze.append(f'The main cover line reads "{zeilen[0]}" in large type.')
        if zeilen[1:]:
            saetze.append("Smaller cover lines down the side read "
                          + _aufzaehlung([f'"{z}"' for z in zeilen[1:]]) + ".")
    schluss = []
    if ausgabe:
        schluss.append(f'the issue "{ausgabe}"')
    if preis:
        schluss.append(f'the price "{preis}"')
    if schluss:
        saetze.append("In the bottom corner stand " + _aufzaehlung(schluss) + ".")
    saetze.append("A barcode sits in the bottom right corner."
                  if felder.get("barcode")
                  else "There is no barcode and no price block on the cover.")
    saetze.append(NUR_DIESE)
    if (rest or "").strip():
        saetze.append(rest.strip())
    return " ".join(saetze)
