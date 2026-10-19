"""Trainingsdaten: erzeugte Bilder mit Bounding Box, abgelegt als YOLO und COCO.

Die Box entsteht **nach** dem Bild, nicht mit ihm. Das Bildmodell kennt keine
Koordinaten, und sobald sich die Kamera aendert, wandert der Gegenstand im
Bild -- eine Box aus dem Basisbild stimmte dann nicht mehr.

Zwei Modelle schauen hin, und das ist der Kern:

    Qwen3-VL-2B      setzt die Box. Gemessen am Basisbild (Heck mit
                     Anhaengerkupplung): eine einzige, saubere Box um
                     Kugelkopf samt Steckdose.
    Grounding DINO   prueft gegen. Allein taugte es nicht: Werte um 0,3,
                     fuenf ueberlappende Teilboxen und eine ums ganze Auto.
                     Die Vereinigung seiner Teilboxen dagegen lag fast genau
                     auf der Box von Qwen3-VL.

Stimmen beide ueberein, ist die Box aufgenommen. Sonst kommt das Bild auf die
Pruefliste -- ein falsches Label schadet einem Detektor mehr als ein
fehlendes Bild.

Bei fester Kamera wird ausserdem mit der Box im Basisbild verglichen -- aber
nur zur Auskunft. Gemessen an sieben Varianten: auch ohne gewuerfelten
Winkel verschiebt und zoomt das Bildmodell den Ausschnitt (am Strand stand
das Auto halb so gross da), die Box sass trotzdem richtig. Als Bedingung
haette der Vergleich gute Bilder aussortiert.

Ablage je Projekt:

    projekte/<p>/datensatz/
        images/  labels/        aufgenommen -- genau das, was trainiert wird
        pruefen/                wartet auf ein Ja oder eine neue Box
        verworfen/              aussortiert, nicht geloescht
        klassen.txt  data.yaml  annotations.json (COCO)
        eintraege.json          je Bild: Box, Status, Gruende, Prompt, Achsen

Bilder ohne Box liegen bewusst nicht in images/: YOLO liest ein Bild ohne
Labeldatei als "hier ist nichts" und lernte damit genau das Falsche.
"""

import csv
import gc
import json
import os
import re
import shutil
import threading
import time

import projekte

VL_MODELL = os.environ.get("QWEN_BOX_MODELL", "Qwen/Qwen3-VL-2B-Instruct")
DINO_MODELL = os.environ.get("QWEN_BOX_PRUEFER", "IDEA-Research/grounding-dino-base")

# Ab hier gelten zwei Boxen als dieselbe.
GLEICH = 0.5
# Eine DINO-Box, die mehr als die Haelfte des Bildes deckt, meint das Auto.
ZU_GROSS = 0.5
# Umschliesst eine DINO-Box die VL-Box und ist so viel groesser, zaehlt sie
# als "das Ganze" und nicht als Teil des gesuchten Objekts.
GANZES = 8
# Nur DINO-Boxen ab diesem Wert zaehlen ueberhaupt.
DINO_SCHWELLE = 0.2
# Darunter passt Qwen3-VL-2B (~4,5 GB in bfloat16) nicht neben DINO auf die
# Karte. Dann wird in zwei Phasen gerechnet, wie beim Bildmodell: erst
# Qwen3-VL fuer alle Bilder auf der Karte, Karte leeren, dann DINO fuer alle.
# So reicht eine 6-GB-Karte. Erst unter VL_MINDESTENS rechnet Qwen3-VL auf
# der CPU -- gemessen rund anderthalb Minuten je Bild.
# QWEN_BOX_GERAET=cpu|cuda setzt das Geraet fest.
VL_KLEINE_KARTE = 8 * 1024 ** 3
VL_MINDESTENS = 5 * 1024 ** 3
# Die Erkenner sehen das Bild hoechstens so gross. Ein Handyfoto mit 12
# Megapixeln ergaebe fuer Qwen3-VL sonst zehntausend Bildtokens -- auf einer
# kleinen Karte zu viel, und genauer wird die Box davon nicht.
ANALYSE_KANTE = 1280
# Echte Fotos landen hoechstens so gross im Datensatz. Trainiert wird mit 640
# bis 1280; ein 4000er Original kostete nur Platte und Ladezeit.
FOTO_KANTE = 2048

