"""Bausteine: Personen, Orte und Gegenstaende zum Wiederverwenden.

Ein Baustein ist ein Stueck Prompt mit einem Namen, einem Bild und Luecken:

    { "id": "person-anna",
      "art": "person",
      "name": "Anna",
      "prompt": "a woman in her thirties, short dark hair, {kleidung}, {schuhe}",
      "variablen": {"kleidung": "a red wool coat", "schuhe": "brown leather boots"},
      "bild": "20260926-101500_t2i_01_seed42.png" }

Die Luecken in geschweiften Klammern werden beim Benutzen gefuellt; was in
`variablen` steht, ist nur die Vorgabe. Genau das macht eine Serie moeglich,
in der dieselbe Person vier Jacken durchprobiert.

Gespeichert wird je Projekt in `bausteine.json`. Bausteine gehoeren zum
Vorhaben, nicht zum Programm -- wer ein Projekt loescht, wird sie auch los.
"""

import json
import os
import re
import shutil
import tempfile
import threading
import time

import projekte
from kataloge import EINSTELLUNGEN, GEZEICHNET, NICHT_FOTO, STYLES, WESEN

# "szene" entsteht nicht von Hand, sondern beim Zusammenstellen: die fertige
# Mischung aus Person, Gegenstand und Ort, mit ihren Luecken, ihrem Bild und
# den Werten, mit denen sie erzeugt wurde. Damit laesst sie sich spaeter
# wiederholen oder weiterverwenden.
ARTEN = {"person": "Person", "ort": "Ort", "gegenstand": "Gegenstand",
         "szene": "Szene"}

# Eine Luecke: {kleidung}. Nur schlichte Namen, damit sich nichts mit den
# geschweiften Klammern beisst, die in Prompt-Vorlagen vorkommen.
LUECKE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}")


# Lesen-aendern-schreiben laeuft aus mehreren Threads (Server, Auftragslauf);
# ohne Sperre ueberschreibt der eine Lauf die Aenderung des anderen. Reentrant,
# weil kopieren() und andere Funktionen unter der Sperre speichern() rufen.
_SPERRE = threading.RLock()


def _gesperrt(fn):
    def innen(*a, **k):
        with _SPERRE:
            return fn(*a, **k)
    innen.__name__, innen.__doc__ = fn.__name__, fn.__doc__
    return innen


def _datei(projekt: str) -> str:
    return os.path.join(projekte.ordner(projekt), "bausteine.json")


def liste(projekt: str) -> list[dict]:
    """Alle Bausteine eines Projekts, nach Art und Namen sortiert."""
    try:
        with open(_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(daten, list):
        return []
    reihung = list(ARTEN)
    return sorted((b for b in daten if isinstance(b, dict)),
                  key=lambda b: (reihung.index(b.get("art"))
                                 if b.get("art") in ARTEN else 9,
                                 (b.get("name") or "").lower()))


def _schreiben(projekt: str, daten: list[dict]) -> None:
    # Erst in eine Nebendatei, dann umbenennen: ein Absturz mitten im
    # Schreiben laesst sonst eine halbe, unlesbare bausteine.json zurueck.
    ziel = _datei(projekt)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ziel), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, ziel)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def variablen(prompt: str) -> list[str]:
    """Die Luecken eines Prompts, in der Reihenfolge ihres Auftretens."""
    gesehen, raus = set(), []
    for name in LUECKE.findall(prompt or ""):
        if name not in gesehen:
            gesehen.add(name)
            raus.append(name)
    return raus


# Eine Luecke samt dem Bindewort davor. Faellt die Luecke weg, muss das Wort
# mit -- "made of {material}" ohne Material ergaebe sonst "made of ,".
# Mehrwortige zuerst: in der Alternative gewinnt der erste Treffer, sonst
# schnappt "of" zu und von "made of" bliebe "made" stehen.
VERBINDER = "|".join((
    r"made\s+of", r"in\s+front\s+of", r"next\s+to", r"dressed\s+in",
    "featuring", "carrying", "standing", "wearing", "holding", "showing",
    "against", "between", "through", "outside", "beneath", "besides",
    "during", "beside", "behind", "inside", "around", "across", "above",
    "under", "over", "near", "onto", "into", "with", "from", "and",
    "for", "of", "in", "on", "at", "by", "to",
))
LUECKE_MIT = re.compile(r"(\s*\b(?:" + VERBINDER + r")\b)?\s*"
                        r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}")


