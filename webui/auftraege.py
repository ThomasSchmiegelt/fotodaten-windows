"""Auftragsabwicklung: was beim Erzeugen eines Bildes oder Ablaufs geschieht.

Der Server nimmt die Anfrage entgegen und beantwortet sie sofort; die Arbeit
laeuft danach in einem eigenen Faden weiter. Hier steht diese Arbeit --
uebersetzen, Groessen bestimmen, die Maschine anwerfen, Bilder ablegen.

Auftraege werden eingereiht statt abgewiesen: `einreihen()` haengt an, ein
einziger Arbeitsfaden nimmt sie der Reihe nach ab. So darf man mehrere
Auftraege hintereinander abschicken, ohne auf das Ende zu warten -- gleichzeitig
rechnen kann die eine Grafikkarte ohnehin nicht.

Was hier oeffentlich heisst, benutzt der Server: `engine`, `current`,
`decode`, `einreihen`, `entfernen`, `uebersicht`, `ziel`.
"""

import base64
import io
import itertools
import json
import os
import random
import re
import sys
import threading
import time
import traceback
from datetime import datetime

from PIL import Image, ImageOps, PngImagePlugin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Engine  # noqa: E402
import sprache as chat  # noqa: E402
import ablauf  # noqa: E402
import demo  # noqa: E402
import projekte  # noqa: E402
import bausteine  # noqa: E402
import cover  # noqa: E402
import baender  # noqa: E402
import szenenbau  # noqa: E402
import cloud  # noqa: E402
import datensatz  # noqa: E402
import detektor  # noqa: E402
import fotodaten  # noqa: E402
import sechsseiten  # noqa: E402
import retusche  # noqa: E402
import vervielfaeltigen  # noqa: E402
from torwache import torwaechter  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Wohin die Bilder gehen, entscheidet das Projekt. Ein Auftrag merkt sich beim
# Einreihen, zu welchem er gehoert -- wer waehrenddessen umschaltet, soll seine
# Bilder nicht ploetzlich woanders wiederfinden.
_projekt_des_laufs = projekte.ALLGEMEIN


def ziel() -> str:
    """Das Bildverzeichnis des gerade laufenden Auftrags."""
    return projekte.bilder(_projekt_des_laufs)


engine = Engine()
# Ergebnisse des laufenden bzw. zuletzt gelaufenen Auftrags.
current = {"files": [], "error": None, "translated": {}, "stage": "",
           "video": None, "gelesen": {}, "nummer": 0, "titel": "", "tor": [],
           "gliederung": [], "expose": {},
           # Der Katalogeintrag einer Sechs-Seiten-Ansicht, waehrend er
           # entsteht. Eigenes Feld, weil diese Bilder nicht in outputs/
           # liegen und deshalb nicht in "files" gehoeren -- die Oberflaeche
           # baut daraus sonst Verweise auf /outputs/, die ins Leere zeigen.
           "seiten": {},
           # Was der letzte Auftrag in den Datensatz gelegt hat.
           "datensatz": {},
           # Die Stufen eines Szenenaufbaus: was in welcher Reihenfolge
           # entsteht. Eigenes Feld, weil "gliederung" die Szenenprompts
           # der Geschichte fuehrt und die Oberflaeche daraus nachlaedt.
           "bau": {},
           # Zaehlstand fuer den Balken, wenn keine Bilder entstehen: das
           # Sprachmodell schreibt Prompt 3 von 8, und das soll man sehen.
           "fortschritt": {"ist": 0, "von": 0}}


def melden(text: str, ist: int = 0, von: int = 0) -> None:
    """Sagen, woran gerade gearbeitet wird.

    Auch die Aufrufe, die nicht in der Warteschlange laufen, schreiben
    hierher -- eine halbe Minute Stille vor einem Knopf sieht aus wie ein
    Fehler, auch wenn alles in Ordnung ist.
    """
    current["stage"] = text
    current["fortschritt"] = {"ist": ist, "von": von}

# Die Warteschlange. Wartende Auftraege halten ihre Referenzbilder als
# Datenzeilen im Speicher -- bei einer Handvoll sind das ein paar Megabyte,
# was in Ordnung ist. Wer hunderte einreiht, sollte sie auf die Platte legen;
# dafuer bekommen hochgeladene Bilder mit den Projekten einen festen Ort.
warteschlange: list[dict] = []
verlauf: list[dict] = []          # die letzten erledigten Auftraege
_wecker = threading.Condition()   # schuetzt beide Listen und weckt den Arbeiter
_zaehler = itertools.count(1)
VERLAUF_LAENGE = 20


def _titel(art: str, params: dict) -> str:
    """Eine Zeile, an der man den Auftrag in der Liste wiedererkennt."""
    if art == "expose":
        return "Geschichte umreissen"
    if art == "ergaenzen":
        return f"{params.get('fehlt') or 0} Szenen ergaenzen"
    if art == "prosa":
        return f"Prosa schreiben, {len(params.get('zeilen') or [])} Szenen"
    if art == "aufbau":
        return ("Geschichte lesen" if params.get("phase") == "rahmen"
                else f"Szenen schreiben, {len(params.get('kapitel') or [])} Abschnitte")
    if art == "prompts":
        return f"Prompts schreiben, {len(params.get('zeilen') or [])} Szenen"
    if art == "szenenbau":
        text = (params.get("text") or "").strip()
        return f"Szene aufbauen: {text[:44]}" if text else "Szene aufbauen"
    if art == "sechsseiten":
        was = (params.get("name") or params.get("text") or "").strip()
        art = "Erstes Bild" if params.get("stufe") == "erstes" else "Sechs Seiten"
        return f"{art}: {was[:44]}" if was else art
    if art == "vervielfaeltigen":
        return f"Datensatz vervielfältigen, {params.get('je_bild') or 10} je Bild"
    if art == "fotodaten":
        return (f"Fotodaten: {len(params.get('fotos') or [])} Foto(s) → "
                f"{params.get('klasse') or 'objekt'}")
    if art == "retusche":
        text = (params.get("prompt") or "").strip()
        return f"Retusche: {text[:48]}" if text else "Retusche"
    if art == "detektor":
        return f"Detektor trainieren: {params.get('modell') or 'dfine-nano'}, {params.get('epochen') or 50} Epochen"
    if art == "demo":
        if params.get("bloecke"):
            return f"Ablauf, {len(params['bloecke'])} Bloecke"
        return f"Ablauf: {params.get('ablauf') or 'reise'}"
    text = (params.get("prompt") or "").strip()
    if text:
        return text[:60] + ("…" if len(text) > 60 else "")
    for feld in ("effect", "form"):
        if params.get(feld):
            return str(params[feld])
    return params.get("mode") or "Auftrag"


def einreihen(art: str, params: dict) -> dict:
    """Haengt einen Auftrag an und weckt den Arbeiter. Antwortet sofort."""
    auftrag = {"nummer": next(_zaehler), "art": art, "params": params,
               "titel": _titel(art, params), "zustand": "wartet",
               "angelegt": time.time(), "bilder": 0, "fehler": None,
               "projekt": projekte.aktiv()}
    with _wecker:
        warteschlange.append(auftrag)
        _wecker.notify()
    return auftrag


def entfernen(nummer: int) -> bool:
    """Nimmt einen wartenden Auftrag wieder heraus. Der laufende bleibt --
    den stoppt `engine.cancel()`, weil er schon Rechenzeit verbraucht hat."""
    with _wecker:
        for i, a in enumerate(warteschlange):
            if a["nummer"] == nummer:
                del warteschlange[i]
                return True
    return False


def verschieben(nummer: int, richtung: int) -> bool:
    """Einen wartenden Auftrag eine Stelle nach vorn oder hinten."""
    with _wecker:
        for i, a in enumerate(warteschlange):
            if a["nummer"] != nummer:
                continue
            ziel = i + richtung
            if not 0 <= ziel < len(warteschlange):
                return False
            warteschlange[i], warteschlange[ziel] = warteschlange[ziel], warteschlange[i]
            return True
    return False


def leeren() -> int:
    """Alle wartenden Auftraege verwerfen. Der laufende bleibt unberuehrt."""
    with _wecker:
        anzahl = len(warteschlange)
        warteschlange.clear()
        return anzahl


def _kurz(auftrag: dict) -> dict:
    """Was die Oberflaeche ueber einen Auftrag wissen muss -- ohne die
    Referenzbilder, die als Datenzeilen im Auftrag stecken."""
    return {k: auftrag[k] for k in
            ("nummer", "art", "titel", "zustand", "angelegt", "bilder",
             "fehler", "projekt")}


def uebersicht() -> dict:
    with _wecker:
        return {"wartend": [_kurz(a) for a in warteschlange],
                "verlauf": [_kurz(a) for a in reversed(verlauf)]}


# Die Achsen, die `plan()` in den Prompt einbaut. Eine Liste, damit sie beim
# Buendeln und beim Einzellauf garantiert dieselbe ist.
ACHSEN = ("view", "style", "light", "camera", "paint", "palette", "scene",
          "angle", "device", "scenario", "material", "haltung", "kleidung")

# Alles, was beim Buendeln uebereinstimmen muss: was die Maschine einmal
# einstellt und nicht je Bild wechseln kann.
GLEICH = ("aspect", "base", "steps", "true_cfg_scale", "negative_prompt")


def _buendelbar(a: dict, b: dict) -> bool:
    """Duerfen diese beiden Auftraege einen Ladevorgang teilen?

    Gemessen kostet ein Ladevorgang rund 68 Sekunden, das Rechnen eines
    kleinen Bildes anderthalb. Wer drei Bilder einzeln einreiht, wartet also
    dreimal auf dasselbe Modell. Zusammen geht das in einem Durchgang.

    Streng gefasst: nur schlichte Text-zu-Bild-Auftraege ohne Referenzbild,
    Effekt, Vorlage oder Serienart. Bei denen ist der fertige Prompt genau
    das, was `plan()` daraus macht -- bei allem anderen baut `run_series` den
    Text noch um, und die Abkuerzung ueber `prompts=` ginge daneben.
    """
    if a["art"] != "generate" or b["art"] != "generate":
        return False
    if a.get("projekt") != b.get("projekt"):
        return False
    pa, pb = a.get("params") or {}, b.get("params") or {}
    for p in (pa, pb):
        if (p.get("mode") or "t2i") != "t2i":
            return False
        if p.get("images") or p.get("effect") or p.get("form"):
            return False
        if p.get("sweep") or p.get("prompts") or p.get("transparent"):
            return False
        if (p.get("training") or {}).get("an"):
            return False            # die Boxen gehoeren zu genau diesem Auftrag
        if int(p.get("count", 1) or 1) != 1:
            return False
    return all(str(pa.get(k, "")) == str(pb.get(k, "")) for k in GLEICH)


