"""Einen D-FINE-Detektor auf dem Datensatz trainieren -- als eigener Prozess.

Aufgerufen von `detektor.py`, nie vom Server direkt: ein Training belegt die
Karte eine Weile, und ein eigener Prozess gibt sie am Ende bestimmt wieder
frei, auch wenn er abgebrochen wird.

D-FINE statt Ultralytics YOLO der Lizenz wegen: D-FINE und seine Gewichte
stehen unter Apache 2.0, Ultralytics unter AGPL-3.0 -- und Ultralytics
rechnet die trainierten Gewichte mit dazu. D-FINE kommt mit `transformers`,
das ohnehin installiert ist.

    python detektor_lauf.py trainieren <auftrag.json>
    python detektor_lauf.py erkennen <gewichte-ordner> <bild> <schwelle>

Je Epoche eine Zeile in `ergebnisse.csv` -- dieselben Kennzahlen, die man von
YOLO kennt: Praezision, Trefferquote, mAP50, mAP50-95.
"""

import csv
import json
import math
import os
import random
import sys
import time

import torch
from PIL import Image, ImageDraw
from transformers import AutoImageProcessor, AutoModelForObjectDetection


# --- Kennzahlen -------------------------------------------------------------
def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    schnitt = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    gesamt = ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - schnitt)
    return schnitt / gesamt if gesamt > 0 else 0.0


def _ap(vorhersagen, wahrheit, klasse, schwelle_iou) -> float:
    """Average Precision einer Klasse bei einer IoU-Schwelle, COCO-artig
    mit 101 Stuetzstellen."""
    soll = {i: [g for g, k in w if k == klasse] for i, w in enumerate(wahrheit)}
    anzahl = sum(len(v) for v in soll.values())
    if not anzahl:
        return float("nan")
    liste = sorted(((s, i, b) for i, v in enumerate(vorhersagen)
                    for b, k, s in v if k == klasse), key=lambda t: -t[0])
    vergeben = {i: [False] * len(v) for i, v in soll.items()}
    tp, fp = [], []
    for _, i, box in liste:
        beste, wo = 0.0, -1
        for j, g in enumerate(soll[i]):
            wert = _iou(box, g)
            if wert > beste:
                beste, wo = wert, j
        if beste >= schwelle_iou and not vergeben[i][wo]:
            vergeben[i][wo] = True
            tp.append(1), fp.append(0)
        else:
            tp.append(0), fp.append(1)
    praez, treffer, ztp, zfp = [], [], 0, 0
    for a, b in zip(tp, fp):
        ztp += a
        zfp += b
        praez.append(ztp / (ztp + zfp))
        treffer.append(ztp / anzahl)
    for i in range(len(praez) - 2, -1, -1):
        praez[i] = max(praez[i], praez[i + 1])
    summe = 0.0
    for r in (x / 100 for x in range(101)):
        summe += next((p for p, t in zip(praez, treffer) if t >= r), 0.0)
    return summe / 101


def kennzahlen(vorhersagen, wahrheit, klassen: int) -> dict:
    """mAP50, mAP50-95, und Praezision und Trefferquote an der Schwelle mit
    dem besten F1 -- so berichtet es auch YOLO.

    Eine feste Schwelle von 0,5 taugte nicht: D-FINE vergibt nach wenigen
    Epochen niedrige Werte, und gemessen stand dort 0,0, waehrend mAP50
    schon bei 1,0 lag.
    """
    def mittel(werte):
        werte = [w for w in werte if not math.isnan(w)]
        return sum(werte) / len(werte) if werte else 0.0
    map50 = mittel([_ap(vorhersagen, wahrheit, k, 0.5) for k in range(klassen)])
    map5095 = mittel([mittel([_ap(vorhersagen, wahrheit, k, t / 100)
                              for t in range(50, 100, 5)]) for k in range(klassen)])
    alle = sum(len(w) for w in wahrheit)
    beste = (0.0, 0.0, -1.0)
    for schwelle in (x / 20 for x in range(1, 20)):
        tp = fp = 0
        for v, w in zip(vorhersagen, wahrheit):
            offen = list(w)
            for box, k, s in sorted(v, key=lambda t: -t[2]):
                if s < schwelle:
                    continue
                treffer = next((g for g in offen
                                if g[1] == k and _iou(box, g[0]) >= 0.5), None)
                if treffer:
                    offen.remove(treffer)
                    tp += 1
                else:
                    fp += 1
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / alle if alle else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        if f1 > beste[2]:
            beste = (p, r, f1)
    return {"praezision": beste[0], "trefferquote": beste[1],
            "map50": map50, "map50_95": map5095}


