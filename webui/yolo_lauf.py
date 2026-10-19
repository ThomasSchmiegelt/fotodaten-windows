"""Einen YOLO26-Detektor (Ultralytics) trainieren -- als eigener Prozess.

Aufgerufen von `detektor.py`, nie vom Server direkt, aus demselben Grund wie
D-FINE: ein eigener Prozess gibt die Karte am Ende bestimmt wieder frei.

    python yolo_lauf.py trainieren <auftrag.json>
    python yolo_lauf.py erkennen <best.pt> <bild> <schwelle>

**Lizenz.** Ultralytics steht unter AGPL-3.0 und zaehlt nach eigener
Auslegung die damit trainierten Gewichte mit dazu. Fuer Forschung und
eigenen Gebrauch ist das gleichgueltig; wer einen YOLO-Detektor weitergibt
oder in ein Produkt einbaut, braucht deren Enterprise-Lizenz oder nimmt
D-FINE (Apache 2.0) aus demselben Reiter.

Der Datensatz liegt schon im YOLO-Format vor (`datensatz/images`,
`datensatz/labels`). Hier entsteht nur eine `data.yaml` fuer genau diesen
Lauf, die auf `train.txt` und `val.txt` der Aufteilung zeigt -- dieselbe
Aufteilung, die D-FINE bekommt, damit sich beide Laeufe vergleichen lassen.

**6 GB.** Die Stapelgroesse waehlt Ultralytics selbst (`batch` als Anteil
des Grafikspeichers, Vorgabe 0,6): auf einer 6-GB-Karte ergibt das fuer
yolo26n bei 640 px rund 16 Bilder, fuer yolo26s rund 8. Gemischte
Genauigkeit (AMP) ist an. `QWEN_YOLO_BATCH` setzt die Stapelgroesse fest.
"""

import json
import os
import shutil
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HIER)
# Ultralytics legt Einstellungen und heruntergeladene Gewichte sonst unter
# %APPDATA% bzw. ins Arbeitsverzeichnis. Hier bleibt alles beim Programm --
# auch in der portablen Fassung auf einem USB-Stick.
MODELLE = os.environ.get("QWEN_YOLO_ORDNER") or os.path.join(ROOT, "modelle", "yolo")
os.makedirs(MODELLE, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(MODELLE, "einstellungen"))
os.environ.setdefault("YOLO_OFFLINE", "0")


def _batch():
    wert = os.environ.get("QWEN_YOLO_BATCH")
    if wert:
        return float(wert) if "." in wert else int(wert)
    return 0.6


def _yaml(a: dict) -> str:
    """data.yaml fuer diesen Lauf, mit eigener Bildliste daneben.

    Die Listen liegen beim Lauf und nicht im Datensatz: ein spaeteres
    Training schreibt dort train.txt neu, und dieser Lauf soll danach noch
    sagen koennen, womit er trainiert wurde. Die Labels findet Ultralytics
    selbst -- es ersetzt im Bildpfad `images` durch `labels`.
    """
    for name in ("train", "val"):
        with open(os.path.join(a["ziel"], name + ".txt"), "w", encoding="utf-8") as fh:
            fh.write("".join(os.path.join(a["bilder"], e["datei"]) + "\n" for e in a[name]))
    pfad = os.path.join(a["ziel"], "data.yaml")
    # Schraegstriche: YAML liest einen Backslash sonst als Fluchtzeichen.
    wurzel = a["ziel"].replace("\\", "/")
    with open(pfad, "w", encoding="utf-8") as fh:
        fh.write(f"path: {json.dumps(wurzel)}\ntrain: train.txt\nval: val.txt\n"
                 f"names:\n" + "".join(f"  {i}: {json.dumps(n)}\n"
                                       for i, n in enumerate(a["klassen"])))
    return pfad


