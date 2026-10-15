"""Freitext verstehen: aus einem deutschen Satz Prompt und Reglerstellung.

Das Sprachmodell darf nur Werte nennen, die es wirklich gibt -- der Systemtext
wird deshalb aus den echten Katalogen gebaut, und `sanitise` prueft trotzdem
jeden Wert nach. Ein 4B-Modell haelt sich nicht immer an Vorgaben.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kataloge import CAMERAS, EFFECTS, FORMS, LIGHTS, STYLES, VIEWS, overrides  # noqa: E402

from .ollama import MODEL, _json, antwort, rufen  # noqa: E402

ASPECTS = ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"]
RESOLUTIONS = [1024, 1536, 2048]
SWEEPS = ["", "view", "style", "light", "camera", "random"]
MODES = ["t2i", "edit", "gruppe", "person"]


def _names(table):
    return ", ".join(table)



def system_prompt(has_images: int) -> str:
    """Der Systemprompt wird aus den echten Tabellen gebaut, damit er nicht
    veraltet, sobald in den Katalogen etwas dazukommt."""
    situation = (
        f"Der Benutzer hat {has_images} Referenzbild(er) hochgeladen."
        if has_images else
        "Der Benutzer hat kein Referenzbild hochgeladen, es wird also neu erzeugt."
    )
    return f"""Du stellst eine lokale Bildgenerierung ein. {situation}

Das Gespräch geht weiter: Sagt der Benutzer danach "und noch ein Hut dazu"
oder "mach es hochkant", dann ändere die vorige Einstellung an dieser einen
Stelle und gib sie sonst unverändert zurück. Fang nicht von vorn an.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. Kein Text davor oder danach.

Feld "prompt": die Bildbeschreibung auf ENGLISCH, ausformuliert und bildhaft.
Das Bildmodell versteht Englisch deutlich besser. Uebersetze also, was der
Benutzer will, und ergaenze es um anschauliche Details -- aber erfinde nichts,
was seiner Absicht widerspricht.

Die uebrigen Felder nur setzen, wenn der Benutzer es sagt oder eindeutig meint.
Sonst weglassen. Erlaubte Werte, nichts anderes:

"aspect": {_names(ASPECTS)}   (quer/breit = 16:9 oder 3:2, hochkant = 3:4 oder 9:16)
"count": ganze Zahl 1 bis 20   (wie viele SEPARATE Bilder erzeugt werden.
   Der "prompt" beschreibt immer nur EIN Bild. "zwei Bilder von einem Fahrrad"
   heisst count=2 und ein Fahrrad im Prompt, nicht zwei Fahrraeder.)
"base": {_names(str(r) for r in RESOLUTIONS)}   (Aufloesung, Vorgabe 1024)
"steps": 1 bis 100   (Vorgabe 40)
"style": {_names(STYLES)}
"light": {_names(LIGHTS)}
"camera": {_names(CAMERAS)}
"view": {_names(VIEWS)}   (Blickrichtung auf eine Person)
"form": {_names(FORMS)}   (Bildsorte, z. B. logo bei "Logo", buchumschlag bei "Buchcover")
"effect": {_names(EFFECTS)}   (Bearbeitung eines vorhandenen Bildes)
"sweep": {_names(s or '(leer)' for s in SWEEPS)}   (Serie variieren: view = einmal um
   die Person herum, camera/style/light = diese Liste durchgehen, random = wuerfeln)
"mode": {_names(MODES)}   (t2i = neu erzeugen, edit = vorhandenes Bild aendern,
   gruppe = mehrere Personen in ein Bild, person = dieselbe Person mehrfach)
"transparent": true bei "freigestellt", "transparent", "ohne Hintergrund"
"note": EIN kurzer deutscher Satz, was du verstanden hast.

Der Normalfall ist ein knapper Wunsch ohne Zusatzangaben. Dann stehen nur
"prompt" und "note" im JSON -- kein Stil, kein Licht, keine Kamera, keine
Vorlage. Das erste Beispiel zeigt das.

Jede Beispielantwort ist reines JSON, ohne Kommentar davor oder danach.

