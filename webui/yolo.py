"""YOLO auf dem eigenen Datensatz trainieren, ansehen und ausprobieren.

Ultralytics laeuft in einer eigenen Umgebung, `yolo_umgebung/`. Es bringt
eigene Abhaengigkeiten mit (OpenCV, Polars ...), und die Bildumgebung soll
davon unberuehrt bleiben -- dort haengt alles an genau abgestimmten
Versionen. PyTorch dagegen teilen sich beide: eine `.pth`-Datei in der
YOLO-Umgebung zeigt auf das von `qwen_bild`. Das spart rund fuenf Gigabyte,
und die Karte sieht dieselbe CUDA-Fassung.

Ein Training ist ein Auftrag in der Warteschlange wie jedes Bild. Es braucht
die Karte fuer sich, und ein Bild daneben brauchte sie auch.

Ablage je Projekt:

    projekte/<p>/datensatz/train.txt, val.txt, yolo.yaml   die Aufteilung
    projekte/<p>/yolo/<lauf>/                               was Ultralytics schreibt
        weights/best.pt  results.csv  args.yaml  *.png     (Kurven, Beispiele)
"""

import csv
import hashlib
import json
import os
import re
import subprocess
import time

import datensatz
import projekte

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(ROOT, "yolo_umgebung", "bin", "python")


def _umgebung() -> dict:
    """Eigene Ultralytics-Einstellungen statt der globalen.

    Die globalen unter ~/.config/Ultralytics gehoeren einem anderen Vorhaben
    -- dort zeigte `weights_dir` in dessen Verzeichnis, und das Training
    brach mit "Permission denied" ab. Hier steht alles in der YOLO-Umgebung.
    """
    # Der Ordner muss bestehen: fehlt er, weicht Ultralytics wortlos nach
    # /tmp aus und legt seine Gewichte dann irgendwo ab.
    ordner = os.path.join(ROOT, "yolo_umgebung", "einstellungen")
    os.makedirs(ordner, exist_ok=True)
    return {**os.environ, "YOLO_CONFIG_DIR": ordner}

MODELLE = {"yolo11n": "Nano -- schnell, fuer den Anfang",
           "yolo11s": "Small -- genauer, doppelt so lange",
           "yolo11m": "Medium -- noch genauer, braucht viele Bilder"}
LAUF = re.compile(r"\d{8}-\d{6}_yolo11[nsm]")
BILD = re.compile(r"[\w.\-]+\.(?:png|jpg)")


def verfuegbar() -> bool:
    return os.path.isfile(PYTHON)


def ordner(projekt: str) -> str:
    pfad = os.path.join(projekte.ordner(projekt), "yolo")
    os.makedirs(pfad, exist_ok=True)
    return pfad


# --- Aufteilung -----------------------------------------------------------
def _gruppe(datei: str) -> str:
    """Bilder eines Auftrags gehoeren zusammen in train oder in val.

    Varianten eines Laufs aehneln sich -- verteilt auf beide Seiten, mess
    die Validierung nur, wie gut YOLO den Nachbarn wiedererkennt.
    """
    teile = datei.split("_")
    return "_".join(teile[:2]) if len(teile) > 2 else datei


