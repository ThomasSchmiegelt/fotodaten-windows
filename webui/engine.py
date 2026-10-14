"""Qwen-Image-2.1 Engine fuer die Web-Oberflaeche.

Das Modell wiegt in bfloat16 rund 33 GB: Text-Encoder ~17.5 GB, Transformer
~14.2 GB, VAE ~1.4 GB. Auf dieser Maschine (24 GB VRAM, 31 GB RAM) passt weder
alles zusammen in die GPU noch alles zusammen in den Hauptspeicher -- deshalb
scheitert `enable_model_cpu_offload()` hier bzw. laeuft in den Swap.

Stattdessen wird ein Auftrag in zwei Phasen abgearbeitet, und zwischen den
Phasen wird die GPU wieder leergeraeumt:

  Phase 1  Text-Encoder (Qwen3-VL) -> GPU, alle Prompts einbetten
  Phase 2  Transformer + VAE       -> GPU, alle Bilder entrauschen

So liegen nie mehr als ~17.5 GB gleichzeitig auf der Karte. Eine ganze Serie
teilt sich die beiden Ladevorgaenge -- zehn Varianten kosten also nicht das
Zehnfache an Ladezeit, sondern nur das Zehnfache an Diffusion.
"""

import gc
import math
import os
import random
import threading
import time

# Weniger Fragmentierung auf der 24-GB-Karte; muss vor dem ersten CUDA-Zugriff stehen.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from diffusers import QwenImage21Pipeline
from diffusers.pipelines.qwenimage21.pipeline_qwenimage21 import calculate_dimensions

from kataloge import (
    ANGLES, AXIS_OFF, CAMERAS, DEVICES, EFFECTS, FORMS, GROUP_ACTIONS, LIGHTS,
    BEKLEIDUNGEN, HALTUNGEN, MATERIALS, PAINTS, PALETTEN, SCENARIOS, SCENES,
    STYLES, TEMPLATES,
    TRANSPARENT_TEMPLATE, VARIANT_TEMPLATE_POSE,
    VIEWS, fragment, variant_axes,
)

REPO = os.environ.get("QWEN_IMAGE_REPO", "Qwen/Qwen-Image-2.1")
DTYPE = torch.bfloat16
DEVICE = "cuda"
MAX_REFERENCES = 4
# Jedes Referenzbild belegt (kante/16)^2/4 Tokens in der Transformer-Sequenz, und
# die Aufmerksamkeit waechst quadratisch damit. Ueber diesem Budget geht der 24-GB-
# Karte die Luft aus, deshalb werden mehrere Referenzen intern kleiner eingelesen.
REFERENCE_TOKEN_BUDGET = 2200
# Bis zu dieser Bildflaeche dekodiert die VAE in einem Stueck. Darueber
# kachelweise, sonst reicht der Platz neben dem Transformer nicht. Ein
# Quadrat von 1024 liegt genau auf der Grenze und geht damit ungekachelt
# durch -- dort sind die Kachelwolken am sichtbarsten, weil ein Katalogbild
# viel glatte Flaeche hat.
VOLLBILD = int(os.environ.get("QWEN_VOLLBILD", 1024 * 1024))


def reference_resolution(base: int, count: int) -> int:
    """Kantenlaenge, mit der `count` Referenzbilder eingelesen werden."""
    if count < 1:
        return base
    limit = int(math.sqrt(REFERENCE_TOKEN_BUDGET * 1024 / count)) // 32 * 32
    return max(512, min(base, limit))

ASPECT_RATIOS = {
    "1:1": 1 / 1,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}


def dimensions_for(aspect: str, base: int) -> tuple[int, int]:
    """Kantenlaengen wie die Pipeline sie selbst berechnet (Vielfache von 32).

    Ein unbekanntes Seitenverhaeltnis -- etwa ein leerer Wert aus einem
    Auswahlfeld, das nicht gefuellt wurde -- ergibt quadratisch, statt den
    ganzen Auftrag mit einem KeyError abzubrechen.
    """
    width, height, _ = calculate_dimensions(
        base * base, ASPECT_RATIOS.get(aspect, ASPECT_RATIOS["1:1"]))
    return width, height