Beispiele:
"ein Apfel auf einem Tisch" ->
{{"prompt":"a single ripe red apple resting on a wooden table","note":"Ein Apfel auf einem Tisch."}}
"mach mir 10 Drachen als Zeichentrick, hochkant" ->
{{"prompt":"A friendly dragon with large wings perched on a rock, bold outlines, flat bright colours","count":10,"style":"zeichentrick","aspect":"3:4","note":"10 Zeichentrick-Drachen im Hochformat."}}
"ein Logo fuer eine Baeckerei, freigestellt" ->
{{"prompt":"a family bakery, a wheat sheaf and a bread loaf","form":"logo","transparent":true,"note":"Ein freigestelltes Baeckerei-Logo."}}
"zeig die Person von allen Seiten" ->
{{"prompt":"standing in the same place","mode":"person","sweep":"view","count":10,"note":"Eine Umrundung der Person in 10 Ansichten."}}
"mach aus den beiden ein Gruppenfoto im Park" ->
{{"prompt":"standing together in a sunlit park, smiling","mode":"gruppe","note":"Ein Gruppenfoto der beiden im Park."}}
"zwei Bilder von einem gelben Fahrrad im Wald" ->
{{"prompt":"a yellow bicycle leaning against a tree in a misty forest","count":2,"note":"Zwei Varianten eines gelben Fahrrads im Wald."}}
"faerb das alte Foto ein" ->
{{"prompt":"","effect":"colorize","mode":"edit","note":"Das alte Foto wird eingefaerbt."}}

