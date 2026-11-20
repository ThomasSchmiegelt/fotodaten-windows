#!/usr/bin/env bash
# Richtet diesen Ordner unter Ubuntu/Linux portabel ein -- die Ubuntu-Fassung
# von einrichten.bat (das laedt eingettetes Windows-Python und rft dann
# portable\bauen.py auf; hier genfigt das Python des Systems).
#
# Danach startet start.sh das Programm. Der ganze Ordner laesst sich
# anschliessend kopieren -- virtuelle Umgebung, Modelle, Projekte liegen
# alle hier:
#
#   <Ordner>/
#       einrichten.sh         einmal ausfuhren
#       start.sh              startet Server und Browser
#       qwen_bild/            virtuelle Umgebung
#       daten/hf/             Hugging-Face-Modelle (Box-Erkenner, ggf. Qwen-Image)
#       modelle/yolo/         YOLO26-Grundgewichte
#       projekte/             Bilder, Datensaetze, Trainingslaeufe
#
#   ./einrichten.sh             Bilder per Cloud-API, Boxen und Training
#                               auf der eigenen Karte (ab 6 GB), ~9 GB
#   ./einrichten.sh training    nur Detektor-Training (YOLO26, D-FINE) --
#                               z. B. Notebook mit RTX 1000 Ada, ~4 GB
#   ./einrichten.sh nurcloud    nur Bilder per Cloud-API, ~100 MB
#   ./einrichten.sh lokal       dazu Qwen-Image auf der eigenen Karte
#                               (braucht ~17 GB Grafikspeicher, ~40 GB)
#   ... cu126                   PyTorch fuer GTX 10xx statt CUDA 13.0
#   ... ohnemodelle             Modelle erst beim ersten Gebrauch laden
#
# Darf mehrfach laufen; was schon da ist, wird nur geprft.
# Voraussetzungen: python3 mit venv (Ubuntu: sudo apt install python3-venv).
set -euo pipefail
cd "$(dirname "$0")"

LOKAL=0; TRAINING=0; NURCLOUD=0; OHNE=0
CUDA="cu130"
for a in "$@"; do
  case "$a" in
    lokal)        LOKAL=1 ;;
    training)     TRAINING=1 ;;
    nurcloud)     NURCLOUD=1 ;;
    ohnemodelle)  OHNE=1 ;;
    cu126|cu128|cu130) CUDA="$a" ;;
    *) echo "Unbekanntes Argument: $a" >&2;
       echo "Mglich: [lokal|training|nurcloud] [ohnemodelle] [cu126|cu128|cu130]" >&2
       exit 1 ;;
  esac
done
if [ "$LOKAL" -eq 1 ] && [ "$NURCLOUD" -eq 1 ]; then
  echo "lokal und nurcloud nicht zusammen." >&2; exit 1
fi
if [ "$TRAINING" -eq 1 ] && [ "$NURCLOUD" -eq 1 ]; then
  echo "training und nurcloud nicht zusammen." >&2; exit 1
fi

# Modelle und Gewichte beim Programm, nicht im Benutzerprofil.
export HF_HOME="$PWD/daten/hf"
export YOLO_CONFIG_DIR="$PWD/modelle/yolo/einstellungen"
# Xet, der neue Download-Weg von Hugging Face, bleibt an manchen Rechnern
# bei 0 Byte stehen; normales HTTP lief.
export HF_HUB_DISABLE_XET=1
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

PY="$(pwd)/qwen_bild/bin/python"   # absolut: Unterordner (modelle/yolo) brauchen ihn auch
pip() { "$PY" -m pip install --disable-pip-version-check "$@"; }

echo "1/5 Python"
if [ ! -x "$PY" ]; then
  command -v python3 >/dev/null || { echo "python3 nicht gefunden (sudo apt install python3 python3-venv)." >&2; exit 1; }
  python3 -m venv qwen_bild
fi
"$PY" -m pip install -q --upgrade pip
echo "  $($PY --version)"

