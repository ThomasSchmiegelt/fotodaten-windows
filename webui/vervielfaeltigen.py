"""Vervielfaeltigen: aus wenigen gepruefte Bildern viele, ohne neue Box.

Der Weg fuer kleine Grafikkarten. Die Basisbilder kommen aus dem grossen
Modell -- lokal auf einer grossen Karte oder ueber das Cloud-Bildmodell --,
ihre Box wird einmal geprueft. Danach wird hier nur noch so veraendert, dass
man weiss, wo die Box hinwandert. Ein Box-Modell braucht es dafuer nicht.

Zwei Verfahren, einzeln oder hintereinander:

    klassisch   spiegeln, hineinzoomen, Helligkeit, Kontrast, Farbe,
                Unschaerfe, Rauschen, JPEG. Nur CPU. Jede Veraenderung ist
                eine bekannte Abbildung, die Box rechnet mit.
    umgebung    Stable Diffusion 1.5 mit ControlNet (Kanten): die Umrisse
                bleiben, Umgebung, Licht und Oberflaechen wechseln nach
                Prompt. Laeuft mit 4 GB (dann mit Auslagerung) und bei 512 px.
                Weil die Geometrie steht, bleibt die Box, wo sie war.
                Wahlweise wird der Gegenstand selbst danach wieder aus dem
                Original eingesetzt -- dann aendert sich nur das Drumherum.

Die Ergebnisse heissen wie ihre Vorlage plus `_mehrNN`. So landen sie bei der
Aufteilung in train/val in derselben Gruppe wie die Vorlage
(detektor._gruppe) -- sonst mass die Validierung nur, wie gut das Modell
den Zwilling eines Trainingsbildes wiedererkennt.
"""

import gc
import io
import os
import random

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import retusche
from kataloge.motiv import OBJECT_SCENES, PERSON_SCENES, VEHICLE_SCENES

SD_MODELL = os.environ.get("QWEN_SD_MODELL", "stable-diffusion-v1-5/stable-diffusion-v1-5")
CN_MODELL = os.environ.get("QWEN_SD_CONTROLNET", "lllyasviel/control_v11p_sd15_canny")
# Unterhalb davon wird SD 1.5 Schicht fuer Schicht auf die Karte geholt.
KLEINE_KARTE = 8 * 1024 ** 3
SD_KANTE = 512

NEGATIV = ("cartoon, drawing, illustration, painting, blurry, deformed, "
           "distorted, text, watermark, logo, frame, border")

# Vorschlaege fuer das Umgebungsfeld -- dieselben Saetze wie bei Varianten.
UMGEBUNGEN = {
    "fahrzeug": [v[1] for v in VEHICLE_SCENES.values()],
    "gegenstand": [v[1] for v in OBJECT_SCENES.values()],
    "person": [v[1] for v in PERSON_SCENES.values()],
}


# --- klassisch -------------------------------------------------------------
def klassisch(bild: Image.Image, box: list, rng: random.Random,
              spiegeln: bool = True) -> tuple[Image.Image, list]:
    """Eine zufaellige, aber nachrechenbare Veraenderung. Die Groesse bleibt."""
    bild = bild.convert("RGB")
    breite, hoehe = bild.size
    x1, y1, x2, y2 = box

    if spiegeln and rng.random() < 0.5:
        bild = ImageOps.mirror(bild)
        x1, x2 = breite - x2, breite - x1

    # Hineinzoomen: ein Ausschnitt im selben Seitenverhaeltnis, der die Box
    # ganz enthaelt, wieder auf volle Groesse. Der Gegenstand wird groesser
    # und wandert -- beides lernt ein Detektor sonst nur aus vielen Fotos.
    if rng.random() < 0.6:
        noetig = 1.1 * max((x2 - x1) / breite, (y2 - y1) / hoehe)
        kleinst = max(0.55, noetig)
        if kleinst < 0.97:
            s = rng.uniform(kleinst, 1.0)
            aw, ah = breite * s, hoehe * s
            ax = rng.uniform(max(0.0, x2 - aw), min(x1, breite - aw))
            ay = rng.uniform(max(0.0, y2 - ah), min(y1, hoehe - ah))
            bild = bild.resize((breite, hoehe), Image.LANCZOS,
                               box=(ax, ay, ax + aw, ay + ah))
            x1, x2 = (x1 - ax) / s, (x2 - ax) / s
            y1, y2 = (y1 - ay) / s, (y2 - ay) / s

    bild = ImageEnhance.Brightness(bild).enhance(rng.uniform(0.7, 1.3))
    bild = ImageEnhance.Contrast(bild).enhance(rng.uniform(0.7, 1.3))
    bild = ImageEnhance.Color(bild).enhance(rng.uniform(0.6, 1.4))
    if rng.random() < 0.2:
        bild = bild.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.6)))
    if rng.random() < 0.3:
        a = np.asarray(bild, dtype=np.float32)
        a += np.random.default_rng(rng.randrange(2 ** 31)).normal(
            0, rng.uniform(3, 9), a.shape)
        bild = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rng.random() < 0.3:
        puffer = io.BytesIO()
        bild.save(puffer, "JPEG", quality=rng.randint(40, 85))
        bild = Image.open(puffer).convert("RGB")

    box = [max(0, round(x1)), max(0, round(y1)),
           min(breite, round(x2)), min(hoehe, round(y2))]
    return bild, box