def einsetzen(prompt: str, werte: dict | None = None) -> str:
    """Fuellt die Luecken und raeumt auf, was eine leere Luecke hinterlaesst.

    Ohne Aufraeumen bliebe von "a basket made of {material}, featuring
    {farbe}" bei leeren Werten "a basket made of , featuring ." stehen. Das
    Bindewort faellt deshalb mit der Luecke, und haengende Satzzeichen danach
    ebenso.
    """
    werte = werte or {}

    def ersatz(treffer):
        wert = str(werte.get(treffer.group(2), "") or "").strip()
        if not wert:
            return ""
        # Das Leerzeichen immer selbst setzen: der Ausdruck verschluckt es vor
        # der Luecke auch dann, wenn gar kein Bindewort davorstand -- aus
        # "under {wetter}" wurde sonst "undersunny". Doppelte werden unten
        # wieder eingedampft.
        return (treffer.group(1) or "") + " " + wert

    text = LUECKE_MIT.sub(ersatz, prompt or "")
    text = re.sub(r"\s*,\s*(?=[,.])", "", text)        # leere Aufzaehlungsglieder
    text = re.sub(r"\s*,\s*(?=$)", "", text)           # haengendes Komma am Ende
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"[\s,]+\.", ".", text)              # " ." und " , ."
    # Ein Bindewort am Schluss hat sein Ziel verloren.
    text = re.sub(r"\s+\b(?:" + VERBINDER + r")\b\s*[.,]?\s*$", "", text)
    return text.strip().strip(",").strip()


def _klein(text: str) -> str:
    """Den Satzanfang kleinschreiben, wenn es nur Satzanfang war.

    Die Teile werden aneinandergehaengt; ein "A woven basket" mitten im Satz
    sieht falsch aus. Ein durchgaengig grosses Wort oder ein Name bleibt.
    """
    erstes = text.split(" ", 1)[0]
    # Ein Kuerzel wie CAD oder NASA bleibt. Alles andere -- auch ein einzelnes
    # "A" -- wird klein; das zweite Zeichen zu pruefen ging daneben, weil dort
    # bei "A woven" ein Leerzeichen steht.
    if text[:1].isupper() and not (len(erstes) > 1 and erstes.isupper()):
        return text[0].lower() + text[1:]
    return text


def _freie_kennung(art: str, daten: list[dict]) -> str:
    """Eine Kennung, die es noch nicht gibt.

    Die Millisekunde allein genuegt nicht: zwei Speichervorgaenge im selben
    Augenblick bekaemen dieselbe, und der zweite ueberschriebe den ersten.
    """
    vergeben = {b.get("id") for b in daten}
    stamm = f"{art}-{int(time.time() * 1000)}"
    kennung, n = stamm, 2
    while kennung in vergeben:
        kennung, n = f"{stamm}-{n}", n + 1
    return kennung


def aliasse(wert) -> list[str]:
    """Die Zweitnamen eines Bausteins, sauber und ohne Doppelte.

    Erlaubt sind Liste oder ein Feld mit Kommas -- die Seite schickt mal so,
    mal so. Leerzeichen werden zu Bindestrichen: der Name wird spaeter mit
    einem Schraegstrich getippt.
    """
    if isinstance(wert, str):
        roh = re.split(r"[,;]", wert)
    else:
        roh = list(wert or [])
    raus = []
    for n in roh:
        n = re.sub(r"\s+", "-", str(n or "").strip().lstrip("/"))[:40]
        if n and not any(n.lower() == x.lower() for x in raus):
            raus.append(n)
    return raus[:8]


def namen(b: dict) -> list[str]:
    """Der Name und alle Zweitnamen eines Bausteins."""
    return [b.get("name") or ""] + aliasse(b.get("alias"))


# Die weiteren Bilder eines Bausteins. Je Eintrag die Datei und wozu sie
# entstanden ist -- ohne den Anlass ist eine Liste von Dateinamen nach zwei
# Wochen nicht mehr zu deuten.
BILDFELDER = ("posen", "spiegelbilder")


def _bildliste(roh) -> list[dict]:
    """Eine Bildliste auf ihre Form bringen. Aeltere Staende haben keine."""
    raus = []
    for eintrag in (roh or []):
        if isinstance(eintrag, str):
            eintrag = {"datei": eintrag}
        if not isinstance(eintrag, dict):
            continue
        datei = str(eintrag.get("datei") or "").strip()
        if not datei:
            continue
        raus.append({"datei": datei,
                     "wozu": str(eintrag.get("wozu") or "")[:120],
                     "prompt": str(eintrag.get("prompt") or "")[:600]})
    # Zwanzig je Feld reichen. Darueber ist es kein Vorrat mehr, sondern
    # eine Halde, und die Auswahl in der Oberflaeche wird unbrauchbar.
    return raus[-20:]


