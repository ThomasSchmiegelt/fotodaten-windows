"""Wie ein Bild aussieht: Stil, Licht, Blickwinkel, Objektiv, Farbe.

Die Bezeichnungen sind deutsch, die Textbausteine englisch -- das Modell folgt
englischen Bildbeschreibungen deutlich zuverlaessiger.
"""

import re

STYLES = {
    "foto": ("Fotorealistisch", "photorealistic, sharp focus, natural colors, high detail"),
    "zeichentrick": ("Zeichentrick", "classic hand-drawn cartoon style, bold outlines, flat bright colors, playful"),
    "anime": ("Anime", "anime illustration, cel shading, expressive eyes, clean line art"),
    "comic": ("Comic", "graphic novel panel, heavy ink lines, halftone shading, saturated colors"),
    "aquarell": ("Aquarell", "watercolor painting, soft bleeding pigments, visible paper texture"),
    "oel": ("Ölgemälde", "oil painting, thick visible brush strokes, rich impasto, gallery lighting"),
    "dystopisch": ("Dystopisch", "dystopian atmosphere, decaying concrete, smog and ash, muted desaturated palette, oppressive mood"),
    "utopisch": ("Utopisch", "utopian solarpunk vision, clean white architecture overgrown with greenery, bright optimistic light"),
    "cyberpunk": ("Cyberpunk", "cyberpunk aesthetic, neon signage, rain-slick streets, holographic advertising, deep blacks"),
    "sportlich": ("Sportlich", "dynamic sports photography, frozen motion, sweat and dust particles, powerful athletic energy"),
    "technisch": ("Technisch", "technical product rendering, precise engineering detail, clean studio backdrop, exploded-view clarity"),
    "erotisch": ("Sinnlich", "sensual boudoir style, intimate and tasteful, soft warm skin tones, silk fabrics, suggestive rather than explicit"),
    "draussen": ("Draußen", "outdoor location shot, natural environment, open sky, authentic weather and atmosphere"),
    "noir": ("Film Noir", "film noir, high contrast black and white, deep shadows, venetian blind light, 1940s mood"),
    "retro": ("Retro 80er", "1980s retro aesthetic, chrome and magenta, grainy analog film, VHS color fringing"),
    "maerchen": ("Märchenhaft", "storybook fairytale illustration, warm glow, whimsical detail, enchanted atmosphere"),
    "minimal": ("Minimalistisch", "minimalist composition, large negative space, few elements, calm restrained palette"),
    "manga": ("Manga", "black and white manga artwork, crisp ink linework, screentone shading, dynamic speed lines, expressive panel composition"),
    "scifi": ("Science-Fiction", "hard science fiction look, brushed metal and composite surfaces, glowing accent edges, cool blue-white palette, believable engineering"),
    "kitsch": ("Kitschig", "unashamedly kitsch, candy colours, glitter and sparkles, rainbow gradients, hearts and stars, glossy greeting-card sheen"),
    "plastik": ("Plastik-Look", "made of glossy injection-moulded plastic like a collectible toy figure, smooth rounded edges, visible mould seams, saturated toy colours"),
    "bleistift": ("Bleistift", "graphite pencil drawing on textured paper, visible hatching and cross-hatching, soft smudged shading, eraser highlights, no colour"),
    "schillernd": ("Schillernd", "iridescent holographic look, rainbow sheen sliding across every surface, oil-slick colour shift, prismatic highlights, mirror-bright foil and chrome, wet-looking reflective fabric"),
}


LIGHTS = {
    "golden": ("Goldene Stunde", "golden hour sunlight, long warm shadows, glowing rim light"),
    "blau": ("Blaue Stunde", "blue hour twilight, cool ambient light, deep sky gradient"),
    "mittag": ("Hartes Mittagslicht", "harsh midday sun, short hard shadows, high contrast"),
    "studio": ("Softbox / Studio", "clean studio lighting, large softbox, gentle falloff, seamless backdrop"),
    "neon": ("Neon", "neon lighting, magenta and cyan color spill, glowing reflections"),
    "kerze": ("Kerzenlicht", "candlelight, warm flickering glow, soft deep shadows"),
    "gegenlicht": ("Gegenlicht", "strong backlight, subject rimmed in light, lens flare, silhouette edges"),
    "nebel": ("Nebliger Morgen", "misty morning light, diffused haze, soft pastel tones, visible light beams"),
    "seitenlicht": ("Dramatisches Seitenlicht", "dramatic side lighting, chiaroscuro, one half in deep shadow"),
    "bewoelkt": ("Bewölkt", "overcast diffuse daylight, soft even shadows, muted natural colors"),
}