"transparent" nur bei ausdruecklichem Wunsch nach Freistellung. Im Zweifel
lieber ein Feld weglassen als raten."""


def ask(text: str, has_images: int = 0, model: str | None = None,
        verlauf: list[dict] | None = None) -> dict:
    """Fragt Ollama. Wirft RuntimeError mit einer lesbaren Meldung.

    `verlauf` sind die bisherigen Wechsel des Gespraechs, als Wechselfolge
    von Benutzer- und Modellbeitraegen. Damit versteht "und jetzt noch einen
    Hut dazu", worauf es sich bezieht -- ohne Verlauf faengt jeder Satz bei
    null an.
    """
    body = {
        "model": model or MODEL,
        # Nur "json", kein JSON-Schema: ein Schema erzwingt zwar gueltige
        # Syntax, aber die grammatikgebundene Ausgabe kostet hier spuerbar
        # Verstaendnis -- gemessen 14 statt 22 Treffern, weil ausdrueckliche
        # Wuensche wie "quer" oder "freigestellt" unter den Tisch fielen.
        # Geprueft wird die Antwort ohnehin in sanitise().
        "format": "json",
        "stream": False,
        "think": False,          # Qwen3 denkt sonst laut, das kostet nur Zeit
        "keep_alive": 0,         # sofort entladen -- die GPU braucht gleich das Bildmodell
        "options": {"temperature": 0.2, "num_predict": 700},
        "messages": [
            {"role": "system", "content": system_prompt(has_images)},
            *(verlauf or []),
            {"role": "user", "content": text},
        ],
    }
    # Ueber rufen(): dort entscheidet sich, ob Ollama oder die Cloud
    # antwortet, und die Fehler kommen schon als Klartext.
    answer = rufen(body, timeout=180)
    try:
        return _json(answer)
    except json.JSONDecodeError:
        raise RuntimeError("Das Sprachmodell hat kein verwertbares JSON geliefert.")


def _clamp(value, low, high, fallback):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def sanitise(raw: dict, has_images: int) -> dict:
    """Nur bekannte Felder mit bekannten Werten. Alles andere fliegt raus."""
    if not isinstance(raw, dict):
        raise RuntimeError("Unerwartete Antwort des Sprachmodells.")

    def pick(key, table):
        value = raw.get(key)
        return value if isinstance(value, str) and value in table else ""

    out = {
        "prompt": str(raw.get("prompt") or "").strip(),
        "aspect": raw.get("aspect") if raw.get("aspect") in ASPECTS else "1:1",
        "base": raw.get("base") if raw.get("base") in RESOLUTIONS else 1024,
        "count": _clamp(raw.get("count", 1), 1, 20, 1),
        "steps": _clamp(raw.get("steps", 40), 1, 100, 40),
        "style": pick("style", STYLES),
        "light": pick("light", LIGHTS),
        "camera": pick("camera", CAMERAS),
        "view": pick("view", VIEWS),
        "form": pick("form", FORMS),
        "effect": pick("effect", EFFECTS),
        "sweep": raw.get("sweep") if raw.get("sweep") in SWEEPS else "",
        "transparent": bool(raw.get("transparent")),
        "note": str(raw.get("note") or "").strip()[:200],
    }

    # Effekte, die ein Bild brauchen, sind ohne Referenz sinnlos.
    if out["effect"] and EFFECTS[out["effect"]].get("needs_image") and not has_images:
        out["effect"] = ""

    # Bei einem reinen Effektbefehl ("faerb das ein") traegt die Anweisung des
    # Effekts den Auftrag, eine eigene Bildbeschreibung braucht es dann nicht.
    if not out["prompt"] and not out["effect"] and not out["form"]:
        raise RuntimeError("Das Sprachmodell hat keine Bildbeschreibung geliefert.")

    # Der Modus haengt vor allem daran, wie viele Bilder daliegen -- das weiss
    # der Server sicherer als das Sprachmodell.
    mode = raw.get("mode") if raw.get("mode") in MODES else None
    if not has_images:
        mode = "t2i"
    elif mode in (None, "t2i"):
        mode = "gruppe" if has_images >= 2 else "edit"
    elif mode == "gruppe" and has_images < 2:
        mode = "edit"
    out["mode"] = mode

    # Was der Effekt oder die Vorlage mitbringt, gilt nur fuer Felder, die das
    # Sprachmodell offengelassen hat -- ein ausgesprochener Wunsch geht vor.
    for key in ("effect", "form"):
        source = EFFECTS if key == "effect" else FORMS
        if out[key]:
            for field, value in overrides(source[out[key]]).items():
                if field in out and not out[field] and not raw.get(field):
                    out[field] = value

    # Der Umrundungs-Modus ohne Umrundung waere ein einzelnes Bild von vorn.
    # Wenn das Sprachmodell den Modus erkannt, die Serienart aber vergessen hat,
    # ist die Absicht trotzdem eindeutig.
    if out["mode"] == "person" and not out["sweep"]:
        out["sweep"] = "view"

    # Eine Liste durchzugehen ergibt nur mit genug Bildern Sinn.
    tables = {"view": VIEWS, "style": STYLES, "light": LIGHTS, "camera": CAMERAS}
    if out["sweep"] in tables and out["count"] == 1:
        out["count"] = min(len(tables[out["sweep"]]), 20)

    out["lock_seed"] = out["sweep"] == "view"
    return out


def interpret(text: str, has_images: int = 0, model: str | None = None,
              verlauf: list[dict] | None = None) -> dict:
    return sanitise(ask(text, has_images, model, verlauf), has_images)


# --- Bausteine -----------------------------------------------------------
BAUSTEIN_SYSTEM = {
    "person": """Du schreibst den Bildprompt für eine Person, die immer wieder
verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die ganze Person auf ENGLISCH, ein Satz: ungefähres Alter,
             Statur, Gesicht, Haarfarbe und Frisur. OHNE Kleidung: kein
             Kleidungsstück, kein Schuh, kein Hut, keine Uniform. Nicht
             "a young woman with short hair and a work jacket", sondern
             "a young woman with short hair" -- die Jacke gehört in
             "kleidung" und käme sonst zweimal ins Bild. Nennt die Beschreibung einen Charakterzug --
             schüchtern, streng, herzlich, misstrauisch --, setze ihn als
             sichtbares Merkmal um: Haltung, Blick, Zug um den Mund. "streng"
             wird zu "an upright bearing and a level, unsmiling gaze", nicht
             zu "strict".
"gesicht"    Nur das Gesicht, auf ENGLISCH, ein kurzer Satz: Form, Augen,
             Haut, Mund, Brauen, der Ansatz der Haare. Nichts vom Körper,
             nichts von der Kleidung -- dieser Text steht allein im Bild,
             wenn die Kamera dicht an die Augen geht. Hautton, Haarfarbe
             und Augenfarbe müssen mit "prompt" übereinstimmen, Wort für
             Wort: zwei verschiedene Hauttöne ergeben zwei verschiedene
             Menschen, einen im Ganzbild und einen in der Großaufnahme.