@_gesperrt
def bild_anhaengen(projekt: str, kennung: str, feld: str, datei: str,
                   wozu: str = "", prompt: str = "") -> bool:
    """Ein weiteres Bild an einen Baustein haengen, ohne die uebrigen
    Felder anzufassen. Der Szenenaufbau legt so seine Zwischenbilder ab."""
    if feld not in BILDFELDER or not datei:
        return False
    daten = liste(projekt)
    for b in daten:
        if b.get("id") != kennung:
            continue
        vorhanden = _bildliste(b.get(feld))
        if any(e["datei"] == datei for e in vorhanden):
            return True
        b[feld] = _bildliste(vorhanden + [{"datei": datei, "wozu": wozu,
                                           "prompt": prompt}])
        _schreiben(projekt, daten)
        return True
    return False


@_gesperrt
def speichern(projekt: str, baustein: dict) -> dict:
    """Legt einen Baustein an oder ersetzt einen vorhandenen."""
    art = baustein.get("art") if baustein.get("art") in ARTEN else "person"
    name = (baustein.get("name") or "").strip() or "ohne Namen"
    prompt = (baustein.get("prompt") or "").strip()
    daten = liste(projekt)
    kennung = (baustein.get("id") or "").strip() or _freie_kennung(art, daten)

    # Nur Vorgaben zu Luecken, die es auch gibt -- sonst sammeln sich Reste
    # von Prompts an, die laengst umgeschrieben wurden.
    offen = variablen(prompt)
    roh = baustein.get("variablen") or {}
    vorgaben = {k: str(roh.get(k) or "").strip() for k in offen}

    # Bei einer Person drei getrennte Prompts: wer sie ist, wie ihr Gesicht
    # aussieht, was sie traegt. Eine Grossaufnahme braucht das Gesicht ohne
    # Kleiderbeschreibung, und eine Szene darf die Kleidung austauschen, ohne
    # die Person anzufassen.
    neu = {"id": kennung, "art": art, "name": name, "prompt": prompt,
           "gesicht": (baustein.get("gesicht") or "").strip(),
           "kleidung": (baustein.get("kleidung") or "").strip(),
           # Hautton, Haar- und Augenfarbe stehen einmal und gelten fuer
           # beides: Ganzbild und Grossaufnahme. Als Text in zwei Prompts
           # liefen sie auseinander, und dann war es ein anderer Mensch.
           "haut": (baustein.get("haut") or "").strip(),
           # Mensch, Androide, Roboter: steht vor allem anderen und gilt
           # fuer Ganzbild und Grossaufnahme. Leer heisst Mensch.
           "wesen": (baustein.get("wesen") or "").strip(),
           # Der Stil gehoert zum Musterbild, nicht zum Baustein: er sagt,
           # wie das Bild entstanden ist. Der Prompt selbst bleibt stilfrei,
           # damit dieselbe Person in der naechsten Geschichte als Manga
           # auftreten kann.
           "stil": (baustein.get("stil") or "").strip(),
           # Zweitnamen: dieselbe Figur heisst in Szene drei "die Frau" und
           # in Szene zwoelf "Nora". Beides soll denselben Baustein treffen.
           "alias": aliasse(baustein.get("alias")),
           # Zweites Bild einer Person: die Grossaufnahme der Augen. Sie
           # zeigt, was bei \\augen entsteht, und deckt auf, wenn Gesicht
           # und Koerper nicht zusammenpassen.
           "bild_augen": baustein.get("bild_augen") or "",
           # Weitere Bilder derselben Figur: Posen aus einem Szenenaufbau
           # und Spiegelbilder. Sie loeschen sich nicht mit dem Bild, das
           # sie hervorgebracht hat -- wer Malva einmal liegend hat, soll
           # sie beim naechsten Mal nicht neu rechnen muessen.
           "posen": _bildliste(baustein.get("posen")),
           "spiegelbilder": _bildliste(baustein.get("spiegelbilder")),
           "variablen": vorgaben, "bild": baustein.get("bild") or ""}

    # Nichts verlieren, was der Aufrufer nicht mitschickt.
    for vorher in daten:
        if vorher.get("id") != kennung:
            continue
        for feld in ("bild", "bild_augen", "gesicht", "kleidung", "haut",
                     "wesen", "stil"):
            if not neu[feld]:
                neu[feld] = vorher.get(feld) or ""
        for feld in ("posen", "spiegelbilder"):
            if not neu[feld]:
                neu[feld] = _bildliste(vorher.get(feld))
        if not neu["alias"]:
            neu["alias"] = aliasse(vorher.get("alias"))
    rest = [b for b in daten if b.get("id") != kennung]
    rest.append(neu)
    _schreiben(projekt, rest)
    return neu


