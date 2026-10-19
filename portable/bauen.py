"""Die portable Windows-Fassung einrichten: ein Ordner, der ueberall laeuft.

Der uebliche Weg ist `einrichten.bat` im Hauptordner -- es laedt Python und
ruft dieses Skript mit `--hier` auf. Von Hand:

    python portable\\bauen.py --hier [Stufe]          das Repository selbst
    python portable\\bauen.py ZIELORDNER [Stufe]      eine Kopie woanders

Nichts wird installiert, nichts landet in %APPDATA% oder im Benutzerprofil.
Mit `--hier` wird der heruntergeladene Ordner selbst portabel:

    <Ordner>\\
        einrichten.bat      einmal ausfuehren
        start.bat           startet Server und Browser
        python\\             eingebettetes Python 3.12 von python.org
        daten\\hf\\           Hugging-Face-Modelle (Box-Erkenner, ggf. Qwen-Image)
        modelle\\yolo\\       YOLO26-Grundgewichte
        projekte\\           Bilder, Datensaetze, Trainingslaeufe
        einstellungen.json  Cloud-Zugang (entsteht beim Eintragen)

**Stufen.**

    --training      nur Detektor-Training: PyTorch und Ultralytics, die
                    YOLO26-Gewichte, keine Box-Modelle. Fuer den Rechner,
                    auf dem nur trainiert wird -- etwa ein Notebook mit
                    RTX 1000 Ada (6 GB); der Datensatz kommt fertig gelabelt
                    von einem anderen Rechner. Rund 4 GB.
    --nurcloud      nur Cloud: Bilder kommen vom API-Modell (OpenAI-
                    kompatibel, etwa franconia.ai). Gut 100 MB, kein
                    Grafikkartenbedarf -- aber auch keine Boxen und kein
                    Training.
    (Vorgabe)       dazu PyTorch mit CUDA, transformers und Ultralytics:
                    Bounding Boxes (Qwen3-VL + Grounding DINO), D-FINE- und
                    YOLO26-Training, ausgelegt auf eine 6-GB-Karte. Die
                    Box-Modelle und YOLO26 n/s werden gleich mitgeladen.
                    Rund 9 GB.
    --lokal         zusaetzlich das Bildmodell Qwen-Image 2.1 auf der eigenen
                    Karte (braucht ~17 GB Grafikspeicher, laedt ~31 GB).

`--cuda cu130` (Vorgabe) laeuft auf GTX 16xx / RTX 20xx bis RTX 50xx.
`--cuda cu126` braucht nur, wer eine GTX 10xx (Pascal) hat -- aber Vorsicht:
Windows' Smart App Control laesst unsignierte DLLs nur mit bekannter
Reputation zu, und gemessen wurde die c10.dll des cu126-Builds blockiert
("Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert"), die des
cu130-Builds nicht.

Ohne `--lokal` rechnet das Bildmodell nie auf der eigenen Karte: start.bat
setzt dann QWEN_NUR_CLOUD=1. Mit `--lokal` entsteht daten\\bildmodell_lokal.txt
und start.bat laesst es weg.

Das Skript darf mehrfach laufen: was schon da ist, wird nur geprueft.
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

# Xet, der neue Download-Weg von Hugging Face, blieb hier bei 0 Byte stehen;
# normales HTTP lief. Gilt fuer alles, was dieses Skript laedt.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

HIER = os.path.dirname(os.path.abspath(__file__))
QUELLE = os.path.dirname(HIER)
PYTHON_VERSION = "3.12.10"
EMBED_URL = (f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
             f"python-{PYTHON_VERSION}-embed-amd64.zip")
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
# Qwen-Image 2.1 steht nur in diffusers von main. Als ZIP von GitHub statt
# git+https: dann braucht der Rechner kein Git.
DIFFUSERS_ZIP = ("https://github.com/huggingface/diffusers/archive/"
                 "cc8644b447d8f11074d3df06d0ee0e3e7c91bf75.zip")
QWEN_IMAGE = "Qwen/Qwen-Image-2.1"
# Der Stand, gegen den der festgenagelte diffusers-Commit geprueft ist. Ein
# spaeterer auf dem Hub kann mehr verlangen; start.bat haelt diesen fest.
QWEN_IMAGE_REVISION = "790c92633540aa0cb11d9abf19eb46d861714758"
MARKE_LOKAL = os.path.join("daten", "bildmodell_lokal.txt")

# Was aus dem Repository mitkommt, wenn in einen anderen Ordner gebaut wird.
# Alles andere -- Projekte, Bilder, einstellungen.json mit dem API-Schluessel --
# bleibt draussen.
MITNEHMEN = ["webui", "demo", "portable", "gimp", "ANLEITUNG.md", "README.md",
             "LICENSE", "requirements.txt", "requirements-yolo.txt",
             "einrichten.bat", "start.bat"]
WEGLASSEN = shutil.ignore_patterns("__pycache__", "*.pyc", "bilder", "*.mp4")


def laden(url: str, ziel: str) -> None:
    print(f"  lade {url}", flush=True)
    with urllib.request.urlopen(url, timeout=300) as antwort, open(ziel, "wb") as fh:
        shutil.copyfileobj(antwort, fh)


def pip(py: str, *argumente: str) -> None:
    subprocess.run([py, "-m", "pip", "install", "--no-warn-script-location",
                    "--disable-pip-version-check", *argumente], check=True)


def python_einrichten(ziel: str, webui: str) -> str:
    """Eingebettetes Python entpacken und fuer pip und site-packages oeffnen.

    einrichten.bat entpackt Python schon selbst (es hat ja noch keins, um
    dieses Skript auszufuehren). Hier wird deshalb nicht nach python.exe
    gefragt, sondern ob pip laeuft.
    """
    ordner = os.path.join(ziel, "python")
    py = os.path.join(ordner, "python.exe")
    if not os.path.isfile(py):
        os.makedirs(ordner, exist_ok=True)
        paket = os.path.join(ziel, "python-embed.zip")
        laden(EMBED_URL, paket)
        with zipfile.ZipFile(paket) as z:
            z.extractall(ordner)
        os.remove(paket)
    # Die ._pth-Datei legt den Suchpfad fest. Ab Werk fehlt `import site` --
    # dann gibt es kein site-packages und kein pip. Das Programmverzeichnis
    # kommt dazu, weil eingebettetes Python das Skriptverzeichnis nicht von
    # selbst in den Pfad nimmt; detektor_lauf.py und yolo_lauf.py brauchen es.
    pth = next(f for f in os.listdir(ordner) if f.endswith("._pth"))
    with open(os.path.join(ordner, pth), "w", encoding="utf-8") as fh:
        fh.write(f"python{PYTHON_VERSION.replace('.', '')[:3]}.zip\n.\n"
                 f"Lib\\site-packages\n{webui}\nimport site\n")
    hat_pip = subprocess.run([py, "-m", "pip", "--version"],
                             capture_output=True).returncode == 0
    if not hat_pip:
        get_pip = os.path.join(ordner, "get-pip.py")
        laden(GET_PIP, get_pip)
        subprocess.run([py, get_pip, "--no-warn-script-location"], check=True)
        os.remove(get_pip)
    return py


def app_kopieren(ziel: str) -> None:
    for name in MITNEHMEN:
        quelle = os.path.join(QUELLE, name)
        if os.path.isdir(quelle):
            shutil.copytree(quelle, os.path.join(ziel, name), ignore=WEGLASSEN,
                            dirs_exist_ok=True)
        elif os.path.isfile(quelle):
            shutil.copy2(quelle, os.path.join(ziel, name))


def modelle_laden(ziel: str, py: str, lokal: bool, boxen: bool = True) -> None:
    """Box-Modelle in den portablen Hugging-Face-Cache, YOLO26 daneben."""
    hf = os.path.join(ziel, "daten", "hf")
    yolo = os.path.join(ziel, "modelle", "yolo")
    os.makedirs(yolo, exist_ok=True)
    auftraege = [("Qwen/Qwen3-VL-2B-Instruct", None),
                 ("IDEA-Research/grounding-dino-base", None)] if boxen else []
    if lokal:
        auftraege.append((QWEN_IMAGE, QWEN_IMAGE_REVISION))
    skript = (
        "import sys\nfrom huggingface_hub import snapshot_download\n"
        f"for r, rev in {auftraege!r}:\n"
        "    print('  ', r, flush=True)\n"
        # Nur safetensors: DINO liegt zusaetzlich als pytorch_model.bin auf
        # dem Hub -- 900 MB doppelt, gebraucht wird nur eine Fassung.
        "    snapshot_download(r, revision=rev, ignore_patterns=["
        "'*.bin', '*.pt', '*.h5', '*.msgpack', '*.onnx'])\n")
    if auftraege:
        subprocess.run([py, "-c", skript], check=True, env={**os.environ, "HF_HOME": hf})
    # Mit vollem Pfad: Ultralytics legt die Datei dann genau dort ab, wo
    # yolo_lauf.py sie sucht, und nicht unter <Git-Wurzel>\weights.
    subprocess.run([py, "-c", "import os\nfrom ultralytics import YOLO\n"
                    "for n in ('yolo26n.pt', 'yolo26s.pt'): YOLO(os.path.abspath(n))"],
                   check=True, cwd=yolo,
                   env={**os.environ, "YOLO_CONFIG_DIR": os.path.join(yolo, "einstellungen")})


def pruefen(py: str, mit_torch: bool) -> None:
    """Laeuft, was installiert ist? Faengt vor allem Smart App Control ab.

    Eine gesperrte DLL meldet sich nicht beim Installieren, sondern erst beim
    Laden -- und polars 2.x haengt dann sogar ohne Fehlermeldung. Deshalb
    hier einmal alles laden, mit Zeitgrenze.
    """
    teile = ["import PIL, numpy"]
    if mit_torch:
        teile += ["import torch, transformers, ultralytics, polars",
                  "print('CUDA:', torch.cuda.is_available(),"
                  " torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"]
    try:
        aus = subprocess.run([py, "-c", "\n".join(teile)], capture_output=True,
                             text=True, timeout=180)
    except subprocess.TimeoutExpired:
        sys.exit("\nEin Paket haengt beim Laden -- vermutlich sperrt Smart App "
                 "Control eine DLL. Siehe README, Abschnitt Windows.")
    if aus.returncode != 0:
        letzte = (aus.stderr.strip().splitlines() or ["?"])[-1]
        hinweis = (" -- Smart App Control sperrt eine DLL" if "4551" in aus.stderr
                   or "Anwendungssteuerung" in aus.stderr else "")
        sys.exit(f"\nPruefung fehlgeschlagen{hinweis}:\n  {letzte}")
    print("  " + (aus.stdout.strip() or "ok"))


def main() -> None:
    teile = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    teile.add_argument("ziel", nargs="?", help="Zielordner (ohne: --hier)")
    teile.add_argument("--hier", action="store_true",
                       help="diesen Ordner selbst portabel einrichten")
    stufe = teile.add_mutually_exclusive_group()
    stufe.add_argument("--nurcloud", action="store_true",
                       help="nur das Cloud-Bildmodell, ohne PyTorch")
    stufe.add_argument("--training", action="store_true",
                       help="nur YOLO-/D-FINE-Training, ohne Box-Modelle")
    stufe.add_argument("--lokal", action="store_true",
                       help="zusaetzlich Qwen-Image auf der eigenen Karte (~17 GB VRAM)")
    teile.add_argument("--ohne-modelle", action="store_true",
                       help="Modelle erst beim ersten Gebrauch laden")
    teile.add_argument("--cuda", default="cu130", choices=("cu126", "cu128", "cu130"))
    a = teile.parse_args()
    if a.hier == bool(a.ziel):
        teile.error("entweder --hier oder ein Zielordner")
    ziel = QUELLE if a.hier else os.path.abspath(a.ziel)
    if not a.hier and (ziel == QUELLE or ziel.startswith(QUELLE + os.sep)):
        sys.exit("Der Zielordner darf nicht im Repository liegen -- dafuer gibt es --hier")
    os.makedirs(ziel, exist_ok=True)

    print("1/5 Python", flush=True)
    py = python_einrichten(ziel, "..\\webui")
    print("2/5 Programm", flush=True)
    if not a.hier:
        app_kopieren(ziel)
    print("3/5 Pakete", flush=True)
    pip(py, "-r", os.path.join(HIER, "requirements-portable.txt"))
    if not a.nurcloud:
        pip(py, "torch==2.14.0", "torchvision==0.29.0",
            "--index-url", f"https://download.pytorch.org/whl/{a.cuda}")
        pip(py, "-r", os.path.join(HIER, "requirements-ausbau.txt"))
    marke = os.path.join(ziel, MARKE_LOKAL)
    if a.lokal:
        # Erst das Ausbau-diffusers, dann der Stand von main darueber.
        pip(py, DIFFUSERS_ZIP)
        os.makedirs(os.path.dirname(marke), exist_ok=True)
        with open(marke, "w", encoding="utf-8") as fh:
            fh.write(f"Qwen-Image laeuft lokal.\nQWEN_IMAGE_REVISION={QWEN_IMAGE_REVISION}\n")
    elif os.path.isfile(marke):
        os.remove(marke)
    print("4/5 Pruefen", flush=True)
    pruefen(py, not a.nurcloud)
    if a.nurcloud or a.ohne_modelle:
        print("5/5 Modelle -- uebersprungen, sie laden beim ersten Gebrauch")
    else:
        print("5/5 Modelle", flush=True)
        modelle_laden(ziel, py, a.lokal, boxen=not a.training)
    groesse = sum(os.path.getsize(os.path.join(w, d)) for w, _, ds in os.walk(ziel) for d in ds)
    print(f"\nFertig: {ziel}  ({groesse / 2**30:.1f} GB)\nStarten mit start.bat")


if __name__ == "__main__":
    main()
