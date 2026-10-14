"""Das Geruest: Prompt-Vorlagen, Effekte, Bildtypen, Gruppenaufgaben.

Waehrend `anmutung` und `motiv` nur Textschnipsel liefern, steht hier das
Geruest, in das der Text des Benutzers eingesetzt wird -- dazu die Effekte,
die nebenbei die Regler umstellen.
"""

# Anweisungen, die je nach Modus vor den Benutzertext gesetzt werden.
# Was Diffusionsmodellen an Menschen regelmaessig misslingt. Beobachtet an
# verschmolzenen Hosenbeinen, einem dritten Schuh und verschmierten
# Zahnreihen. Ein knapper Hinweis hilft spuerbar und kostet nur ein paar
# Wortmarken -- er gehoert ueberall dorthin, wo ein Koerper neu gezeichnet
# wird, nicht nur an die Haltungsachse.
ANATOMIE = (
    "Correct human anatomy: exactly two arms, two hands with five fingers "
    "each, two legs and two feet, nothing doubled, nothing merged, nothing "
    "overlapping itself. If teeth are visible, draw them cleanly: even, "
    "correctly shaped, the right number."
)

TEMPLATES = {
    "gruppe": (
        "A single group photograph showing all {n} people from the reference images together "
        "in one frame, side by side. Keep every person's face, hair and identity clearly "
        "recognizable and consistent with their reference image. " + ANATOMIE
        + " {extra}"
    ),
    "person": (
        "The same person as in the reference image, {extra}. Keep the person's identity, "
        "hairstyle, build and outfit consistent with the reference image, in the same setting. "
        + ANATOMIE
    ),
}


TRANSPARENT_TEMPLATE = (
    "This is an RGBA image with transparency. {extra} "
    "The image has alpha channel and the background is transparent."
)


# Vor den Benutzertext im Varianten-Modus. Die Unveraenderlichkeit steht
# bewusst zweimal drin -- einmal als Anweisung, einmal als Aufzaehlung der
# Merkmale. Ein Diffusionsmodell ueberschreibt sonst gern mit.
VARIANT_TEMPLATE = (
    "A photograph of the same subject as in the reference image. "
    # "relative to the vehicle" stand hier fest, obwohl die Vorlage seit
    # laengerem auch fuer Gegenstaende und Personen gilt -- bei einer Person
    # war das schlicht Unsinn.
    "{keep} must remain exactly identical to the reference: same shape, "
    "same size, same colour, same finish, the same position in the frame and "
    "the same proportions. Do not redesign it, do not move it, "
    "do not change its colour. Everything else in the picture may differ. {extra}"
)

# Wenn sich die Haltung aendern soll, passt die obige Vorlage nicht: sie
# verlangt "do not move it". Beides zusammen -- bewahren und bewegen --
# beantwortet das Modell, indem es die alten Gliedmassen behaelt UND neue
# malt. Beobachtet an einem Bild mit drei Schuhen und einem mit
# verschmolzenen Hosenbeinen. Deshalb hier eine Fassung ohne den
# Widerspruch: die Person bleibt, der Koerper wird neu gezeichnet.
VARIANT_TEMPLATE_POSE = (
    "A photograph of the same person as in the reference image. "
    "{keep} stays exactly as in the reference: the same face, the same hair, "
    "the same clothing, the same colours and materials. "
    "The body takes a new pose -- draw the whole figure fresh for that pose "
    "rather than keeping the old one. "
    + ANATOMIE +
    " Everything else in the picture may differ. {extra}"
)

# Die Variantenvorlage ist selbst eine Modusvorlage -- hier eingehaengt, damit
# TEMPLATES[mode] sie findet wie die anderen.
TEMPLATES["varianten"] = VARIANT_TEMPLATE