"haut"       Hautton, Augenfarbe und Haarfarbe, auf ENGLISCH, wenige
             Wörter: "warm brown skin, dark brown eyes, black hair". NUR
             hier -- in "prompt" und "gesicht" kommt keine dieser Farben
             noch einmal vor. Der Grund: dieser Text steht spaeter in
             beiden Bildern, im Ganzbild und in der Grossaufnahme. Stuenden
             sie zweimal, waeren es zwei verschiedene Menschen.
"kleidung"   Was die Person üblicherweise trägt, auf ENGLISCH, ein kurzer
             Satz mit Schuhen. HIER gehört die Kleidung hin, und hier muss
             etwas stehen: benenne wirkliche Kleidungsstücke. Sagt die
             Anfrage nichts dazu, wähle etwas Schlichtes, das zu der Person
             passt. Niemals "none", "no clothing" oder Ähnliches -- das
             stünde sonst als Text im Bild. Eine Szene darf ihn
             überschreiben.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.

Lücken in geschweiften Klammern sind erlaubt, wo etwas von Bild zu Bild
wechseln darf, etwa {haarfarbe}. Höchstens vier, Namen klein und ohne
Umlaute. Kleidung braucht keine Lücke mehr -- dafür ist "kleidung" da.

Nimm ausschließlich, was in der Anfrage steht, und ergänze nur, was daraus
folgt. Aus dieser Anweisung übernimmst du keine einzige Wendung -- kein
Beispielwort, keine Beispielperson.

Die Form, mit Platzhaltern statt Wörtern:
{"prompt": "<Alter und Statur>, <Frisur>, <Haltung oder Blick>",
 "gesicht": "<Gesichtsform> face with <Augenform>, <Mund>, <Brauen>",
 "haut": "<Hautton> skin, <Augenfarbe> eyes, <Haarfarbe> hair",
 "kleidung": "<Kleidungsstück> over <Kleidungsstück>, <Schuhe>",
 "variablen": {}}""",

    "ort": """Du schreibst den Bildprompt für einen Ort, der immer wieder
verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die Beschreibung auf ENGLISCH, ein bis zwei Sätze, beginnend
             mit einer Ortsangabe wie "in", "on" oder "at". Was den Ort
             ausmacht, gehört in den Text, und zwar handfest: Baustoff,
             Größe, Licht, Boden, was an den Wänden ist, was herumsteht.
             "in a workshop" ist zu wenig -- daraus baut das Modell jedes Mal
             eine andere Werkstatt. KEINE Personen darin, auch keine mit
             Namen: wer dort steht, ist ein eigener Baustein und wird
             davorgesetzt. Steht trotzdem eine Person im Ort, erscheint sie
             im Bild zweimal.
             Wechselndes wie Tageszeit oder Wetter setzt du als
             Lücke in geschweifte Klammern, etwa {tageszeit} oder {wetter}.
             Höchstens drei Lücken, Namen klein und ohne Umlaute.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.""",

    "gegenstand": """Du schreibst den Bildprompt für einen Gegenstand, der
immer wieder verwendet werden soll.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"     Die Beschreibung auf ENGLISCH, ein bis zwei Sätze. Form,
             Größe, Material, Oberfläche und Zustand gehören in den Text --
             bei einer Maschine oder einem Gerät auch, woraus sie besteht,
             wie sie bedient wird und ob sie neu, abgenutzt oder beschädigt
             ist. "a machine" ist zu wenig. KEINE Personen darin, auch keine
             mit Namen -- wer ihn hält, ist ein eigener Baustein. Wechselndes wie Farbe oder Zustand
             setzt du als Lücke in geschweifte Klammern, etwa {farbe}.
             Höchstens drei Lücken, Namen klein und ohne Umlaute.
