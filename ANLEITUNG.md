# Bedienungsanleitung

Diese Anleitung erklärt, **wie man mit dem Programm arbeitet** — Schritt für
Schritt, nach Aufgaben geordnet. Wie es innen gebaut ist und warum, steht in
der [README](README.md).

**Inhalt**

1. [Starten und beenden](#1-starten-und-beenden)
2. [Die Oberfläche auf einen Blick](#2-die-oberfläche-auf-einen-blick)
3. [Das erste Bild: Text → Bild](#3-das-erste-bild-text--bild)
4. [Bilder bearbeiten, Effekte, Retusche](#4-bilder-bearbeiten-effekte-retusche)
5. [Gruppe und Rundum](#5-gruppe-und-rundum)
6. [Varianten](#6-varianten)
7. [Trainingsdaten und eigener Detektor — die ganze Kette](#7-trainingsdaten-und-eigener-detektor--die-ganze-kette)
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

**Unter Windows:** den Ordner von GitHub herunterladen und entpacken, einmal
**`einrichten.bat`** doppelklicken (lädt Python, Pakete und Modelle in diesen
Ordner, ohne Installation), danach **`start.bat`**. Der Ordner ist dann
portabel — kopieren genügt. Für einen Rechner, auf dem nur trainiert wird
(etwa ein Notebook mit RTX 1000 Ada), reicht `einrichten.bat training`;
siehe die Tabelle im README. Einstellungen nur für diesen Rechner — etwa
`set QWEN_HOST=0.0.0.0` — gehören in eine Datei `lokal.bat` daneben;
`start.bat` liest sie mit.

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
| Fotodaten | aus echten Fotos Varianten nach Plan, gleich mit Box im Datensatz |
| Retusche | eine Stelle nachbessern: Fleck, schiefes Lächeln, Hand |
| Ablauf | eine Bildfolge mit Video |
| Bausteine | Personen, Orte, Gegenstände zum Wiederverwenden |
| Szenen | Bausteine zu einem Bild zusammenstellen |
| Geschichte | eine Handlung in Szenen, Prompts und Bilder |
| Katalog | alle Bausteine aus allen Projekten |
| Sechs Seiten | ein Gegenstand von vorn, hinten, links, rechts, oben, unten |
| Datensatz | Bounding Boxes prüfen, aufnehmen, korrigieren |
| Training | einen Detektor (D-FINE oder YOLO26) trainieren und ausprobieren |

**Der große Knopf unten** startet, was der Reiter verspricht. Seine
Beschriftung sagt es jeweils („Erzeugen“, „Erstes Bild erzeugen“,
„Detektor trainieren“ …).

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
| Porträt | Kameraposition der Reihe nach, dazu je eine Porträtbelichtung und ein Fotostil — nur echte Fotos |
| alles würfeln | jedes offene Feld zufällig |

**Porträtserie.** Für Bildnisse einer Person. Im Prompt nur die Person
beschreiben („eine Frau Mitte vierzig mit kurzen grauen Haaren“), dann
*Serie variieren: Porträt*. Die Anzahl springt auf 13, einmal durch alle
Kamerapositionen:

- **Kameraposition:** Kopf und Schultern, Großaufnahme, dreiviertel
  gedreht, Brustbild, Profil, leicht von oben, Halbtotale, Blick über die
  Schulter, leicht von unten, ab Knie, im Umfeld, unbeobachtet, Ganzkörper.
- **Belichtung:** Rembrandt, Schmetterling, Loop, geteiltes Licht,
  Beauty-Licht, Fensterlicht, High Key, Low Key, Kantenlicht, goldene
  Stunde, offener Schatten, bewölkt.
- **Fotostil:** Studio, Editorial, Business, Schwarzweiß Fine Art,
  Farbfilm (Portra), SW-Film (HP5), Mittelformat, Reportage, Lifestyle,
  Straßenporträt, Filmstill.

Belichtung und Stil werden gemischt, jeder Eintrag kommt einmal dran, bevor
sich einer wiederholt. Dieselbe Seed-Zahl ergibt dieselbe Mischung. Stil,
Licht und Kamera aus *Darstellung* gelten in dieser Serie nicht. An jeden
Prompt wird angehängt, dass ein echtes Foto mit natürlicher Hautstruktur
entstehen soll, keine Zeichnung und kein 3D-Rendering. Mit **gleicher Seed**
bleibt die Person über die Serie hinweg ähnlicher. Im Bearbeiten-Modus mit
einem Foto als Referenz geht es auch. Welche Position, Belichtung und welcher
Stil ein Bild bekam, steht in der PNG-Datei (`qwen_position`,
`qwen_belichtung`, `qwen_look`).

**Kurzbefehle** lassen sich direkt in den Prompt tippen und stellen die
Regler selbst um, z. B. `/magazine cover`, `/ptexplosion`, `/cad`,
`/blueprint`, `/remove bg`.

**Rückweg: Prompt aus einem Bild.** Unter „…oder umgekehrt“ ein Bild wählen —
das Sprachmodell beschreibt es als Prompt und stellt Stil, Licht und Objektiv
passend ein.

---

## 4. Bilder bearbeiten, Effekte, Retusche

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

### Retusche: eine Stelle nachbessern

Ein roter Fleck unter der Nase, ein schiefes Lächeln, eine Hand mit sechs
Fingern: dafür ist der Reiter **Retusche** da. Das ganze Bild noch einmal
bearbeiten lassen hilft hier selten, denn das Modell kennt keine Maske und
zeichnet dabei alles neu, auch das Gesicht. Und das Prompt-Feld allein
reicht nicht: „Fleck entfernen“ verstehen die Modelle, doch je kleiner das
Gesicht im Bild ist, desto ungenauer arbeiten sie dort.

1. Unter dem großen Bild auf **Retuschieren** klicken (oder im Reiter ein
   Bild hochladen).
2. Die Stelle **mit dem Pinsel übermalen**. Radierer, „Strich zurück“
   (Strg+Z) und „Maske leeren“ stehen darunter.
3. Sagen, was dort anders sein soll, oder eine Schnellwahl anklicken:
   *Haut glätten, Fleck weg* · *Lächeln gerade* · *Augen klar* ·
   *Hand richtig* · *Gegenstand entfernen*.
4. **Retuschieren.**

Was dabei geschieht: Um die Maske wird ein Ausschnitt gelegt (gestrichelt
angezeigt), und nur dieser geht ins Modell, in voller Auflösung. Ein Mund,
der im Ganzkörperbild 80 Pixel breit ist, bekommt so rund tausend. Das
Ergebnis wird zurückverkleinert, in der Farbe angeglichen und nur innerhalb
der Maske mit weicher Kante eingesetzt. Alles außerhalb bleibt pixelgenau.

- **Versuche**: mehrere Seeds in einem Ladevorgang, den besten aussuchen.
- **Umgebung**: eng gibt der Stelle mehr Auflösung, weit dem Modell mehr
  Zusammenhang. Für ein Lächeln das ganze Gesicht in den Ausschnitt nehmen.
- **Weiche Kante**: sieht man eine Naht, den Wert erhöhen.
- **Schritte** und **Negativ-Prompt** kommen aus der Feineinstellung
  darunter, wie bei den anderen Reitern.
- Das Ergebnis heißt `…_retusche_…png`. Das Original bleibt erhalten und
  steht in den Bilddaten unter `qwen_quelle`. Wer weiter verbessern will,
  klickt beim Ergebnis wieder auf **Retuschieren**.

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

## 7. Trainingsdaten und eigener Detektor — die ganze Kette

Ziel: viele abwechslungsreiche Bilder eines Objekts, jedes mit einer
**Bounding Box**, und daraus ein **Detektor**, der das Objekt in echten Fotos
findet. Beispiel: eine Anhängerkupplung.

Trainiert wird **D-FINE** — ein Echtzeit-Detektor in der Klasse von YOLO,
aber unter **Apache 2.0**: das Modell *und* die damit trainierten Gewichte
dürfen frei weitergegeben und auch kommerziell genutzt werden. (Ultralytics
YOLO steht unter AGPL-3.0, und Ultralytics zählt trainierte Gewichte mit
dazu.) Der Datensatz wird trotzdem auch im YOLO-Format abgelegt — wer mag,
kann ihn mit jedem Werkzeug weiterverwenden.

**Aus eigenen Fotos geht es kürzer:** der Reiter **Fotodaten** erledigt
Schritt 2 für echte Fotos in einem Zug — siehe [7a](#7a-trainingsdaten-aus-echten-fotos).
Trainieren lässt sich außer D-FINE auch **YOLO26** (Schritt 4).

```
 Basisbild ──► Varianten ──► Box suchen ──► Datensatz prüfen ──► Vervielfältigen ──► Detektor trainieren ──► am Foto testen
                (Reiter       (automatisch)   (Reiter              (Reiter Datensatz,   (Reiter
                Varianten)                    Datensatz)            optional)            Training)
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

Über **Zeigen** wechselt man zwischen *zu prüfen*, *aufgenommen*,
*vervielfältigt* und *verworfen* — auch aufgenommene Bilder lassen sich so noch korrigieren.

**Wichtig:** nur aufgenommene Bilder gehen ins Training. Bilder ohne Box
liegen bewusst nicht im Trainingsordner — ein Bild ohne Label hieße dort
„hier ist keine Kupplung“.

### Schritt 3½ — Vervielfältigen (optional)

Aus wenigen geprüften Bildern viele machen, **ohne neue Box**: Es wird nur
so verändert, dass man weiß, wohin die Box wandert. Unten im Reiter
**Datensatz**, Abschnitt **Vervielfältigen**:

| Verfahren | Was es tut | Braucht |
|---|---|---|
| **Klassisch** | spiegeln, hineinzoomen, Helligkeit, Kontrast, Farbe, Unschärfe, Rauschen, JPEG | nur CPU, sehr schnell |
| **Neue Umgebung** | Stable Diffusion 1.5 + ControlNet: die Umrisse bleiben, Umgebung, Licht und Oberflächen wechseln | ab 4 GB Grafikkarte; beim ersten Mal ~3 GB Download |

- **Neue Bilder je Vorlage**: wie viele aus jedem aufgenommenen Bild werden.
- **Umgebungen**: eine je Zeile, zufällig gewählt. Vorbefüllt mit den
  Umgebungen aus dem Varianten-Katalog (Fahrzeug, Gegenstand, Person).
- **Veränderung**: wenig hält sich eng ans Basisbild, viel wechselt mehr,
  verschiebt aber auch eher die Umrisse.
- **Gegenstand unverändert lassen**: Der Gegenstand wird nach dem Rechnen
  aus dem Original zurückgesetzt, nur das Drumherum wechselt. Ausschalten,
  wenn der Gegenstand selbst auch anders aussehen darf (Farbe, Rost …).
- **spiegeln erlaubt**: ausschalten bei Schrift oder Teilen, die es nur
  seitenrichtig gibt.

Die Ergebnisse heißen wie ihre Vorlage plus `_mehr01`, `_mehr02` … und
stehen unter **Zeigen › vervielfältigt**. Beim Training landen sie immer auf
derselben Seite wie ihre Vorlage, damit die Validierung nicht schöngerechnet
wird. **Ändert sich später die Box einer Vorlage** oder wird sie verworfen,
werden ihre Abkömmlinge verworfen (nicht gelöscht). Danach einfach neu
vervielfältigen.

Gemessen auf der RTX 3090: klassisch Bruchteile einer Sekunde je Bild, neue
Umgebung 3–4 s. Auf einer kleinen Karte siehe unten.

### Mit kleiner Grafikkarte (ab 4 GB)

Qwen-Image selbst braucht ~17 GB und läuft auf einer kleinen Karte nicht.
Die Kette geht trotzdem, aufgeteilt:

1. **Basisbilder aus der Cloud.** Kopfzeile › **Cloud-Modelle** ›
   Bildmodell eintragen und „Cloud statt lokal“ anhaken. Dann wie in
   Schritt 2 mit **Varianten** und Haken bei **Trainingsdaten** —
   20 bis 50 Bilder aus verschiedenen Blickwinkeln reichen.
2. **Boxen lokal.** Das Programm erkennt die kleine Karte (unter 8 GB) und
   rechnet in **zwei Phasen**: erst Qwen3-VL für alle Bilder auf der Karte,
   dann wird sie geleert und Grounding DINO läuft über dieselben Bilder. So
   liegen nie beide zugleich auf der Karte, und eine 6-GB-Karte reicht.
   Erst unter 5 GB rechnet Qwen3-VL auf der CPU (rund anderthalb Minuten je
   Bild). Große Fotos sehen die Erkenner höchstens 1280 px groß.
3. **Prüfen** wie in Schritt 3.
4. **Lokal vervielfältigen** wie oben. SD 1.5 wird dann Schicht für Schicht
   auf die Karte geholt: gemessen 1,3 GB Spitze, auf der 3090 ~18 s je Bild,
   auf einer kleinen Karte entsprechend länger.
5. **Trainieren**: D-FINE *nano* oder *small*, oder **YOLO26 n/s** —
   beide gehen auf 6 GB.

Das alles ohne Installation: die **portable Fassung**
(`python portable\bauen.py <Ziel> --ausbau --modelle`) bringt Python,
PyTorch und die Box-Modelle in einem Ordner mit; das Bildmodell kommt dort
immer aus der Cloud.

Die Vielfalt der Blickwinkel kommt so vom großen Modell, die Menge vom
eigenen Rechner. `QWEN_BOX_GERAET=cpu` bzw. `cuda` legt fest, wo Qwen3-VL
rechnet, unabhängig von der Kartengröße.

### Schritt 4 — Detektor trainieren

Reiter **Training**. Die Einstellungen stehen als Tabelle:

| Feld | Empfehlung |
|---|---|
| Modell | **dfine-nano** oder **yolo26n** zum Anfangen; Small/Medium erst ab einigen hundert Bildern |
| Epochen | 50–100 (Vorgabe 80) |
| Bildgröße | 640; **960**, wenn das Objekt klein im Bild ist |
| Validierung | 20 % — dieser Teil wird nicht trainiert, nur gemessen |

Dann der große Knopf **Detektor trainieren**. Das Training reiht sich in die
Warteschlange ein (es braucht die Grafikkarte); die Statuszeile zeigt Epoche
und mAP50.

Bilder aus demselben Auftrag bleiben bei der Aufteilung zusammen — sonst
erkennt das Modell in der Validierung nur den Nachbarn aus derselben Serie wieder
und die Zahlen wären geschönt.

**Die Ergebnistabelle** zeigt je Lauf:

| Spalte | Bedeutung |
|---|---|
| Bilder | Training / Validierung |
| Präzision | wie oft eine gemeldete Box stimmt |
| Trefferquote | wie viele Objekte gefunden werden |
| **mAP50** | die übliche Hauptzahl — 1,0 hieße alles gefunden und richtig umrandet |
| mAP50-95 | strenger: verlangt auch genau sitzende Ränder |

Präzision und Trefferquote werden an der Sicherheitsschwelle gemessen, bei
der beide zusammen am besten sind. **Kurve** klappt die Lernkurve (mAP je
Epoche) und vier Validierungsbilder auf: grün die Wahrheit, rot die
Vorhersage.

**Zu wenige Epochen** erkennt man an den Beispielbildern: das Modell meldet
dann noch, was es aus seinem Vortraining kennt — Kennzeichen, Rücklichter —
statt der Kupplung.

**YOLO26** steht in derselben Liste (`yolo26n`, `yolo26s`, `yolo26m`) —
Ultralytics muss dafür installiert sein (`installieren.bat yolo` bzw.
`requirements-yolo.txt`). Die Stapelgröße wählt es selbst nach dem freien
Grafikspeicher; auf einer 6-GB-Karte gehen n und s bequem. Die Gewichte
liegen danach als `gewichte\best.pt`, dazu Ultralytics' eigene Bilder
(`val_batch0_pred.jpg`, `results.png`) im Lauf. **Lizenz:** AGPL-3.0, und
Ultralytics zählt die trainierten Gewichte dazu — für eigene Versuche
gleichgültig, für ein weitergegebenes Modell nicht. Dann lieber D-FINE.

**Training auf einem zweiten Rechner.** Erzeugen und Labeln auf dem einen
Rechner (oder per Cloud), Trainieren auf einem anderen — etwa einem Notebook
mit RTX 1000 Ada (6 GB), eingerichtet mit `einrichten.bat training`:

1. Auf dem ersten Rechner den ganzen Projektordner kopieren:
   `projekte\<Projekt>\` (darin `projekt.json` und `datensatz\`).
2. Auf dem Trainingsrechner nach `projekte\` legen und `start.bat` starten.
3. Kopfzeile › Projekt wählen, Reiter **Training**, `yolo26n` oder
   `yolo26s`, Bildgröße 640.

Gemessen bei 640 px: yolo26n mit Stapel 16 und yolo26s mit Stapel 8 belegen
je rund 2,8 GB — auf 6 GB bleibt Luft. Bei 960 px wählt Ultralytics auf einer
6-GB-Karte von selbst einen kleineren Stapel. Die Gewichte liegen danach
unter `projekte\<Projekt>\detektor\<Lauf>\gewichteest.pt`.

### Schritt 5 — am Foto ausprobieren

Unter **Ausprobieren** einen Lauf wählen, die **Mindestsicherheit** setzen
(0,25 ist üblich) und ein Foto hochladen — am besten ein **echtes**. Die
gefundenen Boxen erscheinen im Bild. Das läuft auf dem Prozessor und geht
deshalb auch, während die Grafikkarte rechnet.

### Das fertige Modell außerhalb nutzen

Das trainierte Modell liegt unter `projekte/<Projekt>/detektor/<Lauf>/gewichte/`
im Hugging-Face-Format und lässt sich mit `transformers` laden:

```python
from transformers import AutoImageProcessor, AutoModelForObjectDetection
from PIL import Image

ordner = "projekte/training/detektor/<Lauf>/gewichte"
prozessor = AutoImageProcessor.from_pretrained(ordner)
modell = AutoModelForObjectDetection.from_pretrained(ordner)
bild = Image.open("foto.jpg").convert("RGB")
aus = modell(**prozessor(images=bild, return_tensors="pt"))
treffer = prozessor.post_process_object_detection(
    aus, threshold=0.25, target_sizes=[bild.size[::-1]])[0]
print(treffer["boxes"], treffer["scores"])
```

Der Datensatz selbst liegt in `projekte/<Projekt>/datensatz/` und ist
**YOLO- und COCO-Format** zugleich — für jedes andere Werkzeug:

| Datei | Inhalt |
|---|---|
| `images/`, `labels/` | Bilder und Labels im YOLO-Format (je Bild eine `.txt`) |
| `data.yaml` | Klassenliste im YOLO-Format |
| `annotations.json` | dasselbe im COCO-Format |
| `train.txt`, `val.txt` | die Aufteilung des letzten Trainings |
| `pruefen/`, `verworfen/` | Bilder, die (noch) nicht im Training sind |
| `eintraege.json` | je Bild: Box, Status, Gründe, Prompt, gewürfelte Werte |

### Damit das Modell etwas taugt

- **Menge:** einige hundert aufgenommene Bilder sind ein vernünftiges Ziel.
  Mit einer Handvoll prüft man nur, ob die Kette läuft. Vervielfältigen
  bringt Menge, aber keine neuen Blickwinkel; die müssen aus den
  Basisbildern kommen.
- **Echte Fotos zum Testen.** Die eigentliche Frage ist, ob ein Modell aus
  erzeugten Bildern echte Objekte findet.
- **Abwechslung:** Kamera, Licht, Umgebung würfeln lassen — aber Stil auf
  Foto.

---

## 7a. Trainingsdaten aus echten Fotos

Der kurze Weg, wenn es schon Fotos gibt — etwa von einem Auto mit
Anhängerkupplung. Reiter **Fotodaten**:

1. **Fotos** wählen, eines oder viele. Am besten über jedes Objekt mit der
   Maus **eine Box ziehen** (grün). Ein Foto mit Box geht sofort als
   aufgenommen in den Datensatz und ist der Bezug für seine Varianten; ohne
   Box sucht der Erkenner sie wie bei jedem anderen Bild.
2. **Klasse** (`anhaengerkupplung`), **Suchbegriff** (`tow hitch`),
   **Motivart**, und bei der Farbachse, **was umgefärbt wird**
   (`the car body`). Unter **Was unverändert bleiben muss** das Objekt
   selbst — „The black tow hitch with the ball neck and its socket“.
3. **Achsen** anhaken und je Achse die Werte wählen:

   | Achse | ändert |
   |---|---|
   | Farbe | die Farbe des Fahrzeugs (bzw. was oben als Ziel steht) |
   | Untergrund / Umgebung | Schotter, Schnee, Tiefgarage, Waldweg … |
   | Kameraposition | bodennah, schräg von links, erhöht, nah … |
   | Licht | goldene Stunde, Neon, Gegenlicht, Nebel … |
   | Farbstimmung, Kameraart, Werkstoff | wahlweise dazu |

   Nicht angehakte Achsen bleiben wie im Foto. Der Stil steht fest auf Foto.
4. **Plan** wählen:

   | Plan | was entsteht |
   |---|---|
   | einzeln | jede Achse allein, jeder Wert genau einmal — zeigt sauber, was eine Achse tut |
   | kombiniert | alle Achsen zugleich, *Kombinierte je Foto* Bilder; jeder Wert kommt gleich oft dran, keine Kombination doppelt |
   | einzeln und kombiniert | beides hintereinander (Vorgabe) |
   | alle Kombinationen | das volle Kreuzprodukt, höchstens 500 je Foto |

   Unter dem Plan steht, wie viele Bilder das ergibt — bei einem
   Cloud-Bildmodell ist das auch die Zahl der bezahlten Bilder.
5. Großer Knopf **Fotodaten erzeugen**.

Erst rechnet das Bildmodell alle Fotos durch, danach laden die
Box-Erkenner einmal für alles. Am Ende meldet die Statuszeile z. B.
„Datensatz: 24 aufgenommen, 6 zu prüfen“. Weiter wie in Schritt 3
(Prüfliste) und Schritt 4 (Training).

**Gut zu wissen**

- **Handyfotos** werden nach ihrem EXIF-Vermerk aufgerichtet, so wie der
  Browser sie zeigt. Große Fotos werden auf 2048 px verkleinert.
- Original und Varianten eines Fotos heißen `<Zeit>_fotoNN_…` und bleiben
  beim Training **zusammen** in Training oder Validierung.
- **Kameraposition** wirkt schwächer als Farbe und Umgebung: das Bildmodell
  hält sich eng an die Bildaufteilung der Vorlage. Echte Vielfalt im
  Blickwinkel kommt von Fotos aus verschiedenen Winkeln.
- Im Datensatz liegt zusätzlich **`attribute.csv`**: je Bild die Box, ob
  echt oder erzeugt, aus welchem Foto, und jede Achse (Farbe, Untergrund,
  Licht …) — die Merkmal-Labels.

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
Für eine einzelne Stelle ist meist der Reiter **Retusche** bequemer
(Abschnitt 4): Er rechnet den Ausschnitt in voller Auflösung.

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

**Anbieter vorbelegen:** ein Klick auf **franconia.ai** (oder OpenAI) füllt
Adresse, beide Modelle und die Art des Bildmodells aus — danach nur noch den
Schlüssel eintragen. Zeigen beide Plätze auf dieselbe Adresse, reicht der
Schlüssel in einem Feld.

| franconia.ai | |
|---|---|
| Basisadresse | `https://api.franconia.ai/v1` |
| Bildmodell | `Z Image Turbo` |
| Sprachmodell | `Qwen 3.8 27B` |
| Schlüssel | `sk-sovai-…`, im Dashboard unter franconia.ai erstellen |
| Das Modell versteht | **Beschreibungen** |

**Anweisung oder Beschreibung.** Ein Bearbeitungsmodell (gpt-image,
Qwen-Image) versteht „färbe das Auto rot, lass die Kupplung, wie sie ist“.
Z Image Turbo ist ein Text-zu-Bild-Modell und arbeitet mit Vorlage als
**img2img**: es malt die Vorlage nach dem Prompt neu. Steht das Feld auf
*Beschreibungen*, beschreibt das Sprachmodell jedes Foto einmal, und das
Bildmodell bekommt das Zielbild in Worten („a vintage station wagon seen
from behind …, the car body is bright red, standing on a gravel yard“). Die
**Stärke** sagt, wie weit es sich von der Vorlage entfernen darf. Gemessen
mit Z Image Turbo am Auto-Heck: unter 0,7 ändert sich kaum etwas, bei **0,7**
(Vorgabe) wechseln Farbe und Untergrund bei gleichem Aufbau, ab 0,8 wird es
ein anderes Fahrzeug. Von der Fotobeschreibung geht nur der erste Satz mit,
und die Farbe steht vorn — sonst überstimmt die Beschreibung die Farbe.

**Was Z Image Turbo kann und was nicht** (Testlauf, 2 Fotos, 22 Varianten,
rund eine Minute): Schwarz, Silber, Gelb, Schnee und Schotter greifen; Rot
blieb je nach Seed blass; Licht ist nur angedeutet. Die Kameraposition ändert
img2img praktisch nicht — dafür Fotos aus verschiedenen Winkeln mitbringen.
Und: das Modell zeichnet das ganze Bild neu, auch das Objekt. Die Kupplung
sieht danach jedes Mal etwas anders aus, und bei einer Nahaufnahme färbt die
Farbachse die Kupplung selbst um. Die Boxen stimmen trotzdem, sie werden ja
neu gesucht. Wer die Varianten nah am echten Objekt braucht, rechnet sie mit
Qwen-Image auf einer großen Karte (`einrichten.bat lokal`) — das ändert auf
Anweisung nur, was es soll.

Bei franconia.ai gehen **Seed und Schritte** mit, Cloud-Bilder sind dort also
wiederholbar. Vorlagen werden auf Kanten in Vielfachen von 16 gebracht (die
Schnittstelle verlangt das) und höchstens 1536 px groß verschickt.

**Speichern**, dann **Verbindung prüfen**. Ist ein Platz aktiv, steht in der
Kopfzeile z. B. „Cloud: Sprache + Bild“.

Gut zu wissen:

- Der Schlüssel liegt in `einstellungen.json` neben dem Programm, nur für dich
  lesbar und **nicht** im Repository. An die Seite geht er nie zurück.
- Einstellen lässt sich das nur am Rechner des Servers, nicht übers Netz.
- **Cloud-Bilder kosten meist Geld** (franconia.ai ist in der Beta kostenlos,
  100 Anfragen je Minute). Seed und Schritte wirken nur, wo der Anbieter sie
  kennt; „auch dem Modell ausreden“ wirkt in der Cloud nicht.
- Die Box-Erkennung für Trainingsdaten und das Detektor-Training laufen immer
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
| `projekte/<Projekt>/datensatz/` | Trainingsdaten (YOLO- und COCO-Format) |
| `projekte/<Projekt>/detektor/` | Trainingsläufe mit Gewichten und Kennzahlen |
| `projekte/<Projekt>/geschichten/` | Geschichten als JSON |
| `projekte/<Projekt>/bewertung.json` | Sterne, Namen, Notizen |
| `katalog/<Projekt>/` | Sechs-Seiten-Ansichten |
| `einstellungen.json` | Cloud-Zugänge (privat) |

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

Unter Windows heißt die Meldung `[WinError 10048]`:

```bat
netstat -ano | findstr :7860   &rem letzte Spalte ist die Prozessnummer
taskkill /PID <pid> /F
```

**Windows: „Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert“**
Smart App Control oder eine Firmenrichtlinie sperrt `pip.exe`.
`installieren.bat` ruft pip deshalb als `python -m pip` auf; von Hand genauso.

**Erster Auftrag lädt ewig, die Karte bleibt fast leer**
Auf Hugging Face ist ein neuer Stand von Qwen-Image erschienen, und das
Programm lädt erst die geänderten Teile (beim Text-Encoder 17 GB). Den
vorhandenen Stand festhalten: in `lokal.bat`
`set "QWEN_IMAGE_REVISION=<Commit>"` — der Commit ist der Ordnername unter
`%USERPROFILE%\.cache\huggingface\hub\models--Qwen--Qwen-Image-2.1\snapshots`.

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

**Retusche: Naht, Farbfleck oder falsches Gesicht**
Eine sichtbare Kante: **Weiche Kante** erhöhen oder die Stelle großzügiger
übermalen. Passt das Ergebnis nicht zum Rest (ein fremder Mund, eine andere
Haut): **Umgebung** weiter stellen, damit das Modell mehr vom Gesicht sieht.
Wirkt die Änderung zu schwach: die Anweisung deutlicher fassen und mehr
**Versuche** laufen lassen.

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

**Kennzahlen nahe null**
Zu wenige Bilder oder zu wenige Epochen. Mit unter 50 aufgenommenen Bildern
lernt der Detektor nichts
Brauchbares.

**Oben erscheint ein Balken „Der Server läuft noch mit älterem Code“**
Das Programm wurde geändert, der Server läuft noch mit dem alten Stand:
neu starten.