def _ultralytics():
    """YOLO laden und Ultralytics' Ablageorte auf MODELLE festlegen.

    Ohne das legt es heruntergeladene Gewichte unter <Git-Wurzel>\\weights
    ab -- in der portablen Fassung also irgendwo, und beim naechsten Start
    fehlten sie wieder.
    """
    from ultralytics import YOLO, settings
    soll = {"weights_dir": MODELLE, "runs_dir": os.path.join(MODELLE, "laeufe"),
            "sync": False}
    if any(settings.get(k) != v for k, v in soll.items()):
        settings.update(soll)
    # WEIGHTS_DIR liest Ultralytics beim Import einmal aus den Einstellungen.
    # Beim allerersten Lauf stand dort noch der Vorgabeordner, und die
    # AMP-Pruefung legte yolo26n.pt unter <Ordner>\weights ab.
    from pathlib import Path
    import ultralytics.utils
    ultralytics.utils.WEIGHTS_DIR = Path(MODELLE)
    return YOLO


def _gewichte(name: str) -> str:
    """Ein Grundmodell wie "yolo26n.pt" als Pfad in MODELLE."""
    return name if os.path.isabs(name) else os.path.join(MODELLE, name)


def trainieren(auftrag_datei: str) -> None:
    with open(auftrag_datei, encoding="utf-8") as fh:
        a = json.load(fh)
    os.chdir(MODELLE)
    import torch
    YOLO = _ultralytics()

    ziel = a["ziel"]
    csv_ziel = os.path.join(ziel, "ergebnisse.csv")
    lauf = os.path.join(ziel, "yolo")

    modell = YOLO(_gewichte(a["modell"]))    # z. B. modelle/yolo/yolo26n.pt

    def nach_epoche(trainer):
        # Die Oberflaeche liest den Fortschritt aus ergebnisse.csv -- dieselben
        # Spaltennamen, die D-FINE schreibt, weil D-FINE sie von YOLO hat.
        quelle = os.path.join(str(trainer.save_dir), "results.csv")
        if os.path.isfile(quelle):
            shutil.copyfile(quelle, csv_ziel)

    modell.add_callback("on_fit_epoch_end", nach_epoche)
    geraet = 0 if torch.cuda.is_available() else "cpu"
    modell.train(
        data=_yaml(a), epochs=int(a["epochen"]), imgsz=int(a["bildgroesse"]),
        batch=_batch() if geraet == 0 else 4, device=geraet,
        project=ziel, name="yolo", exist_ok=True,
        # Unter Windows startet jeder Lader-Prozess Python neu; acht davon
        # kosten mehr Arbeitsspeicher, als sie an Tempo bringen.
        workers=2 if os.name == "nt" else 4,
        patience=max(20, int(a["epochen"]) // 3), seed=0, deterministic=False,
        plots=True, verbose=False, amp=geraet == 0)

    nach_epoche(modell.trainer)
    gewichte = os.path.join(ziel, "gewichte")
    os.makedirs(gewichte, exist_ok=True)
    for name in ("best.pt", "last.pt"):
        quelle = os.path.join(lauf, "weights", name)
        if os.path.isfile(quelle):
            shutil.copyfile(quelle, os.path.join(gewichte, name))
    # Beispielbilder fuer den Reiter: Wahrheit und Vorhersage der Validierung.
    for name in ("val_batch0_labels.jpg", "val_batch0_pred.jpg", "results.png",
                 "confusion_matrix.png", "BoxPR_curve.png"):
        quelle = os.path.join(lauf, name)
        if os.path.isfile(quelle):
            shutil.copyfile(quelle, os.path.join(ziel, name))


def erkennen(gewichte: str, bild_pfad: str, schwelle: float) -> None:
    """Ein Bild, auf der CPU -- damit es neben einem Bildauftrag laeuft."""
    os.chdir(MODELLE)
    modell = _ultralytics()(gewichte)
    r = modell.predict(bild_pfad, conf=schwelle, device="cpu", verbose=False)[0]
    namen = r.names
    print(json.dumps([{"box": [round(v) for v in b], "wert": round(float(s), 3),
                       "klasse": namen.get(int(k), str(int(k)))}
                      for b, k, s in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(),
                                         r.boxes.conf.tolist())]))


if __name__ == "__main__":
    if sys.argv[1] == "trainieren":
        trainieren(sys.argv[2])
    elif sys.argv[1] == "erkennen":
        erkennen(sys.argv[2], sys.argv[3], float(sys.argv[4]))