"variablen"  Ein Objekt mit genau einer englischen Vorgabe je Lücke,
             als einzelner Text, nicht als Liste. Fällt dir zu einer
             Lücke keine Vorgabe ein, mach dort keine Lücke.""",
}


# Einzelne Teile einer Person nachschaerfen. Die Felder entstehen zwar schon
# beim "Prompt daraus erzeugen" mit -- aber wer eines davon von Hand
# ueberschreibt, tut das auf Deutsch und will es genauso uebersetzt haben.
TEIL_SYSTEM = {
    "gesicht": """Du schreibst den Bildprompt für das GESICHT einer Person.

Antworte ausschließlich mit JSON: {"text": "…"}.

Eine kurze englische Aufzählung, nur das Gesicht: Form, Augen, Haut, Mund,
Brauen, der Ansatz der Haare. Nennt die Beschreibung der Person einen
Hautton, eine Haarfarbe oder eine Augenfarbe, übernimm genau diese --
zwei verschiedene Hauttöne ergeben zwei verschiedene Menschen. Nichts vom Körper, nichts von der Kleidung,
keine Umgebung -- dieser Text steht allein im Bild, wenn die Kamera dicht an
die Augen geht. Ein Charakterzug wird zu etwas Sichtbarem: "misstrauisch"
zu "narrowed eyes and a set jaw", nicht zu "suspicious".

KEIN vollständiger Satz und KEIN Subjekt: nicht "A man's face has …",
sondern gleich das Gesicht, in der Form
"<shape> face with <eyes>, <skin>, <mouth>" -- die Wörter selbst auf
ENGLISCH.
Der Text wird an die Beschreibung der Person angehängt -- ein zweites
"a man" darin setzt eine zweite Person ins Bild.

Nimm ausschließlich, was in der Anfrage steht. Erfinde keine Merkmale dazu
und übernimm keine aus dieser Anweisung. Die Anfrage ist deutsch, die
Antwort ist englisch -- kein deutsches Wort bleibt stehen.""",

    "haut": """Du schreibst Hautton, Augen- und Haarfarbe einer Person.

Antworte ausschließlich mit JSON: {"text": "…"}.

Wenige englische Wörter in der Form
"<Hautton> skin, <Augenfarbe> eyes, <Haarfarbe> hair". Kein Satz, kein
Subjekt, nichts über Alter, Statur, Frisur oder Kleidung. Die Anfrage ist
deutsch, die Antwort englisch.""",

    "kleidung": """Du schreibst den Bildprompt für die KLEIDUNG einer Person.

Antworte ausschließlich mit JSON: {"text": "…"}.

Eine kurze englische Aufzählung, nur was die Person am Leib trägt, von oben
nach unten und mit Schuhen. Stoff und Schnitt gehören dazu, Farbe auch. Kein
Gesicht, kein Körperbau, keine Umgebung, keine Tätigkeit.

Beginne mit dem ersten Kleidungsstück. KEIN Subjekt, kein vollständiger
Satz, und die Person kommt darin nicht vor: nicht "a woman … wearing …",
sondern gleich die Form
"<garment> over <garment>, <shoes>" -- die Wörter selbst auf ENGLISCH.
Der Text wird an die Beschreibung der Person angehängt -- steht sie ein
zweites Mal darin, setzt das eine zweite Person ins Bild.

Nimm ausschließlich die Kleidungsstücke aus der Anfrage. Erfinde keine dazu
und übernimm keine aus dieser Anweisung. Die Anfrage ist deutsch, die
Antwort ist englisch -- kein deutsches Wort bleibt stehen.""",
}


TEILEN_SYSTEM = """Du zerlegst die Beschreibung einer Person in drei Teile.

Du bekommst einen englischen Bildprompt, in dem alles zusammensteht. Trenne
ihn auf, ohne neu zu formulieren: die Wendungen bleiben, wie sie sind, sie
werden nur verteilt.

Antworte ausschließlich mit JSON und genau diesen Schlüsseln:

"prompt"   Alles zur Person selbst OHNE Kleidung: Alter, Statur, Haare,
           Haltung, Blick.