class _StagedPipeline(QwenImage21Pipeline):
    """Reicht die in Phase 1 erzeugte `image_pad_mask` in Phase 2 durch.

    `__call__` ruft `encode_prompt` ohne `image_pad_mask` auf. Mit
    Referenzbildern und vorberechneten Embeddings wuerde das einen Fehler
    ausloesen, weil die Pipeline sonst nicht weiss, welche Positionen der
    Sequenz Bildtokens sind. Die Masken werden in Aufrufreihenfolge
    (erst positiv, dann negativ) nachgereicht.
    """

    _pad_masks: list | None = None

    def encode_prompt(self, *args, **kwargs):
        if kwargs.get("prompt_embeds") is not None and self._pad_masks:
            kwargs["image_pad_mask"] = self._pad_masks.pop(0)
        return super().encode_prompt(*args, **kwargs)


def _free() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def _karte() -> dict:
    """Wie voll die Grafikkarte ist, in Gigabyte.

    Steht in jeder Statusmeldung. Ein Auftrag, der eine Minute nichts sagt,
    sieht aus wie ein haengender -- an der belegten Karte sieht man, dass
    gerechnet wird. `mem_get_info` zaehlt alle Prozesse mit, nicht nur
    diesen: auch Ollama liegt dort.
    """
    if not torch.cuda.is_available():
        return {}
    try:
        frei, gesamt = torch.cuda.mem_get_info()
    except Exception:                       # eine Anzeige darf nie stoeren
        return {}
    return {"belegt": round((gesamt - frei) / 2**30, 1),
            "gesamt": round(gesamt / 2**30, 1)}


def build_prompt(text: str, view=None, style=None, light=None, camera=None,
                 paint=None, palette=None, scene=None, angle=None, device=None,
                 scenario=None, material=None, haltung=None, kleidung=None,
                 paint_target: str = "") -> str:
    """Haengt die gewaehlten Voreinstellungen an den Prompt an.

    Der Blickwinkel steht vorn: er bestimmt die Bildkomposition, waehrend Stil,
    Licht und Objektiv nur noch die Anmutung nachschaerfen.
    """
    bits = [
        fragment(VIEWS, view),
        # Ohne Ziel kein Farbbaustein -- " is bright red" waere Unsinn, und ein
        # stillschweigend eingesetztes Ersatzziel aendert am falschen Objekt.
        f"{paint_target.strip()} is {PAINTS[paint][1]}"
        if paint in PAINTS and paint_target.strip() else None,
        # Anders als der Lack braucht die Farbstimmung kein Ziel: sie faerbt
        # das ganze Bild.
        fragment(PALETTEN, palette),
        # Haltung und Kleidung frueh: sie bestimmen die Figur, nicht nur die
        # Anmutung. Bei der Haltung kommt ein Gegensatz dazu: die
        # Variantenvorlage verlangt "do not move it", und das schlaegt eine
        # blosse Haltungsangabe. Gemessen an vier Bildern blieb die Person
        # dabei praktisch unveraendert stehen. Deshalb hier ausdruecklich,
        # dass gerade die Haltung sich aendern soll.
        fragment(HALTUNGEN, haltung),
        fragment(BEKLEIDUNGEN, kleidung),
        fragment(SCENES, scene),
        fragment(ANGLES, angle),
        fragment(MATERIALS, material),
        fragment(SCENARIOS, scenario),
        fragment(DEVICES, device),
        fragment(STYLES, style),
        fragment(LIGHTS, light),
        fragment(CAMERAS, camera),
    ]
    return ", ".join([text.strip().rstrip(",")] + [b for b in bits if b])


def _axis(value):
    """Leer und "aus" heissen beide: kein Textbaustein."""
    return None if not value or value == AXIS_OFF else value