@_gesperrt
def zusammenfuehren(projekt: str, von: str, nach: str) -> dict:
    """Zwei Bausteine zu einem machen. `von` geht auf, `nach` bleibt.

    Passiert oefter als gedacht: das Sprachmodell schlaegt "Frau" vor, spaeter
    heisst dieselbe Figur "Nora", und nun stehen zwei Personen im Katalog, die
    eine Person sind. Leere Felder des bleibenden Bausteins werden aus dem
    aufgehenden gefuellt -- sonst ginge beim Verschmelzen etwas verloren.
    """
    daten = liste(projekt)
    a = next((b for b in daten if b.get("id") == von), None)
    b = next((x for x in daten if x.get("id") == nach), None)
    if not a or not b or von == nach:
        return {}
    ziel = dict(b)
    for feld in ("prompt", "gesicht", "kleidung", "haut", "wesen", "bild",
                 "bild_augen", "stil"):
        if not (ziel.get(feld) or "").strip():
            ziel[feld] = a.get(feld) or ""
    # Vorgaben zu Luecken, die der bleibende Prompt hat, aber nicht kennt.
    werte = dict(a.get("variablen") or {})
    werte.update({k: v for k, v in (ziel.get("variablen") or {}).items() if v})
    ziel["variablen"] = werte
    rest = [x for x in daten if x.get("id") not in (von, nach)]
    rest.append(ziel)
    _schreiben(projekt, rest)
    return {"ziel": ziel, "alter_name": a.get("name") or "",
            "neuer_name": ziel.get("name") or ""}


@_gesperrt
def loeschen(projekt: str, kennung: str) -> bool:
    daten = liste(projekt)
    rest = [b for b in daten if b.get("id") != kennung]
    if len(rest) == len(daten):
        return False
    _schreiben(projekt, rest)
    return True


@_gesperrt
def bild_setzen(projekt: str, kennung: str, datei: str,
                feld: str = "bild") -> bool:
    """Haengt das erzeugte Bild an den Baustein. Ruft der Auftragslauf auf,
    wenn ein Auftrag mit einer Bausteinkennung fertig geworden ist.

    `feld` ist "bild" fuer das Musterbild und "bild_augen" fuer die
    Grossaufnahme -- eine Person hat beides, und beides soll bleiben.
    """
    if feld not in ("bild", "bild_augen"):
        return False
    daten = liste(projekt)
    for b in daten:
        if b.get("id") == kennung:
            b[feld] = datei
            _schreiben(projekt, daten)
            return True
    return False


def vorlage(teile: list[dict]) -> str:
    """Dieselbe Mischung, aber mit offenen Luecken.

    Was beim Zusammenstellen als Szene gespeichert wird, soll wieder Luecken
    haben -- sonst liesse sich die Person darin nie wieder umziehen.
    """
    reihung = {"person": 0, "gegenstand": 1, "ort": 2, "szene": 3}
    geordnet = sorted(teile, key=lambda b: reihung.get(b.get("art"), 9))
    stuecke = [(b.get("prompt") or "").strip().rstrip(".") for b in geordnet]
    stuecke = [t for t in stuecke if t]
    return ", ".join([stuecke[0]] + [_klein(t) for t in stuecke[1:]]) if stuecke else ""


def ohne_leere_luecken(prompt: str, werte: dict) -> tuple[str, dict]:
    """Luecken ohne Vorgabe aus dem Prompt herausnehmen.

    Das Sprachmodell setzt manchmal eine Luecke und liefert nichts dazu --
    "a cube with a {blue} glow" mit leerem Wert. Fuer einen Baustein, den
    jemand von Hand angelegt hat, mag das angehen; fuer einen automatisch
    vorgeschlagenen ist es eine Falle, die erst im Bild auffaellt.
    """
    leer = [k for k, v in (werte or {}).items() if not str(v or "").strip()]
    if not leer:
        return prompt, dict(werte or {})
    # einsetzen() raeumt Bindewort und Satzzeichen gleich mit weg.
    sauber = einsetzen(prompt, {k: "" for k in leer})
    return sauber, {k: v for k, v in werte.items() if k not in leer}


