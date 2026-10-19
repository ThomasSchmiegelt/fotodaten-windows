"""Was abgebildet wird: Umgebung, Blickwinkel und Werkstoff je Motivart.

Ein Fahrzeug will andere Umgebungen als ein Gegenstand und ein Gegenstand
andere als eine Person -- deshalb drei Saetze Tabellen, die `SUBJECT_KINDS`
zusammenfuehrt. `variant_axes` sagt zum Schluss, woraus eine Variantenserie
wuerfeln darf.
"""

from .anmutung import (
    BEKLEIDUNGEN, DEVICES, HALTUNGEN, PAINTS, PALETTEN, STYLES, VARIANT_LIGHTS,
)

# Fuer ein Fahrzeug der Untergrund, nicht die Umgebung: eine Kupplung sitzt
# dicht ueber dem Boden, und was der Detektor lernen muss, ist sie vor
# Schotter, Gras, Pflaster und nassem Asphalt -- nicht vor einer Tiefgarage
# im Hintergrund. Die Schluessel aelterer Datensaetze bleiben, wo der Sinn
# derselbe ist (hof, schotter, wiese, regen, schnee).
VEHICLE_SCENES = {
    "asphalt":  ("Asphalt", "standing on dry grey asphalt"),
    "regen":    ("Nasser Asphalt", "standing on wet dark asphalt with rain puddles and reflections"),
    "schotter": ("Schotter", "standing on coarse grey gravel"),
    "splitt":   ("Feiner Kies", "standing on fine light pea gravel"),
    "gras":     ("Rasen", "standing on short mown green lawn"),
    "wiese":    ("Wiese", "standing in a meadow with tall grass and wild flowers"),
    "kopfstein": ("Kopfsteinpflaster", "standing on old rounded cobblestones"),
    "hof":      ("Pflastersteine", "standing on grey concrete paving stones"),
    "rasengitter": ("Rasengitter", "standing on grass paver blocks with grass growing through"),
    "beton":    ("Beton", "standing on a smooth grey concrete floor"),
    "erde":     ("Feldweg", "standing on a dry dirt track"),
    "matsch":   ("Matsch", "standing on muddy ground with tyre ruts"),
    "sand":     ("Sand", "standing on loose sand"),
    "laub":     ("Laub", "standing on ground covered in fallen autumn leaves"),
    "schnee":   ("Schnee", "standing on a snow-covered surface in winter"),
}


# Blickwinkel auf ein Fahrzeug. Die Bausteine nennen Stossstange und Heck,
# taugen also nur hier -- fuer Gegenstaende und Personen gibt es eigene Saetze.
VEHICLE_ANGLES = {
    "gerade":     ("Gerade von hinten", "seen straight from behind at bumper height"),
    "linksleicht": ("Leicht von links", "seen from slightly left of centre"),
    "rechtsleicht": ("Leicht von rechts", "seen from slightly right of centre"),
    "linksschraeg": ("Schräg von links", "seen at a 40 degree angle from the left rear"),
    "rechtsschraeg": ("Schräg von rechts", "seen at a 40 degree angle from the right rear"),
    "tief":       ("Bodennah", "seen from a low camera position close to the ground"),
    "erhoeht":    ("Erhöht", "seen from slightly above, looking down at the rear"),
    "nah":        ("Nahaufnahme", "a close-up filling most of the frame"),
    "weit":       ("Abstand", "seen from further away with the whole rear of the vehicle visible"),
    "hochkant":   ("Aufrecht", "an upright portrait framing of the rear"),
    "gekipptlinks": ("Gekippt links", "a handheld shot with the camera tilted a few degrees to the left"),
    "gekipptrechts": ("Gekippt rechts", "a handheld shot with the camera tilted a few degrees to the right"),
}


# --- Motivarten ----------------------------------------------------------
# Umgebung und Blickwinkel haengen davon ab, was auf dem Bild ist. "Auf einem
# Schotterplatz stehend" und "auf Stossstangenhoehe von hinten" passen zu einem
# Auto und zu nichts sonst. Deshalb je ein eigener Satz.
OBJECT_SCENES = {
    "og_studio":  ("Studiotisch", "on a seamless studio backdrop with soft shadows"),
    "og_holz":    ("Holztisch", "on a worn wooden table"),
    "og_werkbank": ("Werkbank", "on a metal workbench with tools around it"),
    "og_beton":   ("Beton", "on a raw concrete surface"),
    "og_stoff":   ("Stoff", "on folded linen fabric"),
    "og_regal":   ("Regal", "on a shelf next to other products"),
    "og_karton":  ("Neben der Verpackung", "next to its cardboard packaging"),
    "og_draussen": ("Im Freien", "outdoors on a stone wall in daylight"),
    "og_labor":   ("Labor", "on a clean white laboratory bench"),
    "og_einsatz": ("Im Einsatz", "in its actual place of use, installed and connected"),
    "og_scifi":   ("Raumstation", "mounted in a bracket aboard a space station, metal bulkhead behind it"),
}