# --- Daten ------------------------------------------------------------------
class Daten(torch.utils.data.Dataset):
    """Bilder mit ihren Boxen. Beim Training zufaellig gespiegelt und in
    Helligkeit und Kontrast leicht verschoben -- mehr braucht es bei
    erzeugten Bildern nicht, die Abwechslung kommt aus den Varianten."""

    def __init__(self, eintraege, ordner, klassen, prozessor, lernen: bool):
        self.e, self.ordner, self.klassen = eintraege, ordner, klassen
        self.p, self.lernen = prozessor, lernen

    def __len__(self):
        return len(self.e)

    def __getitem__(self, i):
        e = self.e[i]
        bild = Image.open(os.path.join(self.ordner, e["datei"])).convert("RGB")
        x1, y1, x2, y2 = e["box"]
        if self.lernen and random.random() < 0.5:
            bild = bild.transpose(Image.FLIP_LEFT_RIGHT)
            x1, x2 = bild.width - x2, bild.width - x1
        if self.lernen:
            from PIL import ImageEnhance
            bild = ImageEnhance.Brightness(bild).enhance(random.uniform(0.8, 1.2))
            bild = ImageEnhance.Contrast(bild).enhance(random.uniform(0.8, 1.2))
        anm = {"image_id": i, "annotations": [{
            "bbox": [x1, y1, x2 - x1, y2 - y1], "area": (x2 - x1) * (y2 - y1),
            "category_id": self.klassen.index(e["klasse"]), "iscrowd": 0}]}
        aus = self.p(images=bild, annotations=anm, return_tensors="pt")
        return aus["pixel_values"][0], aus["labels"][0]


def _buendeln(stapel):
    return torch.stack([s[0] for s in stapel]), [s[1] for s in stapel]