# Umrundung einer Person. Die Reihenfolge ist der Flug: vorne herum bis hinten
# und zurueck, danach die beiden Sonderwinkel von oben und unten.
VIEWS = {
    "vorne":        ("Vorne (0°)", "front view, the person facing the camera directly"),
    "halblinks":    ("Halb links (45°)", "three-quarter view from the front left, the person turned about 45 degrees"),
    "links":        ("Linkes Profil (90°)", "full profile view from the left side, 90 degrees to the camera"),
    "hintenlinks":  ("Hinten links (135°)", "three-quarter view from behind on the left, mostly showing the back"),
    "hinten":       ("Hinten (180°)", "back view from directly behind the person, seen from the rear, face not visible"),
    "hintenrechts": ("Hinten rechts (225°)", "three-quarter view from behind on the right, mostly showing the back"),
    "rechts":       ("Rechtes Profil (270°)", "full profile view from the right side, 90 degrees to the camera"),
    "halbrechts":   ("Halb rechts (315°)", "three-quarter view from the front right, the person turned about 45 degrees"),
    "oben":         ("Von oben", "high angle shot from directly above, looking straight down at the person"),
    "unten":        ("Von unten", "low angle shot from near the ground, camera looking steeply up at the person"),
}


CAMERAS = {
    "portraet": ("Porträt (85 mm)", "85mm portrait lens, shallow depth of field, creamy bokeh, head and shoulders"),
    "weitwinkel": ("Weitwinkel", "24mm wide angle lens, expansive perspective, slight edge distortion"),
    "tele": ("Teleobjektiv", "200mm telephoto compression, flattened perspective, isolated subject"),
    "makro": ("Makro", "extreme macro close-up, fine surface texture, razor-thin focus plane"),
    "frosch": ("Froschperspektive", "low angle shot from ground level looking up, subject towering"),
    "vogel": ("Vogelperspektive", "high overhead angle looking down, bird's eye view"),
    "drohne": ("Drohne", "aerial drone shot, wide landscape context, slight top-down tilt"),
    "schulter": ("Über die Schulter", "over-the-shoulder shot, foreground framing, cinematic depth"),
    "dutch": ("Dutch Angle", "tilted dutch angle, unsettling diagonal horizon"),
    "ganz": ("Ganzkörper", "full body shot, subject fully in frame, environment visible"),
    "fisch": ("Fischauge", "fisheye lens, strong barrel distortion, curved horizon"),
}


# Aufnahmegeraet statt Objektiv: fuer Trainingsdaten ist die Bildanmutung der
# Kamera wichtiger als die Brennweite. Die CAMERAS-Tabelle passt hier nicht,
# ihre Eintraege sind auf Personen gemuenzt ("Kopf und Schultern").
DEVICES = {
    "handy":       ("Smartphone", "shot on a smartphone camera, slightly over-processed"),
    "spiegelreflex": ("Spiegelreflex", "shot on a DSLR with a 50mm lens, clean and sharp"),
    "weitwinkel":  ("Weitwinkel", "shot with a wide angle lens, slight barrel distortion"),
    "tele":        ("Teleobjektiv", "shot with a telephoto lens, compressed perspective"),
    "action":      ("Action-Kamera", "shot on an action camera, very wide, mild fisheye"),
    "dashcam":     ("Dashcam", "a dashcam still, slightly soft with over-sharpened edges"),
    "ueberwachung": ("Überwachungskamera", "a surveillance camera still, low contrast, visible noise"),
    "kompakt":     ("Kompaktkamera", "a compact camera snapshot with direct flash"),
    "analog":      ("Analogfilm", "shot on 35mm colour film with visible grain"),
}


# Sonderwert einer Achse: gar nicht anfassen. Zu unterscheiden von "" -- das
# heisst im Varianten-Modus wuerfeln.
AXIS_OFF = "-"