# --- Effekte -------------------------------------------------------------
# Die meisten "Kurzbefehle" sind keine eigenen Modelle, sondern Anweisungen an
# den Bearbeiten-Pfad. Jeder Eintrag kann zusaetzlich Einstellungen umstellen
# (Kamera, Transparenz, Serienart), die sonst von Hand gesetzt wuerden.
EFFECTS = {
    "removebg": {
        "alias": "/remove bg", "label": "Hintergrund entfernen", "needs_image": True,
        "transparent": True,
        "instruction": "Remove the background completely and keep only the main subject, "
                       "cleanly separated at the edges including fine detail like hair.",
    },
    "magazine": {
        "alias": "/magazine cover", "label": "Magazin-Cover", "needs_image": True,
        "instruction": "Turn this into a glossy magazine cover: masthead across the top, "
                       "cover lines down the sides, barcode and issue date, professional layout.",
    },
    "explosion": {
        "alias": "/ptexplosion", "label": "Explosionszeichnung", "needs_image": True,
        "instruction": "Show this product as an exploded view: the parts separated along their "
                       "assembly axes and floating apart, clean studio backdrop.",
    },
    "lifestyle": {
        "alias": "/lifestyle shot", "label": "Lifestyle-Aufnahme", "needs_image": True,
        "instruction": "Place this product into a natural lifestyle setting where it would "
                       "really be used, with believable surroundings, props and daylight.",
    },
    "expand": {
        # Qwen-Image 2.1 hat keinen Masken-Eingang und kein Outpainting: einen
        # freigelassenen Rand fuellt es nicht auf. Es zeichnet die Szene aber
        # zuverlaessig im neuen Format neu -- die Mitte ist danach nicht
        # pixelgleich, dafuer stimmen Person, Umgebung und Licht.
        "alias": "/expand", "label": "Bildausschnitt erweitern", "needs_image": True,
        "instruction": "Show this exact same scene as a much wider shot: the camera pulls back "
                       "and reveals more of the surroundings on the left and right. Keep the "
                       "subject, the clothing, the setting, the light and the style identical.",
    },
    "cad2real": {
        "alias": "/cad2real", "label": "CAD zu Foto", "needs_image": True,
        "instruction": "Turn this CAD rendering into a photorealistic product photograph. "
                       "Keep the geometry, the proportions and every edge, hole, fastener "
                       "and detail of the design exactly as drawn -- do not redesign "
                       "anything and do not add or remove parts. Replace the flat CAD "
                       "shading with real materials: correct surface finish, faint wear "
                       "and handling marks, realistic reflections, accurate shadows "
                       "including a contact shadow on the surface it rests on, and the "
                       "shallow depth of field of a real camera.",
    },
    "cad": {
        # Der Gegenpart zu /cad2real. Dass das Modell CAD-Darstellungen kennt,
        # zeigt der umgekehrte Weg -- hier muss es die Materialien nur
        # weglassen statt sie zu erfinden. Laengere Aliase werden zuerst
        # geprueft, "/cad" haengt sich also nicht an "/cad2real".
        "alias": "/cad", "label": "Foto zu CAD", "needs_image": True,
        "instruction": "Turn this into a CAD rendering of the same object: an "
                       "untextured solid model in uniform light grey, every "
                       "edge drawn as a crisp darker line, flat even shading "
                       "without reflections, highlights, grain or depth of "
                       "field, on a plain pale background with a faint "
                       "construction grid. Keep the geometry, the proportions "
                       "and every part exactly as in the photograph -- a CAD "
                       "view shows the same object, not a new design.",
    },
    "upscale": {
        # Qwen-Image 2.1 ist kein Skalierer: es zeichnet das Bild in der
        # groesseren Kantenlaenge neu. Das Ergebnis ist deshalb nicht
        # pixelgleich, dafuer entstehen echte Strukturen statt geglaetteter
        # Kanten. Bei base 2048 wird die Vorlage mit 1472 px gelesen und
        # 2496x1664 ausgegeben -- die Proportionen kommen ueber
        # follow_reference aus der Vorlage selbst.
        "alias": "/upscale", "label": "Hochskalieren (mehr Details)",
        "needs_image": True, "mode": "edit", "base": 2048,
        "instruction": "Reproduce this exact image at high resolution. The composition, "
                       "the framing, the subject, the pose, the colours and the light stay "
                       "exactly as they are -- nothing is added, removed, moved or restyled. "
                       "Only the detail becomes finer: crisp edges, clean material and fabric "
                       "texture, individual strands of hair, legible small structures, natural "
                       "skin detail. No blur, no noise, no halos around edges.",
    },
    "colorize": {
        "alias": "/colorize", "label": "Einfärben", "needs_image": True,
        "instruction": "Colorize this black and white photograph with natural, period-accurate "
                       "colors, keeping every detail and the original grain intact.",
    },
    "doubleexposure": {
        "alias": "double exposure", "label": "Doppelbelichtung", "needs_image": True,
        "instruction": "Render this as a double exposure: the silhouette of the subject filled "
                       "with a second scene blending through it.",
    },
    "glass": {
        "alias": "/glass", "label": "Glaseffekt", "needs_image": True,
        "instruction": "Seen through thick textured glass, with refraction, distortion and "
                       "condensation breaking up the shapes.",
    },
    "restore": {
        "alias": "/restore", "label": "Altes Foto auffrischen", "needs_image": True,
        "instruction": "Restore this damaged old photograph: repair scratches, tears and stains, "
                       "recover sharpness and contrast, keep the original composition and faces "
                       "exactly as they are.",
    },
    "tinyhumans": {
        "alias": "/tinyhumans", "label": "Winzige Menschen", "needs_image": True,
        "instruction": "Add tiny miniature people working on and around the subject, "
                       "tilt-shift miniature effect, the subject towering over them.",
    },
    "blueprint": {
        "alias": "/blueprint", "label": "Bauplan", "needs_image": True,
        "instruction": "Turn this into a technical blueprint drawing: white line work on blue "
                       "paper, dimension lines, callouts and a title block.",
    },
    "handwritten": {
        "alias": "/handwritten", "label": "Handschrift", "needs_image": True,
        "instruction": "Redraw the lettering in this image as natural handwriting with ink pen, "
                       "slight irregularity, on paper texture.",
    },
    # Diese beiden stellen nur vorhandene Regler um.
    "droneview": {
        "alias": "/droneview", "label": "Drohnenperspektive", "needs_image": False,
        "camera": "drohne",
    },
    "extremewide": {
        "alias": "extreme wide", "label": "Extremes Weitwinkel", "needs_image": False,
        "camera": "fisch",
    },
    "orbit": {
        "alias": "/360 view", "label": "Rundum-Ansicht", "needs_image": True,
        "mode": "person", "sweep": "view", "count": 10, "lock_seed": True,
    },
}