def _fertiger_prompt(params: dict) -> tuple[str, int]:
    """Prompt und Seed eines Auftrags, so wie die Maschine sie bauen wuerde.

    Ueber `rahmen()` und `plan()` statt von Hand: die Achsenliste waechst,
    und zwei Stellen, die denselben Text bauen, laufen frueher oder spaeter
    auseinander.

    `rahmen()` stand hier lange nicht, und das war ein Fehler: wer einen
    Effekt waehlte *und* etwas ins Prompt-Feld schrieb, bekam einen Auftrag
    mit fertigem Prompt -- und `run_series` ueberspringt den Vorlagenblock,
    sobald einer vorliegt. Die Anweisung des Effekts fiel damit still unter
    den Tisch. Ohne Text im Feld ging es gut, was die Suche nicht leichter
    gemacht haette.
    """
    seed = int(params.get("seed", 42))
    text = Engine.rahmen(
        params.get("prompt", ""),
        mode=params.get("mode") or "t2i",
        effect=params.get("effect") or None,
        form=params.get("form") or None,
        transparent=bool(params.get("transparent", False)),
        keep=params.get("keep") or "The main subject",
        action=params.get("action") or "zusammen",
        group_size=int(params.get("group_size") or 2),
        bilder=len(params.get("images") or []),
        image_prompts=params.get("image_prompts") or [],
        subject=params.get("subject") or "fahrzeug",
        haltung=params.get("haltung") or None)
    auftragsliste = Engine.plan(
        text, 1, seed, None,
        subject=params.get("subject") or "fahrzeug",
        paint_target=params.get("paint_target") or "",
        **{k: params.get(k) or None for k in ACHSEN})
    return auftragsliste[0]["prompt"], auftragsliste[0]["seed"]


def _abarbeiten(auftrag: dict, weitere: list[dict] | None = None) -> None:
    """Einen Auftrag ausfuehren. Nur der Arbeiter ruft das auf."""
    global _projekt_des_laufs
    engine.lock.acquire()
    try:
        _projekt_des_laufs = auftrag.get("projekt") or projekte.ALLGEMEIN
        alle = [auftrag] + (weitere or [])
        for a in alle:
            a["zustand"] = "laeuft"
        engine.aborted = False
        titel = (auftrag["titel"] if len(alle) == 1
                 else f"{len(alle)} Auftraege zusammen")
        current.update(files=[], error=None, translated={}, video=None,
                       gelesen={}, tor=[], gliederung=[], expose={},
                       bau={}, seiten={}, datensatz={},
                       stage="wird vorbereitet",
                       fortschritt={"ist": 0, "von": 0},
                       nummer=auftrag["nummer"], titel=titel)
        if len(alle) == 1:
            laeufe = {"demo": run_demo, "prompts": run_prompts,
                      "expose": run_expose, "ergaenzen": run_ergaenzen,
                      "aufbau": run_aufbau, "prosa": run_prosa,
                      "szenenbau": run_szenenbau,
                      "sechsseiten": run_sechsseiten, "detektor": run_detektor,
                      "retusche": run_retusche,
                      "fotodaten": run_fotodaten,
                      "vervielfaeltigen": run_vervielfaeltigen}
            laeufe.get(auftrag["art"], run_job)(auftrag["params"])
        else:
            # Ein Ladevorgang fuer alle: die fertigen Prompts gehen als Liste
            # an run_series, genau wie bei einem Ablauf.
            fertig = [_fertiger_prompt(a["params"]) for a in alle]
            gemeinsam = dict(auftrag["params"])
            gemeinsam["prompts"] = [t for t, _ in fertig]
            gemeinsam["seeds"] = [sd for _, sd in fertig]
            run_job(gemeinsam)
    finally:
        alle = [auftrag] + (weitere or [])
        zustand = ("fehler" if current["error"]
                   else "abgebrochen" if engine.aborted else "fertig")
        for i, a in enumerate(alle):
            # Im Buendel gehoert jedem Auftrag genau ein Bild, in der
            # Reihenfolge der Prompts. Allein bekommt er alle.
            eigene = (current["files"] if len(alle) == 1
                      else current["files"][i:i + 1])
            kennung = (a.get("params") or {}).get("baustein")
            if kennung and eigene:
                bausteine.bild_setzen(
                    a.get("projekt") or projekte.ALLGEMEIN, str(kennung),
                    eigene[0],
                    str((a.get("params") or {}).get("baustein_feld") or "bild"))
            # Die Sechs-Seiten-Ansicht legt ihre Bilder im Katalog ab und
            # nicht in outputs/ -- sie zaehlt deshalb eigens. Sonst stuende
            # im Verlauf "0 Bild(er)" neben sechs gerechneten.
            a["bilder"] = len(eigene) or len(
                (current["seiten"] or {}).get("bilder") or {})
            a["fehler"] = current["error"]
            a["zustand"] = zustand
            # Die Vorgaben samt Referenzbildern werden nicht aufgehoben.
            a.pop("params", None)
        with _wecker:
            verlauf.extend(alle)
            del verlauf[:-VERLAUF_LAENGE]
        engine.lock.release()


def _arbeiter() -> None:
    while True:
        with _wecker:
            while not warteschlange:
                _wecker.wait()
            auftrag = warteschlange.pop(0)
            # Was gleich dahinter steht und dazu passt, laeuft mit -- das
            # spart je Auftrag einen vollstaendigen Ladevorgang.
            weitere = []
            while warteschlange and _buendelbar(auftrag, warteschlange[0]):
                weitere.append(warteschlange.pop(0))
        try:
            _abarbeiten(auftrag, weitere)
        except Exception:                      # darf den Faden nie beenden
            traceback.print_exc()


threading.Thread(target=_arbeiter, daemon=True, name="auftraege").start()


def decode(data_url: str) -> Image.Image:
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    img = Image.open(io.BytesIO(raw))
    img.load()
    # Handyfotos liegen oft quer in der Datei, die Drehung steht nur im EXIF.
    # Der Browser zeigt sie aufrecht -- das Modell soll dasselbe sehen, und
    # eine im Browser gezogene Box oder Maske muss dazu passen.
    return ImageOps.exif_transpose(img)


def _save(meta: dict, image: Image.Image, stamp: str, kind: str,
          nummer: int | None = None) -> str:
    """Legt das Bild ab und schreibt Prompt/Seed als PNG-Textfelder mit hinein.

    `meta["index"]` zaehlt je Serienaufruf ab 1. Wer mehrere Serien unter
    demselben Zeitstempel ablegt, muss die Nummer deshalb selbst vergeben --
    sonst ueberschreiben sich die Dateien gegenseitig.
    """
    name = f"{stamp}_{kind}_{(nummer if nummer is not None else meta['index']):02d}_seed{meta['seed']}.png"
    info = PngImagePlugin.PngInfo()
    for key in ("prompt", "seed", "view", "style", "light", "camera", "effect",
                "form", "paint", "palette", "scene", "angle", "device",
                "scenario", "material", "haltung", "kleidung", "retusche",
                "quelle", "position", "belichtung", "look"):
        if meta.get(key) is not None:
            info.add_text(f"qwen_{key}", str(meta[key]))
    image.save(os.path.join(ziel(), name), pnginfo=info)
    return name


# Freitextfelder, die im Prompt landen und deshalb englisch sein sollten.
TRANSLATABLE = ("prompt", "keep", "paint_target", "negative_prompt")


def _translate_inputs(params: dict) -> dict:
    """Deutsche Eingaben vor dem Auftrag ins Englische bringen.

    Faellt Ollama aus, bleibt alles wie eingegeben -- lieber ein Bild aus
    deutschem Prompt als gar keines.
    """
    quelle = {k: params.get(k) or "" for k in TRANSLATABLE}
    # Die Rollentexte der einzelnen Referenzbilder sind ebenfalls Freitext.
    rollen = list(params.get("image_prompts") or [])
    for i, text in enumerate(rollen):
        quelle[f"bild{i + 1}"] = text or ""

    engine.note("loading", "Eingaben werden übersetzt …")
    fertig = chat.translate(quelle)

    for i in range(len(rollen)):
        neu = fertig.get(f"bild{i + 1}")
        if neu:
            rollen[i] = neu
    if rollen:
        params["image_prompts"] = rollen
    params.update({k: v for k, v in fertig.items() if k in TRANSLATABLE})
    return fertig


def _cfg_fuer(params: dict) -> float:
    """Der CFG-Wert fuer diesen Auftrag.

    Ein negativer Prompt wirkt nur oberhalb von 1 (engine.py:
    `true_cfg_scale > 1`), und dort laeuft jeder Schritt zweimal -- das Bild
    dauert also rund doppelt so lang. Angehoben wird deshalb nur auf
    ausdruecklichen Wunsch ("streng"). Steht nichts im Feld, kostet es
    ohnehin nichts: der negative Zweig faellt ganz weg.
    """
    wert = float(params.get("true_cfg_scale", 1.0) or 1.0)
    if (wert <= 1.0 and params.get("streng")
            and (params.get("negative_prompt") or "").strip()):
        return 2.5
    return wert


def _durchs_tor(prompt: str, params: dict) -> str:
    """Einen einzelnen Prompt durch den Torwaechter schicken und mitschreiben,
    was dabei herausfiel."""
    sauber, weg = torwaechter(prompt, params.get("negative_prompt") or "")
    if weg:
        current["tor"] = list(current["tor"]) + weg
    return sauber


