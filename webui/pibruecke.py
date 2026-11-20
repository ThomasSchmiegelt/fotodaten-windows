"""pi als Gespraechspartner fuer Bildprompts.

pi (der pi-coding-agent) laeuft als eigener Prozess im RPC-Modus: eine JSON-
Zeile je Befehl auf stdin, eine je Ereignis auf stdout. Ohne Sitzungsdatei,
ohne AGENTS.md/CLAUDE.md, ohne Skills -- und mit genau einem Werkzeug,
`bildprompt_senden` (pi/bildprompt.ts). Der Server liest dessen Aufruf aus
dem Strom und macht daraus eine Uebergabe an die Seite. Ein Rueckweg von pi
zum Server ist dafuer nicht noetig.

Die Seite fragt die Ereignisse ab (`ereignisse(ab)`), wie sie es beim
Auftragsstand auch tut. Ein Gespraech fuer alle -- das Programm laeuft ohnehin
nur fuer einen.
"""

import atexit
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WERKZEUG = os.path.join(HERE, "pi", "bildprompt.ts")
WINDOWS = os.name == "nt"

# Wie viele Ereignisse vorgehalten werden. Ein Text kommt in vielen kleinen
# Stuecken; die Seite holt sie alle paar hundert Millisekunden ab.
VORRAT = 4000

SYSTEM = """Du bist ein Bildprompt-Assistent im Programm „Bildermacher“ (Qwen-Image 2.1).
Du entwickelst mit dem Benutzer im Gespräch einen Bildprompt. Sprich Deutsch,
knapp und konkret. Den Prompt selbst schreibst du auf Englisch, als
zusammenhängende, bildhafte Beschreibung: Motiv, Handlung, Umgebung, Licht,
Bildaufbau. Keine Stichwortlisten, keine Verbote („no …“) im Prompt — was
nicht ins Bild soll, gehört in negative_prompt.

Gefühle setzt du immer in Sichtbares um, nie nur als Wort — „fear“ oder
„joy“ kann das Bildmodell nicht malen. Angst: weit aufgerissene Augen,
hochgezogene Schultern, zurückweichender Körper, kaltes hartes Seitenlicht,
enger Ausschnitt, dunkle Ränder. Freude: offenes Lachen, Lachfältchen,
gelöste offene Haltung, warmes weiches Licht, helle Farben, Weite. Wut,
Trauer, Stolz, Erschöpfung genauso: Gesicht, Körper, Licht, Farbe, Bildaufbau.
In einer Szene mit mehreren Personen sag, wer was fühlt.

Zeige den aktuellen Stand des Prompts immer in einem Block, der mit
```prompt beginnt.

Hängt der Benutzer ein Bild an und sagt etwa „nimm das T-Shirt vom Bild“,
beschreibe genau dieses Teil (Schnitt, Farbe, Material, Aufdruck, Details)
und baue die Beschreibung an passender Stelle in den Prompt ein. Nur das
genannte Teil, nicht den Rest des Bildes.

Variablen: Ein Wort in Rauten, etwa #hose#, ist ein Platzhalter. Im
Bildermacher stehen dafür mehrere Werte, und jedes Bild bekommt zufällig
einen davon. Lass Rauten-Variablen stehen, wie sie sind. Will der Benutzer
etwas variieren, schlag eine Variable mit Werten vor.

Bezugsperson: Ein Name oder eine Beschreibung in Ausrufezeichen, etwa !Kai!
oder !die erste Frau!, markiert die Person,
auf die sich Blickwinkel, Blick, Mimik und Haltung beziehen. Lass die
Ausrufezeichen stehen.

Sagt der Benutzer „senden“, „übernehmen“, „schick rüber“ oder „fertig“,
rufe das Werkzeug bildprompt_senden mit dem fertigen Prompt auf. Setze
Einstellungen nur, wenn sie besprochen wurden. Erlaubte Schlüssel:
{katalog}"""


def _pi_befehl() -> list[str] | None:
    """Der Aufruf von pi. QWEN_PI setzt ihn ausdruecklich."""
    eigen = os.environ.get("QWEN_PI")
    if eigen:
        return [eigen]
    gefunden = shutil.which("pi.cmd" if WINDOWS else "pi") or shutil.which("pi")
    return [gefunden] if gefunden else None