echo "2/5 Grundpakete"
pip pillow==12.3.0 numpy==2.5.2

if [ "$NURCLOUD" -eq 0 ]; then
  echo "3/5 PyTorch ($CUDA) und Ausbau"
  pip "torch==2.14.0" "torchvision==0.29.0" --index-url "https://download.pytorch.org/whl/$CUDA"
  # diffusers: Qwen-Image 2.1 ist erst in diffusers ab main enthalten --
  # der Stand, gegen den die Fassung geprft ist, als ZIP ohne Git:
  #   lokal  -> danach der main-Stand darber (ersetzt 0.41.0)
  #   sonst  -> 0.41.0 bleibt (Vervielfaeltigen mit SD 1.5, ab 4 GB)
  pip diffusers==0.41.0 transformers==5.17.0 accelerate==1.15.0 \
      huggingface_hub==1.32.0 safetensors==0.8.0 scipy==1.18.1 \
      ultralytics==8.4.182 polars==1.31.0
  if [ "$LOKAL" -eq 1 ]; then
    pip "https://github.com/huggingface/diffusers/archive/cc8644b447d8f11074d3df06d0ee0e3e7c91bf75.zip"
    mkdir -p daten
    { echo "Qwen-Image lauft lokal."
      echo "QWEN_IMAGE_REVISION=790c92633540aa0cb11d9abf19eb46d861714758"
    } > daten/bildmodell_lokal.txt
  else
    rm -f daten/bildmodell_lokal.txt
  fi
else
  rm -f daten/bildmodell_lokal.txt
  echo "3/5 PyTorch -- uebersprungen (nurcloud)"
fi

echo "4/5 Prfen"
# Laeuft, was installiert ist? torch nur prfen, wenn es auch dabei ist.
export QWEN_PRUEFE_TORCH=$((1 - NURCLOUD))
"$PY" - <<'PY' || { echo "Prfung fehlgeschlagen." >&2; exit 1; }
import os
import PIL, numpy
print("  PIL", PIL.__version__, "| numpy", numpy.__version__)
if os.environ.get("QWEN_PRUEFE_TORCH") == "1":
    import torch, transformers, ultralytics, polars
    print("  torch", torch.__version__,
          "| CUDA:", torch.cuda.is_available(),
          torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")
PY

echo "5/5 Modelle"
if [ "$OHNE" -eq 1 ]; then
  echo "  uebersprungen, sie laden beim ersten Gebrauch"
  exit 0
fi
BOXEN="0"
[ "$TRAINING" -eq 0 ] && BOXEN="1"
"$PY" - <<PY
import os
from huggingface_hub import snapshot_download
auftraege = (
    [("Qwen/Qwen3-VL-2B-Instruct", None),
     ("IDEA-Research/grounding-dino-base", None)] if $BOXEN == 1 else []
)
if $LOKAL == 1:
    auftraege.append(("Qwen/Qwen-Image-2.1", "790c92633540aa0cb11d9abf19eb46d861714758"))
for r, rev in auftraege:
    print("  lade", r, flush=True)
    # Nur safetensors: DINO liegt zusaetzlich als pytorch_model.bin auf dem
    # Hub -- 900 MB doppelt, gebraucht wird nur eine Fassung.
    snapshot_download(r, revision=rev,
                      ignore_patterns=["*.bin", "*.pt", "*.h5", "*.msgpack", "*.onnx"])
PY
# YOLO26 n/s: Gewichte und Einstellungen beim Programm, nicht unter ~.
mkdir -p modelle/yolo
( cd modelle/yolo && "$PY" -c "import os; from ultralytics import YOLO; [YOLO(os.path.abspath(n)) for n in ('yolo26n.pt','yolo26s.pt')]" )

GROESSE=$(du -sh . | cut -f1)
echo
echo "Fertig: $PWD  ($GROESSE)"
echo "Starten mit: ./start.sh"