ORDNER = {"ok": "images", "pruefen": "pruefen", "verworfen": "verworfen"}
DATEI = re.compile(r"[\w.\-]+\.png")
KLASSE = re.compile(r"[a-z0-9_]{1,40}")

_sperre = threading.Lock()


# --- Ablage ---------------------------------------------------------------
def wurzel(projekt: str) -> str:
    pfad = os.path.join(projekte.ordner(projekt), "datensatz")
    for unter in (*ORDNER.values(), "labels"):
        os.makedirs(os.path.join(pfad, unter), exist_ok=True)
    return pfad


def _eintraege_datei(projekt: str) -> str:
    return os.path.join(wurzel(projekt), "eintraege.json")


def eintraege(projekt: str) -> list[dict]:
    try:
        with open(_eintraege_datei(projekt), encoding="utf-8") as fh:
            daten = json.load(fh)
        return [e for e in daten if isinstance(e, dict) and e.get("datei")]
    except (OSError, json.JSONDecodeError):
        return []


def _speichern(projekt: str, daten: list[dict]) -> None:
    with open(_eintraege_datei(projekt), "w", encoding="utf-8") as fh:
        json.dump(daten, fh, ensure_ascii=False, indent=1)
    _formate(projekt, daten)


def klassen(projekt: str) -> list[str]:
    try:
        with open(os.path.join(wurzel(projekt), "klassen.txt"), encoding="utf-8") as fh:
            return [z.strip() for z in fh if z.strip()]
    except OSError:
        return []