# --- Varianten ------------------------------------------------------
# Vervielfaeltigung eines Basisbilds: alles darf sich aendern ausser dem
# Gegenstand, auf den es ankommt. Die Bausteine sind als vollstaendige
# Aussagen formuliert, damit sie hinter der Unveraenderlichkeits-Anweisung
# stehen koennen, ohne den Satzbau zu zerlegen.
# Nur die Farbe. Woran sie haftet, bestimmt PAINT_TARGET bzw. die Eingabe des
# Benutzers -- "die Karosserie" beim Auto, "die Kleidung der Person" bei einem
# Portraet. Vorher stand "the vehicle body" fest im Baustein, was den Regler
# fuer alles ausser Fahrzeugen unbrauchbar machte.
PAINT_TARGET = "the vehicle body"


PAINTS = {
    "rot":        ("Rot", "bright red"),
    "weiss":      ("Weiß", "plain white"),
    "schwarz":    ("Schwarz", "glossy black"),
    "silber":     ("Silber", "metallic silver"),
    "dunkelgrau": ("Dunkelgrau", "dark grey"),
    "dunkelgruen": ("Dunkelgrün", "dark green"),
    "beige":      ("Beige", "beige"),
    "gelb":       ("Gelb", "bright yellow"),
    "orange":     ("Orange", "orange"),
    "dunkelblau": ("Dunkelblau", "deep navy blue"),
    "bordeaux":   ("Bordeaux", "dark burgundy red"),
    "matt":       ("Mattlack", "a matte grey wrap with no gloss"),
    # Die Liste war gedeckt bis zur Langeweile -- kein Braun zwar, aber auch
    # nichts, was knallt. Diese fuenf sind ausdruecklich grell.
    "pink":       ("Pink", "vivid hot pink"),
    "tuerkis":    ("Türkis", "bright turquoise"),
    "limette":    ("Limettengrün", "electric lime green"),
    "lila":       ("Lila", "vivid purple"),
    "knallorange": ("Knallorange", "glowing neon orange"),
    "neon":       ("Neon", "a fluorescent neon finish that looks lit from within"),
    "neongruen":  ("Neongrün", "fluorescent neon green"),
    "neonpink":   ("Neonpink", "fluorescent neon pink"),
}


# Die Farbstimmung des ganzen Bildes -- etwas anderes als PAINTS, das immer nur
# einen benannten Gegenstand umlackiert und ohne Ziel sogar ganz entfaellt.
# Ohne diese Achse bestimmen Umgebung und Licht die Palette allein, und die
# sind erdlastig: Schotter, Feldweg, Wald, Baustelle, dazu Filmkorn und flauer
# Ueberwachungskontrast. Daher der Braunstich.
PALETTEN = {
    "knallig":    ("Knallig", "a loud saturated colour palette, pure strong hues, high chroma, nothing muted"),
    "pastell":    ("Pastell", "a soft pastel palette, pale tints, milky light, gentle low-contrast colours"),
    "neon":       ("Neon", "a neon palette, glowing magenta cyan and acid green against deep darks"),
    "kitschbunt": ("Kitschbunt", "a gaudy kitsch palette, candy pink lemon yellow and sky blue all at once, rainbow sparkle"),
    "metallic":   ("Metallic", "a metallic palette, polished chrome silver and gold, specular highlights, cool reflective sheen"),
    "monochrom":  ("Monochrom", "a monochrome palette, a single hue in many values, almost no other colour"),
    "erdig":      ("Erdig", "an earthy palette, ochre umber moss and sand, warm muted natural tones"),
    "kalt":       ("Kühl", "a cold palette, steel blue slate and cyan, no warm tones at all"),
    "warm":       ("Warm", "a warm palette, amber terracotta and deep red, sunlit and glowing"),
    "irisierend": ("Irisierend", "an iridescent palette, colours shifting through the spectrum with the angle, oil-slick greens violets and cyans over a bright base"),
}


# Welche Stile gezeichnet sind und nicht fotografiert. Wichtig fuer Folgen:
# ist der Stil Manga, darf keine Achse in Richtung Foto ziehen -- eine
# gewuerfelte "Ueberwachungskamera" oder "Spiegelreflex" macht aus dem
# Manga sonst mittendrin ein Lichtbild.
GEZEICHNET = {
    "zeichentrick", "anime", "comic", "manga", "aquarell", "oel", "bleistift",
    "maerchen", "minimal", "plastik", "kitsch",
}

