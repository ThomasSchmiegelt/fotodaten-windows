"""Einen Gegenstand fuer sechs Ansichten beschreiben.

Die allgemeine Formulierung -- "the picture shows only its top, the sides of
the body are hidden beneath it" -- hebt die Kamera zuverlaessig an, aber sie
weiss nichts ueber den Gegenstand. Sie kann nicht sagen, dass unten die
Parabolantenne sitzt und die Solarpaneele nur noch als schmale Kanten
erscheinen. Das Bildmodell muss es sich dann selbst ausdenken und greift
dabei auf seine gewohnte Schauseite zurueck.

Deshalb vorweg die Frage an das Sprachmodell: wie sieht dieser Gegenstand
von jeder der sechs Seiten aus -- was steht in der Mitte, was rueckt an den
Rand, was ist verdeckt. Aus den Antworten baut `sechsseiten.py` die sechs
Prompts.

Dieselbe Arbeitsteilung wie bei `stellung.py` fuer den Szenenaufbau: das
Sprachmodell denkt ueber den Gegenstand nach, das Bildmodell malt.
"""

import re

from .ollama import MODEL, antwort

# Die sechs Schluessel, in derselben Reihenfolge wie in `sechsseiten.SEITEN`.
SEITEN = ("vorne", "hinten", "links", "rechts", "oben", "unten")

# Kein Beispielsatz im Systemtext: das kleine Modell schreibt ihn
# wortwoertlich zurueck -- gemessen an den Personenprompts, wo der
# Beispielmensch aus der Anleitung als Antwort herauskam. Deshalb nur
# Platzhalter in spitzen Klammern.
SEITEN_SYSTEM = """Du beschreibst einen Gegenstand für sechs Ansichten: von
vorn, von hinten, von links, von rechts, von oben und von unten.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

{"gegenstand": "<der Gegenstand auf ENGLISCH, ein bis zwei Sätze: Form,
                 Größe, Material, Oberfläche, Zustand -- ohne
                 Blickrichtung, ohne Umgebung, ohne Person>",
 "vorne":      "<was in dieser Ansicht zu sehen ist>",
 "ohne_vorne": "<die Teile, die in dieser Ansicht NICHT zu sehen sind>",
 "hinten": "…", "ohne_hinten": "…",
 "links":  "…", "ohne_links":  "…",
 "rechts": "…", "ohne_rechts": "…",
 "oben":   "…", "ohne_oben":   "…",
 "unten":  "…", "ohne_unten":  "…"}

Regeln für die sechs Ansichten:
- Jeder Wert steht auf ENGLISCH, fängt klein an und passt hinter die Wörter
  "The picture shows". Er beginnt deshalb mit "only".
- Sage, WAS ZU SEHEN IST, und nenne die Teile beim Namen: welches Teil in
  der Mitte steht, welches an den Rand rückt, welches nur noch als schmale
  Kante erscheint. Schreibe nie, wo die Kamera steht -- das steht schon
  woanders, und das Bildmodell folgt einer Kameraangabe ohnehin schlecht.
- In "vorne" bis "unten" steht NUR Sichtbares. Was in dieser Ansicht
  verdeckt ist, nennst du dort mit keinem Wort -- auch nicht als "the
  antenna is hidden". Ein Bildmodell malt, was dasteht; die Verneinung
  davor liest es kaum. Verdecktes gehört ausschließlich in "ohne_…".
- KEIN Teil steht in beiden Feldern. Was du in "vorne" nennst, darf in
  "ohne_vorne" nicht vorkommen, und umgekehrt. Die beiden Felder teilen den
  Gegenstand auf: hier das Sichtbare, dort das Verdeckte.
- "ohne_…" ist eine Aufzählung von Teilen, mit Komma getrennt, auf
  ENGLISCH, ohne Satz drumherum. Nenne dort jedes Teil, das in dieser
  Ansicht hinter dem Gegenstand liegt oder von ihm verdeckt wird. Benutze
  genau dieselben Wörter wie in "gegenstand" -- ein anderes Wort für
  dasselbe Teil greift ins Leere.
- Wiederhole nicht die ganze Beschreibung des Gegenstands. Sie steht schon
  in "gegenstand" und käme sonst zweimal ins Bild.
- "unten" ist die schwerste Ansicht: dort ist zu sehen, worauf der
  Gegenstand sonst steht -- Boden, Füße, Naht, Schraubenköpfe, Rollen, was
  immer dort sitzt. Überlege zuerst, was an seiner Unterseite ist, und
  beschreibe dann das. "unten" ist nie dasselbe wie "vorne".
- Ist der Gegenstand links und rechts gleich gebaut, sollen "links" und
  "rechts" dasselbe sagen, nur seitenverkehrt. Zwei zufällig verschiedene
  Ansichten wären falsch.
- Der Gegenstand SCHWEBT frei im Raum. Er steht auf nichts, liegt auf
  nichts und wird von nichts gehalten. Schreibe deshalb nie von Boden,
  Untergrund, Tisch, Fläche, Sockel, Hand oder Schatten -- auch nicht bei
  "unten", wo es am nächsten läge.
- KEINE Zahlenvergleiche wie "viermal so lang wie der Körper". Das
  Bildmodell zählt nicht, es sieht die Zahl und malt vier Stück -- gemessen
  an einem Satelliten, dessen Paneele "four times the length of the body"
  maßen und der daraufhin vier Paneele bekam. Schreibe die Größe in Worten:
  "far wider than the body is long". Eine Zahl steht nur dort, wo sie
  wirklich eine Anzahl ist, und dann genau einmal.
- Erfinde nichts, was die Anfrage nicht hergibt. Was sie offen lässt,
  folgerst du aus der Bauart des Gegenstands.

Aus dieser Anweisung übernimmst du keine einzige Wendung."""