def _klasse_nummer(projekt: str, klasse: str) -> int:
    """Die Nummer einer Klasse; eine neue haengt sich hinten an.

    Nie umsortieren: die Nummer steht in jeder Labeldatei, und eine
    verschobene Liste machte aus jeder Kupplung etwas anderes.
    """
    liste = klassen(projekt)
    if klasse not in liste:
        liste.append(klasse)
        with open(os.path.join(wurzel(projekt), "klassen.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(liste) + "\n")
    return liste.index(klasse)


def _formate(projekt: str, daten: list[dict]) -> None:
    """YOLO-Labels, data.yaml und COCO aus den Eintraegen neu schreiben.

    Immer alles neu: so kann eine Labeldatei nie von ihrem Eintrag
    abweichen, auch nicht nach einer von Hand verschobenen Box.
    """
    pfad = wurzel(projekt)
    namen = klassen(projekt)
    aufgenommen = [e for e in daten if e.get("status") == "ok" and e.get("box")]

    labels = os.path.join(pfad, "labels")
    soll = set()
    for e in aufgenommen:
        x1, y1, x2, y2 = e["box"]
        b, h = e["breite"], e["hoehe"]
        zeile = (f"{namen.index(e['klasse'])} {(x1 + x2) / 2 / b:.6f} "
                 f"{(y1 + y2) / 2 / h:.6f} {(x2 - x1) / b:.6f} {(y2 - y1) / h:.6f}\n")
        name = e["datei"][:-4] + ".txt"
        soll.add(name)
        with open(os.path.join(labels, name), "w", encoding="utf-8") as fh:
            fh.write(zeile)
    for alt in os.listdir(labels):
        if alt.endswith(".txt") and alt not in soll:
            os.remove(os.path.join(labels, alt))

    with open(os.path.join(pfad, "data.yaml"), "w", encoding="utf-8") as fh:
        fh.write(f"# Ultralytics: yolo detect train data={os.path.join(pfad, 'data.yaml')}\n"
                 f"# Noch ohne Aufteilung -- train und val zeigen auf dieselben Bilder.\n"
                 f"path: {pfad}\ntrain: images\nval: images\n"
                 f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(namen)))

    coco = {"info": {"description": f"Trainingsdaten {projekt}",
                     "date_created": time.strftime("%Y-%m-%d %H:%M:%S")},
            "categories": [{"id": i, "name": n} for i, n in enumerate(namen)],
            "images": [], "annotations": []}
    for nummer, e in enumerate(aufgenommen, start=1):
        x1, y1, x2, y2 = e["box"]
        coco["images"].append({"id": nummer, "file_name": e["datei"],
                               "width": e["breite"], "height": e["hoehe"]})
        coco["annotations"].append({
            "id": nummer, "image_id": nummer, "category_id": namen.index(e["klasse"]),
            "bbox": [x1, y1, x2 - x1, y2 - y1], "area": (x2 - x1) * (y2 - y1),
            "iscrowd": 0})
    with open(os.path.join(pfad, "annotations.json"), "w", encoding="utf-8") as fh:
        json.dump(coco, fh, ensure_ascii=False, indent=1)

    # Die Merkmale je Bild als Tabelle: was gewuerfelt wurde, ob echt oder
    # erzeugt, aus welchem Foto. Damit laesst sich der Satz ausbalancieren
    # oder ein Klassifikator auf Farbe, Untergrund, Licht trainieren.
    spalten = ["datei", "status", "klasse", "echt", "foto", "quelle",
               "x1", "y1", "x2", "y2", "breite", "hoehe", *ACHSEN]
    with open(os.path.join(pfad, "attribute.csv"), "w", newline="",
              encoding="utf-8") as fh:
        schreiber = csv.writer(fh)
        schreiber.writerow(spalten)
        for e in daten:
            box = e.get("box") or [None] * 4
            achsen = e.get("achsen") or {}
            schreiber.writerow([e["datei"], e.get("status"), e.get("klasse"),
                                1 if e.get("echt") else 0, e.get("foto") or "",
                                e.get("quelle") or "", *box,
                                e.get("breite"), e.get("hoehe"),
                                *(achsen.get(k) or "" for k in ACHSEN)])


def bildpfad(projekt: str, status: str, datei: str) -> str | None:
    """Der Pfad eines Datensatzbildes -- jeder Teil gegen sein Muster geprueft."""
    if not projekte.SCHLUESSEL.fullmatch(projekt or "") or status not in ORDNER \
            or not DATEI.fullmatch(datei or ""):
        return None
    pfad = os.path.join(wurzel(projekt), ORDNER[status], datei)
    return pfad if os.path.isfile(pfad) else None


def setzen(projekt: str, datei: str, status: str, box: list | None = None) -> dict | None:
    """Ein Bild aufnehmen, zurueckstellen oder verwerfen -- wahlweise mit neuer Box."""
    if status not in ORDNER:
        return None
    with _sperre:
        daten = eintraege(projekt)
        e = next((x for x in daten if x["datei"] == datei), None)
        if not e:
            return None
        if box is not None:
            x1, y1, x2, y2 = (float(v) for v in box)
            x1, x2 = sorted((max(0, min(e["breite"], x1)), max(0, min(e["breite"], x2))))
            y1, y2 = sorted((max(0, min(e["hoehe"], y1)), max(0, min(e["hoehe"], y2))))
            if x2 - x1 < 2 or y2 - y1 < 2:
                return None
            e["box"] = [round(x1), round(y1), round(x2), round(y2)]
            e["von_hand"] = True
        if status == "ok" and not e.get("box"):
            return None
        _verschieben(projekt, e, status)
        # Was aus diesem Bild vervielfaeltigt wurde, traegt seine alte Box
        # mit. Faellt die Vorlage heraus oder bekommt eine neue Box, stimmt
        # das nicht mehr -- verworfen, nicht geloescht.
        if box is not None or status != "ok":
            for kind in daten:
                if kind.get("quelle") == datei and kind["status"] != "verworfen":
                    _verschieben(projekt, kind, "verworfen")
                    kind["gruende"] = ["Vorlage geändert"]
        _speichern(projekt, daten)
        return e


def _verschieben(projekt: str, e: dict, status: str) -> None:
    """Die Datei in den Ordner ihres neuen Status legen."""
    pfad = wurzel(projekt)
    alt = os.path.join(pfad, ORDNER[e["status"]], e["datei"])
    neu = os.path.join(pfad, ORDNER[status], e["datei"])
    if alt != neu and os.path.isfile(alt):
        shutil.move(alt, neu)
    e["status"] = status


def originale(projekt: str) -> list[dict]:
    """Aufgenommene Bilder mit Box, die nicht selbst vervielfaeltigt sind."""
    return [e for e in eintraege(projekt)
            if e.get("status") == "ok" and e.get("box") and not e.get("quelle")]


def hinzufuegen(projekt: str, neue: list[dict]) -> None:
    """Fertige Eintraege anhaengen -- die Dateien liegen schon in images/."""
    with _sperre:
        namen = {n["datei"] for n in neue}
        daten = [e for e in eintraege(projekt) if e["datei"] not in namen] + neue
        _speichern(projekt, daten)


# --- Erkennen -------------------------------------------------------------
def _iou(a, b) -> float:
    if not a or not b:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    schnitt = max(0, x2 - x1) * max(0, y2 - y1)
    flaeche = lambda r: max(0, r[2] - r[0]) * max(0, r[3] - r[1])  # noqa: E731
    gesamt = flaeche(a) + flaeche(b) - schnitt
    return schnitt / gesamt if gesamt else 0.0


def _beruehrt(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _flaeche(r) -> float:
    return max(0, r[2] - r[0]) * max(0, r[3] - r[1])


def _umschliesst(aussen, innen, rand: float = 0.1) -> bool:
    """Liegt `innen` (bis auf einen Rand von 10 % seiner Groesse) in `aussen`?"""
    db, dh = rand * (innen[2] - innen[0]), rand * (innen[3] - innen[1])
    return (aussen[0] <= innen[0] + db and aussen[1] <= innen[1] + dh
            and aussen[2] >= innen[2] - db and aussen[3] >= innen[3] - dh)


def _verkleinert(bild):
    """Das Bild fuer die Erkenner, hoechstens ANALYSE_KANTE gross."""
    from PIL import Image
    f = ANALYSE_KANTE / max(bild.size)
    if f >= 1:
        return bild
    return bild.resize((max(1, round(bild.size[0] * f)), max(1, round(bild.size[1] * f))),
                       Image.LANCZOS)


def _dtype(torch, geraet: str):
    """bfloat16 nur, wo die Karte es selbst rechnet (ab Ampere).

    Eine GTX 1660 oder RTX 2060 -- typische 6-GB-Karten -- emuliert es nur und
    ist damit langsamer als in float16. Auf der CPU bleibt bfloat16: float16
    rechnet dort kaum jemand schnell.
    """
    if geraet == "cuda" and torch.cuda.get_device_capability(0)[0] < 8:
        return torch.float16
    return torch.bfloat16


class Erkenner:
    """Beide Modelle fuer einen ganzen Stapel Bilder.

    Gebraucht wird die Karte erst, wenn das Bildmodell sie freigegeben hat;
    `schliessen()` gibt sie wieder her.

    Auf einer grossen Karte liegen beide zugleich darauf. Auf einer kleinen
    (unter 8 GB) wird in zwei Phasen gerechnet: `alle()` holt erst Qwen3-VL
    fuer saemtliche Bilder auf die Karte, gibt es wieder frei und laesst dann
    DINO ueber dieselben Bilder laufen. Ein Ladevorgang je Modell und Stapel,
    nie beide auf einmal.
    """

    def __init__(self, melden=None):
        import torch
        self.torch = torch
        self.melden = melden or (lambda *a: None)
        self.geraet = "cuda" if torch.cuda.is_available() else "cpu"
        gesamt = torch.cuda.get_device_properties(0).total_memory \
            if self.geraet == "cuda" else 0
        self.vl_geraet = os.environ.get("QWEN_BOX_GERAET") or (
            "cuda" if gesamt >= VL_MINDESTENS else "cpu")
        # Beide zugleich nur, wo der Platz sicher reicht -- oder wenn VL
        # ohnehin auf der CPU liegt und der Karte nichts wegnimmt.
        self.zugleich = gesamt >= VL_KLEINE_KARTE or self.vl_geraet == "cpu"
        self.vl = self.dino = None

    # -- Laden und Freigeben ------------------------------------------------
    def _vl_laden(self) -> None:
        if self.vl is not None:
            return
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self.melden(f"Qwen3-VL wird geladen ({self.vl_geraet})")
        self.vl_proc = AutoProcessor.from_pretrained(VL_MODELL)
        self.vl = AutoModelForImageTextToText.from_pretrained(
            VL_MODELL, dtype=_dtype(self.torch, self.vl_geraet)).to(self.vl_geraet).eval()

    def _dino_laden(self) -> None:
        if self.dino is not None:
            return
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        self.melden("Grounding DINO wird geladen")
        self.dino_proc = AutoProcessor.from_pretrained(DINO_MODELL)
        self.dino = AutoModelForZeroShotObjectDetection.from_pretrained(
            DINO_MODELL).to(self.geraet).eval()

    def _frei(self) -> None:
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()

    def _vl_weg(self) -> None:
        self.vl = None
        self._frei()

    def schliessen(self) -> None:
        self.vl = self.dino = None
        self._frei()

    # -- Einzelne Fragen ----------------------------------------------------
    def vl_box(self, bild, suche: str) -> list | None:
        """Qwen3-VL nach der Box fragen. Es antwortet in 0..1000, relativ."""
        self._vl_laden()
        frage = (f"Find the {suche}. Answer only with JSON: "
                 f'[{{"bbox_2d": [x1, y1, x2, y2], "label": "{suche}"}}]. '
                 "If it is not in the image, answer [].")
        nachricht = [{"role": "user", "content": [{"type": "image",
                                                   "image": _verkleinert(bild)},
                                                  {"type": "text", "text": frage}]}]
        eingabe = self.vl_proc.apply_chat_template(
            nachricht, tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors="pt").to(self.vl_geraet)
        with self.torch.no_grad():
            aus = self.vl.generate(**eingabe, max_new_tokens=120, do_sample=False)
        text = self.vl_proc.batch_decode(
            aus[:, eingabe["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        treffer = re.search(r"\[\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,"
                            r"\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\]", text)
        if not treffer:
            return None
        b, h = bild.size
        x1, y1, x2, y2 = (float(v) for v in treffer.groups())
        box = [round(x1 * b / 1000), round(y1 * h / 1000),
               round(x2 * b / 1000), round(y2 * h / 1000)]
        return box if box[2] > box[0] and box[3] > box[1] else None

    def dino_boxen(self, bild, suche: str) -> list[tuple[list, float]]:
        self._dino_laden()
        eingabe = self.dino_proc(images=_verkleinert(bild),
                                 text=suche.strip().rstrip(".") + ".",
                                 return_tensors="pt").to(self.geraet)
        with self.torch.no_grad():
            aus = self.dino(**eingabe)
        # Die Boxen gleich in der Groesse des Originals.
        r = self.dino_proc.post_process_grounded_object_detection(
            aus, eingabe.input_ids, threshold=DINO_SCHWELLE,
            text_threshold=DINO_SCHWELLE, target_sizes=[bild.size[::-1]])[0]
        b, h = bild.size
        raus = []
        for box, wert in zip(r["boxes"].tolist(), r["scores"].tolist()):
            box = [max(0, round(box[0])), max(0, round(box[1])),
                   min(b, round(box[2])), min(h, round(box[3]))]
            if (box[2] - box[0]) * (box[3] - box[1]) <= ZU_GROSS * b * h:
                raus.append((box, wert))
        return raus

    @staticmethod
    def urteil(vl, dino, basis_box: list | None = None) -> dict:
        """Aus der VL-Box und den DINO-Teilen Box und Urteil machen."""
        gruende = []
        # DINO findet Teile: Kugelkopf hier, Steckdose dort. Die Vereinigung
        # aller Teile, die die VL-Box beruehren, ist seine Antwort.
        bezug = vl or (max(dino, key=lambda d: d[1])[0] if dino else None)
        # Eine DINO-Box, die die VL-Box umschliesst und ein Vielfaches so
        # gross ist, meint das Ganze -- das Auto, an dem die Kupplung haengt.
        # ZU_GROSS faengt das nur, wenn das Auto das halbe Bild fuellt; von
        # hinten fotografiert waren es gemessen 40 %, und die Vereinigung
        # ergab dann das ganze Heck.
        if vl:
            dino = [d for d in dino
                    if not (_flaeche(d[0]) > GANZES * _flaeche(vl) and _umschliesst(d[0], vl))]
        teile = [d for d in dino if bezug and _beruehrt(d[0], bezug)]
        dino_box = ([min(d[0][0] for d in teile), min(d[0][1] for d in teile),
                     max(d[0][2] for d in teile), max(d[0][3] for d in teile)]
                    if teile else None)
        dino_wert = max((d[1] for d in teile), default=0.0)
        ueberein = _iou(vl, dino_box)

        if not vl:
            gruende.append("Qwen3-VL findet nichts")
        if not dino_box:
            gruende.append("DINO findet nichts")
        if vl and dino_box and ueberein < GLEICH:
            gruende.append(f"VL und DINO uneins (IoU {ueberein:.2f})")
        basis = _iou(vl, basis_box) if basis_box and vl else None
        return {"box": vl or dino_box, "vl": vl, "dino": dino_box,
                "dino_wert": round(dino_wert, 3), "ueberein": round(ueberein, 3),
                "basis_iou": None if basis is None else round(basis, 3),
                "status": "pruefen" if gruende else "ok", "gruende": gruende}

    def pruefen(self, bild, suche: str, basis_box: list | None = None) -> dict:
        """Box und Urteil fuer ein einzelnes Bild."""
        return self.urteil(self.vl_box(bild, suche), self.dino_boxen(bild, suche),
                           basis_box)

    # -- Ein ganzer Stapel --------------------------------------------------
    def alle(self, bilder: list, suche: str, melden=None) -> tuple[list, list]:
        """VL-Boxen und DINO-Teile fuer viele Bilder, phasenweise.

        `bilder` sind Pfade oder PIL-Bilder. Zurueck kommen zwei Listen in
        derselben Reihenfolge: die VL-Box je Bild und die DINO-Teile je Bild.
        Die Bilder werden je Phase neu von der Platte gelesen -- bei ein paar
        hundert Bildern sollen sie nicht alle zugleich im Speicher liegen.
        """
        from PIL import Image
        melden = melden or self.melden

        def lesen(b):
            if isinstance(b, str):
                with Image.open(b) as roh:
                    return roh.convert("RGB")
            return b.convert("RGB")

        n = len(bilder)
        vl, dino = [None] * n, [[] for _ in range(n)]
        if self.zugleich:
            for i, b in enumerate(bilder):
                melden(f"Bounding Box {i + 1}/{n}", i, n)
                bild = lesen(b)
                vl[i] = self.vl_box(bild, suche)
                dino[i] = self.dino_boxen(bild, suche)
            return vl, dino
        for i, b in enumerate(bilder):
            melden(f"Bounding Box {i + 1}/{n} · Qwen3-VL", i, 2 * n)
            vl[i] = self.vl_box(lesen(b), suche)
        self._vl_weg()
        for i, b in enumerate(bilder):
            melden(f"Bounding Box {i + 1}/{n} · Grounding DINO", n + i, 2 * n)
            dino[i] = self.dino_boxen(lesen(b), suche)
        return vl, dino


def _kamera_fest(meta: dict) -> bool:
    """Wurde an der Kamera nichts gewuerfelt? Dann muss die Box bleiben, wo sie war."""
    return not any(meta.get(k) for k in ("angle", "device", "view", "camera"))


ACHSEN = ("paint", "palette", "style", "scene", "light", "angle", "device", "view",
          "camera", "material", "scenario")


def _klassenname(klasse: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", (klasse or "objekt").strip().lower())[:40] or "objekt"


def aufnehmen(projekt: str, bilder: list[tuple[str, dict]], klasse: str,
              suche: str, basis=None, melden=None) -> dict:
    """Erzeugte Bilder pruefen und in den Datensatz legen.

    `bilder` sind Paare (Pfad, Metadaten des Auftrags). `basis` ist das
    Vorlagenbild der Varianten, falls es eines gab.
    """
    return aufnehmen_gruppen(projekt, [{"basis": basis, "bilder": bilder}],
                             klasse, suche, melden)


def aufnehmen_gruppen(projekt: str, gruppen: list[dict], klasse: str, suche: str,
                      melden=None) -> dict:
    """Mehrere Gruppen auf einmal: je eine Vorlage und ihre Varianten.

    Eine Gruppe ist ein dict mit

        basis       das Vorlagenbild (PIL) oder None
        basis_box   die Box darin, falls schon bekannt -- etwa von Hand
                    auf einem echten Foto gezogen
        original    (Pfad, Metadaten): die Vorlage selbst kommt mit in den
                    Datensatz. Mit `basis_box` gleich aufgenommen, sonst
                    wie jedes andere Bild geprueft
        bilder      [(Pfad, Metadaten)] -- die Varianten

    Die Erkenner laden einmal fuer alle Gruppen. Das Basisbild jeder Gruppe
    wird im selben Stapel mit erkannt, wenn seine Box noch fehlt.
    """
    from PIL import Image

    klasse = _klassenname(klasse)
    suche = (suche or klasse.replace("_", " ")).strip()
    melden = melden or (lambda *a: None)
    melden("Box-Modelle werden geladen")

    # Ein flacher Stapel: (Gruppe, Art, Pfad oder Bild, Metadaten)
    stapel = []
    for g in gruppen:
        if g.get("basis") is not None and not g.get("basis_box") and not g.get("original"):
            stapel.append((g, "basis", g["basis"], {}))
        if g.get("original"):
            stapel.append((g, "original", g["original"][0], g["original"][1]))
        for pfad, meta in g.get("bilder") or []:
            stapel.append((g, "variante", pfad, meta))

    zu_erkennen = [s for s in stapel
                   if not (s[1] == "original" and s[0].get("basis_box"))]
    erkenner = Erkenner(melden)
    try:
        vl, dino = erkenner.alle([s[2] for s in zu_erkennen], suche, melden) \
            if zu_erkennen else ([], [])
    finally:
        erkenner.schliessen()
    gefunden = {id(s): (vl[i], dino[i]) for i, s in enumerate(zu_erkennen)}

    # Die Basisbox jeder Gruppe: von Hand, sonst was Qwen3-VL im Basisbild
    # oder im Original gesehen hat.
    for g in gruppen:
        if not g.get("basis_box"):
            for s in stapel:
                if s[0] is g and s[1] in ("basis", "original") and id(s) in gefunden:
                    g["basis_box"] = gefunden[id(s)][0]

    _klasse_nummer(projekt, klasse)          # legt sie bei Bedarf an
    zaehler = {"ok": 0, "pruefen": 0}
    neue = []
    for s in stapel:
        g, art, pfad, meta = s
        if art == "basis":
            continue
        with Image.open(pfad) as roh:
            groesse = roh.size
        if art == "original" and g.get("basis_box") and id(s) not in gefunden:
            urteil = {"box": [round(v) for v in g["basis_box"]], "vl": None,
                      "dino": None, "dino_wert": 0.0, "ueberein": None,
                      "basis_iou": None, "status": "ok", "gruende": [],
                      "von_hand": True}
        else:
            # Die Basisbox gilt nur, wenn die Kamera stand und das Bild
            # dasselbe Format hat -- sonst liegt die Kupplung woanders.
            vergleich = None
            basis_groesse = g["basis"].size if g.get("basis") is not None else None
            if art == "variante" and g.get("basis_box") and basis_groesse \
                    and _kamera_fest(meta) and abs(basis_groesse[0] / basis_groesse[1]
                                                   - groesse[0] / groesse[1]) < 0.03:
                f = groesse[0] / basis_groesse[0]
                vergleich = [round(v * f) for v in g["basis_box"]]
            urteil = Erkenner.urteil(*gefunden[id(s)], vergleich)
        datei = os.path.basename(pfad)
        shutil.copy2(pfad, os.path.join(wurzel(projekt), ORDNER[urteil["status"]], datei))
        zaehler[urteil["status"]] += 1
        eintrag = {
            "datei": datei, "klasse": klasse, "suche": suche,
            "breite": groesse[0], "hoehe": groesse[1],
            "angelegt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": meta.get("prompt") or "", "seed": meta.get("seed"),
            "achsen": {k: meta.get(k) for k in ACHSEN if meta.get(k)},
            **urteil}
        if art == "original":
            eintrag["echt"] = True
        if meta.get("foto"):
            eintrag["foto"] = meta["foto"]
        neue.append(eintrag)
    with _sperre:
        daten = [e for e in eintraege(projekt)
                 if e["datei"] not in {n["datei"] for n in neue}] + neue
        _speichern(projekt, daten)
    return zaehler


def uebersicht(projekt: str) -> dict:
    daten = eintraege(projekt)
    return {"pfad": wurzel(projekt), "klassen": klassen(projekt),
            "zahlen": {s: sum(1 for e in daten if e["status"] == s) for s in ORDNER},
            "originale": sum(1 for e in daten if e["status"] == "ok"
                             and e.get("box") and not e.get("quelle")),
            "eintraege": list(reversed(daten))}
