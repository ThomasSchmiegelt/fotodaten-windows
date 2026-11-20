"""Rauten-Variablen und die Bezugsperson im Text->Bild-Prompt.

    #hose#    ein Platzhalter. Auf der Seite stehen dazu beliebig viele Werte
              (Kleid, Shorts, Jeans ...), und jedes Bild bekommt zufaellig
              einen davon -- reproduzierbar aus seinem Seed.
    !Kai!     die Bezugsperson, auch als Beschreibung (!die erste Frau!). Blickwinkel, Blick, Mimik und Haltung aus den
              Reglern gelten fuer sie und nicht fuer irgendeine Person im
              Bild.

Ueber die Uebersetzung kommen beide nicht heil: "#hose#" wurde zu "#pants#"
oder ganz weggelassen. Die Platzhalter gehen deshalb als [[1]], [[2]] ... durch
das Sprachmodell und werden danach geprueft; fehlt einer, bleibt der Satz
unuebersetzt. Die Werte gehen als eigene Felder mit.
"""

import random
import re

# Ein Name ohne Leerzeichen zwischen den Rauten. "#1" oder ein einzelnes "#"
# im Text bleiben so, wie sie sind.
VARIABLE = re.compile(r"#([A-Za-zÄÖÜäöüß_][\wÄÖÜäöüß\-]{0,39})#")
# Ein Name in Ausrufezeichen, ohne Leerzeichen gleich nach dem ersten: aus
# "Hallo! Schoen!" wird so keine Person.
PERSON = re.compile(r"!([A-Za-zÄÖÜäöüß][\wÄÖÜäöüß .\-]{0,39}?)!")
PLATZ = re.compile(r"\[\[(\d+)\]\]")

# Was die Kataloge sagen, wenn sie die Person meinen. Ohne Bezug heisst das
# "irgendwer" -- bei zwei Leuten im Bild sucht sich das Modell einen aus.
UNBESTIMMT = re.compile(
    r"\b(?:the|a) (?:described |main |same |pictured )?(?:person|subject|figure)"
    r"(?P<gen>'s)?\b", re.I)


def namen(text: str) -> list[str]:
    """Die Variablen im Text, jede einmal, in der Reihenfolge des Auftretens."""
    gesehen = []
    for m in VARIABLE.finditer(text or ""):
        if m.group(1).lower() not in (g.lower() for g in gesehen):
            gesehen.append(m.group(1))
    return gesehen


def bezug(text: str) -> tuple[str, str]:
    """Die Bezugsperson heraustrennen: (Text ohne Ausrufezeichen, Name).

    Nur die erste zaehlt als Bezug; weitere Namen in Ausrufezeichen verlieren
    nur die Zeichen.
    """
    gefunden = PERSON.search(text or "")
    if not gefunden:
        return text, ""
    return PERSON.sub(lambda m: m.group(1).strip(), text), gefunden.group(1).strip()


def werte_sauber(roh) -> dict[str, list[str]]:
    """{name: [werte]} aus der Anfrage; leere Werte fallen weg."""
    if not isinstance(roh, dict):
        return {}
    sauber = {}
    for name, werte in roh.items():
        if isinstance(werte, str):
            werte = re.split(r"[\n;]", werte)
        if not isinstance(werte, list):
            continue
        liste = [str(w).strip() for w in werte if str(w).strip()]
        if liste:
            sauber[str(name).strip().lower()] = liste
    return sauber


def maskieren(text: str) -> tuple[str, list[str]]:
    """#name# -> [[n]] fuer die Uebersetzung. Zurueck auch die Reihenfolge."""
    reihe = namen(text)
    index = {n.lower(): i + 1 for i, n in enumerate(reihe)}
    return (VARIABLE.sub(lambda m: f"[[{index[m.group(1).lower()]}]]", text),
            reihe)


def entmaskieren(text: str, reihe: list[str]) -> str | None:
    """[[n]] -> #name#. None, wenn ein Platzhalter verloren ging."""
    gefunden = {int(n) for n in PLATZ.findall(text)}
    if gefunden != set(range(1, len(reihe) + 1)):
        return None
    return PLATZ.sub(lambda m: f"#{reihe[int(m.group(1)) - 1]}#", text)


def einsetzen(text: str, werte: dict[str, list[str]], seed: int,
              nummer: int) -> tuple[str, dict[str, str]]:
    """Jede Variable durch einen zufaelligen Wert ersetzen.

    Je Bild ein eigener Zufall aus Seed und Bildnummer: dieselbe Serie mit
    demselben Seed ergibt dieselbe Verteilung. Dieselbe Variable zweimal im
    Text bekommt in einem Bild denselben Wert. Eine Variable ohne Werte
    verliert nur die Rauten.
    """
    zufall = random.Random(f"{seed}:{nummer}")
    gezogen: dict[str, str] = {}
    for name in namen(text):
        liste = werte.get(name.lower())
        gezogen[name.lower()] = zufall.choice(liste) if liste else name
    return (VARIABLE.sub(lambda m: gezogen[m.group(1).lower()], text), gezogen)


def auf_person(text: str, name: str, eigener: str = "") -> str:
    """Die Angaben der Regler auf die Bezugsperson richten.

    `eigener` ist der Text des Benutzers vorn im Prompt; der bleibt, wie er
    ist -- dort steht die Person schon mit Namen. Umgestellt wird der
    angehaengte Teil aus den Katalogen, und am Ende sagt ein Satz
    ausdruecklich, wen Blick, Haltung und Mimik meinen.
    """
    if not name:
        return text

    def richten(stueck: str) -> str:
        return UNBESTIMMT.sub(lambda m: name + ("'s" if m.group("gen") else ""),
                              stueck)

    # Die Kameraeinstellung steht *vor* dem eigenen Text ("the person faces a
    # large mirror ... <eigener Text>"), die Achsen dahinter. Beide Seiten
    # werden gerichtet, der eigene Text in der Mitte nicht -- bei einem Kampf
    # kann dort "the other person" ganz bewusst der Gegner sein.
    stelle = text.find(eigener) if eigener else -1
    if stelle >= 0:
        text = (richten(text[:stelle]) + eigener
                + richten(text[stelle + len(eigener):]))
    else:
        text = richten(text)
    return (f"{text.rstrip().rstrip('.')}. The camera angle, gaze, facial "
            f"expression and pose described here apply to {name}; everyone "
            f"else acts naturally.")