# --- umgebung --------------------------------------------------------------
def kanten(bild: Image.Image) -> Image.Image:
    """Kantenbild fuer ControlNet, ohne OpenCV.

    Kein echter Canny, aber nah genug: weichzeichnen, Kanten finden,
    Schwelle. Das Kanten-ControlNet nimmt es klaglos.
    """
    grau = bild.convert("L").filter(ImageFilter.GaussianBlur(1.2))
    rand = grau.filter(ImageFilter.FIND_EDGES)
    werte = np.asarray(rand)
    schwelle = max(12, float(np.percentile(werte, 88)))
    return rand.point(lambda v: 255 if v >= schwelle else 0).convert("RGB")


def _sd_groesse(breite: int, hoehe: int) -> tuple[int, int]:
    f = SD_KANTE / min(breite, hoehe)
    return (max(8, round(breite * f / 8) * 8), max(8, round(hoehe * f / 8) * 8))


class Umgebung:
    """SD 1.5 + ControlNet, einmal geladen fuer einen ganzen Stapel."""

    def __init__(self, melden=None):
        import torch
        from diffusers import ControlNetModel, StableDiffusionControlNetImg2ImgPipeline
        (melden or (lambda *a: None))(
            "SD 1.5 und ControlNet werden geladen (beim ersten Mal ~3 GB Download)")
        self.torch = torch
        cuda = torch.cuda.is_available()
        dtype = torch.float16 if cuda else torch.float32
        variante = {"variant": "fp16"} if cuda else {}
        try:
            netz = ControlNetModel.from_pretrained(CN_MODELL, dtype=dtype, **variante)
        except (OSError, ValueError):
            netz = ControlNetModel.from_pretrained(CN_MODELL, dtype=dtype)
        self.pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
            SD_MODELL, controlnet=netz, dtype=dtype, safety_checker=None,
            requires_safety_checker=False, **variante)
        self.pipe.set_progress_bar_config(disable=True)
        if not cuda:
            self.geraet = "cpu"
        elif torch.cuda.get_device_properties(0).total_memory < KLEINE_KARTE:
            # Schicht fuer Schicht auf die Karte. Ganze Teile auszulagern
            # (enable_model_cpu_offload) reicht nicht: UNet und ControlNet
            # rechnen gemeinsam und kamen gemessen auf 3,8 GB -- zu viel fuer
            # eine 4-GB-Karte, auf der auch noch der Bildschirm haengt.
            self.pipe.enable_sequential_cpu_offload()
            self.pipe.enable_attention_slicing()
            self.pipe.vae.enable_slicing()
            self.pipe.vae.enable_tiling()
            self.geraet = "cuda"
        else:
            self.pipe.to("cuda")
            self.geraet = "cuda"

    def schliessen(self) -> None:
        del self.pipe
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()

    def rechnen(self, bild: Image.Image, prompt: str, seed: int,
                staerke: float = 0.75, schritte: int = 25) -> Image.Image:
        """Neue Umgebung, gleiche Umrisse -- zurueck in Originalgroesse."""
        bild = bild.convert("RGB")
        klein = bild.resize(_sd_groesse(*bild.size), Image.LANCZOS)
        aus = self.pipe(
            prompt=prompt, negative_prompt=NEGATIV, image=klein,
            control_image=kanten(klein), strength=staerke,
            num_inference_steps=schritte, guidance_scale=7.0,
            controlnet_conditioning_scale=0.9,
            generator=self.torch.Generator(self.geraet).manual_seed(seed),
        ).images[0]
        return aus.resize(bild.size, Image.LANCZOS)


def gegenstand_behalten(neu: Image.Image, original: Image.Image,
                        box: list) -> Image.Image:
    """Den Gegenstand aus dem Original zurueck ins neue Bild setzen.

    Mit etwas Rand und weicher Kante; die Farbe wird dabei leicht ans neue
    Licht angeglichen (retusche.einsetzen). Ohne das veraendert SD auch den
    Gegenstand -- manchmal gewollt, fuer ein Bauteil mit festem Aussehen
    meist nicht.
    """
    breite, hoehe = original.size
    x1, y1, x2, y2 = box
    rand = max(6, round(0.12 * max(x2 - x1, y2 - y1)))
    maske = Image.new("L", original.size, 0)
    maske.paste(255, (max(0, x1 - rand), max(0, y1 - rand),
                      min(breite, x2 + rand), min(hoehe, y2 + rand)))
    bereich = (max(0, x1 - 2 * rand), max(0, y1 - 2 * rand),
               min(breite, x2 + 2 * rand), min(hoehe, y2 + 2 * rand))
    return retusche.einsetzen(neu.convert("RGB"), original.convert("RGB").crop(bereich),
                              maske, bereich, kante=max(4, rand // 2))


def prompt_fuer(suche: str, umgebung: str) -> str:
    return (f"a realistic photo of a {suche.strip() or 'object'}, {umgebung.strip()}, "
            "natural light, sharp focus, high detail")