"gesicht"  Nur das Gesicht: Form, Augen, Haut, Mund, Brauen. Hautton, Haar-
           und Augenfarbe genau so, wie sie in "prompt" stehen -- zwei
           verschiedene Hauttöne ergeben zwei verschiedene Menschen. Steht
           davon nichts im Text, leite es aus Alter, Statur und Haaren ab und
           nenne trotzdem Form, Augen und Haut -- dieser Text steht allein
           im Bild, wenn die Kamera dicht an die Augen geht, und "alert
           expression" allein ergibt dort kein Gesicht.
"haut"     Hautton, Augen- und Haarfarbe, wenige Wörter. Sie stehen
           danach NUR hier, nicht mehr in "prompt" oder "gesicht": der Text
           gilt fürs Ganzbild und für die Großaufnahme zugleich.
"kleidung" Nur was die Person am Leib trägt, mit Schuhen. Steht nichts
           davon im Text, gib "" zurück -- erfinde keine Kleidung.

Alles auf ENGLISCH, ohne Subjekt, ohne vollständigen Satz. Nichts geht
verloren: was weder Gesicht noch Kleidung ist, bleibt in "prompt"."""


def person_teilen(prompt: str, model: str | None = None) -> dict:
    """Einen alten Personenprompt in allgemein, Gesicht und Kleidung trennen.

    Fuer Bausteine, die vor der Trennung entstanden sind. Neu geschrieben
    wird nichts -- eine Person, die sich bewaehrt hat, soll gleich bleiben.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {}
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 500},
        "messages": [{"role": "system", "content": TEILEN_SYSTEM},
                     {"role": "user", "content": prompt}],
    })
    if not isinstance(roh, dict):
        return {}
    raus = {k: _sinnvoll(_ohne_subjekt(
                str(roh.get(k) or "").strip()[:400].rstrip(".")))
            for k in ("prompt", "gesicht", "kleidung", "haut")}
    # Ohne allgemeinen Teil waere der Baustein hinterher schlechter als
    # vorher. Dann lieber nichts anruehren.
    return raus if raus["prompt"] else {}


def teil_prompt(feld: str, text: str, person: str = "",
                model: str | None = None) -> str:
    """Aus einer deutschen Angabe den Prompt fuer Gesicht oder Kleidung.

    `person` ist der allgemeine Prompt und dient als Umfeld: eine Jacke fuer
    eine Bergsteigerin sieht anders aus als eine fuer eine Beamtin.
    """
    system = TEIL_SYSTEM.get(feld)
    if not system or not (text or "").strip():
        return ""
    if person.strip():
        system += f"\n\nDie Person: {person.strip()}"
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 300},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
    })
    if not isinstance(roh, dict):
        return ""
    fertig = _ohne_subjekt(str(roh.get("text") or "").strip()[:400].rstrip("."))
    # Trotz aller Ansage kommt manchmal ein ganzer Satz zurueck. Das Subjekt
    # davor faellt weg, sonst steht eine zweite Person im Prompt.
    if feld == "kleidung":
        # "... wearing a red coat" -> "a red coat". Alles vor dem Tragen ist
        # die Person, und die steht schon im allgemeinen Prompt.
        fertig = re.sub(r"^.{0,90}?\b(?:wearing|wears|dressed in|clad in)\s+",
                        "", fertig, flags=re.I)
    return _sinnvoll(_ohne_subjekt(fertig))


def _ohne_subjekt(text: str) -> str:
    """"Her expression is alert" -> "alert". Ein zweites Subjekt im Prompt
    setzt neben die Person eine weitere ins Bild."""
    text = re.sub(r"^(?:an?|the|her|his|their)\s+\w+(?:'s)?\s+(?:face\s+)?"
                  r"(?:is|has|are|have)\s+", "", text or "", flags=re.I)
    text = re.sub(r"^(?:she|he|they)\s+(?:is|has|wears|are|have)\s+", "",
                  text, flags=re.I)
    return text[:1].lower() + text[1:] if text else ""


MAX_ZEILEN = 60

# Wie viele Szenen oder Namen in einen Aufruf gehen. Gemessen: bei dreissig
# Szenen auf einmal brach die Antwort mittendrin ab, und die hinteren fehlten
# -- stillschweigend, denn ein abgeschnittenes JSON sieht wie ein kuerzeres aus.
JE_AUFRUF = 8