# --- Vorlagen ------------------------------------------------------------
# Geruest fuer einen Bildtyp. `{extra}` ist das, was der Benutzer eintippt.
FORMS = {
    "portraet": {
        "label": "Porträt", "aspect": "3:4", "style": "foto", "camera": "portraet",
        "template": "A professional portrait photograph of {extra}, "
                    "sharp eyes, flattering framing, clean background.",
    },
    "logo": {
        "label": "Logo", "aspect": "1:1", "transparent": True, "style": "minimal",
        "template": "A clean flat vector logo for {extra}. Simple bold shapes, "
                    "balanced negative space, legible at small size, no photographic detail.",
    },
    "illustration": {
        "label": "Illustration", "aspect": "3:2", "style": "aquarell",
        "template": "An illustration of {extra}, coherent palette, clear focal point.",
    },
    "buchumschlag": {
        "label": "Buchumschlag", "aspect": "2:3",
        "template": "A book cover for {extra}. Title lettering at the top, author name at the "
                    "bottom, strong central image, the typography sharp and correctly spelled.",
    },
    "verpackung": {
        "label": "Produktverpackung", "aspect": "1:1", "style": "technisch",
        "template": "Retail packaging design for {extra}, shown as a product photo of the box "
                    "on a clean surface, readable label, realistic material and print.",
    },
    "symbolbild": {
        "label": "Symbolbild / Icon", "aspect": "1:1", "transparent": True, "style": "minimal",
        "template": "A single clear pictogram icon representing {extra}. "
                    "One centred symbol, uniform stroke weight, no text, no frame.",
    },
    "webseite": {
        "label": "Webseiten-Muster", "aspect": "16:9", "style": "minimal",
        "template": "A clean website landing page mockup for {extra}: header with navigation, "
                    "hero section with headline and button, content cards below, shown flat.",
    },
    "app": {
        "label": "App-Muster", "aspect": "9:16", "style": "minimal",
        "template": "A mobile app screen mockup for {extra}: status bar, title, list of content "
                    "cards, bottom tab bar, modern flat interface design.",
    },
}