# Sagt dem Modell ausdruecklich, dass kein Foto entstehen soll.
NICHT_FOTO = ("This is a drawn illustration, not a photograph: no camera "
              "grain, no lens blur, no photographic lighting.")


# Was eine Figur ist. Steht vor allem anderen im Prompt, denn es bestimmt,
# wie Haut, Augen und Gesicht ueberhaupt aussehen -- und es gilt fuer das
# Ganzbild wie fuer die Grossaufnahme. Leer heisst Mensch; dann steht nichts
# davon im Prompt, so wie es bisher war.
WESEN = {
    "mensch": ("Mensch", ""),
    "androide": ("Androide",
                 "an android built to pass for human: matte synthetic skin "
                 "with a faint seam along the jaw and behind the ear, irises "
                 "that hold a low inner light, pupils a shade too perfect"),
    "roboter": ("Roboter",
                "a humanoid robot with no skin: plated metal shell, visible "
                "joints and cabling, glowing optical sensors instead of eyes"),
    "cyborg": ("Cyborg",
               "part human, part machine: metal plating over one side of the "
               "face and one arm, a lens where one eye used to be, scarred "
               "skin at the seams"),
    "fremdwesen": ("Fremdwesen",
                   "a humanoid alien, clearly not human: unusual skin "
                   "texture and colouring, eyes of a shape no human has"),
    "fabelwesen": ("Fabelwesen",
                   "a mythical being in human shape, clearly not human"),
}


# Kameraeinstellungen fuer Szenen. Etwas anderes als CAMERAS: dort steht das
# Objektiv, hier steht die ganze Anordnung von Kamera, Figuren und was sie
# sehen. In einer Geschichte wird sie mit \Name gesetzt.
#
# "gegentext" macht daraus ein Paar: zwei Bilder, die denselben Augenblick
# von beiden Seiten zeigen. Die Szene ergibt dann zwei Bilder statt einem.
# Jede Einstellung beschreibt eine Anordnung -- und jede Anordnung nennt
# dabei jemanden: "eine Person draussen", "die Gestalt darueber". Das Modell
# liest die Person der Szene dann als eine zweite und malt einen Fremden
# dazu, gern in einem anderen Stil. Gemeldet fuer die Scheibe, gefunden in
# fast allen. Deshalb sagt jede Einstellung ausdruecklich, dass nur die eine
# Person im Bild ist.
# Gilt fuer jede Szene, nicht nur fuer die mit Kameraeinstellung. Gebraucht
# wird das vor allem bei den gezeichneten Stilen: "graphic novel panel" und
# "expressive panel composition" sind Bildsprachen, in denen ueblicherweise
# mehrere Figuren stehen, und Anime setzt von sich aus gern eine zweite
# dazu. Der Satz nennt keine Zahl -- die Szene kann eine oder drei Personen
# beschreiben --, er verbietet nur die ungenannten.
NUR_GENANNTE = ("Only the people described in this prompt appear. No other "
                "figures, no bystanders in the background, no second face, "
                "no reflection of anyone else.")

NUR_EINE = ("Exactly one person is in this picture: the one described in this prompt. "
            "No bystanders, no onlookers, no second face, no reflection of "
            "anyone else.")

# Beim Blick von aussen hinein steht eine Schulter im Vordergrund. Sie ist
# Bildrand, keine zweite Figur -- und muss es auch bleiben.
NUR_EINE_SCHULTER = (
    "Exactly one person is in this picture: the one described in this prompt, seen "
    "through the opening. The shoulder in the foreground is an unlit, "
    "featureless silhouette cut off by the frame, not a second character. "
    "No bystanders, no other faces.")

