#!/usr/bin/env python3
"""Prüft die Oberfläche gegen den laufenden Server.

Die Seite und der Server entwickeln sich getrennt: das Skript vergleicht, ob
die Oberfläche nur Felder liest, die der Server auch liefert, ob jedes
angesprochene Element existiert und ob das Skript syntaktisch geschlossen ist.

Anlass war ein echter Fehler: ein Feld wurde aus `/api/info` entfernt, die
beiden Aufrufe in der Seite blieben stehen. Der dabei geworfene TypeError
brach die gesamte Einrichtung ab, das Seitenverhältnis-Feld blieb leer, und
der Auftrag scheiterte erst im Server mit einem unverständlichen KeyError.

    ./qwen_bild/bin/python webui/pruefung.py [--port 7860]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def seite() -> tuple[str, str]:
    """Aufbau und Verhalten der Oberflaeche.

    Beides liegt seit der Aufteilung in eigenen Dateien: `seite/index.html`
    traegt die Elemente, `seite/app.js` das Skript. Geprueft wird weiter im
    Zusammenhang -- gerade die Frage, ob jedes angesprochene Element auch
    existiert, laesst sich nur ueber beide hinweg beantworten.
    """
    ordner = os.path.join(HERE, "seite")
    with open(os.path.join(ordner, "index.html"), encoding="utf-8") as fh:
        text = fh.read()
    with open(os.path.join(ordner, "app.js"), encoding="utf-8") as fh:
        skript = fh.read()
    return text, skript


def pruefe_elemente(text: str, skript: str) -> list[str]:
    fehler = []
    kennungen = re.findall(r'\bid="([^"]+)"', text)
    doppelt = {k for k in kennungen if kennungen.count(k) > 1}
    if doppelt:
        fehler.append(f"doppelte Element-Kennungen: {sorted(doppelt)}")
    fehlend = sorted(set(re.findall(r'\$\("([^"]+)"\)', skript)) - set(kennungen))
    if fehlend:
        fehler.append(f"angesprochen, aber nicht vorhanden: {fehlend}")
    fehler += pruefe_syntax()
    return fehler


def pruefe_syntax() -> list[str]:
    """Das Skript wirklich zerlegen lassen, wenn node zur Hand ist.

    Klammern zu zaehlen war untauglich: eine Klammer in einer Zeichenkette
    oder in einem regulaeren Ausdruck ist keine Klammer im Code, und beide
    Richtungen haben schon falschen Alarm ausgeloest. `node --check` weiss es
    genau. Ohne node bleibt das Zaehlen als grobe Rueckfallebene.
    """
    datei = os.path.join(HERE, "seite", "app.js")
    if shutil.which("node"):
        fertig = subprocess.run(["node", "--check", datei],
                                capture_output=True, text=True)
        if fertig.returncode:
            erste = [z for z in fertig.stderr.splitlines() if z.strip()][:3]
            return ["node meldet einen Syntaxfehler: " + " / ".join(erste)]
        return []
    with open(datei, encoding="utf-8") as fh:
        code = _nur_code(fh.read())
    return [f"Klammern {auf}{zu} unausgeglichen: "
            f"{code.count(auf)} zu {code.count(zu)} (node fehlt, nur grob gezaehlt)"
            for auf, zu in (("(", ")"), ("{", "}"), ("[", "]"))
            if code.count(auf) != code.count(zu)]


# Alles, was der Browser selbst mitbringt, plus die Schlüsselwörter, die vor
# einer Klammer stehen dürfen. Was ein Aufruf weder hier noch im Skript
# findet, gibt es schlicht nicht.
BEKANNT = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "function",
    "async", "await", "new", "else", "do", "try", "in", "of", "delete", "void",
    "fetch", "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "parseInt", "parseFloat", "isNaN", "encodeURIComponent", "decodeURIComponent",
    "String", "Number", "Boolean", "Array", "Object", "JSON", "Math", "Promise",
    "Error", "Set", "Map", "Date", "RegExp", "alert", "confirm", "console",
    "FileReader", "Blob", "URL", "FormData", "Image", "atob", "btoa",
    "Event", "BroadcastChannel", "requestAnimationFrame",
}


def _ohne_vorlagen(code: str) -> str:
    """Vorlagenzeichenketten (`...`) entfernen, auch verschachtelte.

    Ein regulaerer Ausdruck schafft `a ${x ? `b (c)` : ""} d` nicht: er
    endet am inneren Backtick, und "b (c)" sah aus wie ein Aufruf von b().
    Ein kleiner Zaehler schon. Was in ${...} steht, ist Code und bleibt.
    """
    aus, stapel, i = [], [], 0      # stapel: offene ${ je Vorlagenebene
    in_vorlage = 0
    while i < len(code):
        z = code[i]
        if in_vorlage and (not stapel or stapel[-1] < in_vorlage):
            # mitten im Text einer Vorlage
            if z == "\\":
                i += 2
                continue
            if z == "`":
                in_vorlage -= 1
                aus.append('""')
            elif code.startswith("${", i):
                stapel.append(in_vorlage)
                aus.append("(")
                i += 2
                continue
            elif z == "\n":
                aus.append("\n")
            i += 1
            continue
        if z == "`":
            in_vorlage += 1
        elif z == "}" and stapel and stapel[-1] == in_vorlage:
            stapel.pop()
            aus.append(")")
        else:
            aus.append(z)
        i += 1
    return "".join(aus)

# Zeichenketten und Kommentare enthalten deutschen Fließtext -- "das ist (so)"
# sähe sonst aus wie ein Aufruf von ist().
def _nur_code(skript: str) -> str:
    # Ersetzt wird durch ebenso viele Zeilenumbrueche, wie verschwinden --
    # sonst zeigen alle Meldungen auf die falsche Zeile.
    def leer(treffer):
        return '""' + "\n" * treffer.group(0).count("\n")

    ohne = re.sub(r"/\*.*?\*/", leer, skript, flags=re.S)
    ohne = re.sub(r"(?<![:\w])//[^\n]*", " ", ohne)
    ohne = _ohne_vorlagen(ohne)
    for muster in (r"'(?:[^'\\\n]|\\.)*'", r'"(?:[^"\\\n]|\\.)*"'):
        ohne = re.sub(muster, leer, ohne)
    return ohne


def pruefe_aufrufe(skript: str) -> list[str]:
    """Ruft die Seite eine Funktion auf, die es nicht gibt?

    Anlass war ein echter Fehler: `startSlots` wurde aufgerufen, aber nie
    geschrieben. Der ReferenceError brach `starteDemo` genau vor der
    Fortschrittsabfrage ab -- der Auftrag lief, die Seite erfuhr nie davon,
    und der Startknopf blieb für immer auf "läuft".
    """
    code = _nur_code(skript)
    bekannt = set(BEKANNT)
    bekannt |= set(re.findall(r"\bfunction\s+([\w$]+)", code))
    bekannt |= set(re.findall(r"\b(?:const|let|var)\s+([\w$]+)", code))
    # Mehrfachzuweisungen in einer Zeile: let a = 1, b = 2, c = null
    for zeile in re.findall(r"\b(?:const|let|var)\s+([^;\n]+)", code):
        bekannt |= set(re.findall(r"([\w$]+)\s*=", zeile))
    # Benannte Argumente von Pfeilfunktionen
    bekannt |= set(re.findall(r"\(([\w$]+)\)\s*=>", code))
    bekannt |= set(re.findall(r"\b([\w$]+)\s*=>", code))

    return [f"die Seite ruft {name}() auf, geschrieben ist es nirgends"
            for name in sorted(set(re.findall(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(", code)))
            if name not in bekannt]


def pruefe_reihenfolge(skript: str) -> list[str]:
    """Wird ein `const`/`let` benutzt, bevor es dasteht?

    Anlass war ein echter Fehler: in `setMode` stand die Benutzung von
    `istDemo` vier Zeilen ueber der Deklaration. JavaScript wirft dort einen
    ReferenceError, die Aufrufpruefung sieht das aber nicht -- der Name
    existiert ja, nur eben noch nicht.

    Geprueft wird je Funktion, die auf Spaltenposition null beginnt, und nur
    fuer Deklarationen unmittelbar im Rumpf. Das genuegt fuer diese Seite und
    erspart einen halben Zerteiler. Eine Benutzung in einem Rueckruf, der erst
    spaeter laeuft, waere zwar harmlos, wird aber trotzdem gemeldet -- lieber
    einmal zu viel hinsehen.
    """
    zeilen = _nur_code(skript).split("\n")
    beginn = [i for i, z in enumerate(zeilen)
              if re.match(r"(?:async )?function [\w$]+\(", z)]
    fehler = []
    for nr, anfang in enumerate(beginn):
        ende = beginn[nr + 1] if nr + 1 < len(beginn) else len(zeilen)
        for i in range(anfang + 1, ende):
            if zeilen[i] == "}":          # schliessende Klammer in Spalte null
                ende = i + 1
                break
        rumpf = zeilen[anfang:ende]
        name = re.search(r"function ([\w$]+)", rumpf[0]).group(1)
        for i, zeile in enumerate(rumpf):
            # Nur Deklarationen unmittelbar im Funktionsrumpf. Tiefer liegt
            # eine eigene Ebene -- dort heisst derselbe Name etwas anderes,
            # und die Pruefung wuerde nur Fehlalarme werfen.
            treffer = re.match(r"  (?:const|let) ([\w$]+)\s*=", zeile)
            if not treffer:
                continue
            gesucht = re.compile(r"(?<![.\w$])" + re.escape(treffer.group(1)) + r"(?![\w$])")
            for j in range(1, i):
                if gesucht.search(rumpf[j]):
                    fehler.append(
                        f"{name}(): {treffer.group(1)} wird in Zeile "
                        f"{anfang + j + 1} benutzt, steht aber erst in "
                        f"{anfang + i + 1}")
                    break
    return fehler


def pruefe_felder(skript: str, info: dict) -> list[str]:
    gelesen = sorted(set(re.findall(r"\binfo\.(\w+)", skript)))
    fehlend = [k for k in gelesen if k not in info]
    return [f"die Seite liest info.{k}, der Server liefert es nicht" for k in fehlend]


def main() -> int:
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("--port", type=int, default=7860)
    argumente = zerleger.parse_args()

    text, skript = seite()
    fehler = (pruefe_elemente(text, skript) + pruefe_aufrufe(skript)
              + pruefe_reihenfolge(skript))

    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{argumente.port}/api/info", timeout=20) as antwort:
            info = json.load(antwort)
    except urllib.error.URLError as ausnahme:
        print(f"Kein Server auf Port {argumente.port} ({ausnahme.reason}) – "
              "nur die Seite selbst geprüft.")
        info = None
    else:
        fehler += pruefe_felder(skript, info)
        if info.get("source", {}).get("stale"):
            fehler.append("der Server läuft mit älterem Code als die Dateien auf "
                          f"der Platte: {info['source']['changed']}")

    if fehler:
        print("Beanstandungen:")
        for eintrag in fehler:
            print(f"  - {eintrag}")
        return 1

    geprueft = len(set(re.findall(r'\$\("([^"]+)"\)', skript)))
    felder = len(set(re.findall(r"\binfo\.(\w+)", skript))) if info else 0
    aufrufe = len(set(re.findall(r"(?<![.\w$])([a-zA-Z_$][\w$]*)\s*\(", _nur_code(skript))))
    print(f"in Ordnung: {geprueft} Elemente, {felder} Serverfelder, "
          f"{aufrufe} Aufrufe, Skript zerlegbar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