# Das Modell schreibt den Vorspann gern mit, obwohl er im Prompt schon
# davorsteht. Zweimal ergaebe "The picture shows the picture shows ...".
VORSPANN = re.compile(
    r"^\s*(?:the\s+|this\s+)?(?:picture|image|photo(?:graph)?|view)\s+"
    r"(?:shows|shows us|displays)\s+", re.I)


# Der Gegenstand schwebt -- aber gerade bei "unten" stellt ihn das
# Sprachmodell gern auf etwas: "while the base rests on a flat ground
# plane". Im Prompt angekommen waere das ein Boden im Bild, und die
# Unteransicht wieder verdeckt. Im Systemtext steht es deshalb ausdruecklich,
# und hier noch einmal -- einmal gesagt hat nicht gereicht.
AUFGESTELLT = r"(?:ground|floor|table(?:top)?|pedestal|shadow|" \
              r"(?:rest|sit|stand|plac)(?:s|ed|ing)?\s+on)"

# Der Satzteil, in dem so ein Wort steht. Das Trennzeichen davor ist Pflicht:
# ohne es frass der Ausdruck den Satz von vorn auf, und vom halben Satelliten
# blieb nur noch, was hinter dem Boden stand.
BODEN_TEIL = re.compile(r"\s*(?:[,;]|\s+while|\s+and|\s+with)\s*"
                        r"[^;,]*?\b" + AUFGESTELLT + r"\b[^;,]*", re.I)
BODEN = re.compile(r"\b" + AUFGESTELLT + r"\b", re.I)


# "four times the length of the body" -- so gemeint: viermal so lang. So
# gemalt: vier Paneele. Das Bildmodell zaehlt nicht, es greift sich die Zahl
# und die nachstehende Sache. Gemessen am Satelliten, der daraufhin vier
# Solarpaneele hatte statt zwei. Der Vergleich wird deshalb in Worte
# gebracht, bevor er ins Bild geht.
ZAHLWORT = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
# "drei mal so hoch wie das Gehaeuse" -- die Eigenschaft bleibt erhalten,
# nur die Zahl geht.
MAL_WIE = re.compile(r"\b" + ZAHLWORT + r"\s+times\s+as\s+(\w+)\s+as\s+",
                     re.I)
# "viermal die Laenge des Rumpfes"
MAL_VON = re.compile(r"\b" + ZAHLWORT + r"\s+times\s+(?:the\s+\w+\s+of\s+)?",
                     re.I)
# "doppelt so lang" kommt ohne "times" aus und faellt sonst durch.
MAL_DOPPELT = re.compile(r"\b(?:twice|thrice|double)\s+(?:the\s+)?", re.I)


def ohne_zahlenvergleich(text: str) -> str:
    """Einen Groessenvergleich mit Zahl in Worte fassen.

    Aus "extend four times the length of the body" wird "extend far beyond
    the body", aus "three times as tall as the mast" wird "very tall, far
    beyond the mast". Dieselbe Aussage, ohne die Zahl, die als Anzahl
    durchgeht.
    """
    sauber = MAL_WIE.sub(r"very \1, far beyond ", text or "")
    sauber = MAL_VON.sub("far beyond ", sauber)
    sauber = MAL_DOPPELT.sub("far beyond the ", sauber)
    return re.sub(r"\s{2,}", " ", sauber).strip()