EINSTELLUNGEN = {
    "augen": {
        "label": "Blick in die Augen",
        # Vierte Fassung. Die ersten drei erklaerten die Anordnung und ergaben
        # Ganzkoerper, dann eine Zweiereinstellung, dann ein gewoehnliches
        # Portraet. Was wirkt, ist ein Makro mit Entfernungsangabe und der
        # ausdruecklichen Ansage, dass die Augen fast das ganze Bild fuellen --
        # nach einem Muster, das sich beim Benutzer bewaehrt hat.
        "text": "extreme macro close-up of a face, the camera about 20 "
                "centimetres in front of the eyes. The eyes fill almost the "
                "entire frame, glossy irises with visible texture, a direct "
                "gaze into the camera, individual eyelashes sharp, realistic "
                "skin texture. Nothing but the face is in frame. Mirrored in "
                "the eyes: {spiegelung}",
        # Die Vorgabe darf niemanden hinzuerfinden: "die Silhouette des
        # Gegenuebers" malte einen zweiten Menschen ins Bild.
        "vorgabe": {"spiegelung": "the light and the shapes in front of them"},
        "allein": NUR_EINE,
        "nur_gesicht": True,
    },
    "spiegel": {
        "label": "Blick in den Spiegel",
        "text": "the camera stands behind the person, who faces a large "
                "mirror: their back fills the foreground, their reflected "
                "face looks back out of the mirror, both in the same frame. "
                "Also visible in the mirror: {spiegelung}",
        "vorgabe": {"spiegelung": "the room behind them"},
        "allein": NUR_EINE,
    },
    "raus": {
        "label": "Von drinnen nach draussen",
        # Kein Gitter: die urspruengliche Fassung sprach von Zellenstaeben und
        # malte sie prompt ins Bild. Gemeint war die Blickrichtung, nicht das
        # Gefaengnis.
        "text": "a point-of-view shot from inside an enclosed space looking "
                "out through its opening at the person described in this "
                "prompt, who stands outside in the light, the dark inner "
                "walls framing the edges of the picture, that person lit "
                "and sharp",
        "gegentext": "an over-the-shoulder shot from outside an enclosed "
                     "space, looking past an unlit, featureless shoulder in "
                     "the near foreground, through the opening at the person "
                     "described in this prompt, who is inside, small and lit",
        "paar_label": ("von drinnen heraus", "von draussen hinein"),
        "allein": NUR_EINE_SCHULTER,
    },
    # Dieselben beiden Blicke einzeln. "raus" bleibt das Paar -- gespeicherte
    # Geschichten rechnen damit --, aber in einer Folge will man sie auf zwei
    # Szenen verteilen und dazwischen etwas anderes zeigen.
    "heraus": {
        "label": "Nur von drinnen heraus",
        "text": "a point-of-view shot from inside an enclosed space looking "
                "out through its opening at the person described in this "
                "prompt, who stands outside in the light, the dark inner "
                "walls framing the edges of the picture, that person lit "
                "and sharp",
        "allein": NUR_EINE,
    },
    "rein": {
        "label": "Nur von draussen hinein",
        "text": "an over-the-shoulder shot from outside an enclosed space, "
                "looking past an unlit, featureless shoulder in the near "
                "foreground, through the opening at the person described in "
                "this prompt, who is inside, small and lit",
        "allein": NUR_EINE_SCHULTER,
    },
    "scheibe": {
        "label": "Durch die halbdurchsichtige Scheibe",
        "text": "a shot through a semi-transparent pane of glass: what lies "
                "beyond shows through the glass, dimmed and slightly hazy, "
                "and at the same time reflected on the glass surface: "
                "{spiegelung}. Both layers overlap in the same frame",
        # "das Gesicht des Betrachters" war der gemeldete Fall: ein Fremder
        # erschien auf dem Glas, in einem anderen Stil als die Szene.
        "vorgabe": {"spiegelung": "the dim room on this side of the glass"},
        "allein": NUR_EINE,
    },
    "decke": {
        "label": "Von der Decke",
        "text": "the camera hangs from the ceiling and looks straight down, "
                "from a height of {hoehe}, the person described in this prompt, seen "
                "from directly above, their shadow short on the floor",
        "vorgabe": {"hoehe": "three metres"},
        "allein": NUR_EINE,
    },
    "bettlage": {
        "label": "Bettlage (von unten senkrecht hoch)",
        "text": "the camera lies flat on the ground directly below, looking "
                "straight up, the figure standing over it and leaning into "
                "the frame from above, the ceiling behind them",
        "allein": NUR_EINE,
    },
}


# Dieselben Anordnungen sollen auch dort waehlbar sein, wo man sonst die
# Kameraperspektive einstellt -- in Varianten, beim Bearbeiten, ueberall.
# Das Paar zerfaellt dabei in seine beiden Haelften: eine Achse liefert ein
# Bild, kein Paar.
def _ohne_luecken(text: str) -> str:
    """Die Vorgaben eingesetzt -- eine Achse kann keine Luecke fuellen."""
    return re.sub(r"\{(\w+)\}", lambda m: _VORGABEN.get(m.group(1), ""), text)