def zusammensetzen(teile: list[dict], werte: dict | None = None) -> str:
    """Person, Ort und Gegenstand zu einem Prompt verbinden.

    Die Reihenfolge ist Person, Gegenstand, Ort -- erst wer, dann womit, dann
    wo. Das Modell haengt die Bildkomposition am ersten Satzglied auf, und ein
    Ort am Anfang draengt die Person an den Rand.
    """
    werte = werte or {}
    reihung = {"person": 0, "gegenstand": 1, "ort": 2, "szene": 3}
    geordnet = sorted(teile, key=lambda b: reihung.get(b.get("art"), 9))
    # Eine Person kommt angezogen: die Vorzugskleidung steht seit der Trennung
    # in einem eigenen Feld, und ohne sie erfindet das Modell eine.
    stuecke = [person_text(b, werte) if b.get("art") == "person"
               else einsetzen(b.get("prompt") or "", werte) for b in geordnet]
    stuecke = [s.rstrip(".") for s in stuecke if s]
    return ", ".join([stuecke[0]] + [_klein(s) for s in stuecke[1:]]) if stuecke else ""


# Das Bild zu einem Baustein ist ein Musterbild, keine Szene: es zeigt, wen
# oder was man spaeter einsetzt. Deshalb ganz und vor nichts -- ein Baustein,
# der halb hinter einem Tisch steht, taugt weder zum Wiedererkennen noch als
# Vorlage fuer ein Folgebild.
FREISTELLEN = {
    "person": ("full body from head to toe, the whole figure inside the frame "
               "with room above and below, standing upright and facing the "
               "camera, on a plain seamless neutral grey background, even "
               "studio lighting, no room, no furniture, no scenery, no props"),
    "gegenstand": ("the entire object inside the frame, seen at a slight "
                   "angle, on a plain seamless neutral grey background, even "
                   "studio lighting, no surroundings, no hands, no props"),
}


def eigener_stil(b: dict) -> str:
    """Der Stil, den dieser Baustein selbst mitbringt -- oder leer.

    Frueher galt er nur fuers Musterbild. Jetzt haengt er an jeder
    Verwendung: so laesst sich ein Widerspruch bauen -- eine
    fotorealistische Figur in einer gezeichneten Szene, ein gemalter
    Gegenstand in einem Foto. Wer das nicht will, laesst das Feld leer;
    dann gilt der Stil der Geschichte wie bisher.
    """
    eintrag = STYLES.get((b or {}).get("stil") or "")
    if not eintrag:
        return ""
    text = eintrag[1]
    if b["stil"] in GEZEICHNET:
        text += f" {NICHT_FOTO}"
    return text


def mit_stil(prompt: str, stil: str) -> str:
    """Den Stil an einen fertigen Prompt haengen."""
    eintrag = STYLES.get(stil or "")
    prompt = (prompt or "").strip().rstrip(".")
    if not eintrag or not prompt:
        return prompt
    text = f"{prompt}, {eintrag[1]}"
    if stil in GEZEICHNET:
        text += f" {NICHT_FOTO}"
    return text


def augen_prompt(b: dict, werte: dict | None = None) -> str:
    """Die Grossaufnahme der Augen zu einer Person.

    Nimmt allein die Gesichtsbeschreibung -- eine Hose im Prompt zoege die
    Kamera wieder zurueck -- und setzt die erprobte Makro-Formulierung davor.
    """
    if b.get("art") != "person":
        return ""
    gesicht = person_text(b, werte, nur_gesicht=True).strip().rstrip(".")
    if not gesicht:
        return ""
    e = EINSTELLUNGEN["augen"]
    anordnung = e["text"]
    for name, wert in (e.get("vorgabe") or {}).items():
        anordnung = anordnung.replace("{" + name + "}", wert)
    return f"{anordnung.rstrip('. ')}. {gesicht}."