# --- Gruppenbilder -------------------------------------------------------
# "Zusammenstellen", "ergaenzen" und "entfernen" sind drei verschiedene
# Aufgaben. Eine gemeinsame Anweisung dafuer waere schwammig, deshalb je eine
# eigene -- samt Mindestzahl an Referenzbildern.
GROUP_ACTIONS = {
    "zusammen": {
        "label": "Aus Einzelbildern zusammenstellen", "min": 2,
        "hint": "Pro Person ein Bild, 2 bis 4 Stück.",
        "template": (
            "A single group photograph showing all {n} people from the reference images "
            "together in one frame, side by side. Keep every person's face, hair and "
            "identity clearly recognizable and consistent with their reference image. {extra}"
        ),
    },
    "ergaenzen": {
        "label": "Person ergänzen", "min": 2,
        "hint": "Erstes Bild: das Gruppenfoto. Danach je ein Bild pro Person, die dazu soll.",
        # Ohne ausdrueckliche Zahl verschmilzt das Modell die zusaetzliche Person
        # mit einer vorhandenen -- mit einem vagen "mehr als vorher" stellt es
        # dagegen gleich mehrere dazu. Es kann nicht zaehlen, wie viele schon im
        # Bild sind, deshalb gibt der Benutzer die Endzahl vor.
        "template": (
            "The first reference image is an existing group photograph. The following "
            "{m} reference image(s) each show one further person who is NOT yet part of "
            "that group. Redraw the group photograph so that it contains everyone from "
            "the first image PLUS those {m} further people standing alongside them. "
            "The finished picture must show exactly {total} people, no more and no "
            "fewer. Do not replace "
            "anyone, do not merge two people into one, and do not change anyone's "
            "clothing. Keep the existing people, their faces, their poses, the ground, "
            "the lighting and the background exactly as they are, and match the new "
            "people to that same lighting, perspective and scale. {extra}"
        ),
    },
    # Der Weg zum Stilbruch, den ein einzelner Prompt nicht hergibt: das
    # Bildmodell zieht einen Stil immer ueber das ganze Bild. Zwei fertige
    # Bilder nebeneinanderzulegen kann es dagegen -- eine Collage ist ihm
    # ein vertrautes Motiv, ein halb gezeichnetes Bild nicht.
    "einsetzen": {
        "label": "Figur in eine Szene setzen", "min": 2,
        "hint": "Erstes Bild: die Szene. Danach je ein Bild pro Figur, "
                "freigestellt. Der eigene Stil jeder Figur bleibt erhalten.",
        "template": (
            "The first reference image is a scene. The following {m} reference "
            "image(s) each show one figure standing against a plain "
            "background. Place those figures into the scene so that they "
            "stand in it convincingly: correct scale, a plausible position on "
            "the ground, and a contact shadow where they touch it. "
            "Keep the scene itself unchanged -- its background, its light and "
            "its look. Keep every figure exactly as in its own reference "
            "image: face, hair, clothing, colours AND its visual style. If a "
            "figure is photographic and the scene is drawn, that difference "
            "must stay visible, like a photograph cut out and pasted into a "
            "drawing, with a hard edge where the two meet. Do not redraw a "
            "figure in the style of the scene, and do not restyle the scene "
            "to match a figure. {extra}"
        ),
    },
    "entfernen": {
        "label": "Person entfernen", "min": 1,
        "hint": "Nur das Gruppenfoto. Unten beschreiben, wer verschwinden soll.",
        "template": (
            "The reference image is a group photograph. Remove {extra} from the picture "
            "and close the gap naturally, as if that person had never been there. Keep "
            "everyone else, their faces, their poses, the lighting and the background "
            "exactly as they are."
        ),
    },
}