_VORGABEN = {k: v for e in EINSTELLUNGEN.values()
             for k, v in (e.get("vorgabe") or {}).items()}

CAMERAS.update({
    "e_augen":      ("In die Augen", _ohne_luecken(EINSTELLUNGEN["augen"]["text"])),
    "e_spiegel":    ("In den Spiegel", _ohne_luecken(EINSTELLUNGEN["spiegel"]["text"])),
    "e_scheibe":    ("Durch die halbdurchsichtige Scheibe",
                     _ohne_luecken(EINSTELLUNGEN["scheibe"]["text"])),
    "e_raus":       ("Von drinnen nach draussen", EINSTELLUNGEN["raus"]["text"]),
    "e_rein":       ("Von draussen nach drinnen", EINSTELLUNGEN["raus"]["gegentext"]),
    "e_decke":      ("Von der Decke", _ohne_luecken(EINSTELLUNGEN["decke"]["text"])),
    "e_bettlage":   ("Bettlage, von unten hoch", EINSTELLUNGEN["bettlage"]["text"]),
})


# Folgen: dieselben drei, vier Blicke kommen immer wieder hintereinander --
# erst in die Augen, dann aus etwas heraus, dann in etwas hinein. Sie einzeln
# anzulegen ist dreimal dieselbe Handarbeit. Eine Folge legt die Szenen in
# einem Zug an, jede mit ihrer Einstellung, und uebernimmt dabei den Text der
# Szene, unter der sie entsteht: derselbe Augenblick aus wechselndem Blick.
FOLGEN = {
    "augen_raus_rein": ("Augen · heraus · hinein",
                        ["augen", "heraus", "rein"]),
    "augen_bett_rein": ("Augen · Bettlage · hinein",
                        ["augen", "bettlage", "rein"]),
    "scheibe_rein":    ("Scheibe · hinein", ["scheibe", "rein"]),
    "augen_scheibe":   ("Augen · Scheibe", ["augen", "scheibe"]),
    "raus_rein":       ("heraus · hinein", ["heraus", "rein"]),
    "augen_spiegel":   ("Augen · Spiegel", ["augen", "spiegel"]),
    "decke_bett":      ("Von der Decke · Bettlage", ["decke", "bettlage"]),
}


# Gesichtsausdruck. Fuer Geschichten: die Mimik soll aus der Handlung kommen,
# und ausformuliert trifft sie das Modell zuverlaessiger als ein einzelnes
# Wort wie "traurig". Bewusst knapp gehalten -- der Rest des Prompts hat auch
# noch Platzbedarf.
MIMIK = {
    "lachen":       ("Lachen", "laughing openly, eyes crinkled, head slightly back"),
    "laecheln":     ("Lächeln", "a warm quiet smile, relaxed eyes"),
    "weinen":       ("Weinen", "crying, wet cheeks, reddened eyes, mouth tight"),
    "erschrocken":  ("Erschrocken", "startled, eyes wide, eyebrows high, mouth open"),
    "wuetend":      ("Wütend", "angry, jaw set, brows drawn together, hard stare"),
    "nachdenklich": ("Nachdenklich", "thoughtful, gaze turned away, faint furrow between the brows"),
    "ueberrascht":  ("Überrascht", "surprised, eyebrows raised, a small open smile"),
    "muede":        ("Müde", "tired, heavy eyelids, slack mouth, shoulders low"),
    "entschlossen": ("Entschlossen", "determined, chin up, steady direct gaze"),
    "verlegen":     ("Verlegen", "embarrassed, looking down, a shy half-smile"),
    "ernst":        ("Ernst", "serious, neutral mouth, calm level gaze"),
    "erleichtert":  ("Erleichtert", "relieved, shoulders dropping, a breath let out"),
    "besorgt":      ("Besorgt", "worried, brows drawn up, lips pressed together"),
    "verzweifelt":  ("Verzweifelt", "desperate, face drawn, searching gaze, hands unsteady"),
    "stolz":        ("Stolz", "proud, chin lifted, a small satisfied smile"),
}