def freigestellt(prompt: str, art: str) -> str:
    """Den Prompt eines Musterbildes vor einen neutralen Hintergrund stellen.

    Nur Personen und Gegenstaende. Ein Ort *ist* der Hintergrund -- ihn
    freizustellen ergibt ein leeres Bild.
    """
    zusatz = FREISTELLEN.get(art)
    prompt = (prompt or "").strip().rstrip(".")
    if not zusatz or not prompt:
        return prompt
    return f"{prompt}, {zusatz}"


# --- Katalog ueber alle Projekte -----------------------------------------
def katalog() -> list[dict]:
    """Alle Bausteine aller Projekte, jeder mit seiner Herkunft.

    Die Bibliothek wird mit der Zeit groesser als ein Projekt: wer eine Person
    einmal beschrieben hat, will sie im naechsten Vorhaben wiedersehen, ohne
    sie neu zu bauen.
    """
    raus = []
    for projekt in projekte.liste():
        for b in liste(projekt["key"]):
            raus.append({**b, "projekt": projekt["key"],
                         "projektname": projekt["label"]})
    return raus


def kopieren(von: str, nach: str, kennung: str) -> dict | None:
    """Einen Baustein in ein anderes Projekt uebernehmen.

    Das Bild wandert mit: es liegt im Bildordner des Ursprungsprojekts, und
    ein Verweis dorthin waere nach dem Loeschen jenes Projekts tot. Lieber
    eine Kopie, die zum neuen Projekt gehoert.
    """
    if von == nach:
        return None
    quelle = next((b for b in liste(von) if b.get("id") == kennung), None)
    if not quelle:
        return None

    def mitnehmen(datei: str) -> str:
        """Kopiert eine Bilddatei ins Zielprojekt; leer, wenn sie fehlt."""
        if not datei:
            return ""
        herkunft = os.path.join(projekte.bilder(von), os.path.basename(datei))
        ziel = os.path.join(projekte.bilder(nach), os.path.basename(datei))
        if not os.path.isfile(herkunft):
            return ""                     # Bild ist weg, Baustein bleibt
        if not os.path.isfile(ziel):
            shutil.copy2(herkunft, ziel)
        return datei

    # Alle Felder, auch Gesicht, Kleidung, Posen usw.: sonst ist die Kopie
    # eine halbe Person. Ohne Kennung: das Ziel vergibt eine eigene, sonst
    # kollidierte sie mit einem gleich benannten Baustein, der dort liegt.
    neu = {k: v for k, v in quelle.items() if k != "id"}
    neu["bild"] = mitnehmen(quelle.get("bild") or "")
    neu["bild_augen"] = mitnehmen(quelle.get("bild_augen") or "")
    for feld in BILDFELDER:
        eintraege = []
        for e in _bildliste(quelle.get(feld)):
            if mitnehmen(e["datei"]):
                eintraege.append(e)
        neu[feld] = eintraege
    return speichern(nach, neu)