def _sicht(text: str) -> str:
    """Einen Ansichtssatz so zurechtlegen, dass er mitten im Satz steht."""
    sauber = VORSPANN.sub("", (text or "").strip())
    sauber = BODEN_TEIL.sub("", sauber)
    sauber = ohne_zahlenvergleich(sauber)
    # Steht der Boden nicht in einem Nebensatz, sondern mitten in der
    # Hauptsache, laesst er sich nicht herausschneiden, ohne die Ansicht zu
    # zerreissen. Dann lieber den allgemeinen Satz nehmen.
    if BODEN.search(sauber):
        return ""
    sauber = re.sub(r"\s{2,}", " ", sauber).strip().rstrip(". ")
    # Zu kurz heisst: das Modell hat nichts gesagt. Dann ist der allgemeine
    # Satz aus `sechsseiten.SEITEN` besser als ein halber.
    if len(sauber) < 12:
        return ""
    sauber = sauber[:400]
    # Klein anfangen -- der Satz steht hinter "The picture shows". Ein
    # durchgaengig grosses Wort wie LED bleibt, wie es ist.
    erstes = sauber.split(" ", 1)[0]
    if not erstes.isupper():
        sauber = sauber[0].lower() + sauber[1:]
    # "only" ist nicht Zierde, sondern das Wort, das gegen die gewohnte
    # Schauseite arbeitet: die gemessene Fassung begann damit. Das
    # Sprachmodell laesst es gern weg.
    if not sauber.lower().startswith("only"):
        sauber = "only " + sauber
    return sauber


def ansicht_satz(text: str) -> str:
    """Einen von Hand geschriebenen Ansichtssatz genauso zurechtlegen.

    Was im Eingabefeld hinter `/unten` steht, geht denselben Weg wie der
    Satz des Sprachmodells: es landet an derselben Stelle im Prompt, hinter
    denselben Woertern, und der Boden hat dort ebenso wenig zu suchen.
    """
    return _sicht(text)


def seiten_plan(text: str, modell: str | None = None) -> dict:
    """Der Gegenstand auf Englisch und je Seite, was in ihr zu sehen ist.

    Zurueck kommt `{"gegenstand": str, "sichten": {seite: satz}}`. Was das
    Modell auslaesst, fehlt auch hier -- `sechsseiten.py` nimmt dafuer
    seinen allgemeinen Satz. Lieber eine Seite allgemein beschrieben als
    eine mit einem halben Satz, der ins Leere zeigt.
    """
    leer = {"gegenstand": "", "sichten": {}, "ohne": {}}
    if not (text or "").strip():
        return leer
    roh = antwort({
        "model": modell or MODEL,
        "format": "json",
        # Sieben Felder, je rund achtzig Woerter. Zu knapp bemessen bricht
        # das JSON mittendrin ab, und dann fehlen die letzten Ansichten,
        # ohne dass es auffaellt -- "unten" steht zuletzt.
        "options": {"temperature": 0.3, "num_predict": 900},
        "messages": [{"role": "system", "content": SEITEN_SYSTEM},
                     {"role": "user", "content": text.strip()}],
    })
    if not isinstance(roh, dict):
        return leer
    sichten, ohne = {}, {}
    for seite in SEITEN:
        satz = _sicht(str(roh.get(seite) or ""))
        if satz:
            sichten[seite] = satz
        teile = _ohne(str(roh.get("ohne_" + seite) or ""), satz)
        if teile:
            ohne[seite] = teile
    return {"gegenstand": ohne_zahlenvergleich(
                str(roh.get("gegenstand") or "").strip()[:600].rstrip(".")),
            "sichten": sichten, "ohne": ohne}


def _ohne(text: str, sichtbar: str = "") -> str:
    """Die Aufzaehlung der verdeckten Teile, auf das Noetige gestutzt.

    Ein ganzer Satz taugt hier nicht: der Torwaechter sucht die Woerter
    spaeter im Prompt und wuerde an "which is hidden behind the body"
    haengenbleiben.

    `sichtbar` ist der Satz derselben Ansicht, und was dort vorkommt, faellt
    hier heraus. Gemessen am ersten Vorschlag fuer den Satelliten: das
    Sprachmodell schrieb unter "vorne" den Kameratubus als Hauptsache und
    nannte ihn gleich darauf als verdeckt. Uebernommen haette der
    Torwaechter der Ansicht ihr Motiv weggestrichen.
    """
    roh = (text or "").strip().rstrip(". ")
    stuecke = []
    for stueck in re.split(r"[,;]| and ", roh):
        stueck = re.sub(r"^\s*(?:the|a|an|its)\s+", "", stueck.strip(), flags=re.I)
        stueck = stueck.strip(" .;")
        # Was zu lang ist, ist kein Teil mehr, sondern ein Nebensatz.
        if 2 < len(stueck) <= 40 and stueck.lower() not in (sichtbar or "").lower():
            stuecke.append(stueck)
    return ", ".join(dict.fromkeys(stuecke))[:300]