# --- Training ---------------------------------------------------------------
def trainieren(auftrag_datei: str) -> None:
    with open(auftrag_datei, encoding="utf-8") as fh:
        a = json.load(fh)
    random.seed(0)
    torch.manual_seed(0)
    geraet = "cuda" if torch.cuda.is_available() else "cpu"
    ziel = a["ziel"]
    os.makedirs(ziel, exist_ok=True)
    klassen = a["klassen"]

    groesse = int(a["bildgroesse"])
    prozessor = AutoImageProcessor.from_pretrained(
        a["modell"], size={"height": groesse, "width": groesse})
    modell = AutoModelForObjectDetection.from_pretrained(
        a["modell"], id2label=dict(enumerate(klassen)),
        label2id={k: i for i, k in enumerate(klassen)},
        ignore_mismatched_sizes=True).to(geraet)

    train = Daten(a["train"], a["bilder"], klassen, prozessor, True)
    val = Daten(a["val"], a["bilder"], klassen, prozessor, False)
    # Kleine Datensaetze brauchen kleine Stapel: sonst sind 50 Epochen nur
    # 50 Lernschritte, und das Modell erkennt danach noch immer Kennzeichen
    # und Ruecklichter aus seinem Vortraining statt der neuen Klasse.
    # Gemessen an sechs Bildern: Stapel 6, 40 Epochen -> mAP50 0,02;
    # Stapel 2, 120 Epochen -> 1,0.
    stapel = int(a.get("stapel") or min(8, max(2, len(a["train"]) // 4)))
    lader = torch.utils.data.DataLoader(train, batch_size=stapel, shuffle=True,
                                        collate_fn=_buendeln, num_workers=2,
                                        drop_last=len(train) > stapel)
    epochen = int(a["epochen"])
    # Das Rueckgrat kennt Bilder schon; es lernt langsamer als der Kopf, der
    # die neue Klasse erst lernen muss.
    rueckgrat = [p for n, p in modell.named_parameters() if "backbone" in n]
    rest = [p for n, p in modell.named_parameters() if "backbone" not in n]
    optimierer = torch.optim.AdamW([{"params": rueckgrat, "lr": 1e-5},
                                    {"params": rest, "lr": 1e-4}], weight_decay=1e-4)
    schritte = max(1, epochen * len(lader))
    plan = torch.optim.lr_scheduler.LambdaLR(
        optimierer, lambda s: min(1.0, (s + 1) / min(200, schritte // 10 + 1))
        * 0.5 * (1 + math.cos(math.pi * min(s, schritte) / schritte)))

    csv_pfad = os.path.join(ziel, "ergebnisse.csv")
    with open(csv_pfad, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["epoch", "train/loss", "metrics/precision(B)",
                                 "metrics/recall(B)", "metrics/mAP50(B)",
                                 "metrics/mAP50-95(B)", "zeit"])
    beste = -1.0
    beginn = time.time()
    for epoche in range(1, epochen + 1):
        modell.train()
        verlust, n = 0.0, 0
        for pixel, labels in lader:
            pixel = pixel.to(geraet)
            labels = [{k: v.to(geraet) for k, v in l.items()} for l in labels]
            with torch.autocast(geraet, dtype=torch.bfloat16, enabled=geraet == "cuda"):
                aus = modell(pixel_values=pixel, labels=labels)
            optimierer.zero_grad()
            aus.loss.backward()
            torch.nn.utils.clip_grad_norm_(modell.parameters(), 0.1)
            optimierer.step()
            plan.step()
            verlust += float(aus.loss)
            n += 1
        zahlen = auswerten(modell, prozessor, a["val"], a["bilder"], klassen, geraet)
        with open(csv_pfad, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([epoche, round(verlust / max(n, 1), 5),
                                     round(zahlen["praezision"], 5),
                                     round(zahlen["trefferquote"], 5),
                                     round(zahlen["map50"], 5),
                                     round(zahlen["map50_95"], 5),
                                     round(time.time() - beginn)])
        if zahlen["map50_95"] > beste:
            beste = zahlen["map50_95"]
            modell.save_pretrained(os.path.join(ziel, "gewichte"))
            prozessor.save_pretrained(os.path.join(ziel, "gewichte"))
    beispiele(os.path.join(ziel, "gewichte"), a["val"][:4], a["bilder"],
              os.path.join(ziel, "val_vorhersagen.jpg"), geraet)


@torch.no_grad()
def _vorhersagen(modell, prozessor, bilder, geraet, schwelle=0.001):
    eingabe = prozessor(images=bilder, return_tensors="pt").to(geraet)
    aus = modell(**eingabe)
    return prozessor.post_process_object_detection(
        aus, threshold=schwelle, target_sizes=[b.size[::-1] for b in bilder])


@torch.no_grad()
def auswerten(modell, prozessor, eintraege, ordner, klassen, geraet) -> dict:
    modell.eval()
    vorher, wahr = [], []
    for i in range(0, len(eintraege), 8):
        teil = eintraege[i:i + 8]
        bilder = [Image.open(os.path.join(ordner, e["datei"])).convert("RGB") for e in teil]
        for e, r in zip(teil, _vorhersagen(modell, prozessor, bilder, geraet)):
            vorher.append([(b.tolist(), int(k), float(s)) for b, k, s
                           in zip(r["boxes"], r["labels"], r["scores"])])
            wahr.append([(e["box"], klassen.index(e["klasse"]))])
    return kennzahlen(vorher, wahr, len(klassen))


def beispiele(gewichte, eintraege, ordner, ziel, geraet) -> None:
    """Vier Validierungsbilder mit Vorhersage (rot) und Wahrheit (gruen)."""
    if not eintraege or not os.path.isdir(gewichte):
        return
    prozessor = AutoImageProcessor.from_pretrained(gewichte)
    modell = AutoModelForObjectDetection.from_pretrained(gewichte).to(geraet).eval()
    kacheln = []
    for e in eintraege:
        bild = Image.open(os.path.join(ordner, e["datei"])).convert("RGB")
        r = _vorhersagen(modell, prozessor, [bild], geraet, 0.3)[0]
        zeichnen = ImageDraw.Draw(bild)
        zeichnen.rectangle(e["box"], outline=(0, 220, 0), width=4)
        for b, s in zip(r["boxes"].tolist(), r["scores"].tolist()):
            zeichnen.rectangle(b, outline=(255, 40, 40), width=4)
            zeichnen.text((b[0] + 4, b[1] + 4), f"{s:.2f}", fill=(255, 40, 40))
        bild.thumbnail((640, 640))
        kacheln.append(bild)
    breite = sum(k.width for k in kacheln)
    blatt = Image.new("RGB", (breite, max(k.height for k in kacheln)), "white")
    x = 0
    for k in kacheln:
        blatt.paste(k, (x, 0))
        x += k.width
    blatt.save(ziel, quality=88)


def erkennen(gewichte: str, bild_pfad: str, schwelle: float) -> None:
    """Ein Bild, auf der CPU -- damit es neben einem Bildauftrag laeuft."""
    prozessor = AutoImageProcessor.from_pretrained(gewichte)
    modell = AutoModelForObjectDetection.from_pretrained(gewichte).eval()
    bild = Image.open(bild_pfad).convert("RGB")
    r = _vorhersagen(modell, prozessor, [bild], "cpu", schwelle)[0]
    namen = modell.config.id2label
    print(json.dumps([{"box": [round(v) for v in b], "wert": round(float(s), 3),
                       "klasse": namen.get(int(k), str(int(k)))}
                      for b, k, s in zip(r["boxes"].tolist(), r["labels"].tolist(),
                                         r["scores"].tolist())]))


if __name__ == "__main__":
    if sys.argv[1] == "trainieren":
        trainieren(sys.argv[2])
    elif sys.argv[1] == "erkennen":
        erkennen(sys.argv[2], sys.argv[3], float(sys.argv[4]))