def _erster_satz(text: str, hoechstens: int = 170) -> str:
    """Der erste Satz, hoechstens so lang. Der Rest faellt weg.

    Gebraucht, wenn mehrere Personen in einem Bild stehen: drei volle
    Beschreibungen mit je drei Kleidungssaetzen ergaben einen Prompt von
    zweitausend Zeichen, in dem sich alles widersprach.
    """
    text = (text or "").strip()
    for trenner in (". ", "; "):
        if trenner in text[:hoechstens + 40]:
            text = text.split(trenner, 1)[0]
            break
    if len(text) > hoechstens:
        # An der Wortgrenze abschneiden, nicht mitten im Wort: "covering the
        # arms up to just be" stand so im Prompt.
        schnitt = text.rfind(" ", 0, hoechstens)
        text = text[:schnitt if schnitt > hoechstens // 2 else hoechstens]
    return text.rstrip(" ,.;-")


def person_text(b: dict, werte: dict | None = None, nur_gesicht: bool = False,
                kleidung: str = "", kurz: bool = False,
                ohne_stil: bool = False) -> str:
    """Die Beschreibung einer Person fuer einen Prompt.

    `nur_gesicht` nimmt die Gesichtsbeschreibung allein -- eine Makro-
    Grossaufnahme braucht keine Hose. `kleidung` ersetzt die bevorzugte
    Kleidung, wenn die Szene eine andere verlangt. `kurz` nimmt von jedem
    Stueck nur den ersten Satz: sobald mehrere Personen im Bild stehen,
    zaehlt, dass man sie unterscheiden kann, nicht jede Falte. `ohne_stil`
    laesst den eigenen Stil weg: tragen mehrere Bausteine denselben, steht er
    einmal fuer das ganze Bild statt einmal je Figur.
    """
    # Der Hautton steht in beiden Faellen dabei -- das ist der ganze Zweck
    # des eigenen Feldes: er kann nicht mehr auseinanderlaufen.
    haut = _klein((b.get("haut") or "").strip().rstrip("."))
    # Was die Figur ist, steht vorn: es bestimmt, wie Haut, Augen und
    # Gesicht ueberhaupt aussehen. Ein Androide mit "warm brown skin" hat
    # synthetische braune Haut, kein menschliches Gesicht mit Farbe darauf.
    wesen = (WESEN.get(b.get("wesen") or "") or ("", ""))[1]
    # Steht der Hautton im eigenen Feld, gehoert er nur dorthin. Aus Koerper
    # und Gesicht faellt jede Haut-, Haar- und Augenfarbe heraus -- sonst
    # steht sie zweimal da und widerspricht sich frueher oder spaeter.
    farben_weg = bool(haut)
    if nur_gesicht and (b.get("gesicht") or "").strip():
        gesicht = einsetzen(b["gesicht"], werte).rstrip(".")
        if farben_weg:
            gesicht = ohne_farben(gesicht).rstrip(" .")
        eigen = "" if ohne_stil else _klein(eigener_stil(b))
        return ", ".join(t for t in (wesen, gesicht, haut, eigen) if t)
    stuecke = [t for t in (wesen,) if t]
    allgemein = einsetzen(b.get("prompt") or "", werte).rstrip(".")
    if farben_weg:
        # Nach dem Streichen kann ein Satzpunkt am Ende freiliegen -- die
        # Kleidung haengt sich sonst hinter "… shiny hair., " an.
        allgemein = ohne_farben(allgemein).rstrip(" .")
    stuecke.append(_erster_satz(allgemein) if kurz else allgemein)
    stuecke = [s for s in stuecke if s]
    if wesen and len(stuecke) > 1:
        stuecke[1] = _klein(stuecke[1])
    if haut:
        stuecke.append(_erster_satz(haut, 90) if kurz else haut)
    if not nur_gesicht:
        was = (kleidung or b.get("kleidung") or "").strip()
        if was:
            # Die Kleidung haengt mitten im Satz -- ein grosses "Worn wool
            # coat" dort liest sich wie ein neuer Anfang.
            was = _klein(einsetzen(was, werte).rstrip("."))
            if not _steckt_drin(was, allgemein):
                stuecke.append(_erster_satz(was, 120) if kurz else was)
    # Der eigene Stil steht dicht bei der Figur, nicht am Satzende: dort
    # bezieht ihn das Modell auf sie und nicht auf das ganze Bild.
    eigen = "" if ohne_stil else eigener_stil(b)
    if eigen:
        stuecke.append(_klein(eigen))
    return ", ".join(t for t in stuecke if t)


# Farbwoerter, die vor Haut, Haar oder Augen stehen koennen. Keine
# Wissenschaft -- die Handvoll, die in Bildprompts vorkommt.
FARBWORT = ("black", "white", "brown", "blue", "green", "grey", "gray",
            "hazel", "amber", "red", "ginger", "blonde", "blond", "auburn",
            "silver", "golden", "dark", "light", "pale", "fair", "olive",
            "tan", "tanned", "ebony", "deep", "warm", "cool", "bronze",
            "copper", "chestnut", "platinum", "jet-black", "snow-white")
_FARBEN = "|".join(sorted(FARBWORT, key=len, reverse=True))
# Das Wort darf nicht Teil eines Bindestrichworts sein: "skin-tight" ist
# Kleidung, "hairband" ein Gegenstand.
_NOMEN = r"(skin|hair|eyes|eye|complexion)(?![-\w])"
# Ein Beiwort unmittelbar vor der Farbe gehoert mit dazu: "lawless deep
# black skin" laesst sonst ein "lawless" ohne Hauptwort zurueck.
_BEIWORT = r"(?:\b(?!and\b|with\b|a\b|an\b|the\b|her\b|his\b)\w+\s+)?"
# "deep black skin with a radiant, oily glow" -- der Zusatz gehoert zur Haut
# und faellt mit, auch wenn ein Komma darin steht. Deshalb laeuft dieser
# Durchgang ueber den ganzen Text, nicht ueber die Satzglieder.
_MIT_ZUSATZ = re.compile(
    rf"{_BEIWORT}(?:(?:{_FARBEN})(?:-(?:{_FARBEN}))?\s+){{1,3}}{_NOMEN}"
    rf"\s+with\s+[^;.]{{0,60}}(?=\s*(?:;|\.|$)|,\s*(?:and\s+)?\w+\s+\w)", re.I)
# "Her eyes are a rare, piercing pale ice-blue" -- die Farbe steht hinten.
_NACHGESTELLT = re.compile(
    rf"\b(?:her|his|their|the)\s+{_NOMEN}\s+(?:is|are)\s+[^;.]{{0,70}}"
    rf"(?=\s*(?:;|\.|$))", re.I)
_FARBIG = re.compile(
    rf"\b(?:(?:{_FARBEN})(?:-(?:{_FARBEN}))?\s+){{1,3}}{_NOMEN}", re.I)
# "skin-tight" ist Kleidung, keine Hautfarbe.
_KEIN_TREFFER = re.compile(r"skin-tight|hair\s*band|hairband", re.I)


def ohne_farben(text: str) -> str:
    """Haut-, Haar- und Augenfarbe aus einem Text streichen.

    Sie stehen im eigenen Feld und gelten dort fuer Ganzbild und
    Grossaufnahme zugleich. Ein zweites Mal im allgemeinen Prompt oder im
    Gesicht macht sie nicht deutlicher, sondern widerspricht sich
    frueher oder spaeter -- und laenger wird der Prompt auch.

    Was sonst in dem Satzglied steht, bleibt: aus "glossy black hair pulled
    back into a high ponytail" wird "glossy hair pulled back into a high
    ponytail", nicht ein Loch.
    """
    if not (text or "").strip():
        return text
    # Erst die langen Formen ueber den ganzen Text, denn ihr Zusatz darf
    # Kommas enthalten.
    text = _MIT_ZUSATZ.sub("", text)
    text = _NACHGESTELLT.sub("", text)
    glieder = []
    for glied in re.split(r"([,;])", text):
        if glied in (",", ";"):
            glieder.append(glied)
            continue
        if _KEIN_TREFFER.search(glied):
            glieder.append(glied)
            continue
        sauber = _FARBIG.sub(lambda m: m.group(1), glied)
        # Steht das Wort danach nackt da -- "with skin", "and hair" oder
        # allein --, war das Glied nichts als Farbe und faellt ganz.
        sauber = re.sub(r"\b(?:with|and|has|have)\s+(?:a\s+)?"
                        r"(?:skin|hair|eyes|eye|complexion)\s*(?=[,;.]|$)",
                        "", sauber, flags=re.I)
        if re.fullmatch(r"\s*(?:and\s+)?(?:a\s+)?"
                        r"(?:skin|hair|eyes|eye|complexion)\s*",
                        sauber, re.I):
            sauber = ""
        glieder.append(sauber)
    zusammen = "".join(glieder)
    # Aufraeumen: doppelte Kommas, haengende Bindewoerter, Reste am Rand.
    # "with skin and long hair" -- das nackte Wort mitten im Satzglied.
    zusammen = re.sub(r"\b(with|and)\s+(?:skin|complexion)\s+and\s+",
                      r"\1 ", zusammen, flags=re.I)
    zusammen = re.sub(r"\b(?:and|with)\s*(?=[,;])", "", zusammen)
    zusammen = re.sub(r"\.\s*(?=,)", "", zusammen)
    zusammen = re.sub(r"\s*,\s*(?=,)", "", zusammen)
    zusammen = re.sub(r",\s*(?:and|with)\s*(?=[,;]|$)", "", zusammen)
    zusammen = re.sub(r"\s+(?:and|with)\s*$", "", zusammen)
    zusammen = re.sub(r"\s+([,;.])", r"\1", zusammen)
    zusammen = re.sub(r"\s{2,}", " ", zusammen)
    return zusammen.strip().strip(",;").strip()


def _steckt_drin(teil: str, ganz: str) -> bool:
    """Steht `teil` schon so aehnlich in `ganz`?

    Verglichen wird ueber die Woerter, nicht Zeichen fuer Zeichen: "black
    hair" und "black hair." sollen als dasselbe gelten. Ab drei Vierteln
    Deckung gilt es als schon gesagt.
    """
    worte = lambda t: {w for w in re.findall(r"[a-zA-ZäöüÄÖÜß]{3,}", (t or "").lower())}
    a, b = worte(teil), worte(ganz)
    return bool(a) and len(a & b) >= 0.75 * len(a)