OBJECT_ANGLES = {
    "og_vorn":    ("Von vorn", "seen straight from the front at eye level"),
    "og_schraeg": ("Dreiviertel", "seen at a three-quarter angle from the front left"),
    "og_seite":   ("Von der Seite", "seen from directly at the side"),
    "og_oben":    ("Von oben", "seen from directly above, flat lay"),
    "og_45":      ("Aufsicht 45°", "seen from a 45 degree elevated angle"),
    "og_tief":    ("Untersicht", "seen from slightly below, hero angle"),
    "og_detail":  ("Detail", "an extreme close-up of one part of the object"),
    "og_hand":    ("In der Hand", "held in a hand, showing its scale"),
    "og_frei":    ("Freigestellt", "isolated on a plain background with a soft drop shadow"),
}


PERSON_SCENES = {
    "ps_studio":  ("Studio", "in a photo studio against a plain backdrop"),
    "ps_strasse": ("Stadtstraße", "on a city street"),
    "ps_park":    ("Park", "in a green park"),
    "ps_buero":   ("Büro", "in a modern office"),
    "ps_kueche":  ("Küche", "in a bright kitchen"),
    "ps_cafe":    ("Café", "in a café"),
    "ps_strand":  ("Strand", "on a beach"),
    "ps_wald":    ("Wald", "on a forest path"),
    "ps_bahnhof": ("Bahnhof", "in a railway station concourse"),
    "ps_werkstatt": ("Werkstatt", "in a workshop"),
    "ps_schlaf":  ("Schlafzimmer", "in a bedroom, soft morning light through the curtains, rumpled bedding"),
    "ps_raumschiff": ("Raumschiffbrücke", "on the bridge of a spaceship, glowing consoles and a wide viewport onto stars"),
    "ps_labor":   ("Labor", "in a laboratory behind glass walls, cold even light, instruments on the benches"),
}


PERSON_ANGLES = {
    "pa_vorne":  ("Von vorn", "seen from the front, facing the camera"),
    "pa_halb":   ("Halbprofil", "seen at a three-quarter angle"),
    "pa_profil": ("Profil", "seen from the side in profile"),
    "pa_hinten": ("Von hinten", "seen from behind"),
    "pa_nah":    ("Nah", "a close portrait crop from the chest up"),
    "pa_ganz":   ("Ganzkörper", "a full body shot"),
    "pa_tief":   ("Untersicht", "seen from a low angle"),
    "pa_hoch":   ("Aufsicht", "seen from slightly above"),
}


# Werkstoff. Vor allem fuer Gegenstaende gedacht und deshalb standardmaessig
# abgeschaltet -- eine gewuerfelte "aus Gusseisen"-Person waere Unsinn.
MATERIALS = {
    "alu":       ("Aluminium", "made of brushed aluminium"),
    "stahl":     ("Edelstahl", "made of polished stainless steel"),
    "kunststoff": ("Kunststoff matt", "made of matte injection-moulded plastic"),
    "holz":      ("Holz", "made of oiled hardwood"),
    "carbon":    ("Carbon", "made of carbon fibre with a visible weave"),
    "gummi":     ("Gummi", "made of textured black rubber"),
    "glas":      ("Glas", "made of clear glass"),
    "messing":   ("Messing", "made of brushed brass"),
    "keramik":   ("Keramik", "made of glazed ceramic"),
    "guss":      ("Gusseisen", "made of raw cast iron"),
}


SUBJECT_KINDS = {
    "fahrzeug":   {"label": "Fahrzeug", "scenes": VEHICLE_SCENES, "angles": VEHICLE_ANGLES,
                   "target": "die Karosserie"},
    "gegenstand": {"label": "Gegenstand", "scenes": OBJECT_SCENES, "angles": OBJECT_ANGLES,
                   "target": "das Gehäuse"},
    "person":     {"label": "Person", "scenes": PERSON_SCENES, "angles": PERSON_ANGLES,
                   "target": "die Jacke der Person"},
}


# Zum Nachschlagen eines einzelnen Wertes ist egal, aus welchem Satz er stammt.
SCENES = {**VEHICLE_SCENES, **OBJECT_SCENES, **PERSON_SCENES}


ANGLES = {**VEHICLE_ANGLES, **OBJECT_ANGLES, **PERSON_ANGLES}


def variant_axes(subject: str) -> dict:
    """Die Tabellen, aus denen fuer diese Motivart gewuerfelt wird."""
    kind = SUBJECT_KINDS.get(subject) or SUBJECT_KINDS["fahrzeug"]
    achsen = {"paint": PAINTS, "palette": PALETTEN, "style": STYLES,
              "scene": kind["scenes"], "light": VARIANT_LIGHTS,
              "device": DEVICES, "angle": kind["angles"]}
    # Haltung und Bekleidung ergeben nur bei Lebendigem Sinn -- ein Kotfluegel
    # traegt keine Jeans.
    if subject == "person":
        achsen["haltung"] = HALTUNGEN
        achsen["kleidung"] = BEKLEIDUNGEN
    # Eine gewuerfelte "aus Gusseisen"-Person waere Unsinn. Von Hand festgelegt
    # geht der Werkstoff weiterhin, nur gewuerfelt wird er hier nicht.
    if subject != "person":
        achsen["material"] = MATERIALS
    return achsen