def _series_kwargs(params: dict, refs: list, kind: str, on_image) -> dict:
    """Uebersetzt einen Parametersatz der Schnittstelle in Engine-Argumente.

    Auftrag und Vorfuehrung teilen sich diese Abbildung -- die Vorfuehrung soll
    ausdruecklich denselben Weg nehmen wie ein normaler Auftrag.
    """
    return dict(
        prompt=params.get("prompt", ""),
        negative_prompt=params.get("negative_prompt", ""),
        images=refs,
        mode=kind,
        aspect=params.get("aspect", "1:1"),
        base=int(params.get("base", 1024)),
        follow_reference=bool(params.get("follow_reference", True)),
        steps=int(params.get("steps", 40)),
        seed=int(params.get("seed", 42)),
        true_cfg_scale=_cfg_fuer(params),
        transparent=bool(params.get("transparent", False)),
        effect=params.get("effect") or None,
        form=params.get("form") or None,
        keep=params.get("keep") or "The main subject",
        paint=params.get("paint") or None,
        palette=params.get("palette") or None,
        scene=params.get("scene") or None,
        angle=params.get("angle") or None,
        device=params.get("device") or None,
        paint_target=params.get("paint_target") or "",
        scenario=params.get("scenario") or None,
        material=params.get("material") or None,
        subject=params.get("subject") or "fahrzeug",
        image_prompts=params.get("image_prompts") or [],
        action=params.get("action") or "zusammen",
        group_size=int(params.get("group_size") or 2),
        count=int(params.get("count", 1)),
        sweep=params.get("sweep") or None,
        lock_seed=bool(params.get("lock_seed", False)),
        view=params.get("view") or None,
        style=params.get("style") or None,
        light=params.get("light") or None,
        camera=params.get("camera") or None,
        on_image=on_image,
    )


def run_job(params: dict) -> None:
    try:
        current["translated"] = _translate_inputs(params)
        # Die Zeilen eines Titelblatts sind Text, der ins Bild gemalt wird --
        # sie gehen deshalb *nach* der Uebersetzung in den Prompt. Durch sie
        # hindurch staende auf einem deutschen Heft Englisches.
        #
        # Und als vollstaendige Anweisung statt als Zusatz: die feste
        # Anweisung des Effekts verlangt einen Barcode, auch wenn die Maske
        # keinen will. Sie faellt deshalb weg.
        if cover.gefuellt(params.get("cover")):
            params["prompt"] = cover.anweisung(params["cover"],
                                               params.get("prompt", ""))
            params["effect"] = ""
        refs = [decode(d) for d in (params.get("images") or []) if d]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        kind = params.get("mode") or ("edit" if refs else "t2i")

        manifest = os.path.join(ziel(), f"{stamp}_{kind}.jsonl") if kind == "varianten" else None
        entstanden = []

        def on_image(meta, image):
            name = _save(meta, image, stamp, kind)
            current["files"].append(name)
            entstanden.append((os.path.join(ziel(), name), dict(meta)))
            if manifest:
                # Eine Zeile je Bild: was variiert wurde, direkt neben der Datei.
                # Damit laesst sich der Satz spaeter filtern oder ausbalancieren.
                row = {"file": name, **{k: v for k, v in meta.items() if k != "index"}}
                with open(manifest, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        # `prompts` kommt von einer Serie ueber eine Variable oder aus einem
        # Buendel: dieselbe Person in vier Jacken, ein Ladevorgang fuer alle.
        fertige = [p for p in (params.get("prompts") or []) if str(p).strip()]
        if not fertige:
            # Ohne fertige Liste baut plan() den Prompt -- damit der
            # Torwaechter auch dort greift, wird er hier einmal gebaut.
            fertige = [_fertiger_prompt(params)[0]] if params.get("prompt") else []
            if fertige and int(params.get("count", 1) or 1) != 1:
                fertige = []          # Serien baut plan() selbst

        ausschluss = params.get("negative_prompt") or ""
        gestrichen = []
        if fertige and ausschluss.strip():
            geprueft = []
            for text in fertige:
                sauber, weg = torwaechter(text, ausschluss)
                geprueft.append(sauber)
                gestrichen += weg
            fertige = geprueft
        current["tor"] = gestrichen

        engine.run_series(**_series_kwargs(params, refs, kind, on_image),
                          **({"prompts": fertige} if fertige else {}))
        done = len(current["files"])
        meldung = f"fertig: {done} Bild(er)" if done else "abgebrochen"

        # Trainingsdaten: erst jetzt, wenn das Bildmodell die Karte frei
        # gemacht hat. Das Basisbild zaehlt nur bei Varianten -- dort steht
        # die Kamera, solange sie nicht ausdruecklich gewuerfelt wird.
        training = params.get("training") or {}
        if training.get("an") and entstanden and not engine.aborted:
            zahl = datensatz.aufnehmen(
                _projekt_des_laufs, entstanden, training.get("klasse") or "",
                training.get("suche") or "",
                basis=refs[0] if refs and kind == "varianten" else None,
                melden=melden)
            melden("")
            current["datensatz"] = zahl
            meldung += (f" · Datensatz: {zahl['ok']} aufgenommen, "
                        f"{zahl['pruefen']} zu prüfen")
        engine.note("idle", meldung)
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])
    # Die Sperre haelt und loest der Arbeiter -- siehe _abarbeiten().


def run_fotodaten(params: dict) -> None:
    """Echte Fotos zu Trainingsdaten: Varianten nach Plan, dann die Boxen.

    Erst alle Fotos durch das Bildmodell, dann einmal die Box-Modelle fuer
    alles zusammen -- auf einer kleinen Karte passen die beiden nicht
    nebeneinander, und so laden sie je nur einmal. Siehe fotodaten.py.
    """
    try:
        engine._cancel = False
        engine.aborted = False
        projekt = _projekt_des_laufs
        subject = params.get("subject") or "fahrzeug"
        klasse = str(params.get("klasse") or "").strip()
        suche = str(params.get("suche") or "").strip() or klasse.replace("_", " ")
        current["translated"] = _translate_inputs(params)
        keep = (params.get("keep") or "").strip() or f"The {suche}"
        fotos = [f for f in (params.get("fotos") or []) if f.get("bild")]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        seed = int(params.get("seed") or 0) or random.randrange(1, 2 ** 31)
        gruppen = []
        for nr, foto in enumerate(fotos, start=1):
            # `aborted` und nicht `_cancel`: run_series setzt `_cancel` bei
            # jedem Aufruf zurueck, ein Abbruch gilt aber dem ganzen Auftrag.
            if engine.aborted:
                break
            kind = f"foto{nr:02d}"
            bild = fotodaten.vorbereiten(decode(foto["bild"]))
            anzeige = foto.get("groesse") or bild.size
            box = fotodaten.box_umrechnen(foto.get("box"), tuple(anzeige), bild.size)
            # Der gemalte Bereich, der unveraendert bleiben soll. Ohne
            # gezogene Box ist er zugleich die Box des Originals -- genauer
            # als jede Hand.
            maske = fotodaten.maske_lesen(decode(foto["maske"]), bild.size)                 if foto.get("maske") else None
            if maske is not None and not box:
                box = list(maske.getbbox())
            name_original = None
            if params.get("original", True):
                # Nummer 00 vor den Varianten: so steht das Original in der
                # Galerie und im Datensatz gleich neben seinen Abkoemmlingen.
                name_original = f"{stamp}_{kind}_00_original.png"
                info = PngImagePlugin.PngInfo()
                info.add_text("qwen_quelle", str(foto.get("name") or "Foto"))
                bild.save(os.path.join(ziel(), name_original), pnginfo=info)
                current["files"].append(name_original)
            belegungen = fotodaten.plan(params.get("achsen") or {},
                                        params.get("art") or "beides",
                                        int(params.get("anzahl") or 12),
                                        seed + nr, subject)
            entstanden = []

            def on_image(meta, image, _kind=kind, _liste=entstanden, _maske=maske,
                         _bild=bild):
                meta = dict(meta, foto=_kind)
                if _maske is not None and params.get("bewahren", True):
                    # Die Originalpixel zurueck -- siehe fotodaten.bewahren.
                    # Nur wenn die Stelle sicher gefunden ist: hat das
                    # Bildmodell das Objekt woanders hingemalt (gemessen bei
                    # Z Image Turbo und bei gewuerfelter Kameraposition),
                    # stuenden danach zwei Kupplungen im Bild. Dann bleibt
                    # die Variante, wie sie ist, und die Erkenner suchen.
                    neu, box_neu, lage = fotodaten.bewahren(
                        _bild, _maske, image, licht=params.get("licht", True))
                    meta["lage"] = lage
                    if lage >= datensatz.LAGE_SICHER:
                        image, meta["box_bekannt"] = neu, box_neu
                name = _save(meta, image, stamp, _kind)
                current["files"].append(name)
                _liste.append((os.path.join(ziel(), name), meta))

            # Ein Beschreibungs-Modell (img2img, etwa Z-Image Turbo) braucht
            # das Zielbild in Worten. Das Sprachmodell schaut einmal je Foto
            # hin; antwortet es nicht, genuegt der Suchbegriff.
            beschreibung = ""
            wolke = cloud.aktiv("bild")
            if wolke and wolke.get("art") == "beschreibung":
                melden(f"Foto {nr}/{len(fotos)} wird beschrieben", nr - 1, len(fotos))
                puffer = io.BytesIO()
                fotodaten.verkleinert(bild, 1024).save(puffer, format="JPEG", quality=90)
                beschreibung = chat.bild_zu_prompt(puffer.getvalue())["prompt"] \
                    or f"A realistic photo showing a {suche}"
                current["translated"] = dict(current["translated"] or {},
                                             **{f"foto{nr}": beschreibung})

            melden(f"Foto {nr}/{len(fotos)}: {len(belegungen)} Varianten", nr - 1, len(fotos))
            engine.run_series(
                beschreibung=beschreibung,
                prompt=params.get("prompt") or "", images=[bild], mode="varianten",
                base=int(params.get("base") or 1024), follow_reference=True,
                steps=int(params.get("steps") or 30), seed=seed + 1000 * nr,
                true_cfg_scale=_cfg_fuer(params), keep=keep, subject=subject,
                paint_target=params.get("paint_target") or "",
                kombinationen=belegungen, on_image=on_image)
            gruppen.append({"basis": bild, "basis_box": box,
                            "original": (os.path.join(ziel(), name_original),
                                         {"foto": kind}) if name_original else None,
                            "bilder": entstanden})
        melden("")
        done = len(current["files"])
        meldung = f"fertig: {done} Bild(er) aus {len(gruppen)} Foto(s)"
        if params.get("labeln", True) and gruppen and not engine.aborted:
            zahl = datensatz.aufnehmen_gruppen(projekt, gruppen, klasse, suche, melden)
            melden("")
            current["datensatz"] = zahl
            meldung += (f" · Datensatz: {zahl['ok']} aufgenommen, "
                        f"{zahl['pruefen']} zu prüfen")
        engine.note("idle", ("abgebrochen · " if engine.aborted else "") + meldung)
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        melden("")
        engine.note("error", current["error"])