class Pi:
    """Ein pi-Prozess samt mitgeschriebenem Ereignisstrom."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.modell = {"provider": "", "modell": ""}
        self.katalog = ""
        self._ereignisse: list[dict] = []
        self._nr = 0
        self._neu = threading.Condition()
        self._schreiben = threading.Lock()
        self._antworten: dict[str, dict] = {}
        self._zaehler = 0
        self.laeuft = False          # pi denkt oder schreibt gerade
        self.uebergaben = 0
        self.ollama = "http://127.0.0.1:11434"
        # Prueft eine Uebergabe gegen die Kataloge; setzt der Server.
        self.pruefen = lambda roh: roh
        self._entladen_danach = False

    # -- Prozess ----------------------------------------------------------
    def verfuegbar(self) -> dict:
        befehl = _pi_befehl()
        if not befehl:
            return {"available": False,
                    "reason": "pi nicht gefunden – npm install -g "
                              "@earendil-works/pi-coding-agent, oder QWEN_PI setzen"}
        return {"available": True, "befehl": befehl[0],
                "laeuft": bool(self.proc and self.proc.poll() is None),
                "denkt": self.laeuft, **self.modell}

    def _starten(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        befehl = _pi_befehl()
        if not befehl:
            raise RuntimeError(self.verfuegbar()["reason"])
        args = befehl + [
            "--mode", "rpc", "--no-session",
            "-nc", "-ns", "-np", "--no-themes", "-ne",
            "-e", WERKZEUG, "-t", "bildprompt_senden",
            "--thinking", "off",
            "--system-prompt", SYSTEM.replace("{katalog}", self.katalog),
        ]
        if self.modell["provider"] and self.modell["modell"]:
            args += ["--provider", self.modell["provider"],
                     "--model", self.modell["modell"]]
        # Eigenes Arbeitsverzeichnis: pi soll nichts aus dem Programmordner
        # als Projektdatei lesen.
        arbeit = os.path.join(HERE, "pi")
        self.proc = subprocess.Popen(
            args, cwd=arbeit, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
            bufsize=1)
        threading.Thread(target=self._lesen, args=(self.proc,), daemon=True,
                         name="pi-lesen").start()
        threading.Thread(target=self._fehler_lesen, args=(self.proc,),
                         daemon=True, name="pi-stderr").start()
        self._melden({"art": "info", "text": "pi gestartet"})
        # Welches Modell pi tatsaechlich nimmt, steht erst im Zustand.
        try:
            zustand = self.anfrage({"type": "get_state"}, timeout=20)
            m = (zustand.get("data") or {}).get("model") or {}
            if m:
                self.modell = {"provider": m.get("provider", ""),
                               "modell": m.get("id", "")}
        except RuntimeError:
            pass

    def beenden(self) -> None:
        proc, self.proc = self.proc, None
        self.laeuft = False
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # -- Strom ------------------------------------------------------------
    def _melden(self, ereignis: dict) -> None:
        with self._neu:
            self._nr += 1
            self._ereignisse.append({"nr": self._nr, **ereignis})
            del self._ereignisse[:-VORRAT]
            self._neu.notify_all()

    def _fehler_lesen(self, proc) -> None:
        for zeile in proc.stderr:
            zeile = zeile.strip()
            if zeile:
                print(f"[pi] {zeile}", file=sys.stderr)

    def _lesen(self, proc) -> None:
        for zeile in proc.stdout:
            zeile = zeile.rstrip("\r\n")
            if not zeile:
                continue
            try:
                e = json.loads(zeile)
            except json.JSONDecodeError:
                continue
            self._verarbeiten(e)
        if proc is self.proc or self.proc is None:
            self.laeuft = False
            self._melden({"art": "fehler", "text": "pi wurde beendet"})

    def _verarbeiten(self, e: dict) -> None:
        art = e.get("type")
        if art == "response":
            kennung = e.get("id")
            if kennung:
                with self._neu:
                    self._antworten[kennung] = e
                    self._neu.notify_all()
            if not e.get("success"):
                self._melden({"art": "fehler", "text": str(e.get("error") or "")})
            return
        if art == "agent_start":
            self.laeuft = True
            self._melden({"art": "start"})
        elif art == "message_update":
            d = e.get("assistantMessageEvent") or {}
            if d.get("type") == "text_delta":
                self._melden({"art": "text", "text": d.get("delta", "")})
            elif d.get("type") == "thinking_delta":
                self._melden({"art": "denken", "text": d.get("delta", "")})
        elif art == "message_end":
            m = e.get("message") or {}
            if m.get("role") == "assistant":
                if m.get("stopReason") == "error":
                    self._melden({"art": "fehler",
                                  "text": str(m.get("errorMessage") or "Fehler beim Modell")})
                self._melden({"art": "absatz"})
        elif art == "tool_execution_start" and e.get("toolName") == "bildprompt_senden":
            self.uebergaben += 1
            try:
                daten = self.pruefen(e.get("args") or {})
            except Exception as fehler:
                self._melden({"art": "fehler", "text": f"Uebergabe unbrauchbar: {fehler}"})
            else:
                self._melden({"art": "uebergabe", "daten": daten})
                # Erst wenn pi zu Ende geschrieben hat: sonst laedt die
                # Antwort danach das Modell gleich wieder.
                self._entladen_danach = True
        elif art == "auto_retry_start":
            self._melden({"art": "info", "text": "neuer Versuch: "
                          + str(e.get("errorMessage") or "")[:200]})
        elif art == "agent_settled":
            self.laeuft = False
            self._melden({"art": "fertig"})
            if self._entladen_danach:
                self._entladen_danach = False
                threading.Thread(target=self.entladen, args=(self.ollama,),
                                 daemon=True, name="pi-entladen").start()

    def ereignisse(self, ab: int, warten: float = 20.0) -> dict:
        """Alles nach Nummer `ab`. Wartet, bis etwas kommt (lange Abfrage)."""
        ende = time.time() + warten
        with self._neu:
            while self._nr <= ab and time.time() < ende:
                self._neu.wait(max(0.0, ende - time.time()))
            neu = [x for x in self._ereignisse if x["nr"] > ab]
        return {"ereignisse": neu, "nr": self._nr, "denkt": self.laeuft}

    # -- Befehle ----------------------------------------------------------
    def _senden(self, befehl: dict) -> None:
        self._starten()
        with self._schreiben:
            try:
                self.proc.stdin.write(json.dumps(befehl, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError) as fehler:
                raise RuntimeError(f"pi antwortet nicht mehr: {fehler}")

    def anfrage(self, befehl: dict, timeout: float = 30) -> dict:
        """Ein Befehl mit Antwort."""
        with self._neu:
            self._zaehler += 1
            kennung = f"b{self._zaehler}"
        self._senden({**befehl, "id": kennung})
        ende = time.time() + timeout
        with self._neu:
            while kennung not in self._antworten:
                rest = ende - time.time()
                if rest <= 0:
                    raise RuntimeError("pi antwortet nicht")
                self._neu.wait(rest)
            return self._antworten.pop(kennung)

    def schreiben(self, text: str, bilder: list[dict]) -> None:
        """Eine Nachricht des Benutzers. Laeuft pi noch, wird sie angehaengt."""
        befehl = {"type": "prompt", "message": text}
        if bilder:
            befehl["images"] = bilder
        if self.laeuft:
            befehl["streamingBehavior"] = "followUp"
        self._melden({"art": "ich", "text": text, "bilder": len(bilder)})
        self._senden(befehl)

    def abbrechen(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._senden({"type": "abort"})

    def neu(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.anfrage({"type": "new_session"})
        with self._neu:
            self._ereignisse.clear()
        self._melden({"art": "neu"})

    def modelle(self) -> list[dict]:
        antwort = self.anfrage({"type": "get_available_models"})
        return [{"provider": m.get("provider", ""), "modell": m.get("id", ""),
                 "bilder": "image" in (m.get("input") or [])}
                for m in (antwort.get("data") or {}).get("models") or []]

    def modell_setzen(self, provider: str, modell: str) -> dict:
        self.modell = {"provider": provider, "modell": modell}
        if self.proc and self.proc.poll() is None:
            antwort = self.anfrage({"type": "set_model", "provider": provider,
                                    "modelId": modell})
            if not antwort.get("success"):
                raise RuntimeError(str(antwort.get("error") or "Modell unbekannt"))
        return self.modell

    def entladen(self, ollama_url: str) -> bool:
        """Das Modell von pi aus dem Grafikspeicher nehmen, wenn es Ollama ist.

        pi spricht Ollama ueber die OpenAI-Schnittstelle, und die haelt ein
        Modell fuenf Minuten -- dem Bildmodell fehlen dann 17 GB.
        """
        if self.modell.get("provider") != "ollama" or not self.modell.get("modell"):
            return False
        body = json.dumps({"model": self.modell["modell"], "keep_alive": 0}).encode()
        anfrage = urllib.request.Request(
            ollama_url.rstrip("/") + "/api/generate", body,
            {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=30):
                pass
        except Exception:
            return False
        self._melden({"art": "info", "text": f"{self.modell['modell']} entladen"})
        return True


pi = Pi()

# pi laeuft als Kindprozess; mit dem Server soll er gehen.
atexit.register(pi.beenden)