# Inszenierung einer Gruppe. Bewusst als Beschreibung des Aussehens formuliert
# und nicht als Verweis auf einen Film -- das Modell trifft eine ausformulierte
# Bildbeschreibung deutlich zuverlaessiger als einen Werktitel.
SCENARIOS = {
    "geister": ("Machtgeister", "rendered as glowing translucent blue spirit figures, "
                "softly luminous edges, faint shimmer around their outlines, "
                "semi-transparent robes, dark background"),
    "gefaehrten": ("Fantasy-Gefährten", "as an epic fantasy fellowship in worn travelling "
                   "cloaks with swords, bows and packs, standing on a mountain path at "
                   "dawn, painterly and cinematic"),
    "ritter": ("Tafelrunde", "as medieval knights in polished plate armour with surcoats, "
               "in a torchlit stone hall"),
    "wikinger": ("Wikinger", "as norse warriors in furs and leather with braided hair, "
                 "on a windswept rocky shore under grey clouds"),
    "helden": ("Superhelden", "as comic book superheroes in bold costumes with capes, "
               "heroic low angle, dramatic sky behind them"),
    "crew": ("Raumschiffbesatzung", "as the crew of a spaceship in fitted uniforms, "
             "standing on an illuminated bridge with screens behind them"),
    "western": ("Western", "as characters in a dusty frontier town, long coats and hats, "
                "harsh noon sun, sepia tones"),
    "noir": ("Detektive", "as film noir detectives in trench coats and fedoras, "
             "high contrast black and white, venetian blind shadows"),
    "renaissance": ("Gemälde", "as figures in a renaissance oil painting, rich fabrics, "
                    "chiaroscuro lighting, cracked varnish texture"),
    "abschluss": ("Abschlussfoto", "as a formal graduation photograph in gowns and caps, "
                  "on the steps of a university building"),
    "band": ("Band", "as a rock band photographed for an album cover, leather and denim, "
             "moody backstage lighting"),
    "familie": ("Familienporträt", "as a warm formal family portrait in a photo studio, "
                "soft key light, plain backdrop"),
}


# Einstellungen, die ein Effekt oder eine Vorlage mitbringen darf.
OVERRIDE_KEYS = ("aspect", "style", "light", "camera", "view", "mode",
                 "sweep", "count", "lock_seed", "transparent", "base")


def parse_command(text: str) -> tuple[str | None, str]:
    """Erkennt einen fuehrenden Kurzbefehl und gibt (Effekt-Schluessel, Resttext).

    Laengere Befehle zuerst, damit "/remove bg" nicht an "/remove" haengenbleibt.
    """
    lowered = text.strip().lower()
    for key, spec in sorted(EFFECTS.items(), key=lambda kv: -len(kv[1]["alias"])):
        alias = spec["alias"]
        if lowered.startswith(alias):
            return key, text.strip()[len(alias):].lstrip(" :,")
    return None, text


def overrides(spec: dict) -> dict:
    """Die Einstellungen, die ein Effekt oder eine Vorlage mitbringt."""
    return {k: spec[k] for k in OVERRIDE_KEYS if k in spec}
