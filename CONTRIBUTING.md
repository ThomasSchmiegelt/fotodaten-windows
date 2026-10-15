# Mitmachen

Fehlermeldungen, Ideen und Änderungen sind willkommen. Ein paar Hinweise,
damit sie gut ankommen.

## Fehler melden

Ein [Issue](https://github.com/ThomasSchmiegelt/qwen-image-lokal/issues) mit:

- **was du getan hast** — Reiter, Einstellungen, Prompt;
- **was du erwartet hast und was stattdessen kam** — bei Bildfehlern gern
  das Bild; Prompt und Seed stehen ohnehin im PNG;
- **die Meldung aus dem Terminal**, falls es eine gab;
- Grafikkarte und Speicher, wenn es um Laufzeit oder Speicherüberlauf geht.

Sicherheitslücken bitte **nicht** als Issue, sondern wie in
[SECURITY.md](SECURITY.md) beschrieben.

## Änderungen vorschlagen

1. Größere Vorhaben vorher kurz als Issue ansprechen — dann arbeitet niemand
   umsonst.
2. Einen Zweig anlegen, ändern, Pull Request stellen.
3. Vor dem Pull Request prüfen:

   ```bash
   ./qwen_bild/bin/python webui/pruefung.py   # Server auf 7860 muss laufen
   ```

   Das vergleicht die Oberfläche mit dem laufenden Server: angesprochene
   Elemente, gelieferte Felder, Syntax.

## Wie der Code geschrieben ist

- **Deutsch** in Bezeichnern, Kommentaren und Commit-Nachrichten, so wie der
  vorhandene Code. In Kommentaren und Bezeichnern ohne Umlaute (`ae`, `oe`,
  `ue`), in der Oberfläche und in Markdown mit.
- **Kommentare erklären das Warum**, nicht das Was. Viele Entscheidungen hier
  beruhen auf Messungen („gemessen an sechs Formulierungen …“) — wer etwas
  ändert, das so begründet ist, misst bitte nach und schreibt das Ergebnis
  dazu.
- **Keine Modellgewichte, erzeugten Bilder, Datensätze oder Schlüssel** im
  Pull Request. `.gitignore` hält die üblichen Orte fern (`outputs/`,
  `projekte/`, `katalog/`, `einstellungen.json`).
- Neue Abhängigkeiten nur mit Grund — und mit einer Lizenz, die zur
  MIT-Lizenz dieses Codes passt. Copyleft-Bibliotheken wie AGPL-3.0 bitte
  nicht; siehe den Lizenzabschnitt der [README](README.md#lizenz).

## Lizenz deiner Beiträge

Was du beiträgst, steht wie der übrige Code unter der [MIT-Lizenz](LICENSE).
Mit einem Pull Request erklärst du dich damit einverstanden.

## Umgang miteinander

Es gilt der [Verhaltenskodex](CODE_OF_CONDUCT.md).