RATEN_SYSTEM = """Du ordnest Namen aus einer Geschichte ein.

Du bekommst das Inhaltsverzeichnis einer Bilderfolge und eine Liste von
Namen, die darin mit einem Schrägstrich erwähnt werden. Zu jedem Namen sagst
du, was er ist und wie er aussehen könnte.

Antworte ausschließlich mit JSON: {"teile": [ … ]}. Jeder Eintrag hat genau
diese Schlüssel:

"name"         Der Name, unverändert aus der Liste.
"art"          "person", "ort", "gegenstand" -- oder "unklar". Was in der
               Geschichte handelt, ist eine Person; wo sie sich aufhält, ein
               Ort; was sie benutzt oder trägt, ein Gegenstand. Lässt der
               Name zusammen mit dem Inhaltsverzeichnis nicht erkennen, was
               es ist, schreibe "unklar" -- rate nicht. Ein Gegenstand, der
               als Person angelegt wird, bekommt ein Gesicht und steht als
               Mensch im Bild.
"beschreibung" Ein Satz auf DEUTSCH, wie das aussieht. Halte dich an das,
               was das Inhaltsverzeichnis hergibt, und erfinde den Rest
               plausibel dazu -- es ist ein Vorschlag, den der Benutzer
               danach ändert. Keine Handlung, nur Aussehen. Bei einem Ort
               oder Gegenstand kommt keine Person darin vor, auch nicht
               dem Namen nach: jede Person ist ein eigener Eintrag."""


def bausteine_raten(namen: list[str], umfeld: str = "",
                    model: str | None = None) -> list[dict]:
    """Zu unbekannten /Namen Art und eine deutsche Beschreibung vorschlagen.

    Ein Aufruf fuer alle Namen: sie gehoeren zu derselben Geschichte, und
    einzeln gefragt erfindet das Modell zu jedem eine eigene Welt.
    """
    namen = [n for n in namen if (n or "").strip()][:40]
    if not namen:
        return []
    # Wie bei den Empfehlungen: viele Namen in einem Aufruf brechen die
    # Antwort ab, und die hinteren fehlen dann.
    if len(namen) > JE_AUFRUF:
        raus = []
        for anfang in range(0, len(namen), JE_AUFRUF):
            raus += bausteine_raten(namen[anfang:anfang + JE_AUFRUF],
                                    umfeld, model)
        return raus
    frage = "Namen: " + ", ".join(namen)
    if umfeld.strip():
        frage = f"Inhaltsverzeichnis:\n{umfeld.strip()[:2000]}\n\n{frage}"
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.5,
                    "num_predict": 300 + 150 * len(namen)},
        "messages": [{"role": "system", "content": RATEN_SYSTEM},
                     {"role": "user", "content": frage}],
    }, timeout=300)
    gegeben = roh.get("teile") if isinstance(roh, dict) else None
    nach_name = {}
    for e in gegeben or []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip()
        art = str(e.get("art") or "").strip().lower()
        if name:
            nach_name[name.lower()] = {
                # "unklar" und alles Unbekannte werden zu leer -- der
                # Aufrufer legt dann nichts an, statt das Falsche.
                "art": art if art in ("person", "ort", "gegenstand") else "",
                "beschreibung": str(e.get("beschreibung") or "").strip()[:400]}
    # Jeder gefragte Name kommt zurueck, auch wenn das Modell ihn ausliess --
    # sonst fehlt am Ende ein Baustein, ohne dass jemand es merkt.
    raus = []
    for n in namen:
        e = nach_name.get(n.lower()) or {}
        # Kein Rueckfall auf "person": ein Gegenstand, der als Person
        # angelegt wird, bekommt Gesicht und Kleidung und steht als Mensch
        # im Bild. Lieber leer lassen -- der Aufrufer sieht es dann.
        raus.append({"name": n, "art": e.get("art") or "",
                     "beschreibung": e.get("beschreibung") or ""})
    return raus


