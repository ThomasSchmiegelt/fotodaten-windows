# Sicherheit

## Eine Lücke melden

Bitte **nicht** als öffentliches Issue. Stattdessen vertraulich über
**[Security → Report a vulnerability](https://github.com/ThomasSchmiegelt/qwen-image-lokal/security/advisories/new)**
in diesem Repository.

Hilfreich sind: was betroffen ist, wie es sich auslösen lässt, und was ein
Angreifer damit erreichen könnte. Eine Rückmeldung kommt in der Regel
innerhalb einer Woche.

Unterstützt wird jeweils der aktuelle Stand von `main`.

## Wofür das Programm gebaut ist — und wofür nicht

Das Programm ist ein **Werkzeug für den eigenen Rechner**. Daraus folgt, was
als Lücke zählt:

- Der Server lauscht standardmäßig nur auf `127.0.0.1`. Mit
  `QWEN_HOST=0.0.0.0` ist er im **lokalen Netz** erreichbar — **ohne
  Anmeldung**. Das ist so gewollt (Bedienung vom Handy), gehört aber nie ins
  offene Internet.
- Was etwas auf dem Rechner anrichtet — Projekte und Bilder löschen, GIMP
  starten, Cloud-Zugänge speichern, den Server beenden — nimmt der Server nur
  von `127.0.0.1` an, auch wenn er im Netz hängt. Ein Weg daran vorbei **ist**
  eine Lücke.
- Pfade aus Anfragen (Projekte, Katalog, Datensatz, Trainingsläufe) werden
  gegen feste Muster geprüft. Ein Weg aus diesen Verzeichnissen hinaus **ist**
  eine Lücke.
- **API-Schlüssel** für Cloud-Modelle liegen in `einstellungen.json` (Rechte
  0600, in `.gitignore`) und gehen nie an die Seite zurück. Ein Weg, sie über
  den Server auszulesen, **ist** eine Lücke.
- Erzeugte Bilder tragen ihren Prompt im PNG. Wer Bilder weitergibt, gibt
  damit auch den Prompt weiter — das ist Absicht, keine Lücke.