def aufteilen(projekt: str, val_anteil: float) -> dict:
    """train.txt, val.txt und yolo.yaml schreiben -- stabil ueber den Namen.

    Dieselbe Gruppe landet bei jedem Lauf auf derselben Seite, auch wenn
    neue Bilder dazukommen. Sonst wanderten Bilder zwischen train und val,
    und zwei Laeufe waeren nicht vergleichbar.
    """
    wurzel = datensatz.wurzel(projekt)
    bilder = sorted(e["datei"] for e in datensatz.eintraege(projekt)
                    if e.get("status") == "ok")
    if len(bilder) < 2:
        raise RuntimeError("Fuer ein Training braucht es mindestens zwei "
                           "aufgenommene Bilder im Datensatz")
    gruppen = sorted({_gruppe(b) for b in bilder})
    wert = lambda g: int(hashlib.sha1(g.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF  # noqa: E731
    val_gruppen = {g for g in gruppen if wert(g) < val_anteil}
    # Mindestens eine Gruppe auf jeder Seite, sonst gibt es nichts zu messen
    # oder nichts zu lernen.
    if not val_gruppen and len(gruppen) > 1:
        val_gruppen = {min(gruppen, key=wert)}
    if val_gruppen == set(gruppen) and len(gruppen) > 1:
        val_gruppen.discard(max(gruppen, key=wert))
    train = [b for b in bilder if _gruppe(b) not in val_gruppen]
    val = [b for b in bilder if _gruppe(b) in val_gruppen]
    hinweis = ""
    if len(gruppen) == 1:
        # Nur ein Auftrag: dann eben bildweise, mit dem Hinweis, dass die
        # Zahlen geschoent sind.
        val = [b for b in bilder if wert(b) < val_anteil] or bilder[:1]
        train = [b for b in bilder if b not in val]
        hinweis = ("Alle Bilder stammen aus einem Auftrag -- die Validierung "
                   "ist darum zu optimistisch.")
    for name, liste in (("train.txt", train), ("val.txt", val)):
        with open(os.path.join(wurzel, name), "w", encoding="utf-8") as fh:
            fh.write("".join(os.path.join(wurzel, "images", b) + "\n" for b in liste))
    with open(os.path.join(wurzel, "yolo.yaml"), "w", encoding="utf-8") as fh:
        fh.write(f"path: {wurzel}\ntrain: train.txt\nval: val.txt\nnames:\n"
                 + "".join(f"  {i}: {n}\n" for i, n in enumerate(datensatz.klassen(projekt))))
    return {"train": len(train), "val": len(val), "hinweis": hinweis,
            "yaml": os.path.join(wurzel, "yolo.yaml")}


# --- Training -------------------------------------------------------------
def trainieren(projekt: str, modell: str, epochen: int, bildgroesse: int,
               val_anteil: float, melden, abbrechen) -> dict:
    """Ein Training als eigener Prozess in der YOLO-Umgebung.

    `melden(text, ist, von)` bekommt den Fortschritt aus results.csv,
    `abbrechen()` sagt, ob der Benutzer gestoppt hat.
    """
    if not verfuegbar():
        raise RuntimeError("Die YOLO-Umgebung fehlt (yolo_umgebung/)")
    if modell not in MODELLE:
        raise RuntimeError(f"Unbekanntes Modell: {modell}")
    teilung = aufteilen(projekt, val_anteil)
    name = time.strftime("%Y%m%d-%H%M%S") + "_" + modell
    ziel = ordner(projekt)
    befehl = [PYTHON, "-c",
              "import sys; from ultralytics import YOLO; "
              "YOLO(sys.argv[1]).train(data=sys.argv[2], epochs=int(sys.argv[3]), "
              "imgsz=int(sys.argv[4]), project=sys.argv[5], name=sys.argv[6], "
              "exist_ok=False, plots=True, verbose=False, workers=2)",
              modell + ".pt", teilung["yaml"], str(epochen), str(bildgroesse), ziel, name]
    protokoll = os.path.join(ziel, name + ".log")
    with open(protokoll, "w", encoding="utf-8") as log:
        # Im YOLO-Ordner gestartet: dort legt Ultralytics die geladenen
        # Grundgewichte (yolo11n.pt ...) ab, nicht im Programmverzeichnis.
        prozess = subprocess.Popen(befehl, cwd=ziel, stdout=log,
                                   stderr=subprocess.STDOUT, env=_umgebung())
        ergebnisse = os.path.join(ziel, name, "results.csv")
        while prozess.poll() is None:
            if abbrechen():
                prozess.terminate()
                try:
                    prozess.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    prozess.kill()
                break
            zeilen = _ergebnisse(ergebnisse)
            if zeilen:
                z = zeilen[-1]
                melden(f"YOLO trainiert · Epoche {z['epoche']}/{epochen} · "
                       f"mAP50 {z['map50']:.3f}", z["epoche"], epochen)
            else:
                melden("YOLO bereitet vor (Grundgewichte, Daten pruefen)", 0, epochen)
            time.sleep(3)
    if prozess.returncode not in (0, None) and not abbrechen():
        with open(protokoll, encoding="utf-8", errors="replace") as fh:
            ende = fh.read()[-600:]
        raise RuntimeError(f"YOLO ist abgebrochen: {ende.strip().splitlines()[-1] if ende.strip() else prozess.returncode}")
    return {"lauf": name, **teilung}


def _zahl(text) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _ergebnisse(pfad: str) -> list[dict]:
    """results.csv von Ultralytics, auf die Spalten gestutzt, die zaehlen."""
    try:
        with open(pfad, encoding="utf-8") as fh:
            roh = list(csv.DictReader(fh))
    except OSError:
        return []
    raus = []
    for z in roh:
        z = {k.strip(): v for k, v in z.items() if k}
        raus.append({"epoche": int(_zahl(z.get("epoch"))),
                     "box_loss": _zahl(z.get("train/box_loss")),
                     "praezision": _zahl(z.get("metrics/precision(B)")),
                     "trefferquote": _zahl(z.get("metrics/recall(B)")),
                     "map50": _zahl(z.get("metrics/mAP50(B)")),
                     "map50_95": _zahl(z.get("metrics/mAP50-95(B)"))})
    return raus


def laeufe(projekt: str) -> list[dict]:
    """Alle Trainingslaeufe eines Projekts, der neueste zuerst."""
    ziel = ordner(projekt)
    raus = []
    for name in sorted(os.listdir(ziel), reverse=True):
        pfad = os.path.join(ziel, name)
        if not LAUF.fullmatch(name) or not os.path.isdir(pfad):
            continue
        zeilen = _ergebnisse(os.path.join(pfad, "results.csv"))
        beste = max(zeilen, key=lambda z: z["map50_95"]) if zeilen else None
        einstellungen = {}
        try:
            with open(os.path.join(pfad, "args.yaml"), encoding="utf-8") as fh:
                for zeile in fh:
                    k, _, v = zeile.partition(":")
                    if k in ("epochs", "imgsz", "model", "batch"):
                        einstellungen[k] = v.strip()
        except OSError:
            pass
        raus.append({
            "name": name, "zeilen": zeilen, "beste": beste,
            "einstellungen": einstellungen,
            "gewichte": os.path.join(pfad, "weights", "best.pt")
            if os.path.isfile(os.path.join(pfad, "weights", "best.pt")) else "",
            "bilder": sorted(b for b in os.listdir(pfad) if BILD.fullmatch(b)),
        })
    return raus


def bildpfad(projekt: str, lauf: str, datei: str) -> str | None:
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") or not LAUF.fullmatch(lauf or "") \
            or not BILD.fullmatch(datei or ""):
        return None
    pfad = os.path.join(ordner(projekt), lauf, datei)
    return pfad if os.path.isfile(pfad) else None


# --- Ausprobieren ---------------------------------------------------------
def erkennen(projekt: str, lauf: str, bild_bytes: bytes, schwelle: float = 0.25) -> list[dict]:
    """Ein trainiertes Modell auf ein Bild loslassen -- auf der CPU.

    Die CPU, weil das in einer Sekunde erledigt ist und so neben einem
    laufenden Bildauftrag geht, ohne ihm die Karte streitig zu machen.
    """
    if not LAUF.fullmatch(lauf or ""):
        raise RuntimeError("Unbekannter Lauf")
    gewichte = os.path.join(ordner(projekt), lauf, "weights", "best.pt")
    if not os.path.isfile(gewichte):
        raise RuntimeError("Dieser Lauf hat keine fertigen Gewichte")
    eingabe = os.path.join(ordner(projekt), "probe_eingabe.png")
    with open(eingabe, "wb") as fh:
        fh.write(bild_bytes)
    skript = ("import sys, json; from ultralytics import YOLO; "
              "r = YOLO(sys.argv[1]).predict(sys.argv[2], conf=float(sys.argv[3]), "
              "device='cpu', verbose=False)[0]; "
              "print(json.dumps([{'box': [round(v) for v in b.xyxy[0].tolist()], "
              "'wert': round(float(b.conf), 3), 'klasse': r.names[int(b.cls)]} "
              "for b in r.boxes]))")
    aus = subprocess.run([PYTHON, "-c", skript, gewichte, eingabe, str(schwelle)],
                         capture_output=True, text=True, timeout=120,
                         cwd=ordner(projekt), env=_umgebung())
    if aus.returncode != 0:
        raise RuntimeError("YOLO-Erkennung fehlgeschlagen: "
                           + (aus.stderr.strip().splitlines() or ["?"])[-1])
    return json.loads(aus.stdout.strip().splitlines()[-1])
