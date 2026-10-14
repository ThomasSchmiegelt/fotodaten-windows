"""Das Sprachmodell: verstehen, uebersetzen, sehen.

    ollama        Adresse, Modell, der Aufruf selbst
    deuten        Freitext -> Prompt und Reglerstellung
    ansichten     ein Gegenstand von sechs Seiten: was jede Seite zeigt
    uebersetzen   Deutsch -> Englisch, nur wo noetig
    sehen         Bilder beschreiben und rueckwaerts den Prompt schreiben

Der Server spricht nur mit diesem Paket, nicht mit den einzelnen Dateien.
"""

from .deuten import (
    MODES, ask, baustein_prompt, bausteine_raten,
    interpret,
    luecken_vorschlaege, sanitise,
    person_teilen, system_prompt, teil_prompt,
)
from .ansichten import ansicht_satz, ohne_zahlenvergleich, seiten_plan
from .stellung import bauplan
from .aufbau import (
    abschnitte, kapitel, rahmen, szenen_aus_abschnitt,
)
from .erzaehlen import (
    ERZAEHLER, FREIGABEN, WELTEN, erzaehlerstimme, expose, freigabe,
    geschichte, gliederung, prosa, szenen_ergaenzen,
)
from .ollama import GROSS, MODEL, OLLAMA, available, entladen
from .sehen import bild_frage, bild_lesen, bild_zu_prompt, ist_weiblich
from .uebersetzen import looks_german, translate

__all__ = [
    "abschnitte", "ansicht_satz", "bauplan", "ohne_zahlenvergleich",
    "seiten_plan", "kapitel", "rahmen", "szenen_aus_abschnitt",
    "ERZAEHLER", "FREIGABEN", "GROSS", "MODEL", "MODES", "OLLAMA", "WELTEN",
    "erzaehlerstimme", "freigabe", "entladen", "expose", "ask", "available", "baustein_prompt", "bausteine_raten",
    "bild_frage", "bild_lesen",
    "bild_zu_prompt", "geschichte", "gliederung", "interpret",
    "ist_weiblich",
    "luecken_vorschlaege", "prosa",
    "looks_german", "person_teilen", "sanitise", "szenen_ergaenzen", "teil_prompt",
    "system_prompt", "translate",
]