class Engine:
    """Fuehrt jeweils eine Serie aus; Fortschritt ist von aussen lesbar."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status = {
            "state": "idle",      # idle | loading | encoding | denoising | error
            "image": 0,           # aktuelles Bild der Serie
            "count": 0,           # Groesse der Serie
            "step": 0,
            "total": 0,
            "message": "bereit",
            "started": 0.0,
            "elapsed": 0.0,
        }
        self._cancel = False
        # Bleibt gesetzt, bis ein neuer Auftrag beginnt. `_cancel` gilt nur fuer
        # den laufenden Durchgang und wird von jedem run_series zurueckgesetzt --
        # eine mehrstufige Vorfuehrung liefe damit einfach weiter.
        self.aborted = False

    # -- Status -----------------------------------------------------------
    def _set(self, **kw) -> None:
        self.status.update(kw)
        if self.status["started"]:
            self.status["elapsed"] = round(time.time() - self.status["started"], 1)

    def note(self, state: str, message: str) -> None:
        """Endzustand von aussen setzen (der Server kennt die Dateinamen)."""
        self._set(state=state, message=message)

    def snapshot(self) -> dict:
        s = dict(self.status)
        if s["started"] and s["state"] not in ("idle", "error"):
            s["elapsed"] = round(time.time() - s["started"], 1)
        s["busy"] = self.lock.locked()
        s["karte"] = _karte()
        return s

    def cancel(self) -> None:
        """Abbrechen -- aber erst nach dem laufenden Bild.

        Frueher wurde die Pipeline mitten im Entrauschen unterbrochen. Das
        kostete die halbe Minute Rechenzeit, die schon in dem Bild steckte,
        und lieferte nichts dafuer. Ein Bild dauert bei 24 Schritten keine
        halbe Minute; so lange darf ein Abbruch warten.
        """
        self._cancel = True
        self.aborted = True

    # -- Laden ------------------------------------------------------------
    def _load(self, kacheln: bool = True, **skip):
        pipe = _StagedPipeline.from_pretrained(REPO, dtype=DTYPE, **skip)
        pipe.to(DEVICE)
        if getattr(pipe, "vae", None) is not None:
            # Slicing teilt nur den Stapel und kostet nichts an Bildqualitaet.
            pipe.vae.enable_slicing()
            # Kacheln dagegen zerlegt das Bild in Flaechen und setzt sie
            # ueberblendet wieder zusammen. Harte Naehte gibt das nicht --
            # aber weiche Helligkeitsunterschiede auf Kachelgroesse, und die
            # sieht man auf einer glatten hellen Flaeche als Wolken und
            # senkrechte Schlieren. Deshalb nur, wo der Platz es verlangt.
            if kacheln:
                pipe.vae.enable_tiling()
        return pipe

    # -- Planung ----------------------------------------------------------
    @staticmethod
    def plan(
        prompt: str,
        count: int,
        seed: int,
        sweep: str | None = None,
        view=None,
        style=None,
        light=None,
        camera=None,
        paint=None,
        palette=None,
        scene=None,
        angle=None,
        device=None,
        scenario=None,
        material=None,
        haltung=None,
        kleidung=None,
        subject: str = "fahrzeug",
        paint_target: str = "",
        lock_seed: bool = False,
    ) -> list[dict]:
        """Baut die Auftragsliste einer Serie.

        Fest gewaehlte Voreinstellungen gelten fuer alle Bilder. `sweep` bestimmt,
        wie die Serie variiert:

          None        alle Bilder gleich, nur der Seed unterscheidet sie
          "view"      umrundet die Person: vorne, Seite, hinten, oben, unten
          "camera"    geht die Kameraperspektiven der Reihe nach durch
          "style"     dito fuer Stile, "light" fuer Lichtstimmungen
          "random"    wuerfelt jedes offene Feld -- reproduzierbar aus dem Seed
          "varianten" wuerfelt Lack, Farbstimmung, Stil, Umgebung, Licht,
                      Kameraart und Blickwinkel
                      fuer jedes Bild neu. Eine Achse auf AXIS_OFF bleibt dabei
                      unangetastet -- so laesst sich etwa nur die Farbe aendern,
                      ohne dass der Hintergrund mitwandert

        `lock_seed` gibt allen Bildern denselben Startseed. Bei einer Umrundung
        haelt das Kleidung, Umgebung und Bildaufbau merklich stabiler, weil das
        Ausgangsrauschen identisch bleibt.
        """
        achsen = variant_axes(subject)
        tables = {"view": VIEWS, "style": STYLES, "light": LIGHTS, "camera": CAMERAS,
                  "paint": PAINTS, "palette": PALETTEN, "scene": SCENES,
                  "angle": ANGLES, "device": DEVICES, "material": MATERIALS,
                  "haltung": HALTUNGEN, "kleidung": BEKLEIDUNGEN}
        rng = random.Random(seed)
        jobs = []
        for i in range(count):
            pick = {"view": view, "style": style, "light": light, "camera": camera,
                    "paint": paint, "palette": palette, "scene": scene,
                    "angle": angle, "device": device, "haltung": haltung,
                    "kleidung": kleidung,
                    "scenario": scenario, "material": material}
            if sweep == "varianten":
                # Jede Achse eigenstaendig gewuerfelt. Ein fester Wert bleibt
                # fest, AXIS_OFF schaltet die Achse ganz ab.
                for field, table in achsen.items():
                    if not pick[field]:
                        pick[field] = rng.choice(list(table))
            elif sweep == "random":
                for field, table in tables.items():
                    if field != "view" and not pick[field]:
                        pick[field] = rng.choice(list(table))
            elif sweep in tables:
                # Der Reihe nach, damit sich die Bilder garantiert unterscheiden.
                keys = list(tables[sweep])
                pick[sweep] = keys[i % len(keys)]
            pick = {k: _axis(v) for k, v in pick.items()}
            jobs.append({
                "seed": seed if lock_seed else seed + i,
                "prompt": build_prompt(prompt, paint_target=paint_target, **pick),
                **pick,
            })
        return jobs

    # -- Generierung ------------------------------------------------------
    def run_series(
        self,
        prompt: str,
        negative_prompt: str = "",
        images: list | None = None,
        mode: str = "t2i",
        aspect: str = "1:1",
        base: int = 1024,
        follow_reference: bool = True,
        steps: int = 40,
        seed: int = 42,
        true_cfg_scale: float = 1.0,
        transparent: bool = False,
        effect: str | None = None,
        form: str | None = None,
        count: int = 1,
        sweep: str | None = None,
        lock_seed: bool = False,
        keep: str = "The main subject",
        view=None,
        paint=None,
        palette=None,
        scene=None,
        angle=None,
        device=None,
        scenario=None,
        material=None,
        haltung=None,
        kleidung=None,
        subject: str = "fahrzeug",
        image_prompts: list | None = None,
        prompts: list | None = None,
        seeds: list | None = None,
        action: str = "zusammen",
        group_size: int = 2,
        paint_target: str = "",
        style=None,
        light=None,
        camera=None,
        on_image=None,
    ) -> list[dict]:
        """Erzeugt `count` Bilder. `images` schaltet auf Referenzbilder um.

        `on_image(meta, pil)` wird nach jedem fertigen Bild aufgerufen, damit die
        Oberflaeche die Serie beim Entstehen zusehen kann.
        """
        images = images or []
        if len(images) > MAX_REFERENCES:
            raise ValueError(f"Hoechstens {MAX_REFERENCES} Referenzbilder moeglich.")

        text = prompt.strip()
        if form in FORMS:
            text = FORMS[form]["template"].format(extra=text)
        spec = EFFECTS.get(effect or "", {})
        if spec.get("instruction"):
            # Die Anweisung steht vorn, der Benutzertext praezisiert sie.
            text = f"{spec['instruction']} {text}".strip()
        if mode == "gruppe":
            # Zusammenstellen, ergaenzen und entfernen brauchen je eigene Worte.
            spec_action = GROUP_ACTIONS.get(action) or GROUP_ACTIONS["zusammen"]
            if len(images) < spec_action["min"]:
                raise ValueError(
                    f"„{spec_action['label']}“ braucht mindestens "
                    f"{spec_action['min']} Referenzbild(er).")
            if action == "entfernen" and not text:
                raise ValueError("Bitte beschreiben, wer entfernt werden soll.")
            zusatz = max(len(images) - 1, 1)
            text = spec_action["template"].format(
                n=len(images), m=zusatz, extra=text,
                total=max(group_size, 1) + zusatz)
            # Rollen je Referenzbild: "Person aus Bild 2 als Ritter darstellen".
            rollen = [f"Depict the person from reference image {i + 1} as {d.strip()}"
                      for i, d in enumerate(image_prompts or []) if d and d.strip()]
            if rollen:
                text = f"{text} {'. '.join(rollen)}."
        elif mode in TEMPLATES:
            if not images:
                raise ValueError("Fuer diesen Modus werden Referenzbilder gebraucht.")
            # Soll sich die Haltung aendern, darf die Vorlage nicht zugleich
            # "nicht bewegen" verlangen -- sonst entstehen doppelte Beine.
            vorlage = TEMPLATES[mode]
            if mode == "varianten" and subject == "person" and haltung != AXIS_OFF:
                vorlage = VARIANT_TEMPLATE_POSE
            text = vorlage.format(
                n=len(images), extra=text, keep=keep.strip() or "The main subject")
        if transparent:
            text = TRANSPARENT_TEMPLATE.format(extra=text)

        if prompts:
            # Fertige Prompts, einer je Bild. Damit laesst sich eine ganze Folge
            # verschiedener Bilder in einem einzigen Ladevorgang abarbeiten --
            # sonst kostet jedes Bild erneut eine Minute Modellladen.
            jobs = [{"seed": (seeds[i] if seeds and i < len(seeds)
                              else (seed if lock_seed else seed + i)), "prompt": p,
                     "view": None, "style": None, "light": None, "camera": None,
                     "paint": None, "palette": None, "scene": None, "angle": None,
                     "device": None, "scenario": None, "material": None,
                     "haltung": None, "kleidung": None}
                    for i, p in enumerate(prompts)]
        else:
            # Mit Namen statt der Reihe nach: die Achsenliste waechst, und eine
            # verrutschte Stellung faellt sonst erst am falschen Bild auf.
            jobs = self.plan(text, count, seed, sweep, view=view, style=style,
                             light=light, camera=camera, paint=paint,
                             palette=palette, scene=scene, angle=angle,
                             device=device, scenario=scenario, material=material,
                             haltung=haltung, kleidung=kleidung,
                             subject=subject, paint_target=paint_target,
                             lock_seed=lock_seed)

        self._cancel = False
        self._set(state="loading", image=0, count=len(jobs), step=0, total=steps,
                  started=time.time(), message="Text-Encoder wird geladen")

        # Die Ausgabegroesse wird immer selbst bestimmt. Dadurch steuert
        # `output_resolution` in Phase 2 nur noch, wie gross die Referenzbilder
        # gelesen werden -- die beiden Groessen sind so entkoppelt.
        if images and follow_reference:
            ratio = images[0].size[0] / images[0].size[1]
            width, height, _ = calculate_dimensions(base * base, ratio)
        else:
            width, height = dimensions_for(aspect, base)

        cond_base = reference_resolution(base, len(images))

        # --- Phase 1: alle Prompts einbetten ------------------------------
        encoder = self._load(transformer=None, vae=None)
        try:
            condition = None
            if images:
                # Genau die Groesse, die Phase 2 selbst berechnen wuerde. Nur wenn
                # beide Phasen dieselben Kantenlaengen sehen, passen Bildmaske und
                # Latent-Raster im Transformer zusammen.
                condition = []
                for img in images:
                    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
                    iw, ih, _ = calculate_dimensions(cond_base * cond_base, rgba.size[0] / rgba.size[1])
                    condition.append(encoder.image_processor.resize(rgba, width=iw, height=ih))

            self._set(state="encoding", message=f"{len(jobs)} Prompt(s) werden eingebettet")
            with torch.no_grad():
                for job in jobs:
                    job["embeds"] = encoder.encode_prompt(
                        prompt=job["prompt"], image=condition, device=DEVICE
                    )
                    if self._cancel:
                        break
                negative = None
                if true_cfg_scale > 1 and negative_prompt.strip():
                    negative = encoder.encode_prompt(
                        prompt=negative_prompt, image=condition, device=DEVICE
                    )
        finally:
            del encoder
            _free()

        if self._cancel:
            self._set(state="idle", message="abgebrochen")
            return []

        # --- Phase 2: entrauschen und dekodieren --------------------------
        self._set(state="loading", message="Transformer + VAE werden geladen")
        pipe = self._load(text_encoder=None, kacheln=width * height > VOLLBILD)
        results = []

        try:
            for index, job in enumerate(jobs, start=1):
                if self._cancel:
                    break

                def on_step(_pipe, i, _t, kwargs, _n=index):
                    self._set(state="denoising", image=_n, step=i + 1,
                              message=f"Bild {_n}/{len(jobs)} · Schritt {i + 1}/{steps}")
                    return kwargs

                pos = job["embeds"]
                pipe._pad_masks = [pos[2]] + ([negative[2]] if negative else [])
                self._set(state="denoising", image=index, step=0,
                          message=f"Bild {index}/{len(jobs)} startet")

                out = pipe(
                    prompt_embeds=pos[0],
                    prompt_embeds_mask=pos[1],
                    negative_prompt_embeds=negative[0] if negative else None,
                    negative_prompt_embeds_mask=negative[1] if negative else None,
                    image=condition or None,
                    width=width,
                    height=height,
                    output_resolution=cond_base,
                    num_inference_steps=steps,
                    true_cfg_scale=true_cfg_scale,
                    generator=torch.Generator(DEVICE).manual_seed(job["seed"]),
                    callback_on_step_end=on_step,
                )
                # Kein Abbruch hier: das Bild ist fertig gerechnet, also
                # wird es auch abgelegt. Gestoppt wird danach, am Kopf der
                # naechsten Runde.
                image_out = out.images[0]
                # Alles aus dem Auftrag ausser den Einbettungen. Eine zweite
                # Schluesselliste hier waere eine Falle: eine neue Achse landete
                # sonst im Prompt, aber nicht in den Bilddaten.
                meta = {k: v for k, v in job.items() if k != "embeds"}
                meta["index"] = index
                meta["effect"] = effect
                meta["form"] = form
                results.append(meta)
                if on_image:
                    on_image(meta, image_out)
                job["embeds"] = None
        finally:
            del pipe
            _free()

        return results