# Koerperhaltung. Eine eigene Achse, weil sie das Bild staerker praegt als
# Kleidung oder Licht -- dieselbe Person wirkt stehend, hockend und im Sprung
# wie drei verschiedene Aufnahmen.
HALTUNGEN = {
    "stehen":      ("Aufrecht stehend", "standing upright, weight evenly on both feet, arms relaxed"),
    "kontrapost":  ("Standbein", "standing with the weight on one leg, hip shifted, the other knee loose"),
    "gehen":       ("Im Gehen", "caught mid-stride, walking towards the camera"),
    "sitzen":      ("Sitzend", "sitting, back straight, hands resting on the knees"),
    "hocken":      ("Hockend", "crouching low on the balls of the feet, elbows on the knees"),
    "lehnen":      ("Angelehnt", "leaning against a wall, one shoulder taking the weight"),
    "verschraenkt": ("Arme verschränkt", "standing with the arms folded across the chest"),
    "hueften":     ("Hände in den Hüften", "hands on the hips, elbows out"),
    "zurueck":     ("Zurückgelehnt", "leaning back, relaxed, chin slightly raised"),
    "vorgebeugt":  ("Vorgebeugt", "leaning forward, shoulders rounded, intent"),
    "gedreht":     ("Über die Schulter", "torso turned away, head looking back over the shoulder"),
    "sprung":      ("Im Sprung", "caught mid-jump, both feet off the ground, clothing in motion"),
    "knien":       ("Kniend", "kneeling on one knee"),
    "liegen":      ("Liegend", "lying propped on one elbow"),
}

# Bekleidung als eigene Achse. Fuer "dieselbe Person in zehn Hosen" ist die
# Luecke im Baustein ({hose} mit zehn Zeilen) genauer -- diese Achse streut
# ueber ganze Aufmachungen, wenn man breit variieren will.
BEKLEIDUNGEN = {
    "jeans":    ("Jeans und Shirt", "wearing blue jeans and a plain t-shirt"),
    "anzug":    ("Anzug", "wearing a well-cut dark suit"),
    "kleid":    ("Sommerkleid", "wearing a light summer dress"),
    "mantel":   ("Wollmantel", "wearing a long wool coat over dark trousers"),
    "sport":    ("Sportkleidung", "wearing running gear in technical fabric"),
    "arbeit":   ("Arbeitskleidung", "wearing sturdy canvas work trousers and a worn jacket"),
    "regen":    ("Regenzeug", "wearing a rain jacket and waterproof trousers"),
    "abend":    ("Abendgarderobe", "wearing formal evening wear"),
    "strick":   ("Strick und Cord", "wearing a chunky knitted sweater and corduroy trousers"),
    "leder":    ("Lederjacke", "wearing a leather jacket and black trousers"),
    "leinen":   ("Leinen", "wearing loose linen clothing in natural tones"),
    "uniform":  ("Uniform", "wearing a plain unmarked uniform"),
    "schlaf":   ("Hausanzug", "wearing soft loungewear"),
    "winter":   ("Winterkleidung", "wearing a padded winter coat, scarf and gloves"),
}


# Kerzenlicht auf einem Auto im Hof ergibt keine brauchbare Variante, deshalb
# hier ohne. Wer es doch will, stellt die Lichtachse von Hand ein.
VARIANT_LIGHTS = {k: v for k, v in LIGHTS.items() if k != "kerze"}


# --- Portraetserie ---------------------------------------------------
# Drei Achsen nur fuer Bildnisse, alle fotografisch. Die allgemeinen Tabellen
# taugen dafuer nicht: CAMERAS mischt Makro, Drohne und Fischauge, STYLES
# Zeichentrick und Manga, LIGHTS Neon -- in einer Portraetserie kam dadurch
# zwischen zwei Fotos ploetzlich ein gemaltes Bild heraus.

