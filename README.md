# Qwen-Image 2.1 — lokale Weboberfläche und GIMP-Anbindung

Text zu Bild, Bildbearbeitung, Gruppenbilder und Serien mit
[Qwen-Image 2.1](https://huggingface.co/Qwen/Qwen-Image-2.1) — auf dem eigenen
Rechner; Sprach- und Bildmodell lassen sich wahlweise auf eine
OpenAI-kompatible Cloud-Schnittstelle umstellen. Dazu eine Freitexteingabe auf
Deutsch, ein GIMP-Plugin und eine Kette für **Trainingsdaten**: Varianten
erzeugen, Bounding Boxes automatisch setzen und prüfen, lokal
vervielfältigen (die Box rechnet mit, das geht auch auf einer 4-GB-Karte),
einen Detektor (D-FINE) trainieren.

## Schnellstart unter Windows

1. Repository herunterladen — **Code › Download ZIP** und entpacken, oder
   `git clone`. Ein Ordner ohne Leerzeichen-Ärger, etwa `C:\qwen-image`.
   Beim ZIP vor dem Entpacken: Rechtsklick › Eigenschaften › **Zulassen**
   anhaken — sonst trägt jede Datei den Vermerk „aus dem Internet“, und
   Windows (SmartScreen, Smart App Control) fragt nach oder sperrt.
2. **`einrichten.bat`** doppelklicken. Es lädt ein eingebettetes Python von
   python.org, alle Pakete und die Modelle — in **diesen Ordner**, ohne
   Installation, ohne Adminrechte, ohne vorhandenes Python.
3. **`start.bat`** doppelklicken. Der Browser öffnet `http://127.0.0.1:7860`.

Danach ist der Ordner **portabel**: auf einen USB-Stick oder einen anderen
Rechner kopieren und dort `start.bat` starten. Modelle, Einstellungen,
Projekte und der API-Zugang liegen alle darin.

| Aufruf | Für | Größe |
|---|---|---|
| `einrichten.bat` | Bilder per Cloud-API (etwa franconia.ai), Boxen und Training auf der eigenen Karte ab 6 GB | ~9 GB |
| `einrichten.bat training` | nur Detektor-Training (YOLO26, D-FINE) — etwa ein Notebook mit RTX 1000 Ada; der Datensatz kommt fertig gelabelt von einem anderen Rechner | ~4 GB |
| `einrichten.bat nurcloud` | nur Bilder per Cloud-API, keine Grafikkarte nötig | ~100 MB |
| `einrichten.bat lokal` | dazu Qwen-Image 2.1 auf der eigenen Karte (~17 GB Grafikspeicher) | ~40 GB |

Dahinter steht `portable/bauen.py --hier`; es darf mehrfach laufen — was
schon da ist, wird nur geprüft. Am Ende lädt es einmal torch, transformers,
Ultralytics und polars zur Probe: eine von Windows gesperrte DLL fällt so
beim Einrichten auf und nicht erst mitten im Training.

**Wie man damit arbeitet, steht in der [Bedienungsanleitung](ANLEITUNG.md).**
Diese README erklärt, wie es gebaut ist und warum.

Entwickelt und gemessen auf einer **RTX 3090 (24 GB) mit 31 GB Arbeitsspeicher**.

## Warum zwei Phasen

Qwen-Image 2.1 wiegt in bfloat16 rund **33 GB**: Text-Encoder ~17,5 GB,
Transformer ~14,2 GB, VAE ~1,4 GB. Auf dieser Maschine passt weder alles
zusammen in die GPU noch alles zusammen in den Hauptspeicher —
`enable_model_cpu_offload()` aus den offiziellen Beispielen läuft deshalb in
den Swap oder scheitert.

Stattdessen wird jeder Auftrag zweistufig abgearbeitet, mit einer Leerung der
GPU dazwischen:

1. **Text-Encoder** auf die GPU, alle Prompts der Serie einbetten, freigeben.
2. **Transformer + VAE** auf die GPU, alle Bilder entrauschen und dekodieren.

So liegen nie mehr als ~17,5 GB gleichzeitig auf der Karte. Eine ganze Serie
teilt sich die beiden Ladevorgänge: das erste Bild kostet gut anderthalb
Minuten, jedes weitere nur noch die reine Rechenzeit.

Gemessen bei 1024 px und 30 Schritten: **erstes Bild ~100 s, jedes weitere
~25 s.** Zehn Varianten dauern also rund fünf statt siebzehn Minuten.

**Dekodiert wird bis ein Megapixel am Stück.** Die VAE kann das Bild
kachelweise zusammensetzen, und das war lange bedingungslos eingeschaltet —
der Transformer belegt beim Dekodieren ja noch ~14 GB. Kacheln hinterlässt
aber Spuren: keine harten Nähte, die werden überblendet, sondern weiche
Helligkeitsunterschiede auf Kachelgröße. Auf einer glatten hellen Fläche
sieht man sie als senkrechte Striche und Farbflecken.

Gemessen am selben Prompt mit demselben Seed, nur anders dekodiert: die
Helligkeitsspanne im Hintergrund fällt von **4,3 auf 2,2** Graustufen, der
Farbdrift zwischen den Kanälen von **14 auf 8**. Bis `QWEN_VOLLBILD`
(Vorgabe 1024×1024) dekodiert die VAE deshalb in einem Stück, darüber weiter
kachelweise.

Was dabei *nicht* hilft, ebenfalls gemessen: mehr Schritte (24 und 40 sind
gleich gut), ein höherer CFG-Wert (2,5 verdreifacht die Welligkeit) und vor
allem der Versuch, die Fehler im Prompt zu verbieten — „no gradient, no
clouds, no banding" verdoppelt sie. Dasselbe wie überall: ein Bildmodell malt,
was dasteht, auch wenn ein „no" davorsteht. Ein dunkler Hintergrund ist
praktisch frei davon.

## Installation

```bash
git clone <dieses-repository> qwen_image
cd qwen_image
python3 -m venv qwen_bild
./qwen_bild/bin/pip install -r requirements.txt
```

Qwen-Image 2.1 braucht `diffusers` von `main`; die Version in `requirements.txt`
ist auf den geprüften Stand festgenagelt. Beim ersten Start lädt das Modell
rund 31 GB in den Hugging-Face-Cache.

Die Modelle für Trainingsdaten und Detektor — Qwen3-VL-2B und Grounding DINO
für die Boxen, D-FINE zum Trainieren — lädt das Programm beim ersten Gebrauch
selbst, zusammen rund 5 GB. Wer im Datensatz **neue Umgebungen**
vervielfältigt, lädt dazu einmalig Stable Diffusion 1.5 und ein ControlNet
(~3 GB). Sie laufen mit dem schon installierten
`transformers`; das Training braucht zusätzlich `scipy` (steht in
`requirements.txt`).

### Unter Windows

Der Weg für Anwender ist der [Schnellstart](#schnellstart-unter-windows).
Für die Entwicklung gibt es daneben eine virtuelle Umgebung wie unter Linux:

```bat
installieren.bat            &rem venv qwen_bild, CUDA 13.0
installieren.bat cu126 yolo &rem CUDA 12.6 (auch GTX 10xx), dazu Ultralytics
start.bat                   &rem nimmt python\ (portabel) oder qwen_bild\
```

pip läuft immer als `python -m pip`: auf Rechnern mit Anwendungssteuerung
(Smart App Control, WDAC) ist `pip.exe` gesperrt, `python.exe` nicht.
`start.bat` setzt Python auf UTF-8, damit Umlaute in Meldungen und Dateien
heil bleiben, und lädt Modelle über normales HTTP (`HF_HUB_DISABLE_XET`):
der Xet-Weg von Hugging Face blieb hier gemessen bei 0 Byte stehen.

**Smart App Control.** Ist es eingeschaltet, lässt Windows unsignierte DLLs
nur mit bekannter Reputation laden. Gemessen:

| Paket | Ergebnis |
|---|---|
| torch 2.14 für CUDA 13.0 | lädt |
| torch 2.14 für CUDA 12.6 | „Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert" (`c10.dll`) |
| polars 2.0 | Laufzeit-DLL gesperrt — der Import **hängt** ohne Fehlermeldung, mit ihm das YOLO-Training |
| polars 1.31.0 | lädt |

Deshalb ist cu130 die Vorgabe (GTX 16xx, RTX 20xx bis 50xx, auch RTX 1000
Ada) und polars auf 1.31.0 festgelegt; cu126 nur für eine GTX 10xx und nur
ohne Smart App Control.

**Ein neuer Stand von Qwen-Image auf dem Hub** lädt beim nächsten Auftrag
stillschweigend die geänderten Teile nach — beim Text-Encoder 17 GB.
`QWEN_IMAGE_REVISION` hält einen Stand fest; die portable Einrichtung mit
`lokal` setzt den, gegen den der diffusers-Commit geprüft ist.

Das GIMP-Plugin kopiert `gimp\install.bat` nach
`%APPDATA%\GIMP\<Version>\plug-ins`; „In GIMP öffnen" findet GIMP unter
`Program Files` bzw. `%LOCALAPPDATA%\Programs` selbst.

Unterschiede zu Linux, alle im Code abgefangen: `expandable_segments` gibt
es für PyTorch unter Windows nicht und wird dort nicht gesetzt; ein
abgebrochenes Training wird mit `taskkill /T` samt Lader-Prozessen beendet,
`terminate()` erreichte nur den Hauptprozess.

### Portabel und nur Cloud

Ohne `einrichten.bat lokal` rechnet das Bildmodell nie auf der eigenen
Karte: `start.bat` setzt dann `QWEN_NUR_CLOUD=1`, und `engine.py` lädt torch
und diffusers für das Bildmodell gar nicht erst. Bilder kommen dann vom
Cloud-Bildmodell (Kopfzeile › Cloud-Modelle). Ohne torch — Stufe
`nurcloud` — startet derselbe Code als reine Cloud-Fassung.

Eine Kopie in einen anderen Ordner baut
`python portable\bauen.py D:\ziel [--training|--nurcloud|--lokal]`.

## Starten

```bash
./start.sh              # http://127.0.0.1:7860
./start.sh 8080         # anderer Port
QWEN_HOST=0.0.0.0 ./start.sh   # auch vom Handy im selben Netz erreichbar
```

Immer nur **eine** Instanz gleichzeitig — zwei Prozesse, die je 17 GB auf die
Karte laden, werfen sich gegenseitig heraus.

## Was die Oberfläche kann

**Fünf Betriebsarten:** Text zu Bild · Bearbeiten (1–4 Referenzbilder) ·
Gruppe · Umrundung (eine Person aus wechselnden Blickwinkeln) · Varianten.
Dazu eigene Reiter für Abläufe, Bausteine, Szenen, Geschichten, den Katalog
und die **Sechs-Seiten-Ansicht** eines Gegenstands.

**Retusche** bessert eine gemalte Stelle nach, etwa einen Fleck oder ein
schiefes Lächeln. Weil das Modell keinen Masken-Eingang hat, geht nur ein
Ausschnitt um die Maske ins Modell, in voller Auflösung. Das Ergebnis wird
farblich angeglichen und mit weicher Kante nur innerhalb der Maske
eingesetzt; der Rest bleibt pixelgenau (`webui/retusche.py`).

**Gruppe** kennt drei Aufgaben: *aus Einzelbildern zusammenstellen* (je ein
Bild pro Person), *Person ergänzen* (erstes Bild ist das Gruppenfoto, danach
je ein Bild pro Person, die dazu soll) und *Person entfernen* (beschreiben,
wer verschwinden soll — „die mittlere Person"). **Jedes Referenzbild bekommt
auf Wunsch einen eigenen Text**, der sagt, wie diese Person darzustellen ist —
„ein mittelalterlicher Ritter", „eine Astronautin im Raumanzug". Beim Ergänzen
gibst du an, wie
viele Personen schon auf dem Gruppenfoto sind: das Modell kann nicht zählen,
und ohne feste Zielzahl stellt es wahllos Leute dazu.

Dazu **Inszenierungen** — 12 Vorlagen für das Aussehen der Gruppe, von
leuchtenden Geistern über Fantasy-Gefährten und Tafelrunde bis Detektive und
Familienporträt. Sie beschreiben den Look ausformuliert statt einen Filmtitel
zu nennen; das trifft das Modell zuverlässiger.

**Varianten** vervielfachen ein Basisbild, etwa für Trainingsdaten. Zuerst die
**Motivart** wählen — Fahrzeug, Gegenstand oder Person: davon hängt ab, welche
Umgebungen und Blickwinkel angeboten werden. „Auf Stoßstangenhöhe von hinten"
passt zu einem Auto und zu nichts sonst, ein Gegenstand will „auf der Werkbank"
und „freigestellt mit Schlagschatten".

Bis zu zehn Achsen — Farbe, **Farbstimmung**, **Stil**, Umgebung, Licht,
Kameraart, Blickwinkel, Werkstoff (10 Materialien von Aluminium bis Gusseisen)
sowie **Körperhaltung** und **Bekleidung** bei Personen — lassen
sich je einzeln auf **würfeln**, **unverändert lassen** oder einen festen Wert
stellen. Der Werkstoff steht standardmäßig aus und wird bei Personen nie
gewürfelt. So entsteht wahlweise breite Streuung oder eine Serie, in der sich
nur ein einziges Merkmal ändert — oder umgekehrt: Stil fest auf *Comic*, alles
andere gewürfelt, dann bleibt der Zeichenstil und der Rest wechselt.

Die **Farbstimmung** ist etwas anderes als die Farbe: sie färbt das ganze Bild
(knallig, pastell, neon, kitschbunt, metallic, irisierend, monochrom, erdig,
kühl, warm) und braucht kein Ziel. Ohne sie bestimmen Umgebung und Licht die
Palette allein, und die sind erdlastig — daher der frühere Braunstich. Was umgefärbt wird, beschreibst du selbst
(`the vehicle body`, `the person's coat`), ebenso was unverändert bleiben muss.
Neben den Bildern entsteht ein `*.jsonl`-Manifest mit einer Zeile je Variante.

**Fotodaten** — Trainingsdaten aus **echten** Fotos, in einem Auftrag:
Fotos hochladen, die Box wahlweise von Hand ziehen, je Achse (Farbe,
Untergrund, Kameraposition, Licht, Farbstimmung, Kameraart, Werkstoff) die
Werte wählen. Ein **Plan** statt Würfeln (`webui/fotodaten.py`):
*einzeln* — jede Achse allein, jeder Wert genau einmal, der Rest wie im
Foto; *kombiniert* — alle Achsen zugleich, ausgewogen, jeder Wert gleich oft
und keine Kombination doppelt, solange es freie gibt; *beides*; *alle* —
das Kreuzprodukt, höchstens 500. Erst rechnet das Bildmodell alle Fotos,
dann laden die Box-Erkenner einmal für alles. Das Original geht mit in den
Datensatz — das wertvollste Bild darin; mit Box von Hand wird es sofort
aufgenommen und ist der Bezug für seine Varianten. Original und Varianten
heißen `<stempel>_fotoNN_…` und bleiben beim Training geschlossen auf einer
Seite von train/val. Handyfotos werden nach ihrem EXIF-Vermerk aufgerichtet
(gilt für alle Uploads), sonst läge das Auto für das Modell auf der Seite
und die gezogene Box daneben.

Neben YOLO und COCO schreibt der Datensatz jetzt `attribute.csv`: je Bild
Box, Status, echt/erzeugt, Herkunftsfoto und jede Achse — zum Ausbalancieren
oder für einen Klassifikator auf Farbe, Untergrund, Licht.

**Serien** mit 1–20 Bildern. Variieren nach Umrundung, Kameraperspektive, Stil
oder Lichtstimmung — der Reihe nach oder gewürfelt. Optional derselbe Seed für
alle Bilder, was Kleidung, Umgebung und Bildaufbau stabil hält.

**Warteschlange.** Aufträge werden eingereiht statt abgewiesen: abschicken,
weiterarbeiten, den nächsten anhängen. Ein einziger Arbeitsfaden nimmt die
Liste der Reihe nach ab — gleichzeitig rechnen kann die eine Grafikkarte
ohnehin nicht. Wartende lassen sich verschieben und einzeln verwerfen, der
laufende wird abgebrochen.

Gleichartige Aufträge, die hintereinander warten, **teilen sich einen
Ladevorgang**. Das lohnt sich: gemessen kostet das Laden rund 70 Sekunden, ein
kleines Bild danach anderthalb. Zwei einzeln eingereihte Aufträge brauchten
144 s, gebündelt 78 s. Gebündelt wird streng nur, was wirklich zusammenpasst —
schlichte Text-zu-Bild-Aufträge ohne Referenzbild, Effekt oder Serienart, bei
gleicher Größe, Schrittzahl und Format.

**Projekte.** Jedes Vorhaben bekommt sein eigenes Verzeichnis unter
`projekte/<name>/`: eigene Bilder, eigene Galerie. Ein Auftrag merkt sich beim
Einreihen, zu welchem Projekt er gehört — wer zwischendurch umschaltet, findet
seine Bilder trotzdem am richtigen Ort. Das Projekt **Allgemein** zeigt weiter
auf das alte `outputs/`, dort liegende Bilder müssen nicht umziehen.

**Video aus ausgewählten Bildern.** In der Galerie „Video zusammenstellen"
anklicken, Bilder in der gewünschten Reihenfolge wählen (sie werden
durchnummeriert), Gesamtdauer eintragen — Standzeit und Überblendung rechnet
der Server daraus aus. Die Bilder gehen nahtlos ineinander über, ohne Schnitt
und ohne Beschriftung.

**Noten und gemerkte Prompts.** Unter dem angezeigten Bild stehen fünf
Sterne, ein Namensfeld und eine Notiz. Alles landet in
`projekte/<name>/bewertung.json` — lesbar und zum Weiterreichen gedacht, samt
einer Liste für Verbesserungshinweise. Wer ein Bild benennt, merkt sich
seinen Prompt: in einer Szene holt ihn `\name` oder `\nummer` zurück, genau
wie eine feste Kameraeinstellung. Der Prompt wird dabei aus dem PNG
herausgeschrieben — das Bild darf später weg, der gute Prompt bleibt.

**Was nicht ins Bild soll.** Das Feld arbeitet als **Torwächter**: die
eingetragenen Begriffe werden aus dem fertigen Prompt gestrichen, bevor
gerechnet wird — „Küche" und „Büro" kommen ohnehin als Wort aus einer
Umgebungsachse oder einem Baustein. Das kostet nichts. Was gestrichen wurde,
steht danach unter dem Feld.

Gestrichen wird so viel wie nötig und so wenig wie möglich: steht der Begriff
vorn im Satzglied, ist er dessen Gegenstand und alles fällt (»in a bright
kitchen« verschwindet ganz). Steht er hinten, ist er Beiwerk und nur der
Nebensatz fällt — »eine Markthalle mit Leuchtreklame« bleibt eine Markthalle. Nur für Dinge, die *nicht* im Prompt stehen
(unscharf, sechs Finger), hilft das Häkchen „auch dem Modell ausreden" — dann
läuft jeder Schritt zweimal und das Bild dauert doppelt so lang.

**Bausteine.** Personen, Orte und Gegenstände lassen sich als Prompt mit
Namen und Bild ablegen und immer wieder verwenden. Beschrieben wird auf
Deutsch, das Sprachmodell schreibt daraus den englischen Prompt — und setzt
alles, was sich ändern darf, als Lücke in geschweifte Klammern:

```
a woman in her thirties, slim, short dark hair, wearing {kleidung} and {schuhe}
```

Im Reiter **Zusammenstellen** hakt man Bausteine an, füllt die Lücken und
erzeugt daraus ein Bild. Mehrere Zeilen in einem Lückenfeld ergeben eine ganze
Serie — dieselbe Person in vier Jacken, alle in einem Ladevorgang. Das Ergebnis
lässt sich als **Szene** merken: sie behält ihre Lücken, bekommt das erzeugte
Bild und ist damit wiederholbar.

Leere Lücken hinterlassen keine Bruchstücke: aus `a basket made of {material}`
wird ohne Material `a basket`, nicht `a basket made of ,`.

**Freitext mit Gedächtnis.** Das Gespräch geht weiter: „ein rotes Auto im
Wald" → „mach es hochkant" → „und jetzt als Comic" → „davon bitte sechs
Stück". Jeder Nachsatz ändert genau eine Sache und lässt den Rest stehen; der
Verlauf steht unter dem Feld, „neu anfangen" vergisst ihn.

**Geschichte** in vier Schritten. **Umreißen:** eine Idee genügt — das
Sprachmodell schreibt die Kurzfassung, schlägt den Stil für die ganze Folge
vor und macht einen Vorschlag fürs Inhaltsverzeichnis. Ein **Regler von 0 bis
100 % Fiktion** sagt ihm, wie wirklich es zugehen soll; ohne diese Angabe
biegt es eine Fantasiehandlung so lange zurecht, bis sie alltagstauglich ist.
Gemessen an derselben Idee: bei 0 % sucht eine Frau nachts ein verlegtes Buch,
bei 100 % wandeln sich die Regale, während sie sucht.

**Gliedern:** je Zeile eine Szene, mit `/Name` holst du einen Baustein herein
(`/Anna rennt durch die /Markthalle`), mit `\Name` die Kameraeinstellung.
Sechs gibt es: `\augen` (Makro dicht vor den Augen, die Iris füllt das Bild,
mit Spiegelung darin), `\spiegel` (Kamera hinter den Figuren, Rücken und
Spiegelbild in einem Bild), `\scheibe` (durch eine halbtransparente
Glasscheibe hindurch, das Dahinter dämmrig und zugleich gespiegelt),
`\decke` (Kamera hängt über der Szene und schaut senkrecht herab),
`\bettlage` (vom Boden senkrecht hoch) und `\raus` — das ergibt **zwei**
Bilder, einmal von drinnen heraus und einmal von draußen hinein.

Was in Klammern dahintersteht, füllt die Lücke der Einstellung: bei `\augen`
und `\spiegel`, was sich spiegelt, bei `\decke` die Höhe — `\augen(das
brennende Deck)`, `\decke(fünf Meter)`. Zahl und Einheit übersetzt das
Programm selbst, den Rest einmal das Sprachmodell.

Verlangt eine Einstellung eine Großaufnahme, zählt nur noch das Gesicht:
Kleidung, Ort und Gegenstand fallen aus dem Prompt, sonst zieht eine Hose
darin die Kamera wieder zurück. Deshalb hat eine Person drei Prompts —
allgemein, Gesicht, Bekleidung.

Ein Bild, das du in der Galerie benannt hast, kommt mit demselben Zeichen
wieder: `\augen-makro` oder `\7`. Rechts steht, wie viele Bilder aus
dieser Szene entstehen — mehrere zeigen denselben Augenblick aus wechselndem
Blickwinkel. Gewürfelt wird dabei nur der Blick: Standpunkt, Objektiv und die
sechs Einstellungen, achtzehn Möglichkeiten. Stil, Ort und Kleidung bleiben,
wie sie sind — eine gewürfelte Überwachungskamera machte aus einem Manga
mittendrin ein Lichtbild. Bei den elf gezeichneten Stilen steht zusätzlich
ausdrücklich im Prompt, dass kein Foto entstehen soll; ab 70 % Fiktion rät
das Programm ohnehin zu Anime, Comic oder Manga.

**Schreiben lassen:** die Prompts entstehen der Reihe nach, jede Szene sieht
die vorigen. Dafür ist das große Modell (`qwen3.8:27b-mtp-q4_K_M`, 16,5 GB)
vorgesehen — gemessen rund 30 s zum Laden und dann 7 s je Szene, und es
bleibt zwischen den Szenen geladen. Optional schreibt es auch die Prosa dazu.
Weil es die Grafikkarte belegt, läuft das als Auftrag in der Warteschlange.

**Erzeugen:** in den Ablauf übernehmen und gegenlesen, oder gleich Bilder und
Video.

**Mehrere Geschichten, jede in Bänden.** Eine Geschichte bekommt einen Namen
und die Vorgaben, die für alles gelten: Stil, Welt, Wirklichkeitsgrad,
Sprachmodell. Soll sie weitergehen, hängt *+ Band* einen zweiten Teil an — er
erbt die Vorgaben und kennt die Kurzfassungen der vorigen Bände, knüpft also
an, statt die Figuren neu zu erfinden.

Gespeichert wird als lesbares JSON, eine Datei je Geschichte unter
`projekte/<projekt>/geschichten/<name>.json`: Vorgaben oben, darunter die
Bände mit Idee, Kurzfassung, Inhaltsverzeichnis und Prompts. Damit lässt sich
eine Geschichte auch außerhalb des Programms weiterverarbeiten. Geschrieben
wird verzögert, damit nicht jeder Tastendruck eine Datei anfasst.

Ein `/Name`, zu dem es noch keinen Baustein gibt, ist eine Arbeitsanweisung
und erscheint im **Katalog unter „Noch anzulegen"**, mit dem Projekt, das ihn
verlangt, und einem Knopf, der ihn gleich anlegt. Sobald er existiert,
verschwindet der Eintrag.

Der alte Weg — Handlung auf Deutsch beschreiben, Bausteine anhaken — das
Sprachmodell zerlegt sie in Bilder und nimmt **Mimik und Stil aus der
Handlung**: wer seinen Korb verliert, schaut erschrocken, wer ihn wiederbekommt,
erleichtert. Heraus kommt kein Sonderformat, sondern die vorhandene
Blockstruktur eines **Ablaufs** — gegenlesen, ändern, starten, oder ohne
Prüfung loslaufen lassen. Hat die Hauptperson ein Bild, wird es zum Startbild,
damit die Folge auf einem Gesicht aufsetzt statt in jedem Bild ein neues zu
erfinden.

**Katalog.** Ein Reiter zeigt alle Bausteine aus allen Projekten auf einer
Seite, nach Art und Text durchsuchbar. Von dort lässt sich eine Person, ein
Ort oder ein Gegenstand in ein anderes Projekt übernehmen — das Bild wandert
als Kopie mit, damit es das Löschen des Ursprungsprojekts überlebt.

**Sechs Seiten.** Ein Gegenstand, sechsmal gerade von einer Seite —
vorne, hinten, links, rechts, oben, unten, wie in einem Teilekatalog. Man
beschreibt ihn einmal auf Deutsch (oder wählt einen Baustein der Art
*Gegenstand*), und alle sechs Ansichten entstehen aus demselben Text, mit
demselben Seed, in **einem** Ladevorgang.

Der Gegenstand **schwebt dabei frei im Raum**, und das ist der eigentliche
Trick: steht er auf einem Tisch, zeigt die Ansicht von unten die Tischplatte
statt seines Bodens. Kein Tisch, kein Sockel, keine Hand, kein Boden, kein
Schlagschatten — jedes einzeln genannt, sonst malt das Modell eines davon
dazu.

Kein Vorlagenbild: ein Referenzbild hält die Blickrichtung fest — dieselbe
Beobachtung wie beim Szenenaufbau, wo eine stehende Figur stehen blieb,
obwohl der Text sie liegend wollte. Die Ansicht von unten wäre damit wieder
die von vorn. Derselbe Seed für alle sechs ist das stärkste Mittel, das
bleibt; es hält Größe, Farbe und Anmutung zusammen.

**Nicht wo die Kamera steht, sondern was das Bild zeigt.** Gemessen an sechs
Formulierungen für dieselbe Ansicht, gleicher Seed, gleicher Gegenstand:
„a true top view, the camera directly above it" ergab dasselbe
Dreiviertelbild wie „flat lay", wie die orthografische Zeichnung, wie die
zweimal gesagte Blickrichtung. Deutlich höher kam allein die Fassung, die
beschreibt, *was im Bild ist* — „the picture shows only its top, the sides
of the body are hidden beneath it". Dieselbe Bauart lieferte auch die bis
dahin nicht erreichte Untersicht. Alle sechs Seiten sind seither so gebaut,
und sie sagen jeweils auch, was in dieser Ansicht **verdeckt** ist.

**Das Sprachmodell beschreibt den Gegenstand von jeder Seite.** Ein
allgemeiner Satz weiß nichts über den Gegenstand — er kann nicht sagen, dass
unten die Parabolantenne sitzt und die Solarpaneele dort nur noch schmale
Kanten sind. Deshalb geht die deutsche Beschreibung zuerst an Ollama
(`webui/sprache/ansichten.py`), das daraus den englischen Gegenstandsprompt
*und* je Seite einen Satz schreibt. Dieselbe Arbeitsteilung wie beim
Szenenaufbau: das Sprachmodell denkt über den Gegenstand nach, das Bildmodell
malt. Die sechs Sätze stehen in der Oberfläche über den Bildern und hängen
als Titel an jeder Kachel — geht eine Ansicht daneben, ist ablesbar, woran
es lag.

Eine Falle dabei, zweifach abgesichert: bei *unten* stellt das Sprachmodell
den Gegenstand gern auf etwas („while the base rests on a flat ground
plane"). Im Prompt angekommen wäre das ein Boden im Bild — und die
Unteransicht wieder verdeckt, also genau der Fehler, den die Funktion
vermeiden soll. Der Systemtext verbietet es, und ein Filter schneidet so
einen Satzteil heraus; steht er mitten in der Hauptsache, fällt der ganze
Seitensatz weg und der allgemeine gilt.

**Jede Seite lässt sich selbst schreiben.** Im Eingabefeld steht oben der
Gegenstand, darunter jede Seite mit ihrem eigenen Befehl — dieselbe
Schreibweise wie die `/Namen` in einer Geschichte:

```
ein Erdbeobachtungssatellit, kastenförmiger Körper mit goldener Folie
/hintergrund ein tiefschwarzer Sternenhimmel
/unten  die weiße Parabolantenne füllt die Mitte als voller Kreis, links
        und rechts die Unterseiten der Solarpaneele
/oben   die goldene Oberseite füllt die Mitte als Kreis, die Paneele flach
        daneben
/-oben  Parabolantenne, Kameratubus, Düsen
```

Was dasteht, gilt; was fehlt, schreibt das Sprachmodell. `/hintergrund`
ersetzt das neutrale Grau — ein Satellit gehört vor Sterne, ein Werkzeug vor
nichts. Das Schweben bleibt davon unberührt.

**`/-` ist dabei der eigentliche Kunstgriff.** Was nicht zu sehen sein soll,
darf im Prompt nicht vorkommen — auch nicht als „die Antenne ist verdeckt".
Ein Diffusionsmodell malt, was dasteht; die Verneinung davor liest es kaum.
Gemessen an der Aufsicht des Satelliten: im Prompt stand *„the antenna,
camera tube and thrusters are all hidden"*, und die Antenne war im Bild.
Hinter `/-oben` genannt, fällt sie stattdessen aus dem Satz dieser einen
Ansicht heraus — über den **Torwächter**, der das ganze Aufzählungsglied
entfernt. `/-` ohne Seite gilt für alle sechs, `/+oben` ist dasselbe wie
`/oben`.

**Den ganzen Satz Befehle schreibt auf Wunsch das Sprachmodell.** „Vorschlag
schreiben lassen" füllt das Feld mit allen sechs Seiten samt `/-`-Zeilen — auf
Englisch, so wie es ins Bild geht. Man liest ihn durch, ändert was nicht
stimmt und erzeugt erst dann; zehn Minuten Rechenzeit sind zu viel, um einen
Fehler erst im fertigen Bild zu sehen. Was man selbst geschrieben hat, bleibt
stehen, der Vorschlag füllt nur die Lücken.

Dabei wird die Antwort nicht blind geglaubt: beim ersten Versuch nannte das
Modell unter `/vorne` den Kameratubus als Hauptsache und führte ihn in
derselben Antwort unter `/-vorne` als verdeckt. Übernommen hätte der
Torwächter der Ansicht ihr Motiv weggestrichen. Was im sichtbaren Satz
vorkommt, fällt deshalb aus der Ausschlussliste heraus.

**Zahlenvergleiche werden in Worte gefasst.** „two solar panels … extending
**four times** the length of the body" ergab einen Satelliten mit **vier**
Paneelen: das Bildmodell zählt nicht, es sieht die Zahl neben der Sache. Aus
`four times the length of the body` wird deshalb `far beyond the body`, aus
`three times as tall as the housing` wird `very tall, far beyond the
housing`. Eine echte Anzahl — „two solar panels and 4 thrusters" — bleibt
unangetastet; der Riegel greift nur vor `times`, `twice` und `double`.

Je Seite und nicht für die ganze Reihe, und zwar aus einem Grund: dieselbe
Antenne soll in der Aufsicht verschwinden und ist in der Untersicht die
Hauptsache. Der negative Prompt des Modells kann das nicht — er gilt für alle
Bilder eines Ladevorgangs. Er wurde gemessen (CFG 2,5 gegen
„Dreiviertelansicht, Perspektive"): macht die Bilder schärfer, an der
Blickrichtung ändert er nichts, und er verdoppelt die Rechenzeit. Der
Torwächter kostet nichts und trifft genau.

Die Bilder landen **nicht in `outputs/`**, sondern in
`katalog/<Projekt>/<Eintrag>/` mit einer Liste in
`katalog/<Projekt>/katalog.json`. In `outputs/` wird oft aufgeräumt, und ein
Katalog, der beim Aufräumen verschwindet, ist keiner. Jeder Lauf ergibt einen
eigenen Eintrag — wer denselben Gegenstand noch einmal rechnet, bekommt einen
zweiten daneben und kann vergleichen.

**Prompt aus einem Bild.** Der umgekehrte Weg: ein Bild wählen, das
Sprachmodell beschreibt es als Prompt und stellt Stil, Licht und Objektiv
gleich passend ein (gemessen 5–9 s). Im Ablauf-Reiter wird ein hochgeladenes
Startbild sofort kurz beschrieben; der Text lässt sich vor dem Start ändern.

**Voreinstellungen** in `webui/kataloge/`, frei erweiterbar: 23 Stile,
10 Lichtstimmungen, 18 Kameraperspektiven (elf Objektive und die sieben aus
den Einstellungen), 10 Blickwinkel, 8 Vorlagen
(Porträt, Logo, Buchumschlag, Verpackung, Icon, Web- und App-Muster) sowie
18 Effekte als Kurzbefehle — `/remove BG`, `/colorize`, `/blueprint`,
`/cad2real` (aus einer CAD-Ansicht ein Produktfoto mit echten Materialien,
Oberflächenspuren und Kontaktschatten, bei unveränderter Geometrie),
`/cad` (der Gegenweg: aus dem Foto die Konstruktionsansicht — grauer
Volumenkörper, scharfe Kanten, keine Spiegelungen),
`/upscale` (dasselbe Bild in 2048er Kantenlänge, mit ausgezeichneten
Strukturen statt geglätteter Kanten), `/magazine cover`, `/360 View` und
weitere.

Zum **Magazin-Cover** gehört eine eigene Eingabemaske: Titel, Zeile darunter,
Artikel (eine je Zeile, die erste wird die große Schlagzeile), Ausgabe, Preis
und ein Barcode zum Abwählen. Das ist kein Beiwerk — ohne Vorgabe erfindet
das Modell die Schrift, und zwar als Kauderwelsch: auf dem ersten Versuch
stand „WALD ARAS“ als Titel und „SRDVIS ZYABRNTS“ als Schlagzeile. Vorgegeben
schreibt Qwen-Image sie dagegen sauber, Umlaute und Eurozeichen
eingeschlossen.

Zwei Feinheiten dabei: die Zeilen gehen **nicht** durch die Übersetzung — sie
werden ins Bild gemalt, und auf einem deutschen Heft stünde sonst Englisches.
Und der Prompt endet mit dem Satz, dass jedes Wort auf dem Titelblatt eines
der genannten ist; ohne ihn füllt das Modell den freien Platz weiter mit
erfundener Schrift. Kurzbefehle lassen sich direkt in
das Prompt-Feld tippen und stellen die Regler selbst um.

**Deutsch überall.** Prompt, „was unverändert bleiben muss", „was umgefärbt
wird" und der negative Prompt dürfen deutsch sein. Der Server erkennt das und
übersetzt vor dem Auftrag ins Englische, weil Qwen-Image dem deutlich besser
folgt. Kostet rund vier Sekunden und gilt auch für das GIMP-Plugin. Englische
Eingaben laufen unangetastet durch. Ist Ollama nicht erreichbar, läuft der
Auftrag mit dem Originaltext weiter statt zu scheitern. Was übersetzt wurde,
zeigt die Oberfläche unter dem Prompt-Feld an.

**Freitexteingabe:** Ein Satz auf Deutsch, ein lokales Sprachmodell über
[Ollama](https://ollama.com) übersetzt und stellt ein. Der eigentliche Gewinn
ist die Übersetzung — Qwen-Image folgt englischen Bildbeschreibungen deutlich
besser. Alles Verstandene landet sichtbar in den Reglern, bevor es losgeht.

Die Deutung erzeugt noch kein Bild: erst Text, dann Prompt und Einstellungen,
dann prüfen, dann selbst auf Erzeugen klicken.

Das Sprachmodell wird nach jeder Anfrage sofort wieder entladen
(`keep_alive: 0`), damit die GPU frei für das Bildmodell bleibt.

## Abläufe

Der Reiter **Ablauf** erzeugt eine Bildfolge und schneidet daraus ein Video
ohne Beschriftung, bei dem die Bilder ineinander blenden. Eine Folge ist eine
**Datenstruktur aus Blöcken**, kein fest verdrahteter Code — jeder Block sagt:

| Feld | Bedeutung |
|---|---|
| Referenz | vom Startbild oder vom letzten Bild des vorigen Blocks |
| Vorlage | *behutsam ändern* (bewahrt), *verwandeln* (Stilwechsel) oder *Bewegung* |
| Seed | eigener oder wie das Startbild |
| danach Startbild | blendet das Ausgangsbild wieder ein, ohne es neu zu rechnen |
| Anzahl | wie viele Bilder der Block liefert; mehr als Zeilen heißt, die Zeilen werden der Reihe nach wiederholt |
| was bleibt | die Ausnahme, die stehen bleiben muss |
| Bausteine | ein Bild je Zeile |

Die beiden oberen Felder sind nicht kosmetisch. **Die Prompt-Vorlage:** die
behutsame wiederholt „muss identisch bleiben" mehrfach; ein angehängter
Stilbaustein geht darin unter und das Modell gibt schlicht die Vorlage zurück.
**Der Seed:** ein für alle Bilder gesperrter Seed hält die Bildaufteilung ruhig,
zementiert aber auch die Neigung dieses *einen* Rauschmusters — gemessen wurde
aus „grellem Neon" ein violetter Hauch (Abweichung 42 statt 79).

Sieben Abläufe sind mitgeliefert:

| Ablauf | Bilder | Worum es geht |
|---|---|---|
| **Bogen** | 38 | konservativ über Comic und Neon und zurück |
| **Reise** | 48 | Licht, Perspektive, Person, Schwenk, Bewegung, Hintergrund, Rollen, Szenen bis Cyberpunk, Neonkleidung, Gruppenbild |
| **Klassisch** | 21 | nur Mittel des Fotostudios: Lichtführung, Brennweite, Hintergrund, Schwarzweiß |
| **Zeitreise** | 19 | zwölf Epochen von der Höhle bis in die nahe Zukunft, dazu sechs Aufnahmeverfahren von der Daguerreotypie bis zum Handyfoto |
| **Comicheft** | 16 | zehn Zeichenstile von Ligne claire bis Pop Art, dann immer weiter ins Heft hinein bis zum Rasterpunkt |
| **Neonstadt** | 11 | eine Eskalation, jeder Schritt auf dem vorigen: Neon, Regen, Hologramme, Implantate, Drohnenblick, Glitch — und zurück auf die Straße |
| **Elemente** | 14 | aus Feuer, Wasser, Erde, Luft; dann als Bronze, Marmor, Glas, Holz, Origami, Klemmbaustein; zum Schluss in Bewegung |

Der Ablauf **passt sich dem Startbild an**. Bevor die Blöcke gebaut werden,
beschreibt dasselbe Sprachmodell das Bild — Geschlecht, ungefähres Alter,
Haare, auffällige Kleidung, Umgebung. Daraus folgt zweierlei:

- Ist eine Frau zu sehen, wird aus dem Bart-Schritt ein Haarfarben-Schritt.
  Bei unklarem Befund bleibt es beim Regelfall, statt zu raten.
- Die Beschreibung wandert in jede Bewahrungsklausel. „Die Person muss gleich
  bleiben" trifft das Modell besser, wenn dort steht, *wen* es gleich lassen
  soll — also „die Person (eine Frau Mitte zwanzig mit langen braunen Haaren,
  schwarzes Oberteil)". Was erkannt wurde, steht unter dem hochgeladenen Bild.

Jede Anweisung endet mit einem Hinweis zu den **Zähnen**. Diffusionsmodelle
verzeichnen sie notorisch — zu viele, verschmiert, doppelte Reihen. Der kurze
Zusatz („gleichmäßig, richtig geformt, die richtige Anzahl, nicht verschmiert
oder verdoppelt") hilft spürbar.

Im Editor lassen sich Blöcke hinzufügen, verschieben, löschen und über **als
Text** als JSON sichern und zurückspielen. Die Kommandozeile nimmt so eine
Datei:

```bash
./qwen_bild/bin/python demo/demonstration.py --ablauf reise
./qwen_bild/bin/python demo/demonstration.py --datei eigener_ablauf.json --foto ich.png
```

**Zur Laufzeit:** aufeinanderfolgende Blöcke, die vom Startbild ausgehen, laufen
als *eine* Serie. Bei der Reise sind das 36 Bilder in einem Ladevorgang; nur die
Blöcke, die auf dem letzten Bild aufsetzen, brauchen einen eigenen. 43 Bilder
kosten so rund 29 Minuten statt über einer Stunde.

Die **Kulisse** hinter der Person — Auto, Raumschiff, Fangemeinde, Pferd,
Bagger, Bücherwand und weitere — wird ohne Angabe aus dem Seed abgeleitet und
wechselt damit von Lauf zu Lauf, bleibt aber reproduzierbar.

## GIMP-Plugin

```bash
./gimp/install.sh   # GIMP danach neu starten
```

Menü **Filter › Qwen**: *Text zu Bild*, *Bild bearbeiten*,
*Hintergrund entfernen*. Das Plugin rechnet nichts selbst, es redet über HTTP
mit dem laufenden Server.

**Die GIMP-Auswahl ist die Maske.** Besteht beim Bearbeiten eine Auswahl,
bekommt die Ergebnisebene automatisch eine Ebenenmaske daraus — die Änderung
wirkt nur dort. Qwen-Image 2.1 selbst hat keinen Masken-Eingang; GIMPs
Auswahl- und Pinselwerkzeuge übernehmen diese Rolle. Auswahl vorher ausblenden,
sonst gibt es eine harte Kante.

In der Weboberfläche gibt es unter jedem angezeigten Bild **In GIMP öffnen** —
das startet GIMP auf dem Rechner, auf dem der Server läuft, mit genau diesem
Bild. Weil das ein Programm startet, nimmt der Server diesen Aufruf nur von
`127.0.0.1` an; vom Handy aus bleibt er verwehrt, auch bei `QWEN_HOST=0.0.0.0`.

GIMP 3.2 benutzt `~/.config/GIMP/3.2/plug-ins/`, auch als Snap-Paket. Das
Verzeichnis `~/snap/gimp/*/.config/GIMP/3.0/` ist ein Überbleibsel und wird
nicht gelesen.

## Einstellungen über Umgebungsvariablen

| Variable | Vorgabe | Wirkung |
|---|---|---|
| `QWEN_HOST` | `127.0.0.1` | Bindeadresse des Servers |
| `QWEN_PORT` | `7860` | Port |
| `QWEN_IMAGE_REPO` | `Qwen/Qwen-Image-2.1` | Modell |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama für die Freitexteingabe |
| `QWEN_CHAT_MODEL` | `qwen3.5:4b` | Sprachmodell für die Deutung |
| `QWEN_URL` | `http://127.0.0.1:7860` | Server, den das GIMP-Plugin anspricht |
| `QWEN_GIMP` | `gimp` | Befehl für „In GIMP öffnen" |
| `QWEN_BOX_MODELL` | `Qwen/Qwen3-VL-2B-Instruct` | setzt die Bounding Box |
| `QWEN_BOX_PRUEFER` | `IDEA-Research/grounding-dino-base` | prüft die Box gegen |
| `QWEN_BOX_GERAET` | je nach Karte | `cpu` oder `cuda` für Qwen3-VL |
| `QWEN_NUR_CLOUD` | – | `1`: Bildmodell nie lokal laden (portable Fassung) |
| `QWEN_YOLO_ORDNER` | `modelle/yolo` | YOLO26-Gewichte und -Einstellungen |
| `QWEN_YOLO_BATCH` | `0.6` | Stapelgröße; unter 1 als Anteil des Grafikspeichers |

Cloud-Zugänge stehen nicht in Umgebungsvariablen, sondern in
`einstellungen.json` (Rechte 600, in `.gitignore`) — eingetragen über
**Cloud-Modelle** in der Kopfzeile.

## Bekannte Grenzen

**`/expand` ist kein pixelgenaues Outpainting.** Qwen-Image 2.1 hat weder einen
Masken-Eingang noch einen Outpainting-Prior: einen freigelassenen Rand füllt es
nicht auf, einen unscharf vorgefüllten übernimmt es unscharf. Umgesetzt ist
deshalb der Weg, der zum Modell passt — die Szene wird im neuen Format neu
gezeichnet. Person, Kleidung, Umgebung und Licht bleiben erhalten, die Mitte
ist danach aber nicht pixelgleich.

**`/upscale` rechnet nicht hoch, es zeichnet neu.** Einen Skalierer bringt
Qwen-Image 2.1 nicht mit. Der Effekt gibt das Bild deshalb mit 2048er
Kantenlänge neu aus — das Seitenverhältnis kommt aus der Vorlage, die mit
1472 px gelesen wird. Es entstehen echte Strukturen statt weichgezeichneter
Kanten, das Ergebnis ist dafür nicht pixelgleich: kleine Details können
anders ausfallen als im Original. Für Beweisfotos ist das nichts, für ein
altes Handybild, das groß gedruckt werden soll, sehr wohl.

**`/restore` ist nur ein Prompt.** Ein Diffusionsmodell erfindet Details, statt
sie wiederherzustellen. Für echtes Restaurieren gehört ein eigenes Modell her.

**Das Sprachmodell rät mit.** Kleine Modelle setzen gern Stil oder Licht, nach
denen niemand gefragt hat. Deswegen landet alles sichtbar in den Reglern. Aus
einem Vergleich von vier Modellen auf einem Testsatz aus zehn Anfragen:

| Modell | Testsatz (22 Punkte) | Erfundene Felder bei knappen Wünschen |
|---|---|---|
| `qwen3.5:4b` | 22/22 | 0 |
| `ministral-3:3b` | 21/22 | 0 |
| `qwen3.5:2b` | 22/22 | 0 |
| `granite4.2:3b` | 16/22 | 9 |

Ein JSON-Schema statt `format: "json"` erzwingt zwar gültige Syntax, kostet
aber spürbar Verständnis — gemessen 14 statt 22 Treffern, weil ausdrückliche
Wünsche wie „quer" oder „freigestellt" unter den Tisch fielen. Die Antwort wird
stattdessen serverseitig gegen die echten Tabellen geprüft.

**Der Blickwinkel ändert sich bei Varianten nur wenig.** Qwen-Image 2.1
hält sich eng an die Bildaufteilung der Vorlage. Lack, Umgebung und Licht
wechseln zuverlässig, „bodennah" oder „Nahaufnahme" verschieben den Ausschnitt
dagegen nur leicht. Für echte Perspektivvielfalt braucht es Aufnahmen aus
verschiedenen Winkeln als Basis.

**Farbe und Werkstoff zugleich ist mehrdeutig.** Wer beide Achsen gleichzeitig
würfelt, bekommt womöglich ein gelbes Teil neben einem zweiten aus Carbon. Eins
von beidem wählen, das andere auf „unverändert lassen".

**Rollen je Bild greifen, aber nicht immer vollständig.** Der Ritter kam mit
Rüstung und Jeans. Je knapper und konkreter der Rollentext, desto besser.

**Mehrere Referenzbilder kosten Sequenzlänge.** Vier Referenzen bei voller
Auflösung sprengen den Speicher. Die Referenzauflösung wird deshalb automatisch
gesenkt (1–2 Bilder 1024 px, 3 Bilder 864 px, 4 Bilder 736 px), die
Ausgabegröße bleibt unberührt. VRAM-Spitze bei vier Personen: 19,9 GB.

## Prüfen

```bash
./qwen_bild/bin/python webui/pruefung.py        # Server auf 7860 muss laufen
```

Vergleicht die Oberfläche mit dem laufenden Server: liest die Seite nur Felder,
die `/api/info` auch liefert, existiert jedes angesprochene Element, sind die
Klammern im Skript geschlossen, läuft der Server mit dem Code von der Platte.

Anlass war ein echter Fehler: ein Feld wurde aus `/api/info` entfernt, die
beiden Aufrufe in der Seite blieben stehen. Der TypeError brach die gesamte
Einrichtung ab, das Seitenverhältnis-Feld blieb leer — und der Auftrag
scheiterte erst viel später im Server mit `KeyError: ''`.

## Aufbau

```
start.sh              Server starten, Browser öffnen
ANLEITUNG.md          Bedienungsanleitung
webui/server.py       HTTP-Server, nur Routen und Start
webui/auftraege.py    Warteschlange und Abwicklung eines Auftrags
webui/projekte.py     getrennte Ablagen, Projektverzeichnisse
webui/bausteine.py    Personen, Orte, Gegenstände und Szenen mit Lücken
webui/geschichte.py   Szenen einer Handlung zu Ablaufblöcken
webui/engine.py       zweiphasige Pipeline
webui/kataloge/       Voreinstellungen: anmutung.py (Stil, Licht, Kamera,
                      Farbe), motiv.py (Umgebung, Blickwinkel, Werkstoff),
                      vorlage.py (Prompt-Vorlagen, Effekte, Gruppen)
webui/sprache/        Ollama: deuten.py (Freitext), uebersetzen.py,
                      sehen.py (Bilder lesen), erzaehlen.py (Handlung in
                      Szenen), ansichten.py (ein Gegenstand von sechs
                      Seiten), ollama.py (der Aufruf)
webui/szenenbau.py    eine Szene in Stufen: Kulisse, Posen, Zusammensetzen
webui/sechsseiten.py  sechs Ansichten eines Gegenstands und ihr Katalog
webui/cover.py        die Eingabemaske fuer ein Titelblatt
webui/retusche.py     Ausschnitt um eine Maske, Farbangleich, Einsetzen
webui/cloud.py        Sprach- und Bildmodell ueber eine OpenAI-kompatible API
webui/datensatz.py    Bounding Boxes (Qwen3-VL + Grounding DINO), YOLO/COCO
webui/vervielfaeltigen.py  aus gepruefte Bildern viele, die Box rechnet mit
webui/detektor.py     Detektor-Training (D-FINE): Aufteilung, Laeufe, Ausprobieren
webui/detektor_lauf.py  das Training selbst, als eigener Prozess; mAP-Berechnung
webui/yolo_lauf.py    YOLO26-Training (Ultralytics), ebenfalls eigener Prozess
webui/fotodaten.py    echte Fotos: Plan der Varianten, EXIF, Box umrechnen
webui/browser_oeffnen.py  Browser oeffnen, sobald der Server antwortet (start.bat)
einrichten.bat        portable Einrichtung unter Windows (laedt Python, Pakete, Modelle)
start.bat             Start unter Windows (portabel oder venv)
installieren.bat      venv qwen_bild fuer die Entwicklung unter Windows
portable/             bauen.py (von einrichten.bat aufgerufen) und Paketlisten
webui/ablauf.py       Abläufe als Blöcke, mitgelieferte Folgen
webui/demo.py         Startbild-Vorgabe und Videobau
webui/pruefung.py     Oberfläche gegen den Server prüfen
demo/demonstration.py dieselbe Vorführung von der Kommandozeile
webui/seite/          Oberfläche: index.html (Aufbau), stil.css (Aussehen),
                      app.js (Verhalten)
gimp/qwen-image/      GIMP-3-Plugin
gimp/install.sh       Plugin verknüpfen
```

## Lizenz

Der **Code in diesem Repository** steht unter [MIT](LICENSE).

### Das Modell hat eine andere Lizenz — und die ist strenger

Dieses Repository enthält keine Modellgewichte. Qwen-Image 2.1 wird beim
ersten Start von Hugging Face geladen, und dabei akzeptierst du dessen eigene
Lizenz:

> **Qwen-Image 2.1 steht unter der [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)
> und darf nur für Forschung und Evaluierung genutzt werden.**
> Für kommerzielle Nutzung ist eine gesonderte Lizenz von Hangzhou Tongyi
> Laboratory nötig (`model-business@notice.qwencloud.com`).

Das gilt unabhängig von der MIT-Lizenz dieses Codes. MIT erlaubt dir alles mit
*diesen Dateien* — es verschafft dir keinerlei Rechte am Modell.

Beachtenswert: Qwen-Image 1.0 und Qwen-Image-Edit stehen noch unter Apache 2.0.
Erst mit 2.1 wurde auf die Research License gewechselt.

Zwei Pflichten aus dieser Lizenz betreffen typische Nutzung dieses Werkzeugs:

- **Trainierst du mit den erzeugten Bildern ein Modell und gibst es weiter**,
  musst du gut sichtbar „Built with Qwen" angeben (Abschnitt 4b). Das betrifft
  den Varianten-Modus unmittelbar.
- **„Qwen" darf nicht der primäre Name** eines abgeleiteten Produkts sein;
  beschreibende Verwendung ist erlaubt (Abschnitt 4c).

Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026
Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.

### Die übrigen Modelle und Bibliotheken

Keines davon liegt im Repository; geladen bzw. installiert werden sie beim
ersten Gebrauch, und es gilt jeweils deren eigene Lizenz.

| Bestandteil | Wofür | Lizenz | Kommerziell |
|---|---|---|---|
| Qwen-Image 2.1 | Bilder erzeugen und bearbeiten | Qwen Research License | **nein** (siehe oben) |
| Qwen3-VL-2B-Instruct | Bounding Box setzen | Apache 2.0 | ja |
| Grounding DINO (base) | Bounding Box gegenprüfen | Apache 2.0 | ja |
| D-FINE (nano/small/medium, COCO) | Detektor trainieren | Apache 2.0 | ja — auch die trainierten Gewichte |
| Ultralytics YOLO26 (optional) | Detektor trainieren | AGPL-3.0 | nur mit Enterprise-Lizenz — gilt nach Ultralytics auch für die Gewichte |
| Stable Diffusion 1.5 | Datensatz vervielfältigen (neue Umgebung) | CreativeML OpenRAIL-M | ja, mit den Nutzungsbeschränkungen der Lizenz |
| ControlNet 1.1 Canny (lllyasviel) | dabei die Umrisse festhalten | OpenRAIL | ja, mit Nutzungsbeschränkungen |
| diffusers, transformers, accelerate, huggingface_hub, safetensors | Grundlage | Apache 2.0 | ja |
| PyTorch, torchvision | Grundlage | BSD-3-Clause | ja |
| SciPy | Training | BSD-3-Clause | ja |
| Pillow | Bilder lesen und schreiben | MIT-CMU | ja |
| NumPy | Retusche, Vervielfältigen | BSD-3-Clause | ja |
| Sprachmodell über Ollama oder Cloud | Übersetzen, Prompts | je nach gewähltem Modell bzw. Anbieter | prüfen |

**Warum D-FINE und nicht Ultralytics YOLO.** Ultralytics steht unter
AGPL-3.0 und zählt nach eigener Auslegung auch die damit trainierten Gewichte
dazu: ein Detektor aus diesem Werkzeug wäre selbst AGPL oder bräuchte deren
kostenpflichtige Lizenz. D-FINE ist ein Echtzeit-Detektor derselben Klasse
unter Apache 2.0, und es kommt mit `transformers`, das ohnehin installiert
ist. Der Datensatz wird trotzdem auch im YOLO-Format abgelegt.

**YOLO26 gibt es trotzdem**, auf Wunsch und daneben: im Reiter Training
stehen `yolo26n/s/m` neben D-FINE (`webui/yolo_lauf.py`, `requirements-yolo.txt`).
Für eigene Versuche und interne Auswertung ist die AGPL gleichgültig; wer
ein damit trainiertes Modell weitergibt oder in ein Produkt einbaut, braucht
die Lizenz von Ultralytics — oder nimmt D-FINE. Beide bekommen dieselbe
Aufteilung in train und val und schreiben dieselben Kennzahlen, ein Lauf ist
mit dem anderen vergleichbar.

**Für die Kette Trainingsdaten → Detektor heißt das:** Das Training und die
Gewichte sind frei. Die *Bilder* aber stammen von Qwen-Image 2.1 — wer einen
damit trainierten Detektor kommerziell nutzen will, braucht für das Bildmodell
eine Lizenz von Tongyi oder erzeugt die Bilder mit einem Modell, dessen
Lizenz das erlaubt (etwa über **Cloud-Modelle**).

### Mitmachen

[CONTRIBUTING.md](CONTRIBUTING.md) sagt, wie Fehlermeldungen und Änderungen
willkommen sind, [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) gilt für den Umgang
miteinander, [SECURITY.md](SECURITY.md) für Sicherheitslücken.

*Dies ist eine Zusammenfassung nach bestem Wissen, keine Rechtsberatung.*