def baustein_prompt(text: str, art: str = "person",
                    model: str | None = None) -> dict:
    """Aus einer deutschen Beschreibung einen Baustein-Prompt mit Luecken.

    Die Luecken sind der eigentliche Zweck: dieselbe Person soll spaeter vier
    Jacken durchprobieren koennen, ohne dass man den Prompt neu schreibt. Was
    zurueckkommt, wird nicht blind geglaubt -- die Luecken im Text sind
    massgeblich, nicht die Liste des Modells.
    """
    system = BAUSTEIN_SYSTEM.get(art) or BAUSTEIN_SYSTEM["person"]
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": text}],
    })
    if not isinstance(roh, dict):
        return {"prompt": "", "variablen": {}}
    prompt = str(roh.get("prompt") or "").strip()[:600].rstrip(".")
    gegeben = roh.get("variablen") if isinstance(roh.get("variablen"), dict) else {}
    # Nur Luecken, die wirklich im Text stehen.
    offen = re.findall(r"\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}", prompt)

    def vorgabe(wert):
        # Mal kommt eine Liste von Moeglichkeiten statt einer Vorgabe zurueck.
        # Dann ist die erste gemeint; stumpf in Text verwandelt staende sonst
        # "['morning', 'afternoon']" im Prompt.
        if isinstance(wert, list):
            wert = wert[0] if wert else ""
        return str(wert or "").strip()[:120]

    erg = {"prompt": prompt,
           "variablen": {k: vorgabe(gegeben.get(k)) for k in dict.fromkeys(offen)}}
    # Nur bei Personen: das Gesicht fuer die Grossaufnahme, die Kleidung zum
    # Ueberschreiben durch die Szene. Fehlen sie, bleiben die Felder leer --
    # dann gilt eben der allgemeine Prompt.
    if art == "person":
        for feld in ("gesicht", "kleidung", "haut"):
            erg[feld] = _sinnvoll(str(roh.get(feld) or "").strip()[:400])
    return erg


# Was das Modell schreibt, wenn ihm nichts einfaellt. Als Prompt waere es
# schlimmer als ein leeres Feld: "no clothing" malt das Bildmodell mit.
LEERFLOSKEL = ("none", "no clothing", "nothing", "n/a", "not specified",
               "unspecified", "unknown", "keine", "keine angabe", "nichts",
               "no description", "no face", "-")


def _sinnvoll(text: str) -> str:
    """Leerfloskeln zu einem leeren Feld machen."""
    sauber = text.strip().strip(".").strip()
    return "" if sauber.lower() in LEERFLOSKEL else text


LUECKEN_SYSTEM = """Du füllst eine Lücke in einem Bildprompt mit Vorschlägen.

Antworte ausschließlich mit JSON: {"werte": ["…", "…"]}.

Jeder Wert ist ein kurzes englisches Satzstück, das genau an die Stelle der
Lücke passt — so, dass der Satz danach richtig klingt. Keine Nummern, keine
Erklärungen, keine Wiederholungen. Die Vorschläge sollen sich deutlich
voneinander unterscheiden, nicht nur in der Farbe."""


def luecken_vorschlaege(name: str, umfeld: str, anzahl: int = 10,
                        model: str | None = None) -> list[str]:
    """Vorschlaege fuer eine Luecke -- "hose" ergibt zehn verschiedene Hosen.

    `umfeld` ist der Prompt, in dem die Luecke steht. Ohne ihn schlaegt das
    Modell Hosen vor, die nicht zur Person passen.
    """
    anzahl = max(1, min(int(anzahl or 10), 30))
    roh = antwort({
        "model": model or MODEL,
        "format": "json",
        "options": {"temperature": 0.8, "num_predict": 600},
        "messages": [
            {"role": "system", "content": LUECKEN_SYSTEM},
            {"role": "user", "content":
                f"Lücke: {{{name}}}\nSatz: {umfeld}\n"
                f"Gib genau {anzahl} Vorschläge."},
        ],
    })
    if not isinstance(roh, dict) or not isinstance(roh.get("werte"), list):
        return []
    gesehen, raus = set(), []
    for w in roh["werte"]:
        text = str(w or "").strip().strip(",.").strip()[:120]
        if text and text.lower() not in gesehen:
            gesehen.add(text.lower())
            raus.append(text)
    return raus[:anzahl]