# Wo die Kamera steht und wie viel vom Menschen sie zeigt.
PORTRAET_POSITIONEN = {
    "kopf":       ("Kopf und Schultern, Augenhöhe",
                   "head and shoulders portrait, camera at eye level, 85mm lens"),
    "nah":        ("Großaufnahme Gesicht",
                   "tight close-up of the face from chin to forehead, camera at eye level, 105mm lens"),
    "drehung":    ("Dreiviertel gedreht",
                   "three-quarter view, the face turned about 30 degrees from the camera, eyes towards the lens"),
    "brust":      ("Brustbild",
                   "chest-up portrait, camera at eye level, 85mm lens"),
    "profil":     ("Profil",
                   "clean side profile portrait, the head at 90 degrees to the camera"),
    "oben":       ("Leicht von oben",
                   "camera slightly above eye level, looking gently down at the person"),
    "halb":       ("Halbtotale bis zur Hüfte",
                   "waist-up portrait, 50mm lens at chest height"),
    "schulter":   ("Blick über die Schulter",
                   "the person looking back over their shoulder towards the camera"),
    "unten":      ("Leicht von unten",
                   "camera slightly below eye level, looking a little up at the person"),
    "knie":       ("Amerikanisch, ab Knie",
                   "three-quarter length portrait from the knees up, 50mm lens"),
    "umfeld":     ("Im Umfeld",
                   "environmental portrait with a 35mm lens, the person filling about a third of the frame, their surroundings visible"),
    "beilaeufig": ("Unbeobachtet",
                   "candid moment, the person looking past the camera, unposed"),
    "ganz":       ("Ganzkörper",
                   "full-length portrait from head to feet, 35mm lens from a few metres away"),
}

# Die klassischen Lichtfuehrungen im Studio und draussen.
PORTRAET_LICHTER = {
    "rembrandt":  ("Rembrandt-Licht",
                   "Rembrandt lighting, key light high at 45 degrees, a small triangle of light on the shadow-side cheek"),
    "butterfly":  ("Schmetterlingslicht",
                   "butterfly lighting from high in front, a small shadow under the nose, glowing cheekbones"),
    "loop":       ("Loop-Licht",
                   "loop lighting, the nose shadow falling slightly down and to the side"),
    "split":      ("Geteiltes Licht",
                   "split lighting, exactly one half of the face lit and the other in shadow"),
    "clamshell":  ("Beauty-Licht",
                   "clamshell beauty lighting, soft key from above and a fill from below, even flawless light"),
    "fenster":    ("Fensterlicht",
                   "soft natural window light from one side, gentle falloff into shadow"),
    "highkey":    ("High Key",
                   "high-key lighting, bright white background, very few shadows"),
    "lowkey":     ("Low Key",
                   "low-key lighting, dark background, a single hard light carving the face out of the dark"),
    "kante":      ("Kantenlicht",
                   "rim light from behind outlining hair and shoulders, soft frontal fill"),
    "golden":     ("Goldene Stunde",
                   "late golden hour sun, warm light on the skin, glowing backlit hair"),
    "schatten":   ("Offener Schatten",
                   "open shade outdoors, soft directionless daylight, natural skin tones"),
    "bewoelkt":   ("Bewölkt",
                   "overcast daylight, soft even light, muted natural colours"),
}

# Bildsprache -- ausschliesslich Fotografie.
PORTRAET_LOOKS = {
    "studio":     ("Studio-Porträt",
                   "professional studio portrait photograph, seamless paper backdrop"),
    "editorial":  ("Editorial",
                   "editorial magazine portrait photograph, styled and polished"),
    "business":   ("Business",
                   "corporate headshot photograph, neutral background, approachable"),
    "sw":         ("Schwarzweiß Fine Art",
                   "fine art black and white portrait photograph, rich tonal range"),
    "portra":     ("Farbfilm (Portra)",
                   "shot on Kodak Portra 400 colour film, soft pastel skin tones, fine grain"),
    "hp5":        ("SW-Film (HP5)",
                   "shot on Ilford HP5 black and white film, visible grain, deep blacks"),
    "mittelformat": ("Mittelformat",
                   "medium format camera photograph, extremely fine detail, smooth tonal transitions"),
    "reportage":  ("Reportage",
                   "documentary portrait photograph, natural and honest, available light"),
    "lifestyle":  ("Lifestyle",
                   "natural lifestyle portrait photograph, relaxed, true-to-life colours"),
    "strasse":    ("Straßenporträt",
                   "street portrait photograph taken in the city, background softly out of focus"),
    "kino":       ("Filmstill",
                   "cinematic film still shot on a cinema camera, anamorphic bokeh, subtle colour grade"),
}

# Haengt an jedem Bild der Portraetserie. Ein Stil in der Liste genuegt
# nicht: das Modell zeichnet Menschen gern glatt wie ein 3D-Rendering.
NUR_FOTO = ("A real photograph of a real person taken with a real camera, "
            "not a drawing, painting, illustration, cartoon, anime or 3D "
            "render. Natural skin texture with pores and fine hairs, "
            "realistic eyes with catchlights, true-to-life proportions.")
