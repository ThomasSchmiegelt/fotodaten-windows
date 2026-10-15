# Bedienungsanleitung

Diese Anleitung erklärt, **wie man mit dem Programm arbeitet** — Schritt für
Schritt, nach Aufgaben geordnet. Wie es innen gebaut ist und warum, steht in
der [README](README.md).

**Inhalt**

1. [Starten und beenden](#1-starten-und-beenden)
2. [Die Oberfläche auf einen Blick](#2-die-oberfläche-auf-einen-blick)
3. [Das erste Bild: Text → Bild](#3-das-erste-bild-text--bild)
4. [Bilder bearbeiten und Effekte](#4-bilder-bearbeiten-und-effekte)
5. [Gruppe und Rundum](#5-gruppe-und-rundum)
6. [Varianten](#6-varianten)
7. [Trainingsdaten für YOLO — die ganze Kette](#7-trainingsdaten-für-yolo--die-ganze-kette)
8. [Sechs Seiten eines Gegenstands](#8-sechs-seiten-eines-gegenstands)
9. [Bausteine, Szenen, Katalog](#9-bausteine-szenen-katalog)
10. [Geschichten und Abläufe](#10-geschichten-und-abläufe)
11. [Freitext: einfach sagen, was man will](#11-freitext-einfach-sagen-was-man-will)
12. [Galerie, Noten, Video, GIMP](#12-galerie-noten-video-gimp)
13. [Cloud-Modelle](#13-cloud-modelle)
14. [Projekte und wo was liegt](#14-projekte-und-wo-was-liegt)
15. [Wenn etwas nicht klappt](#15-wenn-etwas-nicht-klappt)

---

## 1. Starten und beenden

```bash
cd ~/ai-project/qwen_image
./start.sh
```

Der Browser öffnet sich mit `http://127.0.0.1:7860`. Beenden mit **Strg+C**
im Terminal.

| Wunsch | Befehl |
|---|---|
| anderer Port | `./start.sh 8080` |
| vom Handy im selben Netz | `QWEN_HOST=0.0.0.0 ./start.sh` |

**Immer nur eine Instanz.** Zwei Server laden je 17 GB auf die Grafikkarte
und werfen sich gegenseitig hinaus. Meldet `start.sh`
`OSError: [Errno 98] Address already in use`, läuft schon einer — siehe
[Wenn etwas nicht klappt](#15-wenn-etwas-nicht-klappt).

**Nach einer Programmänderung neu starten.** Läuft der Server mit älterem
Code als dem auf der Platte, erscheint oben auf der Seite ein Hinweisbalken.

Für Sprache (Übersetzen, Prompts ausformulieren) braucht es
[Ollama](https://ollama.com) mit dem Modell `qwen3.5:4b` — oder ein
[Cloud-Modell](#13-cloud-modelle). Ohne beides laufen Aufträge trotzdem, nur
eben mit dem Originaltext.

---

## 2. Die Oberfläche auf einen Blick

**Kopfzeile:** das **Projekt** (wohin neue Bilder gehen), daneben *+ neu*,
*umbenennen*, *löschen* und **Cloud-Modelle**. Rechts die Bildgröße des
nächsten Auftrags.

**Reiter** — jeder ist eine Arbeitsweise:

| Reiter | Wofür |
|---|---|
| Text→Bild | ein Bild aus einer Beschreibung |
| Bearbeiten | ein vorhandenes Bild verändern, Effekte |
| Gruppe | mehrere Personen in ein Bild |
| Rundum | eine Person von allen Seiten |
| Varianten | ein Basisbild vielfach abwandeln — etwa für Trainingsdaten |
| Ablauf | eine Bildfolge mit Video |
| Bausteine | Personen, Orte, Gegenstände zum Wiederverwenden |
| Szenen | Bausteine zu einem Bild zusammenstellen |
| Geschichte | eine Handlung in Szenen, Prompts und Bilder |
| Katalog | alle Bausteine aus allen Projekten |
| Sechs Seiten | ein Gegenstand von vorn, hinten, links, rechts, oben, unten |
| Datensatz | Bounding Boxes prüfen, aufnehmen, korrigieren |
| Training | YOLO trainieren und ausprobieren |

**Der große Knopf unten** startet, was der Reiter verspricht. Seine
Beschriftung sagt es jeweils („Erzeugen“, „Erstes Bild erzeugen“, „YOLO
trainieren“ …).

**Warteschlange.** Ein Auftrag wird eingereiht, nicht abgewiesen: abschicken,
weiterarbeiten, den nächsten anhängen. Während etwas rechnet, heißt der Knopf
„läuft — noch einen einreihen“. Wartende lassen sich verschieben und
entfernen, der laufende mit **Abbrechen** beenden. Gleichartige einfache
Aufträge teilen sich einen Ladevorgang und sind dadurch schneller.

**Zeiten zum Einschätzen** (RTX 3090, 1024 px, 30 Schritte): das erste Bild
eines Auftrags ~1½ Minuten (Modell laden), jedes weitere ~25–40 Sekunden.

---

## 3. Das erste Bild: Text → Bild

1. Reiter **Text→Bild**.
2. In **Prompt** beschreiben, was zu sehen sein soll. **Deutsch ist in
   Ordnung** — der Server übersetzt vorher ins Englische, weil das Bildmodell
   dem besser folgt. Was übersetzt wurde, steht danach unter dem Feld.
3. Nach Bedarf einstellen:
   - **Darstellung:** Blickwinkel, Stil, Licht, Kamera.
   - **Bild:** Seitenverhältnis (auch **A4** hoch), Kantenlänge, Schritte.
   - **Anzahl Bilder** und **Serie variieren** — siehe unten.
   - **Seed:** dieselbe Zahl ergibt bei gleichen Einstellungen dasselbe
     Bild. Leer oder −1 heißt zufällig.
4. **Erzeugen.**

**Was nicht ins Bild soll** — das Feld streicht die genannten Begriffe aus
dem fertigen Prompt, bevor gerechnet wird. Das kostet nichts. Nur für Dinge,
die gar nicht im Prompt stehen („unscharf“, „sechs Finger“), hilft der Haken
**auch dem Modell ausreden** — dann dauert jedes Bild doppelt so lang.

**Serie variieren** bei mehreren Bildern:

| Einstellung | Ergebnis |
|---|---|
| nichts variieren | gleiche Einstellungen, nur der Seed wechselt |
| Varianten | Farbe, Umgebung, Licht, Kamera, Winkel werden gewürfelt — passend zur Motivart |
| Umrundung | vorne, Seite, hinten, oben, unten |
| Kameraperspektiven / Stile / Lichtstimmungen | der Reihe nach durch die Liste |
| alles würfeln | jedes offene Feld zufällig |

**Kurzbefehle** lassen sich direkt in den Prompt tippen und stellen die
Regler selbst um, z. B. `/magazine cover`, `/ptexplosion`, `/cad`,
`/blueprint`, `/remove bg`.

**Rückweg: Prompt aus einem Bild.** Unter „…oder umgekehrt“ ein Bild wählen —
das Sprachmodell beschreibt es als Prompt und stellt Stil, Licht und Objektiv
passend ein.

---

## 4. Bilder bearbeiten und Effekte

1. Reiter **Bearbeiten**, unter **Referenzbilder** 1–4 Bilder hochladen.
2. Im Prompt sagen, **was sich ändern soll** („die Jacke rot“, „bei Nacht“).
3. Optional unter **Vorlage & Effekt** einen Effekt wählen.
4. **Erzeugen.**

**Seitenverhältnis folgt der Referenz** ist normalerweise an — das Ergebnis
hat das Format der Vorlage. Abschalten, wenn ein anderes Format gewünscht ist.

**Die wichtigsten Effekte:**

| Effekt | Was er tut | Hinweis |
|---|---|---|
| Magazin-Cover | macht das Bild zum Titelblatt | stellt **A4 hoch** selbst ein; Maske ausfüllen (unten) |
| Explosionszeichnung | Teile auseinandergezogen, weißer Grund | **wirkt nur aus Text** — siehe unten |
| CAD-Modell | graues Volumenmodell mit Kantenlinien, weißer Grund | **wirkt nur aus Text** — siehe unten |
| CAD zu Foto | aus einer CAD-Ansicht ein Produktfoto | braucht ein Bild |
| Bauplan | weiße Linien auf blauem Papier | braucht ein Bild |
| Hintergrund entfernen | Motiv freigestellt, transparent | braucht ein Bild |
| Hochskalieren | dasselbe Bild in 2048 px, neu gezeichnet | kein echter Skalierer |
| Bildausschnitt erweitern | weiterer Bildausschnitt | kein pixelgenaues Outpainting |
| Lifestyle, Glas, Doppelbelichtung, Winzige Menschen … | Stilmittel | braucht ein Bild |

**Magazin-Cover:** Sobald der Effekt gewählt ist, erscheint eine Maske —
**Titel**, Zeile darunter, Artikel (je Zeile einer, der erste wird die große
Schlagzeile), Ausgabe, Preis, Barcode. Ausfüllen lohnt sich: ohne Vorgabe
erfindet das Modell Fantasieschrift, mit Vorgabe schreibt es sauber. Die
Texte werden nicht übersetzt — sie stehen so auf dem Heft, wie man sie tippt.

**Explosionszeichnung und CAD-Modell** aus einem Foto heraus funktionieren
nicht: das Modell bleibt beim Foto und stellt höchstens frei. Deshalb beide
in **Text→Bild** benutzen — Gegenstand in den Prompt, Effekt wählen. Beim CAD
werden Farbwörter („gold“, „blau“) automatisch aus dem Prompt genommen, sonst
bleibt das Modell farbig. Aus dem Reiter **Sechs Seiten** heraus geschieht
das mit einem Klick (Stufe 4).

---

## 5. Gruppe und Rundum

**Gruppe** — drei Aufgaben:

| Aufgabe | Bilder |
|---|---|
| aus Einzelbildern zusammenstellen | je ein Bild pro Person |
| Person ergänzen | erstes Bild = Gruppenfoto, danach je eines pro neuer Person; **Anzahl der Personen auf dem Foto** angeben |
| Person entfernen | das Gruppenfoto; im Prompt sagen, wer weg soll („die mittlere Person“) |

Jedes Referenzbild kann einen eigenen Text bekommen („als Ritter“). Unter
**Inszenierung** gibt es 12 fertige Looks für die ganze Gruppe.

**Rundum** — ein Bild einer Person; die Serie fliegt einmal um sie herum
(vorne, Seite, hinten, oben, unten). Derselbe Seed ist dabei voreingestellt,
das hält Kleidung und Umgebung stabil.

---

## 6. Varianten

Ein Basisbild vielfach abwandeln — für Abwechslung oder für Trainingsdaten.

1. Reiter **Varianten**, ein **Basisbild** hochladen.
2. **Motivart** wählen: *Fahrzeug*, *Gegenstand* oder *Person*. Davon hängt
   ab, welche Umgebungen und Blickwinkel angeboten werden.
3. **Was muss unverändert bleiben?** — das Wichtigste im Bild, auf Englisch
   oder Deutsch, z. B. „The black tow hitch with the ball neck“.
4. Jede **Achse** (Farbe, Farbstimmung, Stil, Umgebung, Licht, Kameraart,
   Blickwinkel, Werkstoff; bei Personen Haltung und Kleidung) steht auf
   **würfeln**, **–** (unverändert) oder einem festen Wert.
5. **Serie variieren: Varianten**, Anzahl wählen, **Erzeugen**.

**Achtung bei „alles würfeln“:** Bei Fahrzeug und Gegenstand würfelt es
inzwischen nur noch, was zur Motivart passt. Früher kamen dabei auch
Körperhaltung, Kleidung und Personenkameras ins Spiel — und plötzlich standen
Menschen im Bild.

**Für Trainingsdaten empfohlen:**

| Feld | Einstellung |
|---|---|
| Serie variieren | Varianten |
| Stil | **Foto** fest — gezeichnete Stile schaden einem Detektor für echte Fotos |
| Blickwinkel / Kameraart | würfeln, wenn die Kamera wandern soll, sonst – |
| Was muss unverändert bleiben | das Objekt, das später erkannt werden soll |

Jeder Varianten-Lauf legt neben die Bilder eine `.jsonl`-Datei mit den
gewürfelten Werten je Bild.

---

## 7. Trainingsdaten für YOLO — die ganze Kette

Ziel: viele abwechslungsreiche Bilder eines Objekts, jedes mit einer
**Bounding Box**, und daraus ein **YOLO-Detektor**. Beispiel: eine
Anhängerkupplung.

```
 Basisbild ──► Varianten ──► Box suchen ──► Datensatz prüfen ──► YOLO trainieren ──► am Foto testen
                (Reiter       (automatisch)   (Reiter              (Reiter
                Varianten)                    Datensatz)            Training)
```

### Schritt 1 — Projekt anlegen

Kopfzeile → *+ neu*, z. B. „training“. Alles Weitere landet in
`projekte/training/`.

### Schritt 2 — Bilder erzeugen, mit Box

1. Reiter **Varianten** einstellen wie in [Abschnitt 6](#6-varianten).
2. Im Kasten **Trainingsdaten** den Haken **Bounding Box suchen und in den
   Datensatz legen** setzen.
3. **Klasse** — der Name im Datensatz, klein und ohne Leerzeichen:
   `anhaengerkupplung`.
4. **Suchbegriff (englisch)** — wonach die Erkenner suchen: `tow hitch`.
5. **Erzeugen.**

Nach dem Rechnen schauen zwei Modelle auf jedes Bild:

- **Qwen3-VL** setzt die Box.
- **Grounding DINO** prüft gegen.

Sind sich beide einig, ist das Bild **aufgenommen**. Sonst kommt es auf die
**Prüfliste**. Die Statuszeile meldet am Ende z. B. „Datensatz: 4
aufgenommen, 1 zu prüfen“. Die Box-Modelle laden einmal pro Auftrag
(~1 Minute) und brauchen dann gut eine Sekunde je Bild.

Der Haken funktioniert auch in Text→Bild und Bearbeiten.

### Schritt 3 — Prüfliste abarbeiten

Reiter **Datensatz**, oben die Zahlen, darunter die Bilder:

- **rote Box** = geht ins Label,
- **gelb gestrichelt** = was Grounding DINO gefunden hat,
- darunter der Grund, warum das Bild geprüft werden soll.

| Aktion | Wie |
|---|---|
| Box stimmt | **✓ aufnehmen** |
| Box falsch | mit der Maus **eine neue Box über das Bild ziehen** (grün), dann **✓ aufnehmen** |
| Bild unbrauchbar | **✗ verwerfen** (wird verschoben, nicht gelöscht) |
| doch noch einmal ansehen | **zurück auf prüfen** |

Über **Zeigen** wechselt man zwischen *zu prüfen*, *aufgenommen* und
*verworfen* — auch aufgenommene Bilder lassen sich so noch korrigieren.

**Wichtig:** nur aufgenommene Bilder gehen ins Training. Bilder ohne Box
liegen bewusst nicht dort, wo YOLO sucht — ein Bild ohne Label hieße für YOLO
„hier ist keine Kupplung“.

### Schritt 4 — YOLO trainieren

Reiter **Training**. Die Einstellungen stehen als Tabelle:

| Feld | Empfehlung |
|---|---|
| Modell | **yolo11n** (Nano) zum Anfangen; Small/Medium erst ab einigen hundert Bildern |
| Epochen | 50–100 |
| Bildgröße | 640; **960**, wenn das Objekt klein im Bild ist |
| Validierung | 20 % — dieser Teil wird nicht trainiert, nur gemessen |

Dann der große Knopf **YOLO trainieren**. Das Training reiht sich in die
Warteschlange ein (es braucht die Grafikkarte); die Statuszeile zeigt Epoche
und mAP50.

Bilder aus demselben Auftrag bleiben bei der Aufteilung zusammen — sonst
erkennt YOLO in der Validierung nur den Nachbarn aus derselben Serie wieder
und die Zahlen wären geschönt.

**Die Ergebnistabelle** zeigt je Lauf:

| Spalte | Bedeutung |
|---|---|
| Präzision | wie oft eine gemeldete Box stimmt |
| Trefferquote | wie viele Objekte gefunden werden |
| **mAP50** | die übliche Hauptzahl — 1,0 hieße alles gefunden und richtig umrandet |
| mAP50-95 | strenger: verlangt auch genau sitzende Ränder |

**Kurven** klappt Lernkurven, Vorhersagen auf den Validierungsbildern und die
Konfusionsmatrix auf.

### Schritt 5 — am Foto ausprobieren

Unter **Ausprobieren** einen Lauf wählen, die **Mindestsicherheit** setzen
(0,25 ist üblich) und ein Foto hochladen — am besten ein **echtes**. Die
gefundenen Boxen erscheinen im Bild. Das läuft auf dem Prozessor und geht
deshalb auch, während die Grafikkarte rechnet.

### Das fertige Modell außerhalb nutzen

Die Gewichte liegen unter `projekte/<Projekt>/yolo/<Lauf>/weights/best.pt`:

```bash
./yolo_umgebung/bin/yolo detect predict model=projekte/training/yolo/<Lauf>/weights/best.pt source=foto.jpg
```

Der Datensatz selbst liegt in `projekte/<Projekt>/datensatz/` und ist
**YOLO- und COCO-Format** zugleich:

| Datei | Inhalt |
|---|---|
| `images/`, `labels/` | Bilder und YOLO-Labels (je Bild eine `.txt`) |
| `data.yaml` | Klassenliste für Ultralytics |
| `train.txt`, `val.txt`, `yolo.yaml` | die Aufteilung des letzten Trainings |
| `annotations.json` | dasselbe im COCO-Format |
| `pruefen/`, `verworfen/` | Bilder, die (noch) nicht im Training sind |
| `eintraege.json` | je Bild: Box, Status, Gründe, Prompt, gewürfelte Werte |

### Damit das Modell etwas taugt

- **Menge:** einige hundert aufgenommene Bilder sind ein vernünftiges Ziel.
  Mit einer Handvoll prüft man nur, ob die Kette läuft.
- **Echte Fotos zum Testen.** Die eigentliche Frage ist, ob ein Modell aus
  erzeugten Bildern echte Objekte findet.
- **Abwechslung:** Kamera, Licht, Umgebung würfeln lassen — aber Stil auf
  Foto.

---

## 8. Sechs Seiten eines Gegenstands

Ein Gegenstand sechsmal gerade von einer Seite, frei schwebend, wie in einem
Teilekatalog. Vier Stufen:

1. **Beschreiben und erstes Bild.** Oben den Gegenstand auf Deutsch
   beschreiben (oder einen Baustein der Art *Gegenstand* wählen), Stil wählen,
   **Erstes Bild erzeugen**. Es zeigt den Gegenstand schräg von vorn oben —
   ein Bild statt sechs, um zu sehen, ob er so aussieht wie gedacht. Wenn
   nicht: Beschreibung ändern, noch einmal.
2. **Prompts schreiben lassen.** Das Sprachmodell schreibt zu genau dem
   Gegenstand im ersten Bild, was jede Seite zeigt, und füllt das Feld.
   **Durchlesen und korrigieren** — das kleine Sprachmodell irrt sich gern
   (es setzt z. B. eine Antenne unten an, die oben sitzt).
3. **Sechs Seiten erzeugen** — in denselben Katalogeintrag, mit dem Seed des
   ersten Bildes.
4. **Effekte:** Magazin-Cover (aus dem ersten Bild, A4), Explosionszeichnung
   und CAD-Modell (aus dem Prompt), Bauplan, Lifestyle, Rundum. Ein Klick
   stellt alles in den passenden Reiter; dort nachstellen und erzeugen.

Der große Knopf macht jeweils die nächste Rechnung. Oben steht, welcher
Gegenstand gerade **in Arbeit** ist; *neuen Gegenstand anfangen* setzt das
zurück. Ältere Einträge holt **hiermit weitermachen** im Katalog unten
zurück.

**Befehle im Beschreibungsfeld** (je am Zeilenanfang):

| Befehl | Wirkung |
|---|---|
| `/hintergrund ein tiefschwarzer Sternenhimmel` | ersetzt das neutrale Grau |
| `/oben die goldene Oberseite füllt die Mitte` | was diese Ansicht zeigt (ebenso `/vorne`, `/hinten`, `/links`, `/rechts`, `/unten`) |
| `/-unten Antenne, Düsen` | streicht diese Wörter aus dem Prompt **dieser** Ansicht |
| `/- Kabel` | streicht für alle sechs |

Was nicht zu sehen sein soll, gehört hinter `/-` — nicht als „die Antenne ist
verdeckt“ in den Text: das Modell malt, was dasteht, und überliest die
Verneinung.

Die Bilder liegen in `katalog/<Projekt>/<Eintrag>/` — nicht in `outputs/`, damit
sie beim Aufräumen nicht verschwinden.

---

## 9. Bausteine, Szenen, Katalog

**Bausteine** — Personen, Orte und Gegenstände mit Namen, Bild und Prompt
zum Wiederverwenden. Auf Deutsch beschreiben; das Sprachmodell schreibt den
englischen Prompt und setzt, was sich ändern darf, in geschweifte Klammern:
`a woman in her thirties, wearing {kleidung}`.

**Szenen** — Bausteine anhaken, Lücken füllen, erzeugen. Mehrere Zeilen in
einem Lückenfeld ergeben eine Serie (dieselbe Person in vier Jacken). Das
Ergebnis lässt sich als Szene merken und wiederholen.

**Katalog** — alle Bausteine aus allen Projekten, nach Art und Text
durchsuchbar. Von dort in ein anderes Projekt kopieren. Unter *Noch anzulegen*
stehen Namen, die eine Geschichte verlangt, die es aber noch nicht gibt.

---

## 10. Geschichten und Abläufe

**Geschichte** in vier Schritten:

1. **Umreißen** — eine Idee genügt; das Sprachmodell schreibt Kurzfassung,
   Stil und Inhaltsverzeichnis. Der Regler **Fiktion 0–100 %** sagt, wie
   wirklich es zugehen soll.
2. **Gliedern** — je Zeile eine Szene. `/Name` holt einen Baustein,
   `\augen`, `\spiegel`, `\scheibe`, `\decke`, `\bettlage`, `\raus` eine
   besondere Kameraeinstellung (`\augen(das brennende Deck)` füllt, was sich
   spiegelt).
3. **Schreiben lassen** — die Prompts entstehen der Reihe nach mit dem großen
   Sprachmodell; optional auch Prosa.
4. **Erzeugen** — in den Ablauf übernehmen oder gleich Bilder und Video.

Mit *+ Band* geht eine Geschichte weiter und kennt die vorigen Bände.

**Ablauf** — eine Bildfolge, aus der ein Video mit Überblendungen entsteht.
Startbild hochladen, einen der mitgelieferten Abläufe wählen (Bogen, Reise,
Klassisch, Zeitreise, Comicheft, Neonstadt, Elemente) oder Blöcke selbst
zusammenstellen, starten. Der Ablauf passt sich dem Startbild an (wer zu
sehen ist, wird in jeder Anweisung genannt).

---

## 11. Freitext: einfach sagen, was man will

Oben im Bedienfeld ein Satz auf Deutsch: „ein rotes Auto im Wald“, dann
**→** (oder **Strg+Eingabe**). Das Sprachmodell übersetzt und stellt die
Regler ein — **es erzeugt noch kein Bild**: erst prüfen, dann selbst auf
Erzeugen.

Das Gespräch hat ein Gedächtnis: „mach es hochkant“ → „jetzt als Comic“ →
„davon sechs Stück“ ändert jeweils genau eine Sache. *neu anfangen* vergisst
den Verlauf.

---

## 12. Galerie, Noten, Video, GIMP

**Galerie** — zeigt die Bilder des aktiven Projekts. Unter dem angezeigten
Bild: **fünf Sterne**, ein **Name** und eine **Notiz** (gespeichert in
`projekte/<Projekt>/bewertung.json`). Ein benanntes Bild merkt sich seinen
Prompt; `\name` holt ihn in einer Szene zurück.

**Video zusammenstellen** — in der Galerie anklicken, Bilder in der
gewünschten Reihenfolge wählen, Gesamtdauer eintragen.

**GIMP** — einmalig `./gimp/install.sh`, GIMP neu starten. Menü
**Filter › Qwen**: Text zu Bild, Bild bearbeiten, Hintergrund entfernen. Eine
**Auswahl in GIMP wird zur Maske**: die Änderung wirkt nur dort. Unter jedem
Bild in der Weboberfläche öffnet **In GIMP öffnen** genau dieses Bild (nur am
Rechner des Servers).

---

## 13. Cloud-Modelle

Kopfzeile → **Cloud-Modelle**. Sprachmodell und Bildmodell lassen sich
**getrennt** auf einen Anbieter im Internet umstellen. Jede Schnittstelle, die
OpenAI spricht, geht: OpenAI, OpenRouter, Mistral, DeepSeek, Together, ein
eigenes vLLM …

| Feld | Beispiel |
|---|---|
| Cloud statt lokal | Haken setzen |
| Basisadresse | `https://api.openai.com/v1` (mit `/v1`) |
| Modell | Sprache z. B. `gpt-4.1-mini`, Bild z. B. `gpt-image-1` |
| API-Schlüssel | einmal eintragen; leer lassen behält den hinterlegten |
| Bildgröße (nur Bild) | *genau wie lokal*; bei OpenAI-Bildmodellen *nächstes OpenAI-Format* |

**Speichern**, dann **Verbindung prüfen**. Ist ein Platz aktiv, steht in der
Kopfzeile z. B. „Cloud: Sprache + Bild“.

Gut zu wissen:

- Der Schlüssel liegt in `einstellungen.json` neben dem Programm, nur für dich
  lesbar und **nicht** im Repository. An die Seite geht er nie zurück.
- Einstellen lässt sich das nur am Rechner des Servers, nicht übers Netz.
- **Cloud-Bilder kosten Geld** und sind nicht wiederholbar: Seed und
  „Was nicht ins Bild soll … auch dem Modell ausreden“ wirken dort nicht.
- Die Box-Erkennung für Trainingsdaten und das YOLO-Training laufen immer
  lokal.

---

## 14. Projekte und wo was liegt

Jedes Vorhaben ist ein **Projekt** mit eigener Ablage. Ein Auftrag merkt sich
beim Einreihen sein Projekt — wer zwischendurch umschaltet, findet die Bilder
trotzdem am richtigen Ort.

| Ort | Inhalt |
|---|---|
| `outputs/` | Bilder des Projekts **Allgemein** |
| `projekte/<Projekt>/bilder/` | Bilder aller anderen Projekte |
| `projekte/<Projekt>/datensatz/` | Trainingsdaten (YOLO + COCO) |
| `projekte/<Projekt>/yolo/` | YOLO-Läufe mit Gewichten und Kurven |
| `projekte/<Projekt>/geschichten/` | Geschichten als JSON |
| `projekte/<Projekt>/bewertung.json` | Sterne, Namen, Notizen |
| `katalog/<Projekt>/` | Sechs-Seiten-Ansichten |
| `einstellungen.json` | Cloud-Zugänge (privat) |
| `yolo_umgebung/` | Ultralytics, eigene Python-Umgebung |

Jedes Bild trägt seinen **Prompt und Seed im PNG** — auch nach Jahren lässt
sich nachsehen, wie es entstanden ist.

**Löschen ist endgültig** — es gibt keinen Papierkorb. Verworfene
Datensatzbilder werden nur verschoben, nicht gelöscht.

---

## 15. Wenn etwas nicht klappt

**`OSError: [Errno 98] Address already in use` beim Start**
Es läuft schon ein Server — oft ein verwaister, nachdem das Terminal
geschlossen wurde. Entweder einfach `http://127.0.0.1:7860` öffnen, oder ihn
beenden und neu starten:

```bash
ss -ltnp | grep 7860          # zeigt die Prozessnummer (pid=…)
kill <pid> && ./start.sh
```

**Plötzlich Menschen in Varianten-Bildern**
„Serie variieren“ stand auf *alles würfeln* und hat Körperhaltung, Kleidung
und Personenkameras mitgewürfelt. Ist behoben (siehe Abschnitt 6); für
Trainingsdaten trotzdem **Varianten** wählen.

**`/hintergrund` wirkt nicht**
Ein einzelnes deutsches Wort („Sternenhimmel“) wurde früher nicht als Deutsch
erkannt und nicht übersetzt; außerdem brachten manche Stile ihre eigene
Kulisse mit. Beides ist behoben. Hilft es dennoch nicht: den Hintergrund
ausführlicher beschreiben („ein tiefschwarzer Sternenhimmel mit feinen
Sternen“).

**Explosionszeichnung oder CAD sieht aus wie das Foto**
Im Reiter Bearbeiten wirken beide nicht. In **Text→Bild** benutzen (siehe
Abschnitt 4).

**Ein Auftrag bricht mit „CUDA out of memory“ ab**
Läuft ein zweiter Server oder ein anderes Programm auf der Grafikkarte?
`nvidia-smi` zeigt es. Immer nur eine Instanz.

**Das Sprachmodell liefert Unsinn**
Das kleine lokale Modell (`qwen3.5:4b`) übersetzt mehrdeutige Wörter
manchmal falsch („Anhänger“ → *pendant*) und irrt sich bei Seitenansichten.
Vorschläge vor dem Rechnen lesen und korrigieren — oder unter
[Cloud-Modelle](#13-cloud-modelle) ein größeres Sprachmodell eintragen.

**Datensatz: viele Bilder auf der Prüfliste**
Meist ist der Suchbegriff zu allgemein oder zu speziell. Englisch und so, wie
man das Objekt einem Fremden nennen würde: `tow hitch`, nicht
`anhaengerkupplung` oder `ball neck with socket`.

**YOLO-Werte nahe null**
Zu wenige Bilder. Mit unter 50 aufgenommenen Bildern lernt YOLO nichts
Brauchbares.

**Oben erscheint ein Balken „Der Server läuft noch mit älterem Code“**
Das Programm wurde geändert, der Server läuft noch mit dem alten Stand:
neu starten.