def run_retusche(params: dict) -> None:
    """Eine gemalte Stelle nachbessern -- siehe retusche.py.

    Mehrere Versuche laufen mit aufsteigendem Seed in einem Ladevorgang: wie
    ein Mund geraet, ist Glueckssache, und aussuchen geht schneller als
    viermal neu starten.
    """
    try:
        original = Image.open(params["pfad"]) if params.get("pfad") \
            else decode(params["bild"])
        original.load()
        if original.mode not in ("RGB", "RGBA"):
            original = original.convert("RGBA" if "transparency" in original.info
                                        else "RGB")
        maske = retusche.maske_lesen(decode(params["maske"]), original.size)
        box = retusche.ausschnitt(maske, float(params.get("rand", 0.6)))
        if not box:
            raise ValueError("Keine Stelle markiert")

        current["translated"] = _translate_inputs(params)
        text = retusche.anweisung(params.get("prompt", ""))
        anzahl = max(1, min(int(params.get("count", 1) or 1), 8))
        seed = int(params.get("seed", 42))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        kante = int(params.get("kante", 16))
        # Der Prompt des Originals bleibt am Bild: wer es spaeter benennt
        # oder in einer Szene aufruft, meint das Bild, nicht die Retusche.
        try:
            frueher = str(original.text.get("qwen_prompt") or "")
        except AttributeError:
            frueher = ""

        def on_image(meta, image):
            fertig = retusche.einsetzen(original, image, maske, box, kante)
            name = _save({"index": meta["index"], "seed": meta["seed"],
                          "prompt": frueher or None, "retusche": text,
                          "quelle": params.get("datei") or None},
                         fertig, stamp, "retusche")
            current["files"].append(name)

        engine.run_series(
            prompt=text, negative_prompt=params.get("negative_prompt", ""),
            images=[original.convert("RGB").crop(box)], mode="edit",
            base=int(params.get("base", 1024)), follow_reference=True,
            steps=int(params.get("steps", 40)), seed=seed,
            true_cfg_scale=_cfg_fuer(params),
            prompts=[text] * anzahl, seeds=[seed + i for i in range(anzahl)],
            on_image=on_image)
        done = len(current["files"])
        engine.note("idle", f"fertig: {done} Retusche(n)" if done else "abgebrochen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def run_vervielfaeltigen(params: dict) -> None:
    """Aus den gepruefte Bildern des Datensatzes viele machen -- siehe
    vervielfaeltigen.py. Die Box wandert rechnerisch mit."""
    import random
    umgebung = None
    try:
        engine._cancel = False
        engine.aborted = False
        projekt = _projekt_des_laufs
        vorlagen = datensatz.originale(projekt)
        if not vorlagen:
            raise RuntimeError("Im Datensatz ist noch kein aufgenommenes Bild "
                               "mit Box -- erst Basisbilder erzeugen und prüfen")
        je_bild = max(1, min(int(params.get("je_bild") or 10), 200))
        mit_umgebung = bool(params.get("umgebung"))
        mit_klassisch = bool(params.get("klassisch", True)) or not mit_umgebung
        umgebungen = [z.strip() for z in str(params.get("umgebungen") or "").splitlines()
                      if z.strip()] or vervielfaeltigen.UMGEBUNGEN["gegenstand"]
        staerke = max(0.3, min(float(params.get("staerke") or 0.75), 1.0))
        behalten = bool(params.get("behalten", True))
        spiegeln = bool(params.get("spiegeln", True))
        rng = random.Random(int(params.get("seed") or 0) or None)
        if mit_umgebung:
            umgebung = vervielfaeltigen.Umgebung(melden)

        ordner = os.path.join(datensatz.wurzel(projekt), "images")
        vorhanden = set(os.listdir(ordner))
        gesamt, fertig, neue = len(vorlagen) * je_bild, 0, []
        for vorlage in vorlagen:
            pfad = datensatz.bildpfad(projekt, "ok", vorlage["datei"])
            if not pfad:
                continue
            with Image.open(pfad) as roh:
                original = roh.convert("RGB")
            stamm = vorlage["datei"][:-4]
            nummer = 1
            for _ in range(je_bild):
                if engine._cancel:
                    break
                while f"{stamm}_mehr{nummer:02d}.png" in vorhanden:
                    nummer += 1
                name = f"{stamm}_mehr{nummer:02d}.png"
                vorhanden.add(name)
                melden(f"Vervielfältigen: {vorlage['datei'][:28]}… {fertig + 1}/{gesamt}",
                       fertig, gesamt)
                bild, box, achsen, prompt = original, list(vorlage["box"]), {}, ""
                seed = rng.randrange(2 ** 31)
                if mit_umgebung:
                    ort = rng.choice(umgebungen)
                    prompt = vervielfaeltigen.prompt_fuer(
                        vorlage.get("suche") or vorlage["klasse"], ort)
                    bild = umgebung.rechnen(original, prompt, seed, staerke)
                    if behalten:
                        bild = vervielfaeltigen.gegenstand_behalten(bild, original, box)
                    achsen["umgebung"] = ort
                if mit_klassisch:
                    bild, box = vervielfaeltigen.klassisch(bild, box, rng, spiegeln)
                    achsen["klassisch"] = "ja"
                bild.save(os.path.join(ordner, name))
                neue.append({
                    "datei": name, "klasse": vorlage["klasse"],
                    "suche": vorlage.get("suche") or "",
                    "breite": bild.size[0], "hoehe": bild.size[1],
                    "angelegt": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "prompt": prompt, "seed": seed, "achsen": achsen,
                    "box": box, "status": "ok", "gruende": [],
                    "quelle": vorlage["datei"],
                    # Ein vervielfaeltigtes echtes Foto bleibt ein echtes
                    # Motiv -- fuer attribute.csv und zum Ausbalancieren.
                    **{k: vorlage[k] for k in ("foto", "echt") if vorlage.get(k)}})
                fertig += 1
            # Zwischendurch sichern: ein Abbruch nach einer Stunde soll nicht
            # alles kosten, was bis dahin entstanden ist.
            datensatz.hinzufuegen(projekt, neue)
            if engine._cancel:
                break
        melden("")
        current["datensatz"] = {"ok": fertig, "pruefen": 0}
        engine.note("idle", ("abgebrochen nach " if engine.aborted else "fertig: ")
                    + f"{fertig} Bilder vervielfältigt aus {len(vorlagen)} Vorlagen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        melden("")
        engine.note("error", current["error"])
    finally:
        if umgebung is not None:
            umgebung.schliessen()


def run_expose(params: dict) -> None:
    """Die Geschichte umreissen: Kurzfassung, Welt, Stil, Szenenvorschlag.

    Steht vor allem anderen, weil hier der globale Stil und die Frage
    Wirklichkeit oder Erfindung entschieden werden -- beides gilt danach fuer
    jede Szene.
    """
    try:
        melden("Grosses Sprachmodell wird geladen")
        erg = chat.expose(params.get("idee") or "",
                          fiktion=params.get("fiktion"),
                          vorher=params.get("vorher") or "",
                          model=params.get("modell") or None,
                          anzahl=params.get("anzahl") or 0,
                          alter=params.get("alter") or "")
        current["expose"] = erg
        melden("")
        engine.note("idle", "Geschichte umrissen" if erg["kurz"]
                    else "Das Sprachmodell hat nichts geliefert")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def _eingefuegt(neue: list[dict], schluessel, band: int) -> list[dict]:
    """Neu geschriebene Szenen in die vorhandenen Prompts einsortieren.

    Nur die genannten Nummern werden ersetzt. Ohne das loeschte ein
    Nachbessern an Szene drei die anderen sieben Prompts.
    """
    vorher = []
    if schluessel:
        g = baender.lesen(_projekt_des_laufs, str(schluessel))
        for b in g.get("baende") or []:
            if b.get("nr") == band:
                vorher = list(b.get("prompts") or [])
    ersetzt = {p["nr"] for p in neue}
    zusammen = [p for p in vorher if p.get("nr") not in ersetzt] + list(neue)
    return sorted(zusammen, key=lambda p: p.get("nr") or 0)


def run_aufbau(params: dict) -> None:
    """Eine ganze Geschichte in eine Gliederung verwandeln, in zwei Stufen.

    "rahmen" holt Titel, Kurzfassung, Anfangs- und Schlussszene und teilt den
    Text in Abschnitte mit Ueberschriften. "szenen" schreibt die Szenen je
    Abschnitt. Getrennt, weil man nach dem Rahmen gegenlesen will -- und weil
    das Ende feststehen muss, bevor die Mitte entsteht.
    """
    try:
        text = (params.get("text") or "").strip()
        modell = params.get("modell") or None
        phase = params.get("phase") or "rahmen"
        wieviel = max(2, min(int(params.get("anzahl") or 12), 60))

        if phase == "rahmen":
            melden("Die Geschichte wird gelesen", 0, 2)
            erg = chat.rahmen(text, kurz=params.get("kurz") or "",
                              welt=params.get("welt") or "",
                              fiktion=params.get("fiktion"),
                              stil=params.get("stil") or "", model=modell,
                              alter=params.get("alter") or "")
            # Ein Abschnitt je vier bis sechs Szenen, hoechstens zehn.
            k = max(1, min(round(wieviel / 5), 10))
            stuecke = chat.abschnitte(text, k)
            melden("Die Abschnitte bekommen Überschriften", 1, 2)
            titel = chat.kapitel(stuecke, model=modell)
            current["expose"] = {**erg, "nur_rahmen": True,
                                 "kapitel": [{"titel": t, "text": st}
                                             for t, st in zip(titel, stuecke)]}
            melden("")
            engine.note("idle", f"Rahmen steht, {len(stuecke)} Abschnitte")
            return

        kapitel = params.get("kapitel") or []
        if not kapitel:
            raise ValueError("Keine Abschnitte -- erst den Rahmen holen.")
        anfang = (params.get("anfang") or "").strip()
        ende = (params.get("ende") or "").strip()
        # Anfang und Ende zaehlen mit: sie sind schon geschrieben.
        offen = max(1, wieviel - (1 if anfang else 0) - (1 if ende else 0))
        # Der Anteil je Abschnitt richtet sich nach seiner Laenge, damit ein
        # langer Abschnitt nicht in zwei Bildern abgehandelt wird.
        laengen = [max(1, len(k.get("text") or "")) for k in kapitel]
        gesamt = sum(laengen)
        anteile = [max(1, round(offen * n / gesamt)) for n in laengen]
        zeilen = [anfang] if anfang else []
        for i, (kap, wie) in enumerate(zip(kapitel, anteile), 1):
            melden(f"Abschnitt {i} von {len(kapitel)}: {kap.get('titel') or ''}",
                   i - 1, len(kapitel))
            zeilen += [z for z in chat.szenen_aus_abschnitt(
                kap.get("text") or "", wie, kapitel_titel=kap.get("titel") or "",
                kurz=params.get("kurz") or "", welt=params.get("welt") or "",
                fiktion=params.get("fiktion"), stil=params.get("stil") or "",
                alter=params.get("alter") or "", bisher="\n".join(zeilen[-8:]),
                schluss=ende if i == len(kapitel) else "",
                model=modell) if z]
        chat.entladen(modell or chat.GROSS)
        current["expose"] = {"szenen": zeilen, "nur_szenen": True}
        melden("")
        engine.note("idle", f"{len(zeilen)} Szenen aus {len(kapitel)} Abschnitten")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def run_prosa(params: dict) -> None:
    """Zu jeder Szene den Text schreiben. Ein eigener Schritt.

    Die Prosa stand bisher als Haken am Prompt-Schreiben und lief damit nur
    mit, wenn ohnehin Prompts entstanden. Sie gehoert aber davor: aus ihr
    ergibt sich, was im Bild zu sehen ist und welche Bausteine es braucht.
    """
    try:
        roh = params.get("zeilen") or []
        # "nummern" sagt, welche Szenen der Geschichte das sind. Ohne die
        # Angabe ist es die ganze Gliederung, eins bis n.
        nummern = [int(n) for n in (params.get("nummern") or [])]
        szenen = [{"nr": (nummern[i] if i < len(nummern) else i + 1),
                   "zeile": z.get("text") or ""}
                  for i, z in enumerate(roh) if (z.get("text") or "").strip()]
        if not szenen:
            raise ValueError("Keine Szene")

        def weit(ist, von):
            melden(f"Absatz {ist + 1} von {von}", ist, von)

        melden("Grosses Sprachmodell wird geladen", 0, len(szenen))
        absaetze = chat.prosa(szenen, model=params.get("modell") or None,
                              kurz=params.get("kurz") or "",
                              welt=params.get("welt") or "",
                              fiktion=params.get("fiktion"),
                              alter=params.get("alter") or "",
                              figuren=params.get("figuren") or "",
                              erzaehler=params.get("erzaehler") or "",
                              fortschritt=weit)
        current["expose"] = {"nur_prosa": True,
                             "prosa": [{"nr": s["nr"], "text": t}
                                       for s, t in zip(szenen, absaetze)]}
        melden("")
        engine.note("idle",
                    f"{sum(1 for t in absaetze if t)} von {len(szenen)} Absaetzen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def run_ergaenzen(params: dict) -> None:
    """Die fehlenden Zeilen eines Inhaltsverzeichnisses nachschreiben.

    Als Auftrag wie das Umreissen: es ist dasselbe grosse Modell, und das
    belegt die Karte.
    """
    try:
        melden("Grosses Sprachmodell wird geladen")
        neu = chat.szenen_ergaenzen(
            [z.get("text") or "" for z in (params.get("zeilen") or [])],
            int(params.get("fehlt") or 0),
            kurz=params.get("kurz") or "", welt=params.get("welt") or "",
            fiktion=params.get("fiktion"), stil=params.get("stil") or "",
            model=params.get("modell") or None)
        current["expose"] = {"szenen": neu, "nur_ergaenzung": True}
        melden("")
        engine.note("idle", f"{len([z for z in neu if z])} Szenen ergaenzt")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


def run_prompts(params: dict) -> None:
    """Aus der Gliederung die Bildprompts schreiben, der Reihe nach.

    Laeuft als Auftrag und nicht als Direktaufruf, weil das grosse Modell die
    Grafikkarte belegt: nur so wartet ein Bildauftrag daneben, statt sich mit
    ihm um den Speicher zu streiten. Der Fortschritt landet in `stage`, damit
    die Seite ihn zeigen kann -- bei 16,5 GB und mehreren Szenen dauert es.
    """
    try:
        roh = params.get("zeilen") or []
        zeilen = [z.get("text") or "" for z in roh]
        # Was sich in den Augen spiegelt, tippt der Benutzer deutsch; im
        # Prompt muss es englisch stehen. Ein Aufruf fuer alle Angaben, vor
        # dem grossen Modell -- danach ist die Karte belegt.
        # Dasselbe gilt fuer die #-Hinweise: die Erwartung geht als Auftrag
        # an das Sprachmodell, der Ausschluss streicht spaeter im englischen
        # Prompt -- beides braucht Englisch.
        angaben = sorted({(z.get(feld) or "").strip() for z in roh
                          for feld in ("spiegelung", "erwartung", "ausschluss")
                          if (z.get(feld) or "").strip()})
        englisch = {}
        if angaben:
            melden("Angaben werden übersetzt")
            fertig = chat.translate({f"a{i}": t for i, t in enumerate(angaben)})
            englisch = {t: fertig.get(f"a{i}") or t
                        for i, t in enumerate(angaben)}
        melden("Grosses Sprachmodell wird geladen")

        def fortschritt(nr, gesamt):
            melden(f"Prompt {nr} von {gesamt}", nr - 1, gesamt)

        # Wer unsichtbar ist, wird beim Namen genannt: das Sprachmodell soll
        # ihn nicht ins Bild schreiben.
        nach_id = {b["id"]: b.get("name") or ""
                   for z in roh for b in (z.get("teile") or [])}
        hinweise = [{"erwartung": z.get("erwartung") or "",
                     "ausschluss": z.get("ausschluss") or "",
                     "prosa": z.get("prosa") or "",
                     "unsichtbar": ", ".join(
                         nach_id.get(k, "") for k in (z.get("unsichtbar") or [])
                         if nach_id.get(k))} for z in roh]
        szenen = chat.gliederung(zeilen, hinweise=hinweise,
                                 alter=params.get("alter") or "",
                                 stil=params.get("stil") or "",
                                 welt=params.get("welt") or "",
                                 kurz=params.get("kurz") or "",
                                 fiktion=params.get("fiktion"),
                                 model=params.get("modell") or None,
                                 fortschritt=fortschritt)
        # Ueber die Nummer zuordnen, nicht ueber die Position: leere Zeilen
        # ueberspringt das Sprachmodell, und dann sitzt die Spiegelung in der
        # falschen Szene.
        for szene in szenen:
            i = int(szene.get("nr") or 0) - 1
            if not 0 <= i < len(roh):
                continue
            for feld in ("spiegelung", "ausschluss"):
                quelle = (roh[i].get(feld) or "").strip()
                if quelle:
                    szene[feld] = englisch.get(quelle, quelle)
            # Festhalten, welche Prosa dieser Prompt gesehen hat. Aendert sie
            # sich, ist er von gestern -- genau wie bei der Stichzeile.
            szene["prosa_quelle"] = roh[i].get("prosa") or ""
        if params.get("prosa"):
            melden("Text wird geschrieben")
            absaetze = chat.prosa(szenen, model=params.get("modell") or None,
                                  kurz=params.get("kurz") or "",
                                  welt=params.get("welt") or "",
                                  fiktion=params.get("fiktion"),
                                  alter=params.get("alter") or "")
            for i, s in enumerate(szenen):
                s["prosa"] = absaetze[i] if i < len(absaetze) else ""
        # Eine einzelne Szene ersetzt nur sich selbst. Ohne das loeschte ein
        # Nachbessern an Szene drei die anderen sieben Prompts.
        # "nummern" sagt, welche Szenen der Geschichte hier neu geschrieben
        # wurden. Steht nichts da, ist es die ganze Gliederung.
        nummern = [int(n) for n in (params.get("nummern") or []) if int(n or 0) > 0]
        schluessel = params.get("schluessel")
        if nummern and szenen:
            for k, szene in enumerate(szenen):
                if k < len(nummern):
                    szene["nr"] = nummern[k]
            szenen = _eingefuegt(szenen, schluessel,
                                 int(params.get("band") or 1))
        current["gliederung"] = szenen
        # Sofort in die Geschichte schreiben, nicht erst wenn die Seite es
        # nachholt: `current` wird vom naechsten Auftrag geleert, und eine
        # Minute Arbeit des grossen Modells darf daran nicht haengen.
        if schluessel:
            baender.speichern(_projekt_des_laufs, str(schluessel),
                              {"band": int(params.get("band") or 1),
                               "prompts": szenen})
        melden("")
        if nummern:
            engine.note("idle", "Prompt fuer Szene "
                        + ", ".join(str(n) for n in nummern) + " geschrieben")
        else:
            geschrieben = sum(1 for s in szenen if s.get("prompt"))
            engine.note("idle", f"{geschrieben} von {len(zeilen)} Prompts geschrieben")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])


class Abgebrochen(Exception):
    """Der Benutzer hat die Vorfuehrung gestoppt."""


def _bloecke_gruppieren(bloecke: list[dict]) -> list[tuple[str, list[dict]]]:
    """Faellige Ladevorgaenge buendeln.

    Aufeinanderfolgende Bloecke, die auf dem Startbild aufsetzen, laufen als
    eine Serie -- ein Ladevorgang statt einer je Bild. Ein Block, der auf dem
    vorigen Bild aufsetzt, braucht zwangslaeufig einen eigenen.
    """
    gebuendelt: list[tuple[str, list[dict]]] = []
    for block in bloecke:
        art = "gruppe" if block.get("art") == "gruppe" else block.get("referenz", "start")
        if gebuendelt and gebuendelt[-1][0] == "start" == art:
            gebuendelt[-1][1].append(block)
        else:
            gebuendelt.append((art, [block]))
    return gebuendelt


def _demo_ohne_basis(params, stamp, fest, seed, sammler, pruefe,
                     gesammelt) -> None:
    """Eine einzelne Szene erzeugen -- ohne Startbild, ohne Referenz.

    Der Ablauf baut sonst zuerst ein Startbild, liest es mit dem
    Bildmodell und haengt an jeden Block "dieselbe Person wie im
    Referenzbild". Fuer eine Szene aus der Geschichte ist das dreifach
    falsch: ein Bild zu viel, eine fremde Person als Vorlage und eine
    Bewahrungsklausel, die den Prompt verdoppelt.
    """
    texte = []
    for block in params.get("bloecke") or []:
        texte += [t for t in ablauf.bausteine_von(block) if t]
    if not texte:
        raise RuntimeError("Die Szene ergibt keinen Prompt")

    current["stage"] = f"{len(texte)} Bild(er) werden erzeugt"
    engine.run_series(**_series_kwargs(
        {"mode": "t2i", "prompt": "", "aspect": params.get("aspect") or "3:2",
         "seed": seed, "count": len(texte), **fest}, [], "t2i", sammler),
        prompts=texte, seeds=[seed + i for i in range(len(texte))])
    pruefe()

    # Ein Video aus einem Bild gibt es nicht.
    if (len(gesammelt) > 1 and demo.available()["video"]
            and not params.get("ohne_video")):
        current["stage"] = "Video wird gebaut"
        ziel_datei = os.path.join(ziel(), f"{stamp}_szene.mp4")
        demo.baue_video([os.path.join(ziel(), n) for n in gesammelt],
                        ziel_datei,
                        gesamtdauer=float(params.get("duration") or 8.0))
        current["video"] = os.path.basename(ziel_datei)
    melden("")
    engine.note("idle", f"Szene fertig: {len(gesammelt)} Bild(er)")


def run_szenenbau(params: dict) -> None:
    """Eine Szene Stufe um Stufe bauen statt in einem Zug.

    Erst der Raum, dann jede Figur einzeln in ihrer Haltung, dann das
    Spiegelbild, zuletzt alles ineinander. Jedes Zwischenbild bleibt liegen
    und haengt sich an seinen Baustein -- eine Pose, die einmal stimmt,
    soll wiederverwendbar sein.
    """
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        projekt = _projekt_des_laufs
        alle = {b["id"]: b for b in bausteine.liste(projekt)}
        teile = [alle[k] for k in (params.get("bausteine") or []) if k in alle]
        if not teile:
            raise RuntimeError("Kein Baustein fuer den Aufbau")

        melden("Die Szene wird zerlegt …")
        plan = params.get("plan")
        if not isinstance(plan, dict) or not plan.get("figuren"):
            plan = chat.bauplan(params.get("text") or "",
                                [b["name"] for b in teile],
                                params.get("modell") or None)
        current["bau"] = {"plan": plan, "stufen": []}
        folge = szenenbau.schritte(plan, teile, params.get("stil") or "")
        if not folge:
            raise RuntimeError("Aus der Szene laesst sich kein Aufbau bilden")
        current["bau"] = {"plan": plan,
                          "stufen": szenenbau.uebersicht(folge)}

        fest = {"base": int(params.get("base", 1024)),
                "steps": int(params.get("steps", 24)),
                "aspect": params.get("aspect") or "3:2"}
        seed = int(params.get("seed") or 42)
        dateien: dict[int, str] = {}

        def laden(datei):
            bild = Image.open(os.path.join(ziel(), datei))
            bild.load()
            return bild

        def vorlagen_von(schritt):
            """Die Bilder, auf denen eine Stufe aufsetzt. Eine Zahl meint
            eine fruehere Stufe, "musterbild:<id>" das Bild des Bausteins."""
            raus = []
            for quelle in schritt.get("vorlagen") or []:
                if isinstance(quelle, int):
                    if quelle in dateien:
                        raus.append(laden(dateien[quelle]))
                    continue
                kennung = str(quelle).split(":", 1)[-1]
                datei = (alle.get(kennung) or {}).get("bild") or ""
                pfad = os.path.join(ziel(), datei)
                if datei and os.path.isfile(pfad):
                    raus.append(laden(datei))
            return raus

        for schritt in folge:
            if engine.aborted:
                break
            melden(schritt["titel"], schritt["nr"], len(folge))
            # Eine Stufe, die ein fertiges Bild meint statt eines neuen:
            # eine Figur ohne eigene Haltung steht schon freigestellt im
            # Katalog. Sie noch einmal zu rechnen kostet anderthalb Minuten
            # und ergibt dasselbe.
            vorhanden = str(schritt.get("vorhanden") or "")
            if vorhanden:
                kennung = vorhanden.split(":", 1)[-1]
                datei = (alle.get(kennung) or {}).get("bild") or ""
                if not datei or not os.path.isfile(os.path.join(ziel(), datei)):
                    raise RuntimeError(f"„{schritt['titel']}“ fehlt das Bild")
                dateien[schritt["nr"]] = datei
                continue
            refs = vorlagen_von(schritt)
            text = schritt["prompt"]
            art = ("gruppe" if schritt.get("aktion")
                   else "edit" if refs else "t2i")
            gemacht: list[str] = []

            def sammler(meta, image, _titel=schritt["titel"]):
                name = _save({**meta, "prompt": meta.get("prompt") or _titel},
                             image, stamp, "bau",
                             nummer=len(current["files"]) + 1)
                current["files"].append(name)
                gemacht.append(name)

            engine.run_series(**_series_kwargs(
                {**fest, "mode": art, "prompt": text, "count": 1,
                 "seed": seed + schritt["nr"],
                 "action": schritt.get("aktion") or "zusammen",
                 # Beim Zusammensetzen bestimmt die Kulisse das Format --
                 # ein Hochformat aus dem Posenbild wuerde den Raum
                 # beschneiden.
                 "follow_reference": art != "gruppe"},
                refs, art, sammler))
            if not gemacht:
                if engine.aborted:
                    break
                raise RuntimeError(f"„{schritt['titel']}“ ergab kein Bild")
            dateien[schritt["nr"]] = gemacht[-1]

            # Das Zwischenbild an seinen Baustein. Es bleibt damit auch dann
            # auffindbar, wenn das fertige Bild laengst weiterverarbeitet ist.
            if schritt.get("baustein") and schritt.get("feld"):
                bausteine.bild_anhaengen(
                    projekt, schritt["baustein"], schritt["feld"],
                    gemacht[-1], wozu=(params.get("text") or "")[:120],
                    prompt=text)

        melden("")
        fertig = len(current["files"])
        engine.note("idle", f"Aufbau fertig: {fertig} Bild(er)"
                    if fertig else "abgebrochen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        melden("")
        engine.note("idle", "Aufbau fehlgeschlagen")


def _gegenstandsplan(params: dict, projekt: str, fest: str = "",
                     nur_gegenstand: bool = False) -> dict:
    """Alles, was die sechs Prompts brauchen: Gegenstand, Ansichten, Grund, Ausschluss.

    Drei Quellen, und sie gelten in dieser Rangfolge:

      von Hand         was im Eingabefeld hinter `/unten` steht. Der
                       Benutzer hat es gerade hingeschrieben, also gilt es.
      ein Baustein     sein Prompt mit gefuellten Luecken -- fuer den
                       Gegenstand selbst.
      Sprachmodell     alles Uebrige: den Gegenstand ausformulieren und zu
                       jeder Seite schreiben, was sie zeigt und was in ihr
                       verdeckt ist.

    Gemessen: der allgemeine Satz ("the picture shows only its top") trennt
    vorn, hinten, links und rechts sauber, hebt die Kamera bei oben und
    unten aber nur um zwanzig Grad. Er kann auch nicht wissen, dass unten
    die Parabolantenne sitzt und die Solarpaneele dort nur noch schmale
    Kanten sind. Genau das schreibt das Sprachmodell dazu -- oder man
    schreibt es selbst.
    """
    kennung = str(params.get("gegenstand") or "")
    aus_baustein = ""
    if kennung:
        b = next((x for x in bausteine.liste(projekt)
                  if x.get("id") == kennung), None)
        if not b:
            raise RuntimeError("Den gewaehlten Baustein gibt es nicht mehr")
        aus_baustein = bausteine.einsetzen(b.get("prompt") or "",
                                           b.get("variablen") or {})

    eingabe = sechsseiten.lies_eingabe(params.get("text") or "")
    text = eingabe["allgemein"]
    if not aus_baustein and not text:
        raise RuntimeError("Keine Beschreibung")

    # --- Was von Hand dasteht, in einem Zug uebersetzen ------------------
    # Ein Aufruf fuer alle Felder: einzeln kosteten sie jedes Mal die
    # Wartezeit, und uebersetzt wird ohnehin nur, was deutsch aussieht. Die
    # Schluessel bekommen ein Kuerzel davor, damit sich die Ansicht einer
    # Seite nicht mit ihrem Ausschluss mischt.
    felder = {f"s_{k}": v for k, v in eingabe["sichten"].items()}
    felder.update({f"o_{k}": v for k, v in eingabe["ohne"].items()})
    if eingabe["hintergrund"]:
        felder["hintergrund"] = eingabe["hintergrund"]
    if eingabe["ohne_alle"]:
        felder["o_alle"] = eingabe["ohne_alle"]
    if felder:
        melden("Die eigenen Angaben werden uebersetzt")
        felder.update(chat.translate(felder, immer=("hintergrund",)))

    hintergrund = felder.pop("hintergrund", "")
    ohne_alle = felder.pop("o_alle", "")
    # Der Ausschluss geht unveraendert weiter: der Torwaechter sucht die
    # Woerter spaeter im englischen Prompt, zurechtgebogen faende er sie
    # nicht mehr.
    ohne = {k[2:]: v for k, v in felder.items() if k.startswith("o_")}
    sichten = {k[2:]: chat.ansicht_satz(v) for k, v in felder.items()
               if k.startswith("s_")}
    sichten = {k: v for k, v in sichten.items() if v}

    fehlend = [s for s in sechsseiten.SEITEN if s not in sichten]
    plan = {"text": "", "sichten": sichten, "hintergrund": hintergrund,
            "ohne": ohne, "ohne_alle": ohne_alle}
    if nur_gegenstand:
        # Fuers erste Bild: nur der Gegenstand. Die Ansichten schreibt das
        # Sprachmodell erst danach, aus genau dem Text, der im Bild steckt.
        fehlend = []

    if fest:
        # Der Gegenstand steht seit dem ersten Bild fest. Ausformuliert wird
        # er nicht noch einmal -- ein zweiter Wurf des Sprachmodells waere
        # ein anderer Gegenstand als der, den man gerade gesehen hat.
        if params.get("ausformulieren", True) and fehlend:
            melden(f"Das Sprachmodell schreibt {len(fehlend)} Ansichten")
            geschrieben = chat.seiten_plan(fest, params.get("modell") or None)
            for seite in fehlend:
                if geschrieben.get("sichten", {}).get(seite):
                    sichten[seite] = geschrieben["sichten"][seite]
        return dict(plan, text=fest, sichten=sichten)

    # Ohne Sprachmodell -- oder weil alle sechs Seiten schon dastehen, oder
    # weil ein Baustein den Gegenstand mitbringt und nur er gefragt ist. Der
    # Gegenstand selbst will dann nur noch uebersetzt werden.
    if not params.get("ausformulieren", True) \
            or (nur_gegenstand and aus_baustein) \
            or (not fehlend and not nur_gegenstand):
        if aus_baustein:
            return dict(plan, text=chat.ohne_zahlenvergleich(aus_baustein))
        neu = chat.translate({"prompt": text})
        return dict(plan, text=chat.ohne_zahlenvergleich(
            (neu.get("prompt") or text).strip()))

    melden("Das Sprachmodell beschreibt den Gegenstand" if nur_gegenstand
           else f"Das Sprachmodell schreibt {len(fehlend)} Ansichten")
    geschrieben = chat.seiten_plan(aus_baustein or text,
                                   params.get("modell") or None)
    # Der Baustein behaelt seinen eigenen Prompt -- gefragt war er nur nach
    # den Ansichten.
    gegenstand = chat.ohne_zahlenvergleich(
        aus_baustein or geschrieben.get("gegenstand") or "")
    if not gegenstand.strip():
        # Faellt Ollama aus, lieber uebersetzen als den Auftrag abbrechen.
        neu = chat.translate({"prompt": text})
        gegenstand = chat.ohne_zahlenvergleich((neu.get("prompt") or text).strip())
    # Die eigenen Saetze bleiben oben: sie werden nicht ueberschrieben.
    for seite in fehlend:
        if geschrieben.get("sichten", {}).get(seite):
            sichten[seite] = geschrieben["sichten"][seite]
    return dict(plan, text=gegenstand, sichten=sichten)


def run_sechsseiten(params: dict) -> None:
    """Sechs Ansichten eines Gegenstands, in einem einzigen Ladevorgang.

    Alle sechs Prompts gehen zusammen an die Maschine: der Ladevorgang kostet
    rund eine Minute, das Rechnen eines Bildes anderthalb -- einzeln
    eingereiht waere der Katalogeintrag ein Vielfaches davon.

    Die Bilder gehen in den Katalog, nicht nach `outputs/`. Dort wird oft
    aufgeraeumt, und ein Katalog, der dabei verschwindet, ist keiner.
    """
    try:
        projekt = _projekt_des_laufs
        if params.get("stufe") == "erstes":
            return _erstes_bild(params, projekt)
        # Gibt es schon ein erstes Bild, kommen die sechs Seiten in denselben
        # Eintrag -- und der Gegenstand ist der, der darin zu sehen ist.
        vorher = None
        if params.get("eintrag"):
            projekt = str(params.get("eintrag_projekt") or projekt)
            vorher = sechsseiten.eintrag(projekt, str(params["eintrag"]))
            if not vorher:
                raise RuntimeError("Den Katalogeintrag gibt es nicht mehr")
        fest = ""
        if vorher:
            # Steht oben im Feld noch derselbe Gegenstand -- oder gar keiner
            # --, gilt der des ersten Bildes. Hat man ihn geaendert, gilt
            # das Geaenderte.
            oben = sechsseiten.lies_eingabe(params.get("text") or "")["allgemein"]
            if not oben or oben.rstrip(". ") == (vorher.get("prompt") or "").rstrip(". "):
                fest = vorher.get("prompt") or ""
        plan = _gegenstandsplan(params, projekt, fest=fest)
        text, sichten = plan["text"], plan["sichten"]
        hintergrund = plan["hintergrund"]
        stil = str(params.get("stil") or "")
        paare = sechsseiten.alle_prompts(text, stil, sichten, hintergrund)
        if not paare:
            raise RuntimeError("Aus der Beschreibung laesst sich kein Prompt bilden")

        # Was hinter /- steht, faellt aus dem Prompt -- je Seite einzeln.
        # Ein Ausschluss fuer alle sechs ginge hier nicht: die Antenne soll
        # in der Aufsicht verschwinden und ist in der Untersicht die
        # Hauptsache. Deshalb der Torwaechter je Bild und nicht der negative
        # Prompt, der fuer die ganze Reihe gilt (und die Rechenzeit
        # verdoppelt, ohne an der Blickrichtung etwas zu aendern -- gemessen).
        gestrichen = []
        if plan["ohne"] or plan["ohne_alle"]:
            geprueft = []
            for seite, prompt in paare:
                aus = ", ".join(x for x in (plan["ohne"].get(seite, ""),
                                            plan["ohne_alle"]) if x)
                if aus:
                    prompt, weg = torwaechter(prompt, aus)
                    gestrichen += [f"{sechsseiten.SEITEN[seite][0]}: {w}"
                                   for w in weg]
                geprueft.append((seite, prompt))
            paare = geprueft
        current["tor"] = gestrichen
        seed = int(params.get("seed") or 42)

        # Der Eintrag steht in der Liste, bevor das erste Bild gerechnet ist.
        # Bricht der Lauf in der Mitte ab, ist damit sichtbar, was entstanden
        # ist und was fehlt.
        if vorher:
            # Derselbe Seed wie beim ersten Bild: dasselbe Ausgangsrauschen
            # haelt Farbe und Anmutung naeher an dem, was man gesehen hat.
            seed = int(vorher.get("seed") or seed)
            eintrag = sechsseiten.nachtragen(
                projekt, vorher["id"], prompt=text, stil=stil,
                sichten=sichten, hintergrund=hintergrund, ohne=plan["ohne"])
        else:
            eintrag = sechsseiten.anlegen(
                projekt, str(params.get("name") or ""),
                beschreibung=str(params.get("text") or ""),
                prompt=text, stil=stil, seed=seed, sichten=sichten,
                hintergrund=hintergrund, ohne=plan["ohne"])
        current["seiten"] = {"id": eintrag["id"], "projekt": projekt,
                             "name": eintrag["name"], "prompt": text,
                             # Damit zu sehen ist, wie das Sprachmodell den
                             # Gegenstand von jeder Seite gelesen hat --
                             # daran liegt es, wenn eine Ansicht danebengeht.
                             "sichten": sichten,
                             "bilder": dict(eintrag.get("bilder") or {})}
        melden("Die sechs Seiten werden gerechnet", 0, len(paare))

        def sammler(meta, image):
            seite, gerechnet = paare[meta["index"] - 1]
            datei = sechsseiten.ablegen(projekt, eintrag["id"], seite, image,
                                        prompt=gerechnet, seed=meta["seed"])
            # Die Liste neu setzen statt sie zu ergaenzen: der Server liest
            # sie im selben Augenblick fuer `/api/status`, und ein Wachsen
            # mitten im Serialisieren waere ein Fehler aus dem Nichts.
            current["seiten"] = {
                **current["seiten"],
                "bilder": {**current["seiten"]["bilder"], seite: datei}}
            melden(f"{sechsseiten.SEITEN[seite][0]} ist fertig",
                   meta["index"], len(paare))

        engine.run_series(
            **_series_kwargs(
                {"base": int(params.get("base", 1024)),
                 "steps": int(params.get("steps", 30)),
                 # Quadratisch: ein Katalog zeigt die sechs Seiten
                 # nebeneinander, und ein Format wuerde zu einer der sechs
                 # Ansichten immer schlecht passen.
                 "aspect": "1:1", "seed": seed,
                 # Derselbe Seed fuer alle sechs. Dasselbe Ausgangsrauschen
                 # haelt Groesse, Farbe und Anmutung ueber die Bilder
                 # zusammen -- das einzige Mittel dafuer, das bleibt, wenn
                 # kein Vorlagenbild in Frage kommt.
                 "lock_seed": True},
                [], "t2i", sammler),
            prompts=[p for _, p in paare])

        melden("")
        fertig = len([s for s in current["seiten"]["bilder"]
                      if s in sechsseiten.SEITEN])
        engine.note("idle",
                    f"Katalogeintrag fertig: {fertig} von {len(paare)} Seiten"
                    if fertig else "abgebrochen")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        melden("")
        engine.note("idle", "Die sechs Seiten sind fehlgeschlagen")


def _erstes_bild(params: dict, projekt: str) -> None:
    """Die erste Stufe: der Gegenstand einmal, als Probe.

    Legt den Katalogeintrag an. Die sechs Seiten kommen spaeter in denselben
    Eintrag, mit demselben Gegenstandstext und demselben Seed.
    """
    plan = _gegenstandsplan(params, projekt, nur_gegenstand=True)
    text, stil = plan["text"], str(params.get("stil") or "")
    prompt = sechsseiten.erster_prompt(text, stil, plan["hintergrund"])
    if not prompt:
        raise RuntimeError("Aus der Beschreibung laesst sich kein Prompt bilden")
    seed = int(params.get("seed") or 42)
    eintrag = sechsseiten.anlegen(
        projekt, str(params.get("name") or ""),
        beschreibung=str(params.get("text") or ""), prompt=text, stil=stil,
        seed=seed, hintergrund=plan["hintergrund"], ohne=plan["ohne"])
    current["seiten"] = {"id": eintrag["id"], "projekt": projekt,
                         "name": eintrag["name"], "prompt": text,
                         "sichten": {}, "bilder": {}}
    melden("Das erste Bild wird gerechnet", 0, 1)

    def sammler(meta, image):
        datei = sechsseiten.ablegen(projekt, eintrag["id"], sechsseiten.ERSTES,
                                    image, prompt=prompt, seed=meta["seed"])
        current["seiten"] = {**current["seiten"],
                             "bilder": {sechsseiten.ERSTES: datei}}

    engine.run_series(
        **_series_kwargs(
            {"base": int(params.get("base", 1024)),
             "steps": int(params.get("steps", 30)),
             "aspect": "1:1", "seed": seed, "lock_seed": True},
            [], "t2i", sammler),
        prompts=[prompt])
    melden("")
    engine.note("idle", "Erstes Bild fertig" if current["seiten"]["bilder"]
                else "abgebrochen")


def run_detektor(params: dict) -> None:
    """Ein Detektor-Training. Laeuft als Auftrag, weil es die Karte fuer sich braucht."""
    try:
        engine._cancel = False
        engine.aborted = False
        erg = detektor.trainieren(
            _projekt_des_laufs, str(params.get("modell") or "dfine-nano"),
            max(1, min(1000, int(params.get("epochen") or 50))),
            int(params.get("bildgroesse") or 640),
            max(0.05, min(0.5, float(params.get("val_anteil") or 0.2))),
            melden, lambda: engine._cancel)
        melden("")
        current["detektor"] = erg
        engine.note("idle", "Training abgebrochen" if engine.aborted else
                    f"Training fertig: {erg['lauf']} · {erg['train']} Bilder Training, "
                    f"{erg['val']} Validierung")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        melden("")
        engine.note("error", current["error"])


def run_demo(params: dict) -> None:
    """Arbeitet einen Ablauf ab und baut daraus ein Video."""
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        fest = {"base": int(params.get("base", 1024)),
                "steps": int(params.get("steps", 24)), "true_cfg_scale": 1.0}
        seed = int(params.get("seed") or 3100)

        # Was hinter der Person steht. Ohne Angabe eine aus dem Seed
        # abgeleitete -- so wechselt die Kulisse von Lauf zu Lauf.
        kulisse = demo.kulisse_waehlen(params.get("kulisse") or "", seed)

        eigenes = {"prompt": params.get("prompt") or ""}
        if eigenes["prompt"].strip():
            engine.note("loading", "Eingaben werden übersetzt …")
            current["translated"] = chat.translate(eigenes)
            eigenes.update(current["translated"])

        gesammelt: list[str] = []

        def sammler(meta, image):
            name = _save(meta, image, stamp, "demo", nummer=len(current["files"]) + 1)
            current["files"].append(name)
            gesammelt.append(name)

        def pruefe():
            if engine.aborted:
                raise Abgebrochen()

        def laden(datei):
            bild = Image.open(os.path.join(ziel(), datei))
            bild.load()
            return bild

        # --- Startbild ---------------------------------------------------
        # "ohne_basis" kommt von einer einzelnen Szene. Dort ist das
        # Startbild ein zweites Bild, das niemand bestellt hat -- und seine
        # Bewahrungsklausel ("dieselbe Person wie im Referenzbild") passt
        # nicht, wenn in der Szene ganz andere Figuren stehen.
        if params.get("ohne_basis"):
            return _demo_ohne_basis(params, stamp, fest, seed, sammler,
                                    pruefe, gesammelt)
        pruefe()
        current["stage"] = "Startbild"
        if params.get("image"):
            basis_bild = decode(params["image"]).convert("RGBA")
            basis_datei = _save({"index": 1, "seed": seed, "prompt": "hochgeladenes Startbild"},
                                basis_bild, stamp, "demo", nummer=1)
            current["files"].append(basis_datei)
        else:
            engine.run_series(**_series_kwargs(
                {"mode": "t2i",
                 "prompt": eigenes["prompt"] or demo.basis_prompt(kulisse),
                 "aspect": "3:2", "seed": seed, "count": 1, **fest}, [], "t2i", sammler))
            if not gesammelt:
                pruefe()
                raise RuntimeError("Das Startbild konnte nicht erzeugt werden")
            basis_datei = gesammelt[-1]
            basis_bild = laden(basis_datei)

        # Erst das Startbild ansehen, dann den Ablauf bauen. Zweierlei kommt
        # dabei heraus: manche Schritte passen nicht zu jedem Bild (ein Bart
        # bei einer Frau), und die Beschreibung der Person schaerft danach
        # jede Bewahrungsklausel.
        current["stage"] = "Startbild wird gelesen"
        with open(os.path.join(ziel(), basis_datei), "rb") as fh:
            gelesen = chat.bild_lesen(fh.read())
        current["gelesen"] = gelesen

        # Zu einem hochgeladenen Bild darf man selbst sagen, was darauf zu
        # sehen ist. Das schlaegt die maschinelle Lesung: wer sein eigenes
        # Foto beschreibt, trifft es genauer als ein Blick des Modells.
        eigene = (eigenes["prompt"] or "").strip() if params.get("image") else ""
        if eigene:
            gelesen = dict(gelesen, beschreibung=eigene)
            current["gelesen"] = gelesen

        bloecke = params.get("bloecke")
        if not bloecke:
            name = params.get("ablauf") or "reise"
            eintrag = ablauf.ABLAEUFE.get(name) or ablauf.ABLAEUFE["reise"]
            bloecke = eintrag["bauen"](kulisse, gelesen["geschlecht"] == "frau")
        # Auch ein selbst zusammengestellter Ablauf profitiert davon.
        bloecke = ablauf.mit_beschreibung(bloecke, gelesen["beschreibung"])
        gesamt = ablauf.zu_erzeugen(bloecke)

        # --- Bloecke abarbeiten -------------------------------------------
        je_block: dict[int, list[str]] = {}
        letztes = basis_datei
        zaehler = 1
        for art, buendel in _bloecke_gruppieren(bloecke):
            pruefe()
            namen = [b["titel"] for b in buendel]
            current["stage"] = (f"{', '.join(namen)} · "
                                f"{zaehler + 1}–{zaehler + sum(len(ablauf.bausteine_von(b)) for b in buendel)}"
                                f"/{gesamt}")
            gesammelt.clear()

            if art == "gruppe":
                # Der Gruppen-Pfad, nicht der Bearbeiten-Pfad: letzterer
                # verschmilzt zwei Ansichten derselben Person zu einer. Der
                # Baustein des Blocks geht als Zusatz in die Anweisung und
                # stellt klar, dass zwei Figuren gemeint sind.
                engine.run_series(**_series_kwargs(
                    {"mode": "gruppe", "action": "zusammen",
                     "prompt": ablauf.gruppen_prompt(buendel[0]),
                     "aspect": "3:2", "follow_reference": False, "seed": seed,
                     "count": 1, **fest},
                    [laden(letztes), basis_bild], "gruppe", sammler))
            else:
                vorlage = basis_bild if art == "start" else laden(letztes)
                schritte = [s for b in buendel
                            for s in ablauf.schritte([b])]
                engine.run_series(
                    **_series_kwargs(
                        {"mode": "edit", "prompt": "", "seed": seed,
                         "follow_reference": True, **fest}, [vorlage], "edit", sammler),
                    # Der Torwaechter gilt auch hier: ein Ablauf soll
                    # ausgeschlossene Dinge genauso wenig zeigen.
                    prompts=[_durchs_tor(s["prompt"], params) for s in schritte],
                    seeds=[seed if s["fest"] else seed + zaehler + i
                           for i, s in enumerate(schritte)])

            erwartet = sum(len(ablauf.bausteine_von(b)) for b in buendel)
            if len(gesammelt) < erwartet:
                pruefe()
                raise RuntimeError(f"nur {len(gesammelt)} von {erwartet} Bildern")

            rest = iter(gesammelt)
            for block in buendel:
                je_block[id(block)] = [next(rest) for _ in ablauf.bausteine_von(block)]
            letztes = gesammelt[-1]
            zaehler += erwartet

        # --- Reihenfolge fuers Video ---------------------------------------
        reihenfolge = [basis_datei]
        for block in bloecke:
            reihenfolge += je_block.get(id(block), [])
            if block.get("zurueck"):
                reihenfolge.append(basis_datei)

        # "ohne_video" kommt von einer einzelnen Szene: dort sind die
        # Bilder gewollt, das Zusammenbauen waere verlorene Zeit. Fehlt der
        # Wert, wird gebaut wie bisher.
        if demo.available()["video"] and not params.get("ohne_video"):
            pruefe()
            current["stage"] = "Video wird gebaut"
            video_ziel = os.path.join(ziel(), f"{stamp}_demonstration.mp4")
            demo.baue_video([os.path.join(ziel(), n) for n in reihenfolge], video_ziel,
                            gesamtdauer=float(params.get("duration") or 20.0))
            current["video"] = os.path.basename(video_ziel)

        melden("")
        engine.note("idle", f"Ablauf fertig: {len(reihenfolge)} Bilder im Video")
    except Abgebrochen:
        melden("")
        engine.note("idle", f"abgebrochen nach {len(current['files'])} Bild(ern)")
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        current["error"] = err.strip().splitlines()[-1]
        engine.note("error", current["error"])
    # Die Sperre haelt und loest der Arbeiter -- siehe _abarbeiten().
