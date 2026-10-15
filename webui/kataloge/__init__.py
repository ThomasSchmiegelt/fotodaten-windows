"""Die Voreinstellungen der Oberflaeche, nach Sinn getrennt.

    anmutung   wie es aussieht: Stil, Licht, Blickwinkel, Objektiv, Farbe
    motiv      was abgebildet wird: Umgebung, Blickwinkel, Werkstoff
    vorlage    das Geruest: Prompt-Vorlagen, Effekte, Bildtypen, Gruppen

Alles ist auch von hier erreichbar: `from kataloge import STYLES` genuegt.
Wer nur einen Textbaustein braucht, muss die Aufteilung nicht kennen.
"""

from .anmutung import (
    AXIS_OFF, BEKLEIDUNGEN, CAMERAS, DEVICES, EINSTELLUNGEN, FOLGEN,
    GEZEICHNET, WESEN,
    HALTUNGEN,
    LIGHTS, MIMIK, NICHT_FOTO, NUR_GENANNTE,
    PAINT_TARGET, PAINTS, PALETTEN, STYLES, VARIANT_LIGHTS, VIEWS,
)
from .motiv import (
    ANGLES, MATERIALS, OBJECT_ANGLES, OBJECT_SCENES, PERSON_ANGLES,
    PERSON_SCENES, SCENES, SUBJECT_KINDS, VEHICLE_ANGLES, VEHICLE_SCENES,
    variant_axes,
)
from .vorlage import (
    ANATOMIE, EFFECTS, FORMS, GROUP_ACTIONS, OVERRIDE_KEYS, SCENARIOS, TEMPLATES,
    TRANSPARENT_TEMPLATE, VARIANT_TEMPLATE, VARIANT_TEMPLATE_POSE,
    overrides, parse_command,
)

__all__ = [
    "ANATOMIE", "ANGLES", "AXIS_OFF", "BEKLEIDUNGEN", "CAMERAS", "DEVICES", "EFFECTS",
    "EINSTELLUNGEN", "FOLGEN", "FORMS", "GEZEICHNET", "WESEN", "HALTUNGEN",
    "NICHT_FOTO", "NUR_GENANNTE",
    "GROUP_ACTIONS", "LIGHTS", "MATERIALS", "MIMIK", "OBJECT_ANGLES",
    "OBJECT_SCENES",
    "OVERRIDE_KEYS", "PAINTS", "PAINT_TARGET", "PALETTEN", "PERSON_ANGLES",
    "PERSON_SCENES", "SCENARIOS", "SCENES", "STYLES", "SUBJECT_KINDS",
    "TEMPLATES", "TRANSPARENT_TEMPLATE", "VARIANT_LIGHTS", "VARIANT_TEMPLATE",
    "VARIANT_TEMPLATE_POSE",
    "VEHICLE_ANGLES", "VEHICLE_SCENES", "VIEWS",
    "catalog", "fragment", "overrides", "parse_command", "variant_axes",
]


def catalog() -> dict:
    """Fuer die Weboberflaeche: Schluessel + Anzeigename je Gruppe."""
    return {
        "styles": [{"key": k, "label": v[0]} for k, v in STYLES.items()],
        "lights": [{"key": k, "label": v[0]} for k, v in LIGHTS.items()],
        "cameras": [{"key": k, "label": v[0]} for k, v in CAMERAS.items()],
        "views": [{"key": k, "label": v[0]} for k, v in VIEWS.items()],
        "paints": [{"key": k, "label": v[0], "phrase": v[1]} for k, v in PAINTS.items()],
        "paletten": [{"key": k, "label": v[0]} for k, v in PALETTEN.items()],
        "materials": [{"key": k, "label": v[0]} for k, v in MATERIALS.items()],
        "subjects": [
            {"key": k, "label": v["label"], "target": v["target"],
             "scenes": [{"key": a, "label": b[0]} for a, b in v["scenes"].items()],
             "angles": [{"key": a, "label": b[0]} for a, b in v["angles"].items()],
             # Genau die Achsen, aus denen der Server wirklich wuerfelt --
             # damit die Seite nichts anderes anbietet, als hinterher gilt.
             "axes": {name: [{"key": a, "label": b[0]} for a, b in tabelle.items()]
                      for name, tabelle in variant_axes(k).items()}}
            for k, v in SUBJECT_KINDS.items()
        ],
        "devices": [{"key": k, "label": v[0]} for k, v in DEVICES.items()],
        "scenarios": [{"key": k, "label": v[0]} for k, v in SCENARIOS.items()],
        "group_actions": [{"key": k, "label": v["label"], "min": v["min"], "hint": v["hint"]}
                          for k, v in GROUP_ACTIONS.items()],
        "templates": TEMPLATES,
        "effects": [{"key": k, "label": v["label"], "alias": v["alias"],
                     "needs_image": v["needs_image"],
                     # Hat eine eigene Fassung fuer Text -> Bild.
                     "aus_text": bool(v.get("text")), **overrides(v)}
                    for k, v in EFFECTS.items()],
        "forms": [{"key": k, "label": v["label"], **overrides(v)} for k, v in FORMS.items()],
    }


def fragment(group: dict, key: str | None) -> str | None:
    """Textbaustein zu einem Schluessel, oder None wenn nichts gewaehlt ist."""
    entry = group.get(key or "")
    return entry[1] if entry else None
