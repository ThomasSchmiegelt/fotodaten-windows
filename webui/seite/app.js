// Verhalten der Oberflaeche. Der Aufbau steht in index.html, das Aussehen
// in stil.css. Geladen wird die Datei am Ende des Rumpfes -- die Elemente
// sind dann alle vorhanden.
const $ = id => document.getElementById(id);
const RATIOS = {"1:1":1, "4:3":4/3, "3:4":3/4, "3:2":3/2, "2:3":2/3, "16:9":16/9, "9:16":9/16};
const esc = t => String(t).replace(/[<>&"]/g, c => ({"<":"&lt;", ">":"&gt;", "&":"&amp;", '"':"&quot;"}[c]));

const MODES = {
  t2i:    {label: "Erzeugen", refs: 0, sweep: "", count: 1, lock: false,
           ph: 'A neon shop sign that reads "QWEN IMAGE 2.1", rainy night, reflections on wet pavement'},
  edit:   {label: "Bearbeiten", refs: 1, sweep: "", count: 1, lock: false, follow: true,
           ph: "Change the background to a sunset beach",
           hint: refs => `Bis zu ${refs} Bilder. Mehrere werden gemeinsam als Vorlage gelesen.`},
  gruppe: {label: "Gruppenbild erzeugen", refs: 2, sweep: "", count: 1, lock: false, follow: false,
           ph: "standing together in a sunlit park, smiling, casual clothing",
           hint: refs => `Pro Person ein Bild, 2 bis ${refs} Stück. Gesicht gut sichtbar.`},
  person: {label: "Umrundung erzeugen", refs: 1, sweep: "view", count: 10, follow: false, lock: true,
           ph: "standing in a city street, wearing a dark coat",
           hint: () => "Ein Bild der Person. Die Serie fliegt einmal um sie herum."},
  demo: {label: "Ablauf starten", refs: 0, ph: "", hint: () => ""},
  bausteine: {label: "Baustein-Bild erzeugen", refs: 0, ph: "", hint: () => ""},
  szenen: {label: "Szene erzeugen", refs: 0, ph: "", hint: () => ""},
  geschichte: {label: "Geschichte erzeugen", refs: 0, ph: "", hint: () => ""},
  katalog: {label: "Katalog", refs: 0, ph: "", hint: () => ""},
  seiten: {label: "Sechs Seiten erzeugen", refs: 0, ph: "", hint: () => ""},
  varianten: {label: "Varianten erzeugen", refs: 1, sweep: "varianten", count: 12,
              follow: true, lock: false,
              ph: "(optional) zusätzliche Angaben, die für jede Variante gelten",
              hint: () => "Das Basisbild. Welche Achsen sich ändern, stellst du unten ein."}
};

let mode = "t2i", eigenerReiter = false, refs = [], refPrompts = [], polling = null, maxRefs = 4, templates = {}, refBudget = 2200;
let EFFECTS = [], FORMS = [], PAINTS = [], ACTIONS = [], SUBJECTS = [],
    hasGimp = false, AXIS_OFF = "-";

// ---------- Voreinstellungen laden ----------
fetch("/api/info").then(r => r.json()).then(info => {
  // Das Wichtigste zuerst: bricht weiter unten etwas ab, sind die Grundregler
  // wenigstens gefüllt. Vorher blieb das Seitenverhältnis leer und der Auftrag
  // scheiterte im Server mit einem KeyError auf einem leeren Wert.
  $("aspect").innerHTML = (info.aspects || ["1:1"])
    .map(a => `<option>${a}</option>`).join("");
  maxRefs = info.max_references;
  templates = info.templates;
  refBudget = info.reference_token_budget;
  Object.assign(SWEEP_LEN, {view: info.views.length, style: info.styles.length,
                            light: info.lights.length, camera: info.cameras.length});
  fill("view", info.views); fill("style", info.styles);
  fill("light", info.lights); fill("camera", info.cameras);
  EFFECTS = info.effects; FORMS = info.forms;
  hasGimp = !!(info.gimp && info.gimp.available);
  ABLAEUFE = info.ablaeufe || [];
  $("ablaufWahl").innerHTML = ABLAEUFE.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  if (ABLAEUFE.length) { $("ablaufWahl").value = ABLAEUFE[0].key; $("ablaufWahl").onchange(); }
  // Ein sehr alter Server meldet gar kein "source" -- dann ist er erst recht
  // veraltet und kann es nur nicht selbst sagen.
  const neustart = " Bitte im Terminal <code>Strg+C</code> und <code>./start.sh</code>.";
  if (!info.source) {
    $("staleBar").style.display = "block";
    $("staleBar").innerHTML = "Dieser Server ist älter als die Oberfläche und kann "
      + "seinen Stand nicht melden. Das gibt widersprüchliches Verhalten." + neustart;
  } else if (info.source.stale) {
    $("staleBar").style.display = "block";
    $("staleBar").innerHTML = "Der Server läuft noch mit älterem Code ("
      + info.source.changed.map(esc).join(", ")
      + " wurde seither geändert). Die Seite hier ist aktuell, der Server nicht —"
      + " das gibt widersprüchliches Verhalten." + neustart;
  }
  if (info.chat && info.chat.available) {
    $("chatBox").style.display = "block";
    $("chat").placeholder = "Sag einfach, was du willst — „10 Drachen als Zeichentrick, hochkant“";
    $("chatNote").textContent = "Freitext, deutsch. " + info.chat.model
      + " übersetzt und stellt die Regler unten ein. Erzeugt wird erst auf deinen Klick.";
  }
  zeigeProjekte(info.projekte, info.projekt);
  BSARTEN = info.bausteinarten || [];
  $("bsArt").innerHTML = BSARTEN.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  personFelder();
  MIMIKLISTE = info.mimik || [];
  EINSTELLUNGEN = info.einstellungen || [];
  STILLISTE = info.styles || [];
  fill("gsStil", info.styles);
  fill("gsFreigabe", info.freigaben);
  fill("gsErzaehler", info.erzaehler);
  ERZAEHLERLISTE = info.erzaehler || [];
  FOLGENLISTE = info.folgen || [];
  fill("bsWesen", info.wesen);
  WESENLISTE = info.wesen || [];
  $("bsStil").innerHTML = `<option value="">— Stil der Geschichte —</option>`
    + (info.styles || []).map(x =>
        `<option value="${x.key}">${esc(x.label)}</option>`).join("");
  // Leer heisst hier wirklich ohne Stilangabe -- ein Katalogbild soll
  // schlicht sein duerfen.
  $("seitenStil").innerHTML = `<option value="">— ohne Stilangabe —</option>`
    + (info.styles || []).map(x =>
        `<option value="${x.key}">${esc(x.label)}</option>`).join("");
  SEITENNAMEN = info.katalogseiten || [];
  GEZEICHNET = info.gezeichnet || [];
  fill("gsWelt", info.welten);
  // Gross fuer die schoepferische Arbeit, klein fuer alles andere.
  $("gsModell").innerHTML =
    `<option value="${info.gross}">${esc(info.gross)} (gross, besser)</option>`
    + `<option value="${(info.chat || {}).model || ""}">`
    + `${esc((info.chat || {}).model || "klein")} (klein, schneller)</option>`;
  zeigeSelbstszenen();
  zeigeGrad();
  zeigeBausteine(info.bausteine);
  fill("effect", EFFECTS); fill("form", FORMS);
  AXIS_OFF = info.axis_off || "-";
  // Alle Achsenfelder fuellt subjectChanged() aus info.subjects[].axes --
  // genau der Liste, aus der der Server auch wuerfelt.
  SUBJECTS = info.subjects;
  $("subject").innerHTML = SUBJECTS.map(
    x => `<option value="${x.key}">${esc(x.label)}</option>`).join("");
  subjectChanged();
  $("material").value = AXIS_OFF;   // Werkstoff nur auf Wunsch
  fill("scenario", info.scenarios);
  ACTIONS = info.group_actions;
  $("action").innerHTML = ACTIONS.map(
    a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  $("ausBildernAktion").innerHTML = $("action").innerHTML;
  $("t2iEinst").innerHTML = `<option value="">— keine —</option>`
    + EINSTELLUNGEN.map(e => `<option value="${e.key}">${esc(e.label)}${
        e.paar ? " (zwei Bilder)" : ""}</option>`).join("");
  t2iEinstChanged();
  PAINTS = info.paints;
  paintPreview();
  $("cmdHint").innerHTML = "Direkt tippbar im Prompt: "
    + EFFECTS.map(e => `<code>${esc(e.alias)}</code>`).join(", ")
    + ". Ein getippter Befehl stellt die Regler selbst um.";
  setMode("t2i");
}).catch(fehler => {
  console.error(fehler);
  $("staleBar").style.display = "block";
  $("staleBar").textContent = "Die Oberfläche konnte sich nicht einrichten: "
    + fehler.message + " — läuft der Server mit dem passenden Code?";
});
// Fehlt dem Server ein Feld, soll das auffallen statt die Seite abzuwürgen:
// ein leeres Auswahlfeld liefert sonst "" und der Auftrag scheitert erst
// weit später mit einer unverständlichen Meldung.
function meldeLuecke(id) {
  console.warn("Der Server liefert keine Daten für", id);
  $("staleBar").style.display = "block";
  $("staleBar").textContent = `Der Server liefert keine Daten für „${id}“. `
    + "Wahrscheinlich läuft er mit älterem Code – bitte Strg+C und ./start.sh.";
}

// Achsen im Varianten-Modus kennen drei Zustaende: wuerfeln, unveraendert
// lassen, oder ein fester Wert.
function fillAxis(id, items) {
  if (!Array.isArray(items)) return meldeLuecke(id);
  $(id).innerHTML = '<option value="">würfeln</option>'
    + `<option value="${AXIS_OFF}">unverändert lassen</option>`
    + items.map(i => `<option value="${i.key}">${esc(i.label)}</option>`).join("");
}
function fill(id, items) {
  if (!Array.isArray(items)) return meldeLuecke(id);
  $(id).innerHTML = '<option value="">— automatisch —</option>'
    + items.map(i => `<option value="${i.key}">${esc(i.label)}</option>`).join("");
}

// ---------- Größenanzeige ----------
function dims() {
  const area = $("base").value ** 2, r = RATIOS[$("aspect").value] || 1;
  return [Math.round(Math.sqrt(area * r) / 32) * 32, Math.round(Math.sqrt(area / r) / 32) * 32];
}
// Spiegelt reference_resolution() aus der Engine wider.
function refSize(base, n) {
  if (!n) return base;
  return Math.max(512, Math.min(base, Math.floor(Math.sqrt(refBudget * 1024 / n) / 32) * 32));
}
function refresh() {
  const useRef = refs.length && $("follow").checked && mode !== "t2i";
  $("aspect").disabled = useRef;
  const [w, h] = dims();
  const n = parseInt($("count").value, 10) || 1;
  $("dims").textContent = (useRef ? `Seitenverhältnis folgt der Referenz · ${$("base").value} px Basis` : `${w} × ${h} px`)
    + (n > 1 ? ` · ${n} Bilder` : "") + " · lokal auf der RTX 3090";

  const base = parseInt($("base").value, 10), r = refSize(base, refs.length);
  $("refNote").textContent = refs.length && r < base
    ? `Referenzen werden intern mit ${r} px gelesen, damit die Sequenz ins VRAM passt. `
      + `Die Ausgabe bleibt bei ${base} px.`
    : "";
}
["aspect", "base", "count", "follow"].forEach(id => $(id).addEventListener("change", refresh));

// Bei einem Durchlauf durch eine Tabelle ist deren Laenge die sinnvolle Anzahl.
const SWEEP_LEN = {};
function sweepChanged() {
  const s = $("sweep").value, n = SWEEP_LEN[s];
  if (n) $("count").value = Math.min(n, 20);
  $("seedHint").textContent = $("lockSeed").checked
    ? "Gleicher Seed: Kleidung, Umgebung und Bildaufbau bleiben über die Serie hinweg stabiler."
    : "Aufsteigende Seeds: jedes Bild wird eigenständiger, aber weniger konsistent.";
  refresh();
}
$("sweep").addEventListener("change", sweepChanged);
$("lockSeed").addEventListener("change", sweepChanged);

// Umgebung und Blickwinkel haengen von der Motivart ab.
// Welches Auswahlfeld welche Achse zeigt. Die Namen rechts sind die des
// Servers (variant_axes), links stehen die Felder der Seite.
const ACHSENFELDER = {paint: "paint", palette: "palette", vstyle: "style",
                      scene: "scene", vlight: "light", device: "device",
                      angle: "angle", material: "material",
                      haltung: "haltung", kleidung: "kleidung"};

function subjectChanged() {
  const k = SUBJECTS.find(x => x.key === $("subject").value) || SUBJECTS[0];
  if (!k) return;
  const achsen = k.axes || {};
  Object.keys(ACHSENFELDER).forEach(id => {
    const liste = achsen[ACHSENFELDER[id]];
    const vorher = $(id).value;
    // Nicht jede Motivart kennt jede Achse -- ein gewuerfelter Werkstoff
    // ergibt bei einer Person keinen Sinn, deshalb fehlt er dort.
    if (!Array.isArray(liste)) {
      $(id).innerHTML = `<option value="${AXIS_OFF}">hier nicht vorgesehen</option>`;
      $(id).disabled = true;
      return;
    }
    $(id).disabled = false;
    fillAxis(id, liste);
    // Die bisherige Wahl behalten, wenn es sie hier auch gibt.
    if (vorher === AXIS_OFF || liste.some(i => i.key === vorher)) $(id).value = vorher;
  });
  $("paintTarget").placeholder = "z. B. " + k.target;
  paintPreview();
}
$("subject").addEventListener("change", subjectChanged);

// Zeigt den Satz, den die Farbachse erzeugen wird. Ohne das bleibt unsichtbar,
// dass ein unpassendes Ziel die Achse wirkungslos macht.
function paintPreview() {
  const el = $("paintPreview"), wahl = $("paint").value, ziel = $("paintTarget").value.trim();
  el.className = "hint";
  if (wahl === AXIS_OFF) { el.textContent = "Die Farbe bleibt unverändert."; return; }
  if (!ziel) {
    el.className = "hint warn";
    el.textContent = "Bitte eintragen, wovon die Farbe geändert werden soll — "
      + "sonst bleibt die Farbachse wirkungslos.";
    return;
  }
  const treffer = PAINTS.find(p => p.key === wahl);
  el.textContent = treffer
    ? `Ergibt: „${ziel} is ${treffer.phrase}“`
    : `Pro Bild eine andere Farbe, z. B. „${ziel} is ${(PAINTS[0] || {}).phrase || "red"}“`;
}
$("paint").addEventListener("change", paintPreview);
$("paintTarget").addEventListener("input", paintPreview);

// ---------- Modus ----------
function setMode(next) {
  mode = next;
  const cfg = MODES[next];
  Object.keys(MODES).forEach(m => $("tab-" + m).classList.toggle("on", m === next));
  $("uploadBox").style.display = cfg.refs ? "block" : "none";
  $("followBox").style.display = cfg.refs ? "flex" : "none";
  $("prompt").placeholder = cfg.ph;
  if (!$("go").classList.contains("busy")) $("go").textContent = cfg.label;
  $("ableitenZeile").style.display = cfg.refs ? "block" : "none";
  $("uploadHint").textContent = mode === "gruppe" ? (aktion().hint || "")
                                : (cfg.hint ? cfg.hint(maxRefs) : "");
  if (cfg.sweep !== undefined) $("sweep").value = cfg.sweep;
  if (cfg.count !== undefined) $("count").value = cfg.count;
  if (cfg.follow !== undefined) $("follow").checked = cfg.follow;
  if (cfg.lock !== undefined) $("lockSeed").checked = cfg.lock;
  sweepChanged();

  const tpl = templates[next];
  const istDemo = next === "demo";
  const istBausteine = next === "bausteine";
  const istSzenen = next === "szenen";
  const istGeschichte = next === "geschichte";
  if (istGeschichte) gsHolen();
  const istKatalog = next === "katalog";
  $("katalogBox").style.display = istKatalog ? "block" : "none";
  if (istKatalog) katalogHolen();
  const istSeiten = next === "seiten";
  $("seitenBox").style.display = istSeiten ? "block" : "none";
  if (istSeiten) { seitenGegenstandFuellen(); seitenHolen(); }
  $("szenenBox").style.display = istSzenen ? "block" : "none";
  $("geschichteBox").style.display = istGeschichte ? "block" : "none";
  // Beide Reiter haben eine eigene Bedienung und brauchen die ueblichen
  // Kaesten nicht -- Prompt, Darstellung, Bildgroesse.
  const eigen = istDemo || istBausteine || istSzenen || istGeschichte
                || istKatalog || istSeiten;
  eigenerReiter = eigen;
  $("demoBox").style.display = istDemo ? "block" : "none";
  $("bausteinBox").style.display = istBausteine ? "block" : "none";
  // Im Ablauf-Reiter ist das Prompt-Feld ausgeblendet -- dort waere das
  // Ableiten wirkungslos. Der Reiter hat dafuer seine eigene Zeile.
  document.querySelectorAll(".ableiten").forEach(
    el => { el.style.display = eigen ? "none" : "block"; });
  ["boxVorlage", "boxDarstellung", "boxBild", "boxFein", "uploadBox"].forEach(
    id => { if (eigen) $(id).style.display = "none"; });
  $("prompt").parentElement.querySelectorAll("#prompt, #transNote, #tplHint")
    .forEach(el => { el.style.display = eigen ? "none" : ""; });
  document.querySelectorAll("label[for=prompt]").forEach(
    el => el.style.display = eigen ? "none" : "");
  if (!eigen) { $("boxVorlage").style.display = ""; $("boxDarstellung").style.display = "";
                $("boxBild").style.display = ""; $("boxFein").style.display = ""; }
  demoDauer();
  const istVarianten = next === "varianten";
  $("gruppeBox").style.display = next === "gruppe" ? "block" : "none";
  $("aufbauBox").style.display = next === "t2i" ? "block" : "none";
  if (next === "t2i") ausBildernZeigen();
  groupSizeSichtbar();
  paintPreview();
  $("variantenBox").style.display = istVarianten ? "block" : "none";
  coverSichtbar();
  // Licht und Stil steuern im Varianten-Modus die Achsen, nicht diese Regler.
  [["light", "Licht"], ["style", "Stil"]].forEach(([id, wort]) => {
    $(id).disabled = istVarianten;
    $(id).title = istVarianten
      ? `Im Varianten-Modus zählt die ${wort}-Achse weiter unten` : "";
  });
  $("tplHint").style.display = tpl && next !== "varianten" ? "block" : "none";
  if (tpl) $("tplHint").textContent = "Der Server setzt automatisch davor: „"
    + tpl.replace("{extra}", "…").replace("{n}", refs.length || "N") + "“";
  drawThumbs();
}
Object.keys(MODES).forEach(m => $("tab-" + m).onclick = () => {
  // Ein Effekt, der ein Bild braucht, passt nicht zu Text -> Bild.
  const e = EFFECTS.find(x => x.key === $("effect").value);
  if (m === "t2i" && e && e.needs_image) $("effect").value = "";
  setMode(m);
});

// Effekte und Vorlagen bringen Einstellungen mit. Die werden sichtbar in die
// Regler geschrieben, damit nichts unsichtbar im Hintergrund passiert.
function applyOverrides(o) {
  ["aspect", "style", "light", "camera", "view", "sweep"].forEach(k => {
    if (o[k] !== undefined) $(k).value = o[k];
  });
  if (o.transparent !== undefined) $("transparent").checked = !!o.transparent;
  if (o.lock_seed !== undefined) $("lockSeed").checked = !!o.lock_seed;
  if (o.count !== undefined) $("count").value = o.count;
  // Hochskalieren bringt eine groessere Kantenlaenge mit -- der Regler muss
  // sie zeigen, sonst waere nicht zu sehen, warum es laenger dauert.
  if (o.base !== undefined) $("base").value = o.base;
  refresh();
}
// Die Felder fuers Titelblatt gehoeren zum Effekt, nicht zum Reiter: sie
// erscheinen, sobald /magazine cover gewaehlt ist.
function coverSichtbar() {
  $("coverBox").style.display =
    !eigenerReiter && $("effect").value === "magazine" ? "block" : "none";
}

// Was auf dem Heft stehen soll. Ist nichts ausgefuellt, geht nichts mit --
// eine leere Maske wuerde dem Modell sagen, auf dem Titelblatt stehe kein
// einziges Wort.
function coverFelder() {
  if ($("effect").value !== "magazine") return null;
  const zeilen = $("coverZeilen").value.split("\n")
    .map(z => z.trim()).filter(z => z);
  const titel = $("coverTitel").value.trim();
  if (!titel && !zeilen.length) return null;
  return {titel: titel, untertitel: $("coverUnter").value.trim(),
          zeilen: zeilen, ausgabe: $("coverAusgabe").value.trim(),
          preis: $("coverPreis").value.trim(),
          barcode: $("coverBarcode").checked};
}

$("effect").onchange = () => {
  coverSichtbar();
  const e = EFFECTS.find(x => x.key === $("effect").value);
  if (!e) return;
  if (e.mode) setMode(e.mode);
  else if (e.needs_image && mode === "t2i") setMode("edit");
  applyOverrides(e);
};
$("form").onchange = () => {
  const f = FORMS.find(x => x.key === $("form").value);
  if (f) applyOverrides(f);
};

// Die gewählte Gruppen-Aktion bestimmt, wie viele Bilder nötig sind.
function aktion() {
  return ACTIONS.find(a => a.key === $("action").value) || {min: 2, hint: ""};
}
$("action").addEventListener("change", () => { setMode(mode); refresh(); });

// ---------- Kameraeinstellung in Text->Bild ----------
// Dieselben Einstellungen wie hinter dem Rueckwaertsschraegstrich in einer
// Szene. Was sich spiegelt, bekommt eine eigene Zeile: im Prompt
// dazwischengeschrieben landet es irgendwo im Satz, und das Modell bezieht
// es dann auf das falsche.
function t2iEintrag() {
  return EINSTELLUNGEN.find(e => e.key === $("t2iEinst").value) || null;
}
function t2iEinstChanged() {
  const e = t2iEintrag();
  const luecke = e ? e.luecke : "";
  $("t2iSpiegelZeile").style.display = luecke ? "block" : "none";
  $("t2iSpiegelLabel").textContent = luecke === "hoehe"
    ? "Wie hoch die Kamera hängt" : "Was sich spiegelt";
  $("t2iSpiegel").placeholder = luecke === "hoehe"
    ? "z. B. fünf Meter" : "z. B. das brennende Schiff";
}
$("t2iEinst").addEventListener("change", t2iEinstChanged);

// ---------- Bild aus den Musterbildern der Bausteine ----------
// Die Kennungen der Bausteine, die ueber -> in den Prompt gewandert sind.
// Aus ihren Musterbildern laesst sich das Bild zusammensetzen, statt die
// Personen im Prompt zu beschreiben und zu hoffen -- bei mehr als zwei
// Figuren ist das der verlaesslichere Weg.
let promptTeile = [];

// Welche Aktion zu einer Menge Bausteine passt und was davon ein Bild hat.
// Ein Ort mit Musterbild ist die Szene und gehoert nach vorn: "Figur in
// eine Szene setzen" liest das erste Bild als Kulisse.
function ausBildernPlan(ids) {
  const teile = ids.map(id => BAUSTEINE.find(b => b.id === id))
                   .filter(b => b);
  const ohne = teile.filter(b => !b.bild);
  const orte = teile.filter(b => b.bild && b.art === "ort");
  const rest = teile.filter(b => b.bild && b.art !== "ort");
  const reihe = orte.slice(0, 1).concat(rest);
  return {teile: teile, ohne: ohne, reihe: reihe,
          aktion: orte.length ? "einsetzen" : "zusammen"};
}

function ausBildernZeigen() {
  const an = promptTeile.length > 0;
  $("ausBildernBox").style.display = an ? "block" : "none";
  if (!an) { $("ausBildern").checked = false; }
  $("ausBildernWahl").style.display =
    an && $("ausBildern").checked ? "block" : "none";
  if (!an) return;
  const plan = ausBildernPlan(promptTeile);
  $("ausBildernListe").innerHTML = plan.teile.map(b =>
    `<code>/${esc(b.name)}</code>${b.bild ? "" : " <b>ohne Bild</b>"}`)
    .join(" · ");
  const stufen = $("ausBildernWeg").value === "stufen";
  $("ausBildernAktionZeile").style.display = stufen ? "none" : "block";
  const wahl = ACTIONS.find(a => a.key === $("ausBildernAktion").value);
  const noetig = stufen ? 1 : (wahl ? wahl.min : 2);
  const teile = [];
  if (plan.ohne.length) {
    teile.push("Ohne Musterbild geht es nicht: "
      + plan.ohne.map(b => b.name).join(", ")
      + " — erst im Reiter Bausteine mit ▣ eines erzeugen.");
  }
  if (plan.reihe.length < noetig) {
    teile.push(`Dieser Weg braucht ${noetig} Bild(er), vorhanden sind ${
      plan.reihe.length}.`);
  } else if (stufen) {
    teile.push("Erst liest das Sprachmodell aus deinem Prompt heraus, wer "
      + "welche Haltung einnimmt. Dann entsteht der Raum, danach jede Figur "
      + "einzeln in dieser Haltung, zuletzt wird eins ins andere gesetzt. "
      + "Dauert länger und trifft die Beschreibung besser. Die Posen bleiben "
      + "liegen und hängen sich an ihren Baustein.");
  } else if (plan.reihe.length > maxRefs) {
    teile.push(`Das Modell nimmt höchstens ${maxRefs} Vorlagen, hier sind es ${
      plan.reihe.length}. Nimm einen Baustein heraus — oder bau in Stufen auf, `
      + "das kennt die Grenze nicht.");
  } else {
    teile.push("Reihenfolge: "
      + plan.reihe.map((b, n) => `${n + 1}. ${b.name}`).join(", ")
      + ". Die Musterbilder gehen unverändert hinein — steht die Figur "
      + "darauf, steht sie auch im Bild.");
  }
  $("ausBildernNote").textContent = teile.join(" ");
}
$("ausBildern").addEventListener("change", ausBildernZeigen);
$("ausBildernAktion").addEventListener("change", ausBildernZeigen);
$("ausBildernWeg").addEventListener("change", ausBildernZeigen);
$("ausBildernLeeren").onclick = e => {
  e.preventDefault();
  promptTeile = [];
  ausBildernZeigen();
};
function groupSizeSichtbar() {
  $("groupSizeBox").style.display = $("action").value === "ergaenzen" ? "block" : "none";
}

// ---------- Referenzbilder ----------
$("file").onchange = e => {
  const files = [...e.target.files].slice(0, maxRefs - refs.length);
  let pending = files.length;
  files.forEach(f => {
    const reader = new FileReader();
    reader.onload = () => {
      refs.push(reader.result); refPrompts.push("");
      if (!--pending) { drawThumbs(); setMode(mode); }
    };
    reader.readAsDataURL(f);
  });
  e.target.value = "";
};
function drawThumbs() {
  const kachel = (src, i) =>
    `<div class="thumb"><img src="${src}" alt="Referenz ${i + 1}"><i>${i + 1}</i>`
    + `<b onclick="dropRef(${i})">×</b></div>`;
  const rollen = mode === "gruppe";
  $("thumbs").className = "thumbs" + (rollen ? " rollen" : "");
  $("thumbs").innerHTML = rollen
    ? refs.map((src, i) =>
        `<div class="refrow">${kachel(src, i)}`
        + `<input class="refprompt" data-i="${i}" value="${esc(refPrompts[i] || "")}"`
        + ` placeholder="Wie soll Bild ${i + 1} dargestellt werden? (optional)"></div>`).join("")
    : refs.map(kachel).join("");
  [...document.querySelectorAll(".refprompt")].forEach(el =>
    el.addEventListener("input", () => { refPrompts[el.dataset.i] = el.value; }));
  $("refCount").textContent = refs.length ? `(${refs.length}/${maxRefs})` : "";
  refresh();
}
function dropRef(i) { refs.splice(i, 1); refPrompts.splice(i, 1); drawThumbs(); setMode(mode); }

// ---------- Ablauf ----------
let demoRef = null, ABLAEUFE = [], bloecke = [];

function blockZeichnen() {
  $("bloecke").innerHTML = bloecke.map((b, i) => `
    <div class="block" data-i="${i}">
      <div class="blockkopf">
        <input class="btitel" value="${esc(b.titel || "")}" placeholder="Name des Blocks">
        <a href="#" data-tu="hoch" title="nach oben">&uarr;</a>
        <a href="#" data-tu="runter" title="nach unten">&darr;</a>
        <a href="#" data-tu="weg" title="entfernen">&times;</a>
      </div>
      <div class="row4">
        <input type="number" class="banzahl" min="0" max="40" placeholder="Anzahl"
               title="Wie viele Bilder? Leer = eine je Zeile"
               ${b.art === "gruppe" ? "disabled" : ""}
               value="${b.art === "gruppe" ? "1" : (b.anzahl || "")}">
        <select class="bref">
          <option value="start"${b.referenz !== "letztes" ? " selected" : ""}>vom Startbild</option>
          <option value="letztes"${b.referenz === "letztes" ? " selected" : ""}>vom letzten Bild</option>
        </select>
        <select class="bart">
          <option value="behutsam"${b.art !== "gruppe" && b.vorlage !== "verwandeln" ? " selected" : ""}>behutsam ändern</option>
          <option value="verwandeln"${b.vorlage === "verwandeln" ? " selected" : ""}>verwandeln</option>
          <option value="aktion"${b.vorlage === "aktion" ? " selected" : ""}>Bewegung</option>
          <option value="gruppe"${b.art === "gruppe" ? " selected" : ""}>Gruppenbild</option>
        </select>
        <select class="bseed">
          <option value=""${!b.fest ? " selected" : ""}>eigener Seed</option>
          <option value="1"${b.fest ? " selected" : ""}>Seed wie Start</option>
        </select>
      </div>
      <label>Was bleibt unverändert?</label>
      <input class="bbleibt" value="${esc(b.bleibt || "")}" placeholder="z. B. die Person, ihr Gesicht und ihre Haltung">
      <label>Ein Bild je Zeile &ndash; oder oben eine Anzahl angeben</label>
      <textarea class="bbausteine"${b.art === "gruppe" ? " disabled" : ""}>${esc((b.bausteine || []).join("\n"))}</textarea>
      <div class="check">
        <input type="checkbox" class="bzurueck"${b.zurueck ? " checked" : ""}>
        <label>danach wieder das Startbild zeigen</label>
      </div>
    </div>`).join("");

  $("bloecke").querySelectorAll(".block").forEach(el => {
    const i = +el.dataset.i;
    el.querySelector(".btitel").oninput = e => bloecke[i].titel = e.target.value;
    el.querySelector(".bbleibt").oninput = e => bloecke[i].bleibt = e.target.value;
    el.querySelector(".bbausteine").oninput = e => {
      bloecke[i].bausteine = e.target.value.split("\n").filter(z => z.trim());
      demoDauer();
    };
    el.querySelector(".banzahl").oninput = e => {
      const n = parseInt(e.target.value, 10);
      bloecke[i].anzahl = Number.isFinite(n) && n > 0 ? n : undefined;
      demoDauer();
    };
    el.querySelector(".bref").onchange = e => bloecke[i].referenz = e.target.value;
    el.querySelector(".bseed").onchange = e => bloecke[i].fest = !!e.target.value;
    el.querySelector(".bzurueck").onchange = e => { bloecke[i].zurueck = e.target.checked; demoDauer(); };
    el.querySelector(".bart").onchange = e => {
      const w = e.target.value;
      bloecke[i].art = w === "gruppe" ? "gruppe" : undefined;
      bloecke[i].vorlage = w === "gruppe" ? undefined : w;
      // Ein Gruppenbild ist immer genau ein Bild; eine Anzahl daneben wuerde
      // nur eine Erwartung wecken, die der Server nicht einloest.
      if (w === "gruppe") { bloecke[i].bausteine = [""]; bloecke[i].anzahl = undefined; }
      blockZeichnen(); demoDauer();
    };
    el.querySelectorAll("[data-tu]").forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const tu = a.dataset.tu;
      if (tu === "weg") bloecke.splice(i, 1);
      else {
        const j = tu === "hoch" ? i - 1 : i + 1;
        if (j < 0 || j >= bloecke.length) return;
        [bloecke[i], bloecke[j]] = [bloecke[j], bloecke[i]];
      }
      blockZeichnen(); demoDauer();
    });
  });
}

$("blockNeu").onclick = e => {
  e.preventDefault();
  bloecke.push({titel: "Neuer Block", referenz: "start", vorlage: "verwandeln",
                bleibt: "die Person, ihr Gesicht und ihre Haltung", bausteine: [], zurueck: false});
  blockZeichnen(); demoDauer();
};
$("alsText").onclick = e => {
  e.preventDefault();
  const t = $("ablaufText");
  if (t.style.display === "none") {
    t.value = JSON.stringify(bloecke, null, 1); t.style.display = "block";
  } else {
    try { bloecke = JSON.parse(t.value); blockZeichnen(); demoDauer(); } catch (x) {
      return say("Der Text ist kein gültiges JSON: " + x.message, "err");
    }
    t.style.display = "none";
  }
};
$("ablaufWahl").onchange = () => {
  const a = ABLAEUFE.find(x => x.key === $("ablaufWahl").value);
  if (!a) return;
  bloecke = JSON.parse(JSON.stringify(a.bloecke));
  $("ablaufInfo").textContent = a.label;
  blockZeichnen(); demoDauer();
};
$("demoFile").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const leser = new FileReader();
  leser.onload = () => {
    demoRef = leser.result;
    $("demoPreview").src = demoRef; $("demoPreview").style.display = "block";
    $("demoRefNote").textContent = "Dein Foto wird als Basisbild verwendet. "
      + "Der Text unten beschreibt dann, wer darauf zu sehen ist.";
    $("demoPrompt").disabled = false;
    $("demoPromptLabel").textContent =
      "…kurz beschreiben, wer auf dem Bild ist (leer lassen: der Server liest es selbst)";
    $("demoPrompt").placeholder =
      "z. B. eine Frau Mitte dreißig mit kurzen blonden Haaren, dunkler Jacke";
    $("demoAbleitenZeile").style.display = "block";
    // Gleich beschreiben lassen, statt es erst beim Start zu tun: so steht
    // der Text vor dem Lauf da und laesst sich noch aendern.
    if (!$("demoPrompt").value.trim()) demoBeschreiben();
  };
  leser.readAsDataURL(f);
};
function demoDauer() {
  const n = parseInt($("demoSteps").value, 10) || 24;
  // Dieselbe Regel wie im Server: Anzahl schlaegt die Zahl der Zeilen.
  const proBlock = b => {
    const zeilen = (b.bausteine || []).length;
    if (b.art === "gruppe") return Math.min(zeilen, 1);
    return b.anzahl > 0 && zeilen ? b.anzahl : zeilen;
  };
  const erzeugt = 1 + bloecke.reduce((s, b) => s + proBlock(b), 0);
  const imVideo = erzeugt + bloecke.filter(b => b.zurueck).length;
  // Ein Ladevorgang je Block, der nicht vom Startbild ausgeht, plus einer.
  const laden = 2 + bloecke.filter(b => b.referenz === "letztes" || b.art === "gruppe").length;
  const minuten = Math.round((laden * 60 + erzeugt * (n * 1.5 + 3)) / 60);
  $("demoDauer").textContent = `${erzeugt} Bilder erzeugen, ${imVideo} im Video, `
    + `grob ${minuten} Minuten. Solange ist die Grafikkarte belegt.`;
}
["demoSteps", "demoBase", "demoDuration"].forEach(id => $(id).addEventListener("input", demoDauer));

// Gelten nur fuer den naechsten Start: "Bild" statt "Video" an einer Szene,
// und eine Szene ohne Startbild.
let ohneVideo = false, ohneBasis = false;

async function starteDemo() {
  const laeuftSchon = $("go").classList.contains("busy");
  buttonState("busy");
  if (!laeuftSchon) $("stage").dataset.file = "";
  say(laeuftSchon ? "Ablauf wird eingereiht …" : "Vorführung wird vorbereitet …");
  const res = await fetch("/api/demo", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      image: demoRef, prompt: $("demoPrompt").value, bloecke,
      base: parseInt($("demoBase").value, 10),
      steps: parseInt($("demoSteps").value, 10) || 24,
      duration: parseInt($("demoDuration").value, 10) || 20,
      // Ohne Video, wenn nur die Bilder gewollt sind: das Zusammenbauen
      // kostet Zeit und bei einem einzigen Bild ergibt es ohnehin nichts.
      ohne_video: !!ohneVideo,
      ohne_basis: !!ohneBasis
    })
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    buttonState("idle");
    return say(err.error || "Die Vorführung ließ sich nicht starten.", "err");
  }
  // Der Auftrag laeuft ab hier auf dem Server. Was beim Vorzeichnen
  // schiefgeht, darf die Fortschrittsabfrage nicht mitreissen -- sonst
  // bliebe der Knopf fuer immer auf "laeuft".
  try {
    if (!laeuftSchon) startSlots(1 + bloecke.reduce((s, b) => {
      const zeilen = (b.bausteine || []).length;
      if (b.art === "gruppe") return s + Math.min(zeilen, 1);
      return s + (b.anzahl > 0 && zeilen ? b.anzahl : zeilen);
    }, 0));
  } catch (e) {
    console.error(e);
  }
  poll();
}

// ---------- Start ----------
function say(text, cls = "") { $("status").textContent = text; $("status").className = cls; }

// Wie voll die Grafikkarte ist. Ein Auftrag, der eine Minute nichts sagt,
// sieht aus wie ein haengender -- hier sieht man, dass gerechnet wird.
function karteText(s) {
  const k = (s || {}).karte || {};
  return k.gesamt ? ` · Karte ${k.belegt}/${k.gesamt} GB` : "";
}

// ---------- Puls ----------
// Ein Sprachmodell braucht fuer einen Prompt fuenf bis dreissig Sekunden.
// Stille vor einem Knopf sieht in dieser Zeit aus wie ein Fehler. Also sagt
// die Zeile mit, was der Server gerade tut, und zaehlt die Sekunden mit --
// auch fuer die Aufrufe, die nicht durch die Warteschlange gehen.
let pulsUhr = null, pulsSeit = 0, pulsText = "";

function pulsAn(text) {
  pulsAus();
  pulsText = text;
  pulsSeit = Date.now();
  $("fill").parentElement.classList.add("puls");
  const schlag = async () => {
    const s = Math.round((Date.now() - pulsSeit) / 1000);
    let was = pulsText;
    // Was der Server von sich aus meldet, geht vor: "Baustein 2 von 5" sagt
    // mehr als "wird geschrieben".
    const st = await fetch("/api/status").then(r => r.json()).catch(() => null);
    let karte = "";
    if (st) {
      karte = karteText(st);
      if (st.stage) {
        was = st.stage;
        const f = st.fortschritt || {};
        if (f.von) $("fill").style.width = (100 * f.ist / f.von) + "%";
      }
    }
    if (pulsUhr) say(`${was} · ${s} s${karte}`);
  };
  schlag();
  pulsUhr = setInterval(schlag, 1000);
}

function pulsAus() {
  if (!pulsUhr) return;
  clearInterval(pulsUhr);
  pulsUhr = null;
  $("fill").parentElement.classList.remove("puls");
  $("fill").style.width = "0";
}

// Der Knopf zeigt den Zustand mit: gelb waehrend der Berechnung, kurz gruen
// wenn fertig, danach wieder normal.
function buttonState(state) {
  const go = $("go");
  go.classList.remove("busy", "done", "ready");
  clearTimeout(buttonState.timer);
  if (state === "busy") {
    // Nicht gesperrt: waehrend etwas rechnet, haengt ein Klick den naechsten
    // Auftrag hinten an. Sonst brauchte man die Warteschlange gar nicht.
    go.disabled = false; go.classList.add("busy");
    go.textContent = "läuft — noch einen einreihen";
    $("stop").style.display = "block";
  } else {
    go.disabled = false; go.textContent = MODES[mode].label;
    $("stop").style.display = "none";
    if (state === "done") {
      go.classList.add("done");
      buttonState.timer = setTimeout(() => go.classList.remove("done"), 2500);
    }
  }
}

// Eine Szene Stufe um Stufe bauen. Der Server zerlegt den Satz, erzeugt
// den Raum, jede Figur einzeln in ihrer Haltung und das Spiegelbild, und
// setzt dann eins ins andere. Laenger als ein Zug, aber die Haltung stimmt:
// ein Musterbild zeigt die Figur stehend, und stehend bleibt sie sonst
// auch dann, wenn die Szene sie liegend haben will.
async function stufenAufbau(text, ids, stil) {
  if (!text.trim()) return say("Bitte beschreiben, was zu sehen ist.", "err");
  let seed = parseInt($("seed").value, 10);
  if (isNaN(seed) || seed < 0) seed = Math.floor(Math.random() * 2 ** 31);
  buttonState("busy");
  const res = await fetch("/api/szenenbau", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      text: text, bausteine: ids, stil: stil || "",
      aspect: $("aspect").value, base: parseInt($("base").value, 10),
      steps: parseInt($("steps").value, 10), seed: seed,
      modell: $("gsModell").value})
  }).then(r => r.json()).catch(() => null);
  if (!res || res.error) {
    buttonState("idle");
    return say(res ? res.error : "Der Server ist nicht erreichbar.", "err");
  }
  say("Die Szene wird in Stufen aufgebaut …", "ok");
  poll();
}

async function start() {
  const prompt = $("prompt").value.trim();
  const need = mode === "gruppe" ? aktion().min : MODES[mode].refs;
  // Text->Bild aus den Musterbildern: nach aussen bleibt es der Reiter
  // Text->Bild, der Auftrag laeuft aber als Gruppenbild. Die Bilder holt
  // der Server selbst aus den Bausteinen -- hochladen muss hier niemand.
  const ausBild = mode === "t2i" && $("ausBildern").checked
                  && promptTeile.length > 0;
  // Der Stufenweg ist kein Auftrag an das Bildmodell, sondern eine Kette
  // davon. Er geht deshalb an einen eigenen Endpunkt und verlaesst start()
  // gleich wieder.
  if (ausBild && $("ausBildernWeg").value === "stufen") {
    return stufenAufbau(prompt, promptTeile, $("style").value);
  }
  const plan = ausBild ? ausBildernPlan(promptTeile) : null;
  if (plan) {
    const wahl = ACTIONS.find(a => a.key === $("ausBildernAktion").value);
    if (plan.ohne.length) {
      return say("Ohne Musterbild: "
        + plan.ohne.map(b => b.name).join(", ")
        + " — erst bei Bausteine mit ▣ eines erzeugen.", "err");
    }
    if (plan.reihe.length < (wahl ? wahl.min : 2)) {
      return say(`„${wahl ? wahl.label : "Diese Aktion"}“ braucht ${
        wahl ? wahl.min : 2} Musterbilder.`, "err");
    }
    if (plan.reihe.length > maxRefs) {
      return say(`Höchstens ${maxRefs} Vorlagen — hier sind es ${
        plan.reihe.length}.`, "err");
    }
  }
  // Ein Effekt bringt seine eigene Anweisung mit -- /upscale, /removebg und
  // die uebrigen brauchen kein Wort Eingabe. Der Server sieht das genauso.
  if (!prompt && !templates[mode] && !$("effect").value)
    return say("Bitte einen Prompt eingeben.", "err");
  if (refs.length < need) return say(`Bitte ${need} Referenzbild(er) hochladen.`, "err");
  if (mode === "varianten" && $("paint").value !== AXIS_OFF && !$("paintTarget").value.trim()) {
    paintPreview();
    return say("Die Farbachse braucht ein Ziel — oder stell sie auf „unverändert lassen“.", "err");
  }

  let seed = parseInt($("seed").value, 10);
  if (isNaN(seed) || seed < 0) { seed = Math.floor(Math.random() * 2 ** 31); $("seed").value = seed; }

  const body = {
    mode: plan ? "gruppe" : mode, prompt,
    negative_prompt: $("negative").value,
    // Die Musterbilder nennt die Seite nur bei der Kennung; laden tut sie
    // der Server aus dem Projekt. Base64 durch den Browser zu schicken,
    // was ohnehin schon auf der Platte liegt, waere unnoetig.
    bausteine: plan ? plan.reihe.map(b => b.id) : [],
    einstellung: mode === "t2i" ? $("t2iEinst").value : "",
    spiegelung: mode === "t2i" ? $("t2iSpiegel").value : "",
    images: need ? refs : [],
    image_prompts: mode === "gruppe" ? refs.map((_, i) => refPrompts[i] || "") : [],
    aspect: $("aspect").value, base: parseInt($("base").value, 10),
    follow_reference: $("follow").checked,
    steps: parseInt($("steps").value, 10),
    seed, count: parseInt($("count").value, 10) || 1,
    sweep: $("sweep").value, lock_seed: $("lockSeed").checked,
    view: $("view").value, effect: $("effect").value, form: $("form").value,
    keep: $("keep").value, scenario: $("scenario").value,
    cover: coverFelder(),
    action: plan ? $("ausBildernAktion").value : $("action").value,
    group_size: parseInt($("groupSize").value, 10) || 2,
    paint: $("paint").value, palette: $("palette").value,
    scene: $("scene").value,
    angle: $("angle").value, device: $("device").value,
    material: $("material").value, subject: $("subject").value,
    haltung: $("haltung").value, kleidung: $("kleidung").value,
    camera: $("camera").value,
    // In den Varianten haben Stil und Licht eigene Achsenfelder, damit sich
    // beide auf "wuerfeln" stellen lassen.
    style: mode === "varianten" ? $("vstyle").value : $("style").value,
    light: mode === "varianten" ? $("vlight").value : $("light").value,
    paint_target: $("paintTarget").value,
    true_cfg_scale: parseFloat($("cfg").value),
    transparent: $("transparent").checked,
    streng: $("streng").checked
  };

  const laeuftSchon = $("go").classList.contains("busy");
  buttonState("busy");
  $("transNote").style.display = "none";
  say(laeuftSchon ? "Wird eingereiht …" : "Auftrag wird gestartet …");
  // Nur wenn nichts laeuft, das Mosaik leeren -- sonst verschwaende man die
  // Anzeige des Auftrags, der gerade rechnet.
  if (!laeuftSchon) { $("stage").dataset.file = ""; paintSeries([], body.count, 1); }

  // Bricht die Verbindung weg, muss der Knopf zurueckspringen -- sonst
  // steht er fuer immer auf "laeuft", ohne dass etwas rechnet.
  const res = await fetch("/api/generate", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
  }).catch(() => null);
  if (!res) {
    buttonState("idle");
    return say("Der Server ist nicht erreichbar.", "err");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({error: res.statusText}));
    buttonState("idle");
    return say(err.error, "err");
  }
  poll();
}
$("go").onclick = () => {
  if (mode === "demo") return starteDemo();
  if (mode === "seiten") return seitenStarten();
  start();
};
$("stop").onclick = () => {
  // Nur den laufenden Auftrag. Wartende nimmt man einzeln aus der Liste.
  fetch("/api/cancel", {method: "POST"});
  say("Abbruch des laufenden Auftrags angefordert …");
};

// ---------- Freitexteingabe ----------
// Der Server liefert einen fertigen Satz Einstellungen. Die werden sichtbar in
// die Regler geschrieben, bevor es losgeht -- so ist nachvollziehbar, was das
// Sprachmodell verstanden hat, und korrigierbar, wenn es danebenlag.
function applyPlan(plan) {
  setMode(plan.mode);
  $("prompt").value = plan.prompt || "";
  ["aspect", "style", "light", "camera", "view", "sweep", "effect", "form"].forEach(
    k => { if (plan[k] !== undefined) $(k).value = plan[k]; });
  $("base").value = plan.base;
  $("count").value = plan.count;
  $("steps").value = plan.steps;
  $("transparent").checked = !!plan.transparent;
  $("lockSeed").checked = !!plan.lock_seed;
  refresh();
}

async function sendChat() {
  const text = $("chat").value.trim();
  if (!text) return;
  $("chatGo").disabled = true;
  $("chatNote").className = "hint";
  $("chatNote").textContent = "verstehe …";

  const res = await fetch("/api/chat", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text, has_images: refs.length})
  }).catch(() => null);
  $("chatGo").disabled = false;

  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    $("chatNote").className = "hint err";
    $("chatNote").textContent = err.error || "Das Sprachmodell antwortet nicht.";
    return;
  }
  const plan = await res.json();
  applyPlan(plan);
  zeigeGespraech(plan.verlauf);
  $("chatNote").textContent = (plan.note || "Verstanden.")
    + ` Einstellungen unten prüfen, dann auf „${MODES[mode].label}“.`;
  $("chat").value = "";
  // Bewusst kein Start: erst Text, dann Prompt, dann prüfen, dann Bild.
  $("go").classList.add("ready");
  setTimeout(() => $("go").classList.remove("ready"), 6000);
}
$("chatGo").onclick = sendChat;

// Der Verlauf steht beim Server; hier wird nur gezeigt, was war. So ist
// nachvollziehbar, worauf sich ein "und jetzt noch einen Hut dazu" bezieht.
function zeigeGespraech(verlauf) {
  if (!Array.isArray(verlauf) || !verlauf.length) {
    $("chatLog").innerHTML = "";
    return;
  }
  $("chatLog").innerHTML = verlauf.map(z => {
    if (z.wer === "user") {
      return `<div class="zug ich"><b>du</b>${esc(z.was)}</div>`;
    }
    let notiz = z.was;
    try { notiz = JSON.parse(z.was).note || z.was; } catch (e) { /* roh zeigen */ }
    return `<div class="zug"><b>verstanden</b>${esc(notiz)}</div>`;
  }).join("")
    + `<p class="hint"><a href="#" onclick="gespraechNeu();return false">`
    + `neu anfangen</a> — vergisst das Bisherige.</p>`;
}

async function gespraechNeu() {
  await fetch("/api/chat", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({neu: true})
  }).catch(() => null);
  $("chatLog").innerHTML = "";
  say("Gespräch zurückgesetzt.", "ok");
}
$("beenden").onclick = e => { e.preventDefault(); programmBeenden(); };
$("ableiten").onclick = e => { e.preventDefault(); promptAusBild(); };
$("ableitenBild").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const leser = new FileReader();
  leser.onload = () => promptAusBild(leser.result);
  leser.readAsDataURL(f);
};
$("demoAbleiten").onclick = e => { e.preventDefault(); demoBeschreiben(); };

// Im Ablauf beschreibt der Text, wen das Modell bewahren soll -- dafuer
// genuegt der kurze Halbsatz, nicht der ganze Bildprompt.
async function demoBeschreiben() {
  if (!demoRef) return say("Erst ein Startbild wählen.", "err");
  say("Das Startbild wird gelesen …");
  const g = await bildLesen("/api/bild-lesen", demoRef);
  if (!g || !g.beschreibung) return;
  $("demoPrompt").value = g.beschreibung;
  $("demoRefNote").textContent = "Im Startbild erkannt: " + g.beschreibung
    + (g.geschlecht !== "unklar" ? ` (${g.geschlecht})` : "");
  say("Beschreibung aus dem Startbild übernommen. Unten änderbar.", "ok");
}

// Rueckwaerts: das hochgeladene Bild ansehen und den Prompt dazu schreiben.
// Lesen darf nur das Sprachmodell, deshalb geht es nicht waehrend eines
// Auftrags -- beide wollen dieselbe Grafikkarte.
// Das Bild einmal ansehen lassen. `pfad` unterscheidet die kurze Fassung
// (wer ist zu sehen) von der langen (der ganze Bildprompt).
async function bildLesen(pfad, bild) {
  const res = await fetch(pfad, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({image: bild})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das Bild ließ sich nicht lesen.", "err");
    return null;
  }
  return res.json();
}

// Der umgekehrte Weg: aus einem Bild den Prompt. Ohne Angabe wird das erste
// Referenzbild genommen, damit man es nicht zweimal hochladen muss.
async function promptAusBild(bild) {
  bild = bild || refs[0];
  if (!bild) return say("Erst ein Bild wählen.", "err");
  say("Das Bild wird gelesen …");
  const g = await bildLesen("/api/bild-prompt", bild);
  if (!g) return;
  $("prompt").value = g.prompt;
  if (g.stil) $("style").value = g.stil;
  if (g.licht) $("light").value = g.licht;
  if (g.kamera) $("camera").value = g.kamera;
  const gesetzt = [["Stil", g.stil], ["Licht", g.licht], ["Objektiv", g.kamera]]
    .filter(x => x[1]).map(x => x[0]).join(", ");
  say("Prompt aus dem Bild abgeleitet"
      + (gesetzt ? ` — ${gesetzt} mitgestellt.` : ".") + " Bitte gegenlesen.", "ok");
}
// Mehrzeilig: Eingabe macht einen Umbruch, abgeschickt wird mit Strg+Eingabe
// oder dem Pfeil daneben.
$("chat").addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); }
});

// ---------- Bausteine ----------
// Personen, Orte und Gegenstaende zum Wiederverwenden. Was sich aendern darf,
// steht als Luecke in geschweiften Klammern und wird beim Benutzen gefuellt.
let BAUSTEINE = [], BSARTEN = [], MIMIKLISTE = [], STILLISTE = [],
    EINSTELLUNGEN = [], GEZEICHNET = [], WESENLISTE = [], ERZAEHLERLISTE = [], FOLGENLISTE = [];
const LUECKE = /\{([a-zA-Z][a-zA-Z0-9_]{0,29})\}/g;

function luecken(text) {
  return [...new Set([...(text || "").matchAll(LUECKE)].map(m => m[1]))];
}

// Aufgeklappte Bausteine. Wie bei den Szenen: zu steht eine Zeile da, auf
// steht alles. Mit dreissig Bausteinen war die volle Liste nicht mehr zu
// ueberblicken.
const BSOFFEN = new Set();

function bausteinKlappen(id) {
  if (BSOFFEN.has(id)) BSOFFEN.delete(id);
  else BSOFFEN.add(id);
  zeigeBausteine(BAUSTEINE);
}

function zeigeBausteine(liste) {
  if (!Array.isArray(liste)) return;
  BAUSTEINE = liste;
  const label = k => (BSARTEN.find(a => a.key === k) || {}).label || k;
  const stilname = k => (STILLISTE.find(x => x.key === k) || {}).label || k;
  $("bausteinListe").innerHTML = liste.length
    ? liste.map(b => {
      const offen = BSOFFEN.has(b.id);
      const person = b.art === "person";
      // Was die Kopfzeile sagt, wenn alles zu ist.
      const wesenname = k => (WESENLISTE.find(x => x.key === k) || {}).label || k;
      const kurz = [label(b.art),
                    b.wesen && b.wesen !== "mensch" ? wesenname(b.wesen) : "",
                    (b.alias || []).length ? "= " + b.alias.join(", ") : "",
                    b.bild ? "Bild" : "",
                    b.bild_augen ? "Augen" : "",
                    person && !(b.gesicht || "").trim() ? "ohne Gesicht" : "",
                    person && !(b.kleidung || "").trim() ? "ohne Kleidung" : "",
                    person && !(b.haut || "").trim() ? "ohne Hautton" : "",
                    b.stil ? stilname(b.stil) : ""].filter(Boolean).join(" · ");
      const andere = liste.filter(x => x.id !== b.id && x.art === b.art);
      return `<div class="baustein${offen ? " auf" : ""}">
        <div class="bskopf">
          <span class="pfeil" onclick="bausteinKlappen('${b.id}')">${
            offen ? "▾" : "▸"}</span>
          ${b.bild ? `<img src="/outputs/${b.bild}" alt="${esc(b.name)}"
               onclick="show('${b.bild}')">` : `<span class="ohnebild">?</span>`}
          <div class="bstext" onclick="bausteinKlappen('${b.id}')">
            <b>${esc(b.name)}</b><br><span class="art">${esc(kurz)}</span>
          </div>
          <span class="knopf" onclick="bausteinInPrompt('${b.id}')"
            title="in den Prompt bei Text→Bild übernehmen">→</span>
          <span class="knopf" onclick="bausteinLaden('${b.id}')"
            title="bearbeiten">✎</span>
          <span class="knopf" onclick="bausteinBild('${b.id}')"
            title="${b.bild ? "Musterbild neu erzeugen und ersetzen"
                            : "Musterbild dazu erzeugen"}">▣</span>
          ${person ? `<span class="knopf" onclick="bausteinAugen('${b.id}')"
            title="${b.bild_augen ? "Blick in die Augen neu erzeugen"
                                  : "Blick in die Augen erzeugen"}">◉</span>` : ""}
          <span class="knopf" onclick="bausteinWeg('${b.id}')"
            title="löschen">×</span>
        </div>
        ${!offen ? "" : `<div class="bsdetail">
          <code>${esc(b.prompt)}</code>
          ${person && b.wesen && b.wesen !== "mensch"
            ? `<div><span class="art">Wesen</span> ${esc(wesenname(b.wesen))}</div>`
            : ""}
          ${person ? `<div class="hautzeile"><span class="art">Haut</span> ${
            (b.haut || "").trim() ? esc(b.haut)
              : `<i>noch nicht gesetzt — gilt für Ganzbild und Großaufnahme</i>`
            }</div>` : ""}
          ${person && (b.gesicht || "").trim()
            ? `<div><span class="art">Gesicht</span> ${esc(b.gesicht)}</div>` : ""}
          ${person && (b.kleidung || "").trim()
            ? `<div><span class="art">Kleidung</span> ${esc(b.kleidung)}</div>` : ""}
          ${Object.keys(b.variablen || {}).length
            ? `<div><span class="art">Lücken</span> ${esc(
                Object.entries(b.variablen).map(([k, v]) => k + ": " + v)
                  .join(" · "))}</div>` : ""}
          ${b.bild_augen ? `<div><span class="art">Augen</span>
              <img class="augenbild" src="/outputs/${b.bild_augen}"
                alt="Blick in die Augen" onclick="show('${b.bild_augen}')"></div>`
            : ""}
          ${andere.length ? `<select class="verschmelzen"
               onchange="bausteineVerschmelzen('${b.id}', this)">
              <option value="">↦ aufgehen in …</option>
              ${andere.map(x =>
                `<option value="${x.id}">${esc(x.name)}</option>`).join("")}
            </select>` : ""}
        </div>`}
      </div>`;
    }).join("")
    : `<p class="hint">Noch keine Bausteine in diesem Projekt.</p>`;
  // Aus wessen Sicht erzaehlt wird: nur Personen kommen dafuer infrage.
  // Die Liste waechst mit den Bausteinen, deshalb steht sie hier.
  const wer = $("gsErzaehlerWer").value;
  $("gsErzaehlerWer").innerHTML = `<option value="">— niemand bestimmtes —</option>`
    + liste.filter(b => b.art === "person").map(b =>
        `<option value="${esc(b.name)}">${esc(b.name)}</option>`).join("");
  $("gsErzaehlerWer").value = wer;
  zeigeWahl();
  zeigeSelbstszenen();
}

// Zu jeder Luecke ein Feld. `mehrzeilig` erlaubt eine Werteliste -- daraus
// wird spaeter eine Serie mit einem Bild je Zeile.
function luckenFelder(wohin, text, vorgaben, mehrzeilig) {
  const namen = luecken(text);
  $(wohin).innerHTML = namen.map(n => `
    <label for="${wohin}-${n}">${esc(n)}</label>
    ${mehrzeilig
      ? `<textarea id="${wohin}-${n}" class="lueckenfeld" data-l="${n}"
           style="min-height:40px">${esc((vorgaben || {})[n] || "")}</textarea>
         <p class="hint"><a href="#" onclick="luckenVorschlaege('${n}');return false">
           10 Vorschläge</a> — eine Zeile je Bild.</p>`
      : `<input id="${wohin}-${n}" class="lueckenfeld" data-l="${n}"
           value="${esc((vorgaben || {})[n] || "")}">`}`).join("");
  return namen;
}

function lueckenWerte(wohin) {
  const werte = {};
  $(wohin).querySelectorAll(".lueckenfeld").forEach(
    el => werte[el.dataset.l] = el.value);
  return werte;
}

// Diese Aufrufe gehen ans Sprachmodell und dauern. Die uebrigen -- speichern,
// loeschen, zusammensetzen -- sind sofort da und brauchen keinen Puls.
const LANGSAM = {
  aktualisieren: "Die Bausteine werden nachgezogen",
  auffrischen: "Die Personen werden aufgeteilt",
  prompt: "Der Prompt wird geschrieben",
  teilprompt: "Der Prompt wird geschrieben",
  luecken: "Vorschläge werden gesucht",
  vorschlagen: "Die Bausteine werden geschrieben",
};

async function bausteinRuf(rumpf) {
  const puls = LANGSAM[rumpf.tu];
  if (puls) pulsAn(puls);
  const res = await fetch("/api/baustein", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (puls) pulsAus();
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  return res.json();
}

async function bausteineHolen() {
  const info = await fetch("/api/info").then(r => r.json()).catch(() => null);
  if (info) zeigeBausteine(info.bausteine);
}

$("bsErzeugen").onclick = async e => {
  e.preventDefault();
  const text = $("bsText").value.trim();
  if (!text) return say("Erst auf Deutsch beschreiben.", "err");
  say("Der Prompt wird geschrieben …");
  const g = await bausteinRuf({tu: "prompt", text, art: $("bsArt").value});
  if (!g) return;
  $("bsPrompt").value = g.prompt;
  $("bsGesicht").value = g.gesicht || "";
  $("bsKleidung").value = g.kleidung || "";
  $("bsHaut").value = g.haut || "";
  luckenFelder("bsVariablen", g.prompt, g.variablen, false);
  say(`Prompt erzeugt, ${luecken(g.prompt).length} Lücke(n). Bitte gegenlesen.`, "ok");
};

// Gesicht und Kleidung einzeln schreiben lassen. Beide Felder entstehen
// schon beim "Prompt daraus erzeugen" mit -- das hier ist fuer danach: eine
// Kleidung, die man auf Deutsch hineingetippt hat, kommt englisch zurueck.
async function teilSchreiben(feld, id) {
  const eigen = $(id).value.trim();
  const text = eigen || $("bsText").value.trim();
  if (!text) return say("Erst beschreiben — im Feld oder oben auf Deutsch.", "err");
  say("Der Prompt wird geschrieben …");
  const g = await bausteinRuf({tu: "teilprompt", feld, text,
                               person: $("bsPrompt").value});
  if (!g) return;
  $(id).value = g.text;
  say("Geschrieben. Bitte gegenlesen.", "ok");
}

$("bsGesichtNeu").onclick = e => {
  e.preventDefault();
  teilSchreiben("gesicht", "bsGesicht");
};

$("bsKleidungNeu").onclick = e => {
  e.preventDefault();
  teilSchreiben("kleidung", "bsKleidung");
};

$("bsHautNeu").onclick = e => {
  e.preventDefault();
  teilSchreiben("haut", "bsHaut");
};

$("bsPrompt").addEventListener("input", () => {
  luckenFelder("bsVariablen", $("bsPrompt").value, lueckenWerte("bsVariablen"), false);
});

function bausteinAusFeldern() {
  return {id: $("bsPrompt").dataset.id || "", art: $("bsArt").value,
          name: $("bsName").value, prompt: $("bsPrompt").value,
          gesicht: $("bsGesicht").value, kleidung: $("bsKleidung").value,
          haut: $("bsHaut").value, wesen: $("bsWesen").value,
          alias: $("bsAlias").value,
          stil: musterStil(), variablen: lueckenWerte("bsVariablen")};
}

// Der Stil fuers Musterbild: was im Feld steht, sonst der der Geschichte.
// Er haengt nur am Bild -- der Prompt des Bausteins bleibt stilfrei, sonst
// koennte ihn keine zweite Geschichte mehr anders zeichnen.
function musterStil() {
  return $("bsStil").value || $("gsStil").value || "";
}

// Gesicht und Kleidung gibt es nur bei Personen. Ein Ort hat kein Gesicht,
// und ein leeres Feld, das nie etwas tut, verwirrt nur.
function personFelder() {
  $("bsPersonBox").style.display =
    $("bsArt").value === "person" ? "block" : "none";
}
$("bsArt").addEventListener("change", personFelder);

$("bsSpeichern").onclick = async e => {
  e.preventDefault();
  if (!$("bsPrompt").value.trim()) return say("Kein Prompt.", "err");
  const b = await bausteinRuf({tu: "speichern", baustein: bausteinAusFeldern()});
  if (!b) return;
  await bausteineHolen();
  say(`„${b.name}“ gespeichert.`, "ok");
  bausteinLeeren();
};

$("bsBild").onclick = async e => {
  e.preventDefault();
  if (!$("bsPrompt").value.trim()) return say("Kein Prompt.", "err");
  const b = await bausteinRuf({tu: "speichern", baustein: bausteinAusFeldern()});
  if (!b) return;
  await bausteineHolen();
  // Mit den Vorgaben gefuellt -- das Bild soll den Baustein zeigen, wie er
  // gemeint ist, nicht mit offenen Luecken.
  const g = await bausteinRuf({tu: "zusammensetzen", ids: [b.id],
                               werte: b.variablen, freistellen: true,
                               stil: musterStil()});
  if (!g) return;
  await einreihenEinfach({prompt: g.prompt, baustein: b.id, aspect: "3:4"});
  const dazu = await augenDazu(b, musterStil());
  // Aufraeumen nicht vergessen: bleibt die Kennung stehen, ueberschreibt der
  // naechste Baustein diesen hier. Genau das ist passiert.
  bausteinLeeren();
  say(`„${b.name}“ gespeichert, Bild dazu eingereiht${dazu}.`, "ok");
};

// Zwei Bausteine, eine Figur. Passiert, wenn das Sprachmodell erst "Frau"
// vorschlaegt und die Figur spaeter "Nora" heisst. Der eine geht im anderen
// auf, und alle Geschichten nennen danach den bleibenden Namen.
async function bausteineVerschmelzen(von, feld) {
  const nach = feld.value;
  feld.value = "";
  if (!nach) return;
  const a = BAUSTEINE.find(x => x.id === von);
  const b = BAUSTEINE.find(x => x.id === nach);
  if (!a || !b) return;
  if (!confirm(`„${a.name}“ in „${b.name}“ aufgehen lassen? `
               + `„${a.name}“ verschwindet, und alle Szenen sagen danach `
               + `/${b.name}.`)) return;
  const g = await bausteinRuf({tu: "zusammenfuehren", von, nach});
  if (!g) return;
  await bausteineHolen();
  await gsListe(GSAKTUELL);            // die Geschichte kann sich geaendert haben
  say(`„${g.alter_name}“ ist in „${g.ziel.name}“ aufgegangen`
      + (g.zeilen ? `, ${g.zeilen} Szenenzeile(n) umbenannt.` : "."), "ok");
}

// Bausteine entstehen zuerst ohne Bild -- erst der Text, dann sieht man, ob
// er taugt. Das Musterbild kommt hinterher, je Baustein einzeln.
async function bausteinBild(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!b) return;
  // Ein vorhandenes Bild wird ersetzt, nicht ergaenzt -- das sagt man besser
  // vorher, sonst ist das gute von gestern weg.
  if (b.bild && !confirm(`Das Musterbild von „${b.name}“ neu erzeugen? `
                         + "Das bisherige wird ersetzt.")) return;
  // Der zuletzt benutzte Stil des Bausteins gilt weiter, solange keiner
  // gewaehlt ist: ein zweiter Anlauf soll nicht ploetzlich anders aussehen.
  const stil = $("bsStil").value || b.stil || $("gsStil").value || "";
  const g = await bausteinRuf({tu: "zusammensetzen", ids: [id],
                               werte: b.variablen, freistellen: true, stil});
  if (!g) return;
  if (stil !== (b.stil || "")) {
    await bausteinRuf({tu: "speichern", baustein: {...b, stil}});
  }
  await einreihenEinfach({prompt: g.prompt, baustein: id, aspect: "3:4"});
  const dazu = await augenDazu(b, stil);
  say(`Bild zu „${b.name}“ eingereiht${dazu}.`, "ok");
}

// Zu einer Person gehoeren zwei Bilder: die ganze Gestalt und der Blick in
// die Augen. Sie entstehen zusammen -- beide sind schlichte Text-zu-Bild-
// Auftraege, laufen also in einem Ladevorgang durch und kosten kaum mehr
// als einer. Ohne Gesichtsbeschreibung entfaellt der zweite.
async function augenDazu(b, stil) {
  if (b.art !== "person" || !(b.gesicht || "").trim()) return "";
  const a = await bausteinRuf({tu: "zusammensetzen", ids: [b.id], augen: true,
                               werte: b.variablen, stil});
  if (!a) return "";
  await einreihenEinfach({prompt: a.prompt, baustein: b.id,
                          baustein_feld: "bild_augen", aspect: "1:1"});
  return " samt Blick in die Augen";
}

// Personen aus der Zeit vor der Trennung nachziehen. Eine Geschichte, die
// sie benutzt, bekommt die Aenderung von selbst: ihre Bloecke werden aus den
// Bausteinen gebaut, nicht aus einer alten Abschrift.
$("bsAuffrischen").onclick = async e => {
  e.preventDefault();
  if (!confirm("Bei allen Personen ohne Gesicht oder Kleidung beides aus dem "
               + "vorhandenen Prompt herauslösen?")) return;
  const g = await bausteinRuf({tu: "auffrischen"});
  if (!g) return;
  if (!g.neu.length) return say(g.hinweis || "Nichts aufzufrischen.", "ok");
  await bausteineHolen();
  say(`Aufgefrischt: ${g.neu.map(b => b.name).join(", ")}.`, "ok");
};

// Einen Baustein nach Text->Bild uebernehmen. Angehaengt, nicht ersetzt:
// so lassen sich mehrere hintereinander holen und von Hand verbinden.
async function bausteinInPrompt(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!b) return;
  const g = await bausteinRuf({tu: "zusammensetzen", ids: [id],
                               werte: b.variablen});
  if (!g || !g.prompt) return;
  setMode("t2i");
  const da = $("prompt").value.trim();
  $("prompt").value = da ? `${da}, ${g.prompt}` : g.prompt;
  $("prompt").focus();
  if (!promptTeile.includes(id)) promptTeile.push(id);
  ausBildernZeigen();
  say(`„${b.name}“ in den Prompt übernommen.`, "ok");
}

// Zu einer Person gehoert ein zweites Bild: die Grossaufnahme der Augen.
// Sie zeigt, was bei \augen entsteht -- und deckt auf, wenn Gesicht und
// Koerper nicht denselben Menschen beschreiben.
async function bausteinAugen(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!b) return;
  if (!(b.gesicht || "").trim()) {
    bausteinLaden(id);
    return say("Erst eine Gesichtsbeschreibung eintragen — "
               + "daraus entsteht die Großaufnahme.", "err");
  }
  if (b.bild_augen && !confirm(`Den Blick in die Augen von „${b.name}“ neu `
                               + "erzeugen? Das bisherige Bild wird ersetzt."))
    return;
  const stil = $("bsStil").value || b.stil || $("gsStil").value || "";
  const g = await bausteinRuf({tu: "zusammensetzen", ids: [id], augen: true,
                               werte: b.variablen, stil});
  if (!g) return;
  await einreihenEinfach({prompt: g.prompt, baustein: id,
                          baustein_feld: "bild_augen", aspect: "1:1"});
  say(`Blick in die Augen von „${b.name}“ eingereiht.`, "ok");
}

$("bsLeeren").onclick = e => { e.preventDefault(); bausteinLeeren(); };

function bausteinLeeren() {
  ["bsName", "bsText", "bsPrompt", "bsGesicht", "bsKleidung", "bsHaut"]
    .forEach(id => $(id).value = "");
  $("bsStil").value = "";
  $("bsWesen").value = "";
  $("bsAlias").value = "";
  personFelder();
  $("bsPrompt").dataset.id = "";
  $("bsVariablen").innerHTML = "";
  bausteinKopf();
}

// Ob gerade ein neuer Baustein entsteht oder ein vorhandener geaendert wird,
// muss man sehen koennen -- sonst ueberschreibt man aus Versehen.
function bausteinKopf() {
  const id = $("bsPrompt").dataset.id;
  const b = id && BAUSTEINE.find(x => x.id === id);
  $("bsKopf").innerHTML = b
    ? `Ändert „${esc(b.name)}“ <a href="#" onclick="bausteinLeeren();return false"
         style="font-size:11.5px">stattdessen neu anlegen</a>`
    : "Neu anlegen";
}

function bausteinLaden(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!b) return;
  $("bsArt").value = b.art;
  $("bsName").value = b.name;
  $("bsPrompt").value = b.prompt;
  $("bsGesicht").value = b.gesicht || "";
  $("bsKleidung").value = b.kleidung || "";
  $("bsHaut").value = b.haut || "";
  $("bsWesen").value = b.wesen || "";
  $("bsStil").value = b.stil || "";
  $("bsAlias").value = (b.alias || []).join(", ");
  $("bsPrompt").dataset.id = b.id;
  personFelder();
  luckenFelder("bsVariablen", b.prompt, b.variablen, false);
  bausteinKopf();
  say(`„${b.name}“ geladen. Ändern und speichern.`);
}

async function bausteinWeg(id) {
  const b = BAUSTEINE.find(x => x.id === id);
  if (!confirm(`„${b ? b.name : id}“ löschen? Der Verweis verschwindet auch `
               + "aus allen Szenen dieses Projekts.")) return;
  const g = await bausteinRuf({tu: "loeschen", id});
  if (!g) return;
  await bausteineHolen();
  // Die Geschichte neu laden: ihre Zeilen stehen jetzt anders in der Datei.
  if (GSAKTUELL) await gsOeffnen(GSAKTUELL, gsBandNr);
  say("Baustein gelöscht"
      + (g.zeilen ? `, aus ${g.zeilen} Szenenzeile(n) entfernt.` : "."), "ok");
}

// --- Zusammensetzen ---
function zeigeWahl() {
  $("bsWahl").innerHTML = BAUSTEINE.length
    ? BAUSTEINE.map(b => `<label class="wahl"><input type="checkbox"
        class="bswahl" value="${b.id}"> ${esc(b.name)}</label>`).join("")
    : "";
  $("bsWahl").querySelectorAll(".bswahl").forEach(
    el => el.onchange = wahlGeaendert);
  wahlGeaendert();
}

function gewaehlte() {
  const ids = [...$("bsWahl").querySelectorAll(".bswahl:checked")].map(el => el.value);
  return BAUSTEINE.filter(b => ids.includes(b.id));
}

function wahlGeaendert() {
  const teile = gewaehlte();
  const text = teile.map(b => b.prompt).join(" ");
  const vorgaben = {};
  teile.forEach(b => Object.assign(vorgaben, b.variablen || {}));
  luckenFelder("bsFelder", text, {...vorgaben, ...lueckenWerte("bsFelder")}, true);
  $("bsFelder").querySelectorAll(".lueckenfeld").forEach(
    el => el.addEventListener("input", vorschau));
  vorschau();
}

// Eine Luecke mit mehreren Zeilen ergibt eine Serie: ein Bild je Zeile.
function serienWerte() {
  const werte = lueckenWerte("bsFelder");
  let laenge = 1;
  Object.values(werte).forEach(v => {
    const zeilen = String(v).split("\n").filter(z => z.trim());
    if (zeilen.length > laenge) laenge = zeilen.length;
  });
  const reihe = [];
  for (let i = 0; i < laenge; i++) {
    const eins = {};
    Object.entries(werte).forEach(([k, v]) => {
      const zeilen = String(v).split("\n").filter(z => z.trim());
      eins[k] = zeilen.length ? zeilen[Math.min(i, zeilen.length - 1)].trim() : "";
    });
    reihe.push(eins);
  }
  return reihe;
}

// Zehn verschiedene Hosen fuer die Luecke {hose}: das Sprachmodell kennt
// den Satz, in dem sie steht, und schlaegt Passendes vor.
async function luckenVorschlaege(name) {
  const teile = gewaehlte();
  const umfeld = teile.map(b => b.prompt).join(" ");
  say(`Vorschläge für „${name}“ …`);
  const g = await bausteinRuf({tu: "vorschlaege", luecke: name,
                               umfeld, anzahl: 10});
  if (!g) return;
  const feld = $("bsFelder-" + name);
  if (feld) {
    feld.value = g.werte.join("\n");
    feld.dispatchEvent(new Event("input"));
  }
  say(`${g.werte.length} Vorschläge eingesetzt — Zeilen ändern oder löschen.`, "ok");
}

async function vorschau() {
  const teile = gewaehlte();
  if (!teile.length) { $("bsVorschau").value = ""; return; }
  const reihe = serienWerte();
  const g = await bausteinRuf({tu: "zusammensetzen",
                               ids: teile.map(b => b.id), werte: reihe[0]});
  if (!g) return;
  // Den reinen Prompt getrennt aufheben -- ihn spaeter aus der Anzeige
  // zurueckzuschneiden waere bruechig.
  $("bsVorschau").dataset.prompt = g.prompt;
  $("bsVorschau").value = reihe.length > 1
    ? `${g.prompt}\n\n… und ${reihe.length - 1} weitere daraus`
    : g.prompt;
}

$("bsUebernehmen").onclick = e => {
  e.preventDefault();
  const text = $("bsVorschau").dataset.prompt || "";
  if (!text.trim()) return say("Erst Bausteine anhaken.", "err");
  setMode("t2i");
  $("prompt").value = text;
  say("In den Prompt übernommen.", "ok");
};

$("bsSerie").onclick = async e => {
  e.preventDefault();
  const teile = gewaehlte();
  if (!teile.length) return say("Erst Bausteine anhaken.", "err");
  const ids = teile.map(b => b.id);
  const reihe = serienWerte();
  const prompts = [];
  let vorlage = "";
  for (const werte of reihe) {
    const g = await bausteinRuf({tu: "zusammensetzen", ids, werte});
    if (!g) return;
    prompts.push(g.prompt);
    vorlage = g.vorlage;
  }
  // Die Szene behaelt ihre Luecken und die zuletzt benutzten Werte -- so
  // laesst sie sich spaeter wiederholen und weiter abwandeln.
  const name = $("szName").value.trim();
  let merken = null;
  if (name) {
    merken = await bausteinRuf({tu: "speichern", baustein: {
      art: "szene", name, prompt: vorlage, variablen: reihe[0]}});
    if (merken) await bausteineHolen();
  }
  await einreihenEinfach({
    prompt: prompts[0], prompts, aspect: $("szFormat").value,
    ...(merken ? {baustein: merken.id} : {})});
  say(`${prompts.length} Bild(er) eingereiht`
      + (merken ? `, als Szene „${name}“ gemerkt.` : "."), "ok");
};

// Einen schlichten Auftrag einreihen, ohne die Regler der anderen Reiter.
async function einreihenEinfach(zusatz) {
  const rumpf = {mode: "t2i", aspect: "3:2", base: parseInt($("base").value, 10) || 1024,
                 steps: parseInt($("steps").value, 10) || 24, count: 1,
                 seed: parseInt($("seed").value, 10) || 42, ...zusatz};
  const res = await fetch("/api/generate", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Einreihen ging nicht.", "err");
  }
  buttonState("busy");
  poll();
}

// ---------- Geschichte ----------
// Drei Schritte: umreissen, gliedern, schreiben lassen. Der Stil und die
// Frage Wirklichkeit oder Erfindung stehen ganz vorn, weil beides fuer jede
// Szene gilt -- und weil ein Modell, dem niemand sagt, dass Drachen erlaubt
// sind, die Handlung so lange zurechtbiegt, bis sie alltagstauglich wird.
let GESCHICHTE = null, gsZeilen = [{text: "", bilder: 1}], gsLetzteNr = 0;
let gsErgaenztZuletzt = "", gsProsaZuletzt = "";
// Rahmen einer langen Vorlage: Anfangsszene, Schlussszene, Abschnitte.
let GSRAHMEN = {anfang: "", ende: "", kapitel: []};

// Die Kameraeinstellung steht als \Name in der Zeile -- aber niemand soll
// sie dort suchen muessen. Jede Szene traegt deshalb ein Auswahlfeld, das
// zeigt, was gesetzt ist, und daneben das Feld fuer die Klammer.
const EINST_MUSTER =
  /\\([A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß-]{0,29})(?:\(([^)]{1,120})\))?/;

// Namen mit Schraegstrich, zu denen es noch keinen Baustein gibt. Damit
// weiss die Szene, ob sie etwas anzulegen hat.
// Das Minus gehoert dazu: /-Susi ist derselbe Verweis, nur hinter der
// Kamera. Ohne es im Muster verschwand ein so gekennzeichneter Baustein aus
// der Leiste und liess sich nicht mehr zurueckholen.
const VERWEIS_MUSTER = /\/(-?)([A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]{1,39})/g;

function offeneNamen(text) {
  const da = new Set(BAUSTEINE.flatMap(b =>
    [(b.name || "").toLowerCase()].concat(
      (b.alias || []).map(a => (a || "").toLowerCase()))));
  const raus = [];
  for (const m of String(text || "").matchAll(VERWEIS_MUSTER)) {
    const n = m[2];
    if (!da.has(n.toLowerCase()) && !raus.includes(n)) raus.push(n);
  }
  return raus;
}

// Ein geschriebener Prompt merkt sich die Zeile, aus der er entstand. Weicht
// die jetzige davon ab, ist er von gestern -- und niemand sieht es dem Bild
// hinterher an.
function geschriebeneZeile(nr) {
  const p = ((GESCHICHTE && GESCHICHTE.prompts) || []).find(x => x.nr === nr);
  return p ? (p.zeile || "") : null;
}

function veraltet(i) {
  const p = ((GESCHICHTE && GESCHICHTE.prompts) || []).find(x => x.nr === i + 1);
  if (!p) return false;
  // Verglichen wird, was das Sprachmodell zu sehen bekam: die Stichzeile ohne
  // #, ohne \ und ohne die Erklaerungen in Anfuehrungszeichen -- und die
  // Prosa, denn auch sie bestimmt, was man sieht.
  return blankZeile(gsZeilen[i].text) !== blankZeile(p.zeile || "")
      || (gsZeilen[i].prosa || "").trim() !== (p.prosa_quelle || "").trim();
}

function blankZeile(text) {
  return String(text || "")
    .replace(/#[^#\n]*/g, "")
    .replace(/\\[A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß-]{0,29}(\([^)]*\))?/g, "")
    .replace(/"[^"]*"|„[^“]*“|»[^«]*«/g, "")
    .replace(/\//g, "")
    .replace(/\s{2,}/g, " ").trim();
}

// Welche Bausteine in dieser Zeile stehen, in der Reihenfolge des Textes.
// Nur die angelegten: ein Name ohne Baustein laesst sich nicht tauschen.
function bausteineInZeile(text) {
  const raus = [];
  for (const m of String(text || "").matchAll(VERWEIS_MUSTER)) {
    const gesucht = m[2].toLowerCase();
    const b = BAUSTEINE.find(x => (x.name || "").toLowerCase() === gesucht
      || (x.alias || []).some(a => (a || "").toLowerCase() === gesucht));
    if (b && !raus.includes(b)) raus.push(b);
  }
  return raus;
}

// Einen Baustein aus einer Zeile nehmen oder gegen einen anderen tauschen.
// Beides ueber dasselbe Feld: es zeigt, was drinsteht, und was daraus
// werden kann.
const VORWORT = "durch|in|an|auf|zu|zum|zur|bei|mit|über|unter|vor|hinter"
              + "|neben|aus|nach|von|gegen|um|ohne|entlang";
const ARTIKEL = "der|die|das|den|dem|des|ein|eine|einen|einem|einer|eines"
              + "|sein|seine|ihr|ihre|ihren|seinen";

// Steht ein Minus vor dem Namen, gehoert die Figur zur Szene, aber nicht
// ins Bild: sie ist die, die hindurchschaut.
function blickwinkel(text, name) {
  return new RegExp("/-" + name.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")
                    + "\\b", "i").test(text || "");
}

function bausteinWahl(i, name, wahl) {
  if (wahl === "__weg") return bausteinInZeile(i, name, "");
  if (wahl === "__blick") return blickUmschalten(i, name);
  bausteinInZeile(i, name, wahl);
}

function blickUmschalten(i, name) {
  const z = gsZeilen[i];
  const roh = name.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&");
  z.text = blickwinkel(z.text, name)
    ? z.text.replace(new RegExp("/-" + roh + "\\b", "gi"), "/" + name)
    : z.text.replace(new RegExp("/" + roh + "\\b", "gi"), "/-" + name);
  zeigeSelbstszenen();
  gsMerken();
  gsVorschau();
}

function bausteinInZeile(i, alt, neu) {
  const z = gsZeilen[i];
  const roh = alt.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&");
  if (neu) {
    z.text = z.text.replace(new RegExp("/(-?)" + roh + "\\b", "gi"),
                            "/$1" + neu);
  } else {
    // Beim Entfernen faellt der Artikel davor mit, und ein Vorwort davor
    // auch: aus "rennt durch die /Halle" bliebe sonst "rennt durch die".
    z.text = z.text.replace(
      new RegExp(`(?:\\b(?:${VORWORT})\\s+)?(?:\\b(?:${ARTIKEL})\\s+)?/-?${roh}\\b`,
                 "gi"), "");
  }
  z.text = z.text.replace(/\s{2,}/g, " ").replace(/\s+([,.;!?])/g, "$1").trim();
  zeigeSelbstszenen();
  gsMerken();
  gsVorschau();
}

function einstellungBekannt(name) {
  const klein = (name || "").toLowerCase();
  return EINSTELLUNGEN.some(x => x.key === klein)
      || GEMERKTE.some(x => (x.name || "").toLowerCase() === klein);
}

// Was in dieser Zeile an Kamera steht: {key, angabe, treffer} oder null.
function einstellungInZeile(text) {
  const m = EINST_MUSTER.exec(text || "");
  if (!m || !einstellungBekannt(m[1])) return null;
  return {key: m[1].toLowerCase(), angabe: m[2] || "", treffer: m[0]};
}

function einstellungEintrag(key) {
  return EINSTELLUNGEN.find(x => x.key === key) || null;
}

// Einstellung und Klammer einer Szene neu setzen. Der Text bleibt, was er
// ist -- getauscht wird nur das \Wort.
function einstellungSchreiben(i, key, angabe) {
  const z = gsZeilen[i];
  const alt = einstellungInZeile(z.text);
  let text = alt ? z.text.replace(alt.treffer, "").replace(/\s{2,}/g, " ").trim()
                 : z.text;
  if (key) {
    const klammer = (angabe || "").trim() ? `(${angabe.trim()})` : "";
    text = (`\\${key}${klammer} ` + text).trim();
  }
  z.text = text;
  zeigeSelbstszenen();
  gsMerken();
}

// Drei Zustaende, drei Farben. Gruen ist von Hand gesetzt: fertig heisst,
// jemand hat es angesehen und fuer gut befunden -- das kann kein Programm
// entscheiden. Blau und Orange rechnet die Seite aus, mit denselben Regeln
// wie das Durchsehen, nur ohne Server: sie muessen bei jedem Tastendruck
// stimmen.
function szeneStand(i, drin, fest, p) {
  const z = gsZeilen[i];
  if (z.fertig) {
    return {klasse: "fertig", wort: "fertig",
            warum: "von Hand als fertig gekennzeichnet"};
  }
  const fehlt = [];
  if (!z.text.trim()) fehlt.push("die Zeile ist leer");
  const offen = offeneNamen(z.text);
  if (offen.length) fehlt.push(offen.map(n => "/" + n).join(", ")
                               + " nicht angelegt");
  if (!offen.length && !drin.length) fehlt.push("kein Baustein");
  if (!drin.some(b => b.art === "ort")) fehlt.push("kein Ort");
  if (fest && fest.luecke === "spiegelung" && drin.length
      && !drin.some(b => b.art === "person")) fehlt.push("keine Person");
  if (fest && fest.nur_gesicht) {
    const ohne = drin.filter(b => b.art === "person"
                             && !(b.gesicht || "").trim());
    if (ohne.length) fehlt.push(ohne.map(b => b.name).join(", ")
                                + " ohne Gesichtsbeschreibung");
  }
  if (!(z.prosa || "").trim()) fehlt.push("keine Prosa");
  if (!p || !(p.prompt || "").trim()) fehlt.push("kein Bildprompt");
  else if (veraltet(i)) fehlt.push("der Prompt passt nicht mehr zur Szene");
  return fehlt.length
    ? {klasse: "offen", wort: "offen", warum: "Es fehlt: " + fehlt.join(" · ")}
    : {klasse: "voll", wort: "vollständig",
       warum: "Bausteine, Ort, Prosa und Bildprompt stehen"};
}

function szeneFertig(i) {
  gsZeilen[i].fertig = !gsZeilen[i].fertig;
  zeigeSelbstszenen();
  gsMerken();
}

function zeigeSelbstszenen() {
  // Wer gerade schreibt, soll weiterschreiben koennen. Die Liste wird ganz
  // neu gezeichnet, dabei geht das Feld unter dem Zeiger verloren -- also
  // merken, wo der Zeiger stand, und ihn danach zurueckstellen.
  const aktiv = document.activeElement;
  const warI = aktiv && aktiv.classList && aktiv.classList.contains("gszeile")
    ? aktiv.dataset.i : null;
  const warPos = warI !== null ? aktiv.selectionStart : 0;
  $("gsSelbst").innerHTML = gsZeilen.map((z, i) => {
    const e = einstellungInZeile(z.text);
    const fest = e ? einstellungEintrag(e.key) : null;
    const luecke = fest ? fest.luecke : "";
    const wahl = [`<option value="">— ohne Kamera —</option>`]
      .concat(EINSTELLUNGEN.map(x =>
        `<option value="${x.key}"${e && e.key === x.key ? " selected" : ""}>${
          esc(x.label)}${x.paar ? " (2 Bilder)" : ""}</option>`))
      .concat(GEMERKTE.map(x =>
        `<option value="${esc(x.name)}"${
          e && e.key === (x.name || "").toLowerCase() ? " selected" : ""
        }>gemerkt: ${esc(x.name)}</option>`))
      .join("");
    const drin = bausteineInZeile(z.text);
    // Eingeklappt steht nur, was gesetzt ist. Mit zwanzig Szenen waeren
    // zwanzig volle Menues untereinander nicht mehr zu ueberblicken, und
    // meistens will man nur den Text lesen.
    const kurz = [drin.map(b => (blickwinkel(z.text, b.name) ? "◌ " : "")
                                + b.name).join(" · "),
                  fest ? fest.label : (e ? "\\" + e.key : ""),
                  (z.prosa || "").trim() ? "Prosa" : "",
                  (z.bilder || 1) > 1 ? `${z.bilder} Bilder` : ""]
      .filter(Boolean).join(" · ") || "nichts gesetzt";
    const p = ((GESCHICHTE && GESCHICHTE.prompts) || []).find(x => x.nr === i + 1);
    const stand = szeneStand(i, drin, fest, p);
    // Was das Bildmodell wirklich bekommt -- mit der Beschreibung der Figur
    // statt ihres Namens. Der Text des Sprachmodells steht nur da, solange
    // es den fertigen noch nicht gibt.
    const fertig = ((GESCHICHTE && GESCHICHTE.je_szene) || [])
      .filter(x => x.nr === i + 1).flatMap(x => x.texte || []);
    return `
    <div class="selbstszene ${stand.klasse}${e ? " mitkamera" : ""}">
      <div class="szkopf"><span class="nr">${i + 1}</span>
        <textarea class="gszeile" data-i="${i}" rows="2"
          placeholder="was in diesem Bild zu sehen ist">${esc(z.text)}</textarea>
        <span class="knopf haken${z.fertig ? " an" : ""}"
          onclick="szeneFertig(${i})"
          title="${z.fertig ? "doch noch nicht fertig"
                            : "diese Szene als fertig kennzeichnen"}">✓</span>
        <span class="knopf" onclick="gsSchieben(${i}, -1)" title="nach oben">▲</span>
        <span class="knopf" onclick="gsSchieben(${i}, 1)" title="nach unten">▼</span>
        <span class="knopf" onclick="gsSzeneDazu(${i})"
          title="leere Szene darunter einfügen">+</span>
        <span class="knopf" onclick="gsZeileWeg(${i})" title="entfernen">×</span>
      </div>
      <div class="szkurz">
        <span class="pfeil" onclick="szeneKlappen(${i})">${
          z.offen ? "▾" : "▸"}</span>
        <span onclick="szeneKlappen(${i})" style="flex:1">${esc(kurz)}</span>
        <span class="ampel ${stand.klasse}" title="${esc(stand.warum)}">${
          esc(stand.wort)}</span>
        ${veraltet(i) ? `<span class="wink">geändert</span>` : ""}
        <a href="#" class="szprompt"
           title="Diese Szene ganz nachziehen: Bausteine und Bildprompt"
           onclick="szeneAktualisieren(${i});return false">aktualisieren</a>
      </div>
      ${!z.offen ? "" : `
      <div class="szgruppe">
        <h4>Prosa <a href="#" class="szprompt"
          onclick="prosaFuerSzene(${i});return false">${
            (z.prosa || "").trim() ? "neu schreiben" : "schreiben"}</a></h4>
        <textarea class="gsprosa" data-i="${i}" rows="2"
          placeholder="der Text zu dieser Szene">${esc(z.prosa || "")}</textarea>
      </div>

      <div class="szgruppe">
        <h4>Bausteine <a href="#" class="szprompt"
          title="Erklärungen in Anführungszeichen übernehmen und Fehlende anlegen"
          onclick="bausteineAktualisierenSzene(${i});return false">aktualisieren</a></h4>
        <div class="szleiste">
          ${drin.map(b => `
            <select class="gsdrin${blickwinkel(z.text, b.name) ? " blick" : ""}"
              title="tauschen, verstecken oder entfernen"
              onchange="bausteinWahl(${i}, '${esc(b.name)}', this.value)">
              ${BAUSTEINE.filter(x => x.art === b.art).map(x =>
                `<option value="${esc(x.name)}"${
                  x.id === b.id ? " selected" : ""}>${
                  blickwinkel(z.text, b.name) && x.id === b.id ? "◌ " : ""
                  }/${esc(x.name)}</option>`).join("")}
              <option value="__blick">${blickwinkel(z.text, b.name)
                ? "● wieder zeigen" : "◌ nur Blickwinkel, nicht im Bild"}</option>
              <option value="__weg">⨯ entfernen</option>
            </select>`).join("")}
          <select class="gsfolge" title="Folge von Szenen darunter anlegen"
          onchange="gsFolgeDazu(${i}, this)">
          <option value="">+ Folge …</option>
          ${FOLGENLISTE.map(f =>
            `<option value="${f.key}">${esc(f.label)}</option>`).join("")}
        </select>
        <select class="gsteil" data-i="${i}" title="Baustein einsetzen">
            <option value="">+ Baustein …</option>
            ${BAUSTEINE.map(b =>
              `<option value="${esc(b.name)}">/${esc(b.name)}</option>`).join("")}
          </select>
          <span class="fuell"></span>
          ${offeneNamen(z.text).length
            ? `<a href="#" class="szprompt" title="${
                 esc(offeneNamen(z.text).join(", "))} anlegen"
                 onclick="bausteineDerSzene(${i});return false">+ ${
                 offeneNamen(z.text).length} anlegen</a>` : ""}
        </div>
      </div>

      <div class="szgruppe">
        <h4>Was man sieht</h4>
        <div class="szleiste">
          <select class="gseinst" data-i="${i}" title="Kameraeinstellung">${wahl}</select>
          ${luecke ? `<input class="gsangabe" data-i="${i}"
              placeholder="${esc(luecke === "hoehe" ? "Höhe, z. B. fünf Meter"
                                                    : "was sich spiegelt")}"
              value="${esc(e.angabe)}">` : ""}
          <span class="fuell"></span>
          <input type="number" class="gsbilder" data-i="${i}" min="1" max="20"
            title="wie viele Bilder aus dieser Szene" value="${z.bilder || 1}">
          <a href="#" class="szprompt${veraltet(i) ? " alt" : ""}" data-i="${i}"
             title="${veraltet(i)
               ? "Die Zeile hat sich geändert — Prompt neu schreiben lassen"
               : "nur für diese Szene den Bildprompt schreiben lassen"}"
             onclick="promptFuerSzene(${i});return false">${
               veraltet(i) ? "Prompt ↻" : "Prompt"}</a>
          <a href="#" class="szprompt" title="nur diese Szene erzeugen"
             onclick="szeneErzeugen(${i}, false);return false">Bild</a>
          <a href="#" class="szprompt"
             title="Stufe um Stufe aufbauen: erst der Raum, dann jede Figur einzeln in ihrer Haltung, dann das Spiegelbild, zuletzt alles ineinander"
             onclick="szeneAusBildern(${i});return false">Aufbau ⧉</a>
          <a href="#" class="szprompt"
             title="diese Szene erzeugen und daraus ein Video bauen"
             onclick="szeneErzeugen(${i}, true);return false">Video</a>
        </div>
        ${fertig.length ? fertig.map(t => `<code class="szsicht${
            t.length > 800 ? " lang" : ""}">${esc(t)}<span class="zeichen">${
            t.length} Zeichen</span></code>`).join("")
          : (p && p.prompt
             ? `<code class="szsicht roh">${esc(p.prompt)}<span class="zeichen"
                 >noch nicht zusammengesetzt</span></code>` : "")}
      </div>`}
    </div>`;
  }).join("")
    + (BAUSTEINE.length
        ? `<p class="hint">Bausteine: ` + BAUSTEINE.map(x =>
            `<a href="#" onclick="gsEinfuegen('/', '${esc(x.name)}');return false">/${esc(x.name)}</a>`
          ).join(" · ") + `</p>`
        : "")
    + (EINSTELLUNGEN.length
        ? `<p class="hint">Kamera: ` + EINSTELLUNGEN.map(x =>
            `<a href="#" onclick="gsEinfuegen('\\\\', '${x.key}');return false"
               title="${esc(x.label)}">\\${x.key}</a>${x.paar ? " (2 Bilder)" : ""}`
          ).join(" · ") + `</p>`
        : "")
    // Was sich einmal bewaehrt hat, steht neben den festen Einstellungen:
    // ein gemerkter Prompt wird genauso gerufen.
    + (GEMERKTE.length
        ? `<p class="hint">Gemerkt: ` + GEMERKTE.map(x =>
            `<a href="#" onclick="gsEinfuegen('\\', '${esc(x.name)}');return false"
               title="${esc(x.prompt.slice(0, 160))}">\\${esc(x.name)}</a>`
          ).join(" · ") + `</p>`
        : "");
  $("gsSelbst").querySelectorAll(".gszeile").forEach(el => {
    // Beim Tippen NICHT die Vorschau holen: sie zeichnet die Liste neu, das
    // Feld verschwindet mitten im Wort und der Fokus mit ihm. Nachgezogen
    // wird, wenn man das Feld verlaesst.
    el.oninput = () => {
      gsZeilen[+el.dataset.i].text = el.value;
      mitwachsen(el);
    };
    el.onchange = () => gsVorschau();
    el.onfocus = () => gsLetzteNr = +el.dataset.i;
    mitwachsen(el);
  });
  $("gsSelbst").querySelectorAll(".gsbilder").forEach(el => {
    el.oninput = () => {
      gsZeilen[+el.dataset.i].bilder = Math.max(1, parseInt(el.value, 10) || 1);
      gsSumme();
    };
  });
  $("gsSelbst").querySelectorAll(".gsprosa").forEach(el => {
    el.oninput = () => { gsZeilen[+el.dataset.i].prosa = el.value; mitwachsen(el); };
    el.onchange = gsMerken;
    mitwachsen(el);
  });
  $("gsSelbst").querySelectorAll(".gsteil").forEach(el => {
    el.onchange = () => {
      if (el.value) bausteinDazu(+el.dataset.i, el.value);
      el.value = "";
    };
  });
  $("gsSelbst").querySelectorAll(".gseinst").forEach(el => {
    el.onchange = () => {
      const i = +el.dataset.i;
      const alt = einstellungInZeile(gsZeilen[i].text);
      einstellungSchreiben(i, el.value, alt ? alt.angabe : "");
    };
  });
  $("gsSelbst").querySelectorAll(".gsangabe").forEach(el => {
    // Erst beim Verlassen schreiben: bei jedem Tastendruck neu zu zeichnen
    // naehme dem Feld den Fokus.
    el.onchange = () => {
      const i = +el.dataset.i;
      const alt = einstellungInZeile(gsZeilen[i].text);
      if (alt) einstellungSchreiben(i, alt.key, el.value);
    };
  });
  if (warI !== null) {
    const zurueck = $("gsSelbst")
      .querySelector(`.gszeile[data-i="${warI}"]`);
    if (zurueck) {
      zurueck.focus();
      try { zurueck.setSelectionRange(warPos, warPos); } catch (e) { /* egal */ }
    }
  }
  gsSumme();
  gsMerken();
}

// Ein Feld waechst mit dem Text, schrumpft aber nie unter das, was man ihm
// von Hand gegeben hat: wer es groesser gezogen hat, will es so behalten.
function mitwachsen(el) {
  // Die jetzige Hoehe zuerst merken: hat der Benutzer das Feld von Hand
  // groesser gezogen, soll das Tippen es nicht wieder zusammenziehen.
  const jetzt = el.offsetHeight;
  el.style.height = "auto";
  el.style.height = Math.max(el.scrollHeight, jetzt, 46) + "px";
}

function gsSumme() {
  const n = gsZeilen.reduce((s, z) => s + (z.bilder || 1), 0);
  $("gsSumme").textContent = `${gsZeilen.filter(z => z.text.trim()).length} Szenen, `
    + `${n} Bild(er)`;
  $("gsKlappen").textContent = gsZeilen.some(z => z.offen)
    ? "alle einklappen" : "alle ausklappen";
}

// Einen Baustein oder eine Kameraeinstellung in die zuletzt angeklickte
// Zeile schreiben. `zeichen` ist / oder der Rueckwaertsschraegstrich.
function gsEinfuegen(zeichen, name) {
  const i = Math.min(gsLetzteNr, gsZeilen.length - 1);
  const dazu = zeichen === "/" ? verweisText(name) : zeichen + name;
  gsZeilen[i].text = (gsZeilen[i].text + " " + dazu).trim();
  zeigeSelbstszenen();
  gsMerken();
}

// Ein uebernommener Baustein bekommt gleich die leeren Anfuehrungszeichen
// mit: was man dort hineinschreibt, wird beim Aktualisieren zu seiner
// Beschreibung. Ohne das Angebot faellt niemandem ein, dass es geht.
function verweisText(name) {
  return `/${name} ""`;
}

// Einen Baustein in eine Zeile schreiben -- von Hand gewaehlt, nicht
// vorgeschlagen. Die leeren Anfuehrungszeichen kommen mit: was dort steht,
// wird beim Aktualisieren zur Beschreibung.
function bausteinDazu(i, name) {
  const z = gsZeilen[i];
  if (stehtDrin(z.text, name)) return;
  z.text = (z.text.trim() + " " + verweisText(name)).trim();
  zeigeSelbstszenen();
  gsMerken();
  gsVorschau();
}

function stehtDrin(text, name) {
  return new RegExp("/" + name.replace(/[.*+?^${}()|[\]\\-]/g, "\\$&")
                    + "\\b", "i").test(text);
}

function szeneKlappen(i) {
  gsZeilen[i].offen = !gsZeilen[i].offen;
  zeigeSelbstszenen();
}

function alleKlappen(offen) {
  gsZeilen.forEach(z => z.offen = offen);
  zeigeSelbstszenen();
}

// Eine leere Szene unter dieser einfuegen. Ganz unten anzuhaengen und dann
// zwoelfmal nach oben zu schieben ist keine Arbeitsweise.
function gsSzeneDazu(i) {
  gsZeilen.splice(i + 1, 0, {text: "", bilder: 1, offen: true});
  gsLetzteNr = i + 1;
  zeigeSelbstszenen();
  gsMerken();
}

// Eine ganze Folge darunter: erst in die Augen, dann aus etwas heraus, dann
// in etwas hinein. Immer dieselben drei Handgriffe -- hier in einem. Der
// Text der Szene wandert mit, ohne ihre Kamera: derselbe Augenblick aus
// wechselndem Blick.
function gsFolgeDazu(i, feld) {
  const f = FOLGENLISTE.find(x => x.key === feld.value);
  feld.value = "";
  if (!f) return;
  const e = einstellungInZeile(gsZeilen[i].text);
  const roh = (e ? gsZeilen[i].text.replace(e.treffer, "") : gsZeilen[i].text)
    .replace(/\s{2,}/g, " ").trim();
  const neu = f.schritte.map(k => ({
    text: (`\\${k} ` + roh).trim(), bilder: 1, offen: false,
    prosa: gsZeilen[i].prosa || ""}));
  gsZeilen.splice(i + 1, 0, ...neu);
  zeigeSelbstszenen();
  gsMerken();
  say(`${neu.length} Szenen angelegt: ${f.label}. Der Text der Szene ${i + 1} `
      + "steht in allen, nur der Blick wechselt.", "ok");
}

// Nur diese eine Szene erzeugen -- mit Video oder ohne. Der Weg ist
// derselbe wie fuer die ganze Geschichte, nur mit einer Zeile.
async function szeneErzeugen(i, mitVideo) {
  const z = gsZeilen[i];
  if (!z || !z.text.trim()) return say("Die Szene ist leer.", "err");
  const g = await fetch("/api/szenen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      zeilen: [z], stil: $("gsStil").value,
      prompts: [{nr: 1, ...(((GESCHICHTE && GESCHICHTE.prompts) || [])
                 .find(p => p.nr === i + 1) || {}), nr: 1}]})
  }).then(r => r.json()).catch(() => null);
  if (!g || !g.bloecke || !g.bloecke.length) {
    return say("Für diese Szene gibt es noch keinen Prompt — erst „Prompt“.",
               "err");
  }
  bloecke = JSON.parse(JSON.stringify(g.bloecke));
  blockZeichnen();
  // Ohne Startbild: der Ablauf baut sonst zuerst ein Bild, das niemand
  // bestellt hat, und haengt an die Szene "dieselbe Person wie im
  // Referenzbild" -- mit einer Person, die gar nicht darin vorkommt.
  ohneBasis = true;
  ohneVideo = !mitVideo;
  await starteDemo();
  ohneBasis = false;
  ohneVideo = false;
  say(mitVideo ? `Szene ${i + 1} wird erzeugt, danach das Video …`
               : `Szene ${i + 1} wird erzeugt …`);
}

// Dieselbe Szene, aber aus den Musterbildern der beteiligten Bausteine
// zusammengesetzt. Bei mehr als zwei Figuren ist das der verlaesslichere
// Weg: ein Prompt kann Kleidung und Gesicht nicht an einzelne Personen
// binden, ein Referenzbild je Figur schon. Der Ort kommt nach vorn -- bei
// "Figur in eine Szene setzen" ist das erste Bild die Kulisse.
async function szeneAusBildern(i) {
  const z = gsZeilen[i];
  if (!z || !z.text.trim()) return say("Die Szene ist leer.", "err");
  const g = await fetch("/api/szenen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      zeilen: [z], stil: $("gsStil").value,
      prompts: [{nr: 1, ...(((GESCHICHTE && GESCHICHTE.prompts) || [])
                 .find(p => p.nr === i + 1) || {}), nr: 1}]})
  }).then(r => r.json()).catch(() => null);
  const fertig = g && g.je_szene && g.je_szene.length ? g.je_szene[0].texte : [];
  if (!fertig.length) {
    return say("Für diese Szene gibt es noch keinen Prompt — erst „Prompt“.",
               "err");
  }
  const plan = ausBildernPlan((g.szenen[0] || {}).teile || []);
  if (plan.ohne.length) {
    return say("Ohne Musterbild: " + plan.ohne.map(b => b.name).join(", ")
      + " — erst bei Bausteine mit ▣ eines erzeugen.", "err");
  }
  if (!plan.reihe.length) {
    return say("Kein Baustein der Szene hat ein Musterbild.", "err");
  }
  // Die getippte Zeile, nicht der fertige Prompt: aus ihr liest das
  // Sprachmodell die Haltungen heraus, und dort stehen sie im Klartext.
  // Der fertige Prompt hat die Namen laengst durch Beschreibungen ersetzt.
  const text = gsZeilen[i].text;
  await stufenAufbau(text, plan.reihe.map(b => b.id), $("gsStil").value);
  say(`Szene ${i + 1} wird in Stufen aufgebaut …`, "ok");
}

// Die Reihenfolge aendern. Eine Szene an die falsche Stelle zu schreiben
// passiert staendig; sie dafuer zweimal abzutippen ist zu viel verlangt.
function gsSchieben(i, wohin) {
  const ziel = i + wohin;
  if (ziel < 0 || ziel >= gsZeilen.length) return;
  const [weg] = gsZeilen.splice(i, 1);
  gsZeilen.splice(ziel, 0, weg);
  gsLetzteNr = ziel;
  zeigeSelbstszenen();
  gsMerken();
  gsVorschau();
}

function gsZeileWeg(i) {
  gsZeilen.splice(i, 1);
  if (!gsZeilen.length) gsZeilen = [{text: "", bilder: 1}];
  zeigeSelbstszenen();
  gsMerken();
  gsVorschau();
}

// Die Bausteine genau dieser Szene anlegen. Derselbe Weg wie fuer die ganze
// Gliederung, nur mit einer Zeile -- wer eine Figur gerade erfunden hat, will
// sie sofort haben und nicht erst am Ende.
async function bausteineDerSzene(i) {
  const z = gsZeilen[i];
  if (!z || !offeneNamen(z.text).length) return;
  say("Der Baustein wird geschrieben …");
  const g = await bausteinRuf({tu: "vorschlagen", zeilen: [z]});
  if (!g) return;
  if (!g.neu.length) return say(g.hinweis || "Nichts anzulegen.", "ok");
  await bausteineHolen();
  zeigeSelbstszenen();
  say(`Angelegt: ${g.neu.map(b => b.name).join(", ")} `
      + "— im Reiter Bausteine gegenlesen und ändern.", "ok");
}

// Den Bildprompt fuer eine einzelne Szene schreiben lassen. Dieselbe Strecke
// wie fuer die ganze Gliederung, nur mit einer Zeile -- und das Ergebnis
// ersetzt genau diesen einen Prompt, nicht die anderen sieben.
async function promptFuerSzene(i) {
  const z = gsZeilen[i];
  if (!z || !z.text.trim()) return say("Die Szene ist leer.", "err");
  const res = await fetch("/api/gliederung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen: [z], nummern: [i + 1],
                          stil: $("gsStil").value, welt: $("gsWelt").value,
                          kurz: $("gsKurz").value, fiktion: +$("gsFiktion").value,
                          alter: $("gsFreigabe").value,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Der Prompt ließ sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say(`Der Prompt für Szene ${i + 1} wird geschrieben …`);
}

// Fehlt die Gliederung an Zeilen, schreibt das Sprachmodell sie nach. Was
// dasteht, bleibt -- angehaengt wird nur, was fehlt.
$("gsErgaenzen").onclick = async e => {
  e.preventDefault();
  const da = gsZeilen.filter(z => z.text.trim()).length;
  const ziel = parseInt($("gsAnzahl").value, 10) || 0;
  const fehlt = ziel ? ziel - da : parseInt(prompt("Wie viele Szenen dazu?", "5"), 10);
  if (!fehlt || fehlt < 1) {
    return say(ziel ? `Es stehen schon ${da} von ${ziel} Szenen.`
                    : "Keine Zahl angegeben.", ziel ? "ok" : "err");
  }
  const res = await fetch("/api/ergaenzen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen: gsZeilen.filter(z => z.text.trim()), fehlt,
                          kurz: $("gsKurz").value, welt: $("gsWelt").value,
                          stil: $("gsStil").value,
                          fiktion: +$("gsFiktion").value,
                          modell: $("gsModell").value})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das ließ sich nicht ergänzen.", "err");
  }
  buttonState("busy");
  poll();
  say(`${fehlt} Szenen werden geschrieben …`);
};

// Alle Szenen, die sich seit ihrem Prompt geaendert haben, in einem Zug
// nachschreiben. In einem Auftrag, nicht in fuenf: das grosse Modell zu
// laden kostet eine halbe Minute, und das fuenfmal waere Unfug.
$("gsEinpflegen").onclick = async e => {
  e.preventDefault();
  const offen = gsZeilen.map((z, i) => i).filter(i => veraltet(i));
  if (!offen.length) {
    return say(GESCHICHTE && GESCHICHTE.prompts && GESCHICHTE.prompts.length
      ? "Alle Prompts sind auf dem Stand der Szenen."
      : "Es sind noch keine Prompts geschrieben.", "ok");
  }
  const res = await fetch("/api/gliederung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen: offen.map(i => gsZeilen[i]),
                          nummern: offen.map(i => i + 1),
                          stil: $("gsStil").value, welt: $("gsWelt").value,
                          kurz: $("gsKurz").value, fiktion: +$("gsFiktion").value,
                          alter: $("gsFreigabe").value,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das ließ sich nicht einpflegen.", "err");
  }
  buttonState("busy");
  poll();
  say(`${offen.length} geänderte Szene(n) werden neu geschrieben …`);
};

// Was in den Anfuehrungszeichen steht, in die Bausteine uebernehmen. Gilt
// auch fuer vorhandene: wer es gerade hingeschrieben hat, meint es so.
$("gsAktualisieren").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  if (!confirm("Was zwischen den Anführungszeichen steht, wird zur "
               + "Beschreibung des Bausteins. Vorhandene Prompts werden dabei "
               + "überschrieben. Weiter?")) return;
  const g = await bausteinRuf({tu: "aktualisieren", zeilen});
  if (!g) return;
  await bausteineHolen();
  zeigeSelbstszenen();
  const teile = [];
  if ((g.weg || []).length) teile.push(`${g.weg.join(", ")} aufgegangen`);
  if (g.neu.length) teile.push("nachgezogen: " + mitArt(g.neu));
  say(teile.length ? teile.join(" · ") + "."
                   : (g.hinweis || "Nichts zu übernehmen."), "ok");
};

// Durchsehen, was noch fehlt. Kostet nichts -- kein Sprachmodell, nur
// Nachsehen -- und sagt vor dem teuren Teil, was schiefgehen wird.
$("gsPruefen").onclick = async e => {
  e.preventDefault();
  const g = await bausteinRuf({tu: "pruefen", zeilen: gsZeilen});
  if (!g) return;
  const rang = {fehler: 0, warnung: 1, hinweis: 2};
  const funde = (g.funde || []).sort((a, b) =>
    (rang[a.schwere] - rang[b.schwere]) || (a.nr - b.nr));
  $("gsPruefung").innerHTML = funde.length
    ? `<p class="hint">${g.szenen} Szenen, ${funde.length} Anmerkung(en):</p>`
      + funde.map(f => `<div class="fund ${f.schwere}">`
          + (f.nr ? `<b>Szene ${f.nr}</b> ` : "")
          + esc(f.text) + `</div>`).join("")
    : `<div class="fund gut">Alle ${g.szenen} Szenen sind versorgt: `
      + `Bausteine genannt, angelegt und beschrieben.</div>`;
  say(funde.length ? `${funde.length} Anmerkung(en) — siehe unten.`
                   : "Die Gliederung ist vollständig.",
      funde.length ? "" : "ok");
};

// Der ganze Weg in einem Zug: vorschlagen, in die Szenen uebernehmen,
// anlegen. Wer eine Gliederung fertig hat, will nicht dreimal klicken --
// und was dabei entsteht, laesst sich danach genauso aendern.
$("gsAllesAnlegen").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  // Angelegt wird nur, was in den Zeilen steht. Vorschlaege schreibt das
  // Programm nicht mehr von selbst hinein -- wer sie will, klickt sie an.
  // Vorher wanderten sie mit, und dann stand eine Figur im Projekt, die
  // niemand verlangt hatte.
  const g = await bausteinRuf({tu: "aktualisieren", zeilen});
  if (!g) return;
  const h = await bausteinRuf({tu: "vorschlagen", zeilen});
  if (!h) return;
  await bausteineHolen();
  zeigeSelbstszenen();
  gsVorschau();
  const teile = [];
  if ((g.weg || []).length) teile.push(`${g.weg.join(", ")} aufgegangen`);
  if (g.neu.length) teile.push("nachgezogen: " + mitArt(g.neu));
  if (h.neu.length) teile.push("angelegt: " + mitArt(h.neu));
  if (h.unklar && h.unklar.length)
    teile.push(`nicht eingeordnet: ${h.unklar.join(", ")}`);
  say(teile.length ? teile.join(" · ") + "."
                   : "Alle genannten Bausteine gibt es schon.", "ok");
};

// Immer mit der Art: wer sieht, dass "Kristall (Person)" entstanden ist,
// merkt den Fehler sofort -- ein blosser Name verrät ihn nicht.
function mitArt(liste) {
  const label = k => (BSARTEN.find(a => a.key === k) || {}).label || k;
  return liste.map(b => `${b.name} (${label(b.art)})`).join(", ");
}


// Alles, was die Geschichte mit /Name verlangt und noch nicht gibt, gleich
// anlegen -- mit geratener Art und geschriebenem Prompt. Ein Vorschlag zum
// Abaendern ist mehr wert als ein leeres Feld.
$("gsFehlend").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  say("Die fehlenden Bausteine werden geschrieben …");
  const g = await bausteinRuf({tu: "vorschlagen", zeilen});
  if (!g) return;
  if (!g.neu.length) return say(g.hinweis || "Nichts anzulegen.", "ok");
  await bausteineHolen();
  zeigeSelbstszenen();
  say(`${g.neu.length} Baustein(e) angelegt: ` + mitArt(g.neu)
      + (g.unklar && g.unklar.length
         ? ` · nicht eingeordnet: ${g.unklar.join(", ")}` : "")
      + " — im Reiter Bausteine gegenlesen und ändern.", "ok");
};

// Regler und Einordnung halten sich stimmig: der Regler sagt, wie weit weg
// von der Wirklichkeit, das Feld sagt wohin.
const GRADTEXT = [
  "ganz die wirkliche Welt — nichts Übernatürliches",
  "ganz die wirkliche Welt — nichts Übernatürliches",
  "wirklich, mit einem Hauch von Unwirklichem am Rand",
  "wirklich, mit einem Hauch von Unwirklichem am Rand",
  "die Grenze zum Unmöglichen ist durchlässig",
  "die Grenze zum Unmöglichen ist durchlässig",
  "erfundene Welt mit eigenen, folgerichtigen Regeln",
  "erfundene Welt mit eigenen, folgerichtigen Regeln",
  "Magie und Fabelwesen gehören dazu",
  "Magie und Fabelwesen gehören dazu",
  "Märchenlogik — Wunder brauchen keine Begründung",
];

function zeigeGrad() {
  const n = +$("gsFiktion").value;
  $("gsFiktionText").textContent = `${n * 10} % Fiktion — ${GRADTEXT[n]}`;
  const passend = n <= 3 ? "wirklich" : n <= 5 ? "scifi"
                : n <= 7 ? "fantasie" : n <= 9 ? "fantasie" : "maerchen";
  if ($("gsWelt").value === "wirklich" || n <= 3) $("gsWelt").value = passend;
  stilHinweis();
}

// Je unwirklicher die Geschichte, desto besser fahren Anime, Comic und Manga:
// ein Foto muss glaubhaft sein, eine Zeichnung darf alles. Gesagt wird es nur
// -- gewaehlt wird der Stil weiter von Hand.
function stilHinweis() {
  const hoch = +$("gsFiktion").value >= 7;
  const stil = $("gsStil").value;
  const gezeichnet = !stil || GEZEICHNET.includes(stil);
  $("gsStilHinweis").textContent = hoch && !gezeichnet
    ? "Bei so viel Fiktion sind Anime, Comic und Manga klar im Vorteil — "
      + "ein Foto muss glaubhaft aussehen, eine Zeichnung darf alles."
    : "";
}
$("gsStil").addEventListener("change", stilHinweis);

$("gsFiktion").addEventListener("input", zeigeGrad);

// Mehrere Geschichten je Projekt, jede in Baenden. Die Vorgaben -- Stil,
// Welt, Wirklichkeitsgrad, Modell -- gehoeren der Geschichte und gelten fuer
// alle Baende; Idee, Gliederung und Prompts gehoeren dem Band.
let gsSpeicherUhr = null, GSAKTUELL = null, gsBandNr = 1;

async function gsRuf(rumpf) {
  const res = await fetch("/api/geschichten", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  return res.json();
}

function gsStand() {
  return {band: gsBandNr,
          anfang: GSRAHMEN.anfang, ende: GSRAHMEN.ende,
          kapitel: GSRAHMEN.kapitel,
          stil: $("gsStil").value, welt: $("gsWelt").value,
          fiktion: +$("gsFiktion").value, alter: $("gsFreigabe").value,
          erzaehler: $("gsErzaehler").value,
          erzaehler_wer: $("gsErzaehlerWer").value,
          erzaehler_text: $("gsErzaehlerText").value,
          modell: $("gsModell").value,
          idee: $("gsIdee").value, kurz: $("gsKurz").value,
          zeilen: gsZeilen,
          prompts: (GESCHICHTE && GESCHICHTE.prompts) || []};
}

function gsMerken() {
  if (!GSAKTUELL) return;
  clearTimeout(gsSpeicherUhr);
  $("gsStand").textContent = "· ungespeichert";
  gsSpeicherUhr = setTimeout(gsJetztSpeichern, 1200);
}

// Von Hand speichern. Die Nebenbei-Sicherung laeuft weiter -- aber wer eine
// Stunde an einem Inhaltsverzeichnis sitzt, will einmal selbst den Knopf
// druecken und schwarz auf weiss lesen, dass es liegt.
async function gsJetztSpeichern() {
  if (!GSAKTUELL) {
    say("Erst eine Geschichte anlegen.", "err");
    return false;
  }
  clearTimeout(gsSpeicherUhr);
  const g = await gsRuf({tu: "speichern", schluessel: GSAKTUELL, stand: gsStand()});
  if (!g) { $("gsStand").textContent = "· nicht gespeichert"; return false; }
  const uhr = new Date().toLocaleTimeString("de-DE",
    {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  $("gsStand").textContent = `· gespeichert ${uhr}`;
  return true;
}

$("gsSpeichern").onclick = async e => {
  e.preventDefault();
  if (await gsJetztSpeichern()) say("Geschichte gespeichert.", "ok");
};

async function gsListe(waehle) {
  const g = await gsRuf({tu: "liste"});
  if (!g) return;
  $("gsWahl").innerHTML = g.geschichten.length
    ? g.geschichten.map(x =>
        `<option value="${x.schluessel}">${esc(x.name)} (${x.baende} Bd.)</option>`).join("")
    : `<option value="">— noch keine —</option>`;
  const ziel = waehle || (g.geschichten[0] || {}).schluessel || "";
  if (ziel) { $("gsWahl").value = ziel; await gsOeffnen(ziel); }
  else { GSAKTUELL = null; $("gsBand").innerHTML = ""; }
}

async function gsOeffnen(schluessel, nr) {
  const g = await gsRuf({tu: "lesen", schluessel});
  if (!g) return;
  GSAKTUELL = schluessel;
  const baende = g.baende || [];
  $("gsBand").innerHTML = baende.map(b =>
    `<option value="${b.nr}">Band ${b.nr}</option>`).join("");
  gsBandNr = nr || baende[baende.length - 1].nr;
  $("gsBand").value = gsBandNr;
  // Vorgaben der Geschichte
  if (g.stil) $("gsStil").value = g.stil;
  if (g.welt) $("gsWelt").value = g.welt;
  if (g.modell) $("gsModell").value = g.modell;
  if (g.fiktion !== null && g.fiktion !== undefined) $("gsFiktion").value = g.fiktion;
  if (g.alter) $("gsFreigabe").value = g.alter;
  // Aeltere Geschichten haben die drei Felder nicht -- dann bleibt es beim
  // neutralen Erzaehler, so wie sie geschrieben wurden.
  $("gsErzaehler").value = g.erzaehler || "";
  $("gsErzaehlerWer").value = g.erzaehler_wer || "";
  $("gsErzaehlerText").value = g.erzaehler_text || "";
  zeigeGrad();
  // Inhalt des Bandes
  const band = baende.find(x => x.nr === gsBandNr) || {};
  $("gsIdee").value = band.idee || "";
  $("gsKurz").value = band.kurz || "";
  gsZeilen = (band.zeilen && band.zeilen.length)
    ? band.zeilen : [{text: "", bilder: 1}];
  GSRAHMEN = {anfang: band.anfang || "", ende: band.ende || "",
              kapitel: band.kapitel || []};
  zeigeRahmen();
  zeigeSelbstszenen();
  GESCHICHTE = null;
  $("gsSzenen").innerHTML = "";
  $("gsKnoepfe").style.display = "none";
  if (band.prompts && band.prompts.length) zeigeGliederung(band.prompts);
  gsFassungenZeigen();
  say(`„${g.name}“, Band ${gsBandNr} geladen.`);
}

$("gsWahl").onchange = () => gsOeffnen($("gsWahl").value);
$("gsBand").onchange = () => gsOeffnen(GSAKTUELL, +$("gsBand").value);

$("gsNeu").onclick = async e => {
  e.preventDefault();
  const name = prompt("Wie soll die Geschichte heißen?");
  if (!name) return;
  const g = await gsRuf({tu: "anlegen", name, globale: {
    stil: $("gsStil").value, welt: $("gsWelt").value,
    fiktion: +$("gsFiktion").value, modell: $("gsModell").value}});
  if (!g) return;
  await gsListe(g.schluessel);
  say(`„${g.name}“ angelegt — Band 1 ist leer.`, "ok");
};

$("gsBandNeu").onclick = async e => {
  e.preventDefault();
  if (!GSAKTUELL) return say("Erst eine Geschichte anlegen.", "err");
  const g = await gsRuf({tu: "band", schluessel: GSAKTUELL});
  if (!g) return;
  const neu = g.baende[g.baende.length - 1].nr;
  await gsListe(GSAKTUELL);
  await gsOeffnen(GSAKTUELL, neu);
  say(`Band ${neu} angelegt. Die Vorgaben gelten weiter, die Vorgeschichte `
      + "kennt das Sprachmodell beim Umreißen.", "ok");
};

$("gsWeg").onclick = async e => {
  e.preventDefault();
  if (!GSAKTUELL) return;
  const name = $("gsWahl").selectedOptions[0].textContent;
  if (!confirm(`„${name}“ mit allen Bänden löschen?`)) return;
  if (!await gsRuf({tu: "loeschen", schluessel: GSAKTUELL})) return;
  GSAKTUELL = null;
  await gsListe();
  say("Geschichte gelöscht.", "ok");
};

async function gsHolen() {
  if (!GSAKTUELL) await gsListe();
}

["gsIdee", "gsKurz", "gsStil", "gsWelt", "gsFiktion", "gsModell"].forEach(
  id => $(id).addEventListener("input", gsMerken));

$("gsPlus").onclick = e => {
  e.preventDefault();
  gsZeilen.push({text: "", bilder: 1});
  zeigeSelbstszenen();
};

// --- Schritt 1: umreissen ---
$("gsUmreissen").onclick = async e => {
  e.preventDefault();
  const idee = $("gsIdee").value.trim();
  if (!idee) return say("Erst eine Idee eintippen.", "err");
  const res = await fetch("/api/expose", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({idee, fiktion: +$("gsFiktion").value,
                          anzahl: parseInt($("gsAnzahl").value, 10) || 0,
                          alter: $("gsFreigabe").value,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das ließ sich nicht umreißen.", "err");
  }
  buttonState("busy");
  poll();
  say("Die Geschichte wird umrissen …");
};

// Stufe 1: die Geschichte lesen. Titel, Kurzfassung, erste und letzte
// Szene, und der Text in Abschnitte geteilt. Das Ende steht damit fest,
// bevor die Mitte geschrieben wird -- vorher lief eine lange Vorlage aus,
// ohne je anzukommen.
$("gsLesen").onclick = async e => {
  e.preventDefault();
  const text = $("gsIdee").value.trim();
  if (!text) return say("Erst die Geschichte oder die Idee eintippen.", "err");
  if (!$("gsStil").value || !$("gsWelt").value) {
    return say("Erst Stil und Welt wählen — danach wird die Idee unter "
               + "diesen Vorgaben gelesen.", "err");
  }
  const res = await fetch("/api/aufbau", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({phase: "rahmen", text, kurz: $("gsKurz").value,
                          welt: $("gsWelt").value, stil: $("gsStil").value,
                          fiktion: +$("gsFiktion").value,
                          alter: $("gsFreigabe").value,
                          anzahl: parseInt($("gsAnzahl").value, 10) || 12,
                          modell: $("gsModell").value})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das ließ sich nicht lesen.", "err");
  }
  buttonState("busy");
  poll();
  say("Die Geschichte wird gelesen …");
};

// Stufe 2: die Szenen je Abschnitt, mit dem Ende als letzter Zeile.
$("gsSzenenSchreiben").onclick = async e => {
  e.preventDefault();
  if (!GSRAHMEN.kapitel.length) {
    return say("Erst „Geschichte lesen“ — dann stehen die Abschnitte fest.",
               "err");
  }
  const res = await fetch("/api/aufbau", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({phase: "szenen", kurz: $("gsKurz").value,
                          welt: $("gsWelt").value, stil: $("gsStil").value,
                          fiktion: +$("gsFiktion").value,
                          anzahl: parseInt($("gsAnzahl").value, 10) || 12,
                          alter: $("gsFreigabe").value,
                          anfang: GSRAHMEN.anfang, ende: GSRAHMEN.ende,
                          kapitel: GSRAHMEN.kapitel,
                          modell: $("gsModell").value})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Die Szenen ließen sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say(`Die Szenen werden geschrieben, ${GSRAHMEN.kapitel.length} Abschnitte …`);
};

function zeigeRahmen() {
  const k = GSRAHMEN.kapitel || [];
  $("gsRahmen").innerHTML = !k.length ? "" : `
    <div class="fund gut"><b>Anfang</b> ${esc(GSRAHMEN.anfang)}</div>
    <div class="fund gut"><b>Ende</b> ${esc(GSRAHMEN.ende)}</div>
    <p class="hint">${k.length} Abschnitte: ${
      k.map(x => esc(x.titel)).join(" · ")}</p>`;
}

// Die Prosa zu allen Szenen. Ein eigener Schritt vor den Bausteinen: aus
// ihr ergibt sich, was im Bild zu sehen ist und wen es dafuer braucht.
$("gsProsaSchreiben").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  // Steht schon Prosa da, wird sie ueberschrieben. Vorher als Fassung
  // sichern -- die Arbeit von gestern soll ein neuer Autor nicht wegnehmen.
  if (zeilen.some(z => (z.prosa || "").trim())) {
    const wer = (ERZAEHLERLISTE.find(x => x.key === $("gsErzaehler").value)
                 || {}).label || "neu";
    await gsFassungSichern(`vor „${wer}“`, true);
  }
  const res = await fetch("/api/prosa", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, kurz: $("gsKurz").value,
                          welt: $("gsWelt").value,
                          alter: $("gsFreigabe").value,
                          fiktion: +$("gsFiktion").value,
                          ...erzaehlerFelder(),
                          modell: $("gsModell").value})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Die Prosa ließ sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say(`Der Text zu ${zeilen.length} Szenen wird geschrieben …`);
};

// Die Zeilen, wie sie an den Server gehen: mit dem Haken "nur die genannten
// Figuren". Er gehoert zur Geschichte, gilt aber je Szene -- deshalb wird er
// hier angehaengt statt in jede Zeile geschrieben.
function zeilenFuerServer(liste) {
  const nur = $("gsNurGenannte").checked;
  return (liste || gsZeilen).filter(z => z.text.trim())
    .map(z => ({...z, nur_genannte: nur}));
}

// Wer die Prosa schreibt. An einer Stelle gebaut, weil zwei Aufrufe sie
// brauchen -- die ganze Geschichte und die einzelne Szene.
function erzaehlerFelder() {
  return {erzaehler: $("gsErzaehler").value,
          erzaehler_wer: $("gsErzaehlerWer").value,
          erzaehler_text: $("gsErzaehlerText").value};
}

// ---------- Fassungen ----------
// Der Stand eines Bandes zu einem Zeitpunkt. Damit laesst sich ein neuer
// Autor gefahrlos ausprobieren: die bisherige Arbeit liegt daneben.
async function gsFassungSichern(name, still) {
  if (!GSAKTUELL) {
    if (!still) say("Erst eine Geschichte anlegen.", "err");
    return false;
  }
  // Erst den jetzigen Stand in die Datei, dann sichern -- sonst fehlte der
  // Fassung genau das, was seit der letzten Sicherung getippt wurde.
  await gsJetztSpeichern();
  const g = await gsRuf({tu: "sichern", schluessel: GSAKTUELL,
                         band: gsBandNr, name});
  if (!g) return false;
  await gsFassungenZeigen();
  if (!still) say(`Fassung „${g.fassung.name}“ gesichert.`, "ok");
  return true;
}

async function gsFassungenZeigen() {
  if (!GSAKTUELL) { $("gsFassungen").innerHTML = ""; return; }
  const g = await gsRuf({tu: "fassungen", schluessel: GSAKTUELL,
                         band: gsBandNr});
  if (!g) return;
  const liste = g.fassungen || [];
  $("gsFassungen").innerHTML = !liste.length ? "" :
    `<p class="hint">Fassungen dieses Bandes:</p>`
    + liste.slice().reverse().map(f => `<div class="fassung">
        <b>${esc(f.name)}</b>
        <span class="art">${esc(f.wann)} · ${f.zeilen} Szenen</span>
        <span class="fuell"></span>
        <a href="#" onclick="gsFassungHolen(${f.nr});return false">zurückholen</a>
        <span class="knopf" onclick="gsFassungWeg(${f.nr})"
          title="Fassung löschen">×</span>
      </div>`).join("");
}

async function gsFassungHolen(index) {
  if (!confirm("Diese Fassung zurückholen? Der jetzige Stand wird vorher "
               + "selbst als Fassung gesichert, es geht nichts verloren."))
    return;
  const g = await gsRuf({tu: "holen", schluessel: GSAKTUELL,
                         band: gsBandNr, index});
  if (!g) return;
  await gsOeffnen(GSAKTUELL, gsBandNr);
  say("Fassung zurückgeholt. Der vorige Stand liegt als Fassung daneben.", "ok");
}

async function gsFassungWeg(index) {
  if (!confirm("Diese Fassung endgültig löschen?")) return;
  if (!await gsRuf({tu: "fassung_weg", schluessel: GSAKTUELL,
                    band: gsBandNr, index})) return;
  await gsFassungenZeigen();
  say("Fassung gelöscht.", "ok");
}

$("gsSichern").onclick = e => {
  e.preventDefault();
  const name = prompt("Wie soll die Fassung heißen?", "");
  if (name === null) return;
  gsFassungSichern(name, false);
};

// Dieselben drei Schritte, aber nur fuer eine Szene: Text, Bausteine, Bild.
// Wer eine Zeile geaendert hat, will nicht die ganze Geschichte neu rechnen.
async function prosaFuerSzene(i) {
  const z = gsZeilen[i];
  if (!z || !z.text.trim()) return say("Die Szene ist leer.", "err");
  const res = await fetch("/api/prosa", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen: [z], nummern: [i + 1],
                          kurz: $("gsKurz").value, welt: $("gsWelt").value,
                          alter: $("gsFreigabe").value,
                          fiktion: +$("gsFiktion").value,
                          ...erzaehlerFelder(),
                          modell: $("gsModell").value})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Die Prosa ließ sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say(`Der Text zu Szene ${i + 1} wird geschrieben …`);
}

async function bausteineAktualisierenSzene(i) {
  const z = gsZeilen[i];
  if (!z || !z.text.trim()) return;
  const g = await bausteinRuf({tu: "aktualisieren", zeilen: [z]});
  if (!g) return;
  const h = offeneNamen(z.text).length
    ? await bausteinRuf({tu: "vorschlagen", zeilen: [z]}) : {neu: []};
  if (!h) return;
  await bausteineHolen();
  zeigeSelbstszenen();
  const teile = [];
  if ((g.weg || []).length) teile.push(`${g.weg.join(", ")} aufgegangen`);
  if (g.neu.length) teile.push("nachgezogen: " + mitArt(g.neu));
  if (h.neu.length) teile.push("angelegt: " + mitArt(h.neu));
  say(teile.length ? teile.join(" · ") + "."
                   : `Szene ${i + 1}: nichts zu übernehmen.`, "ok");
}

// Alles fuer diese eine Szene: erst die Bausteine, dann das Bild.
async function szeneAktualisieren(i) {
  await bausteineAktualisierenSzene(i);
  await promptFuerSzene(i);
}

function zeigeExpose(e) {
  // Der Text zu den Szenen, aus dem eigenen Schritt.
  if (e && e.nur_prosa) {
    const liste = e.prosa || [];
    if (!liste.length || gsProsaZuletzt === JSON.stringify(liste)) return;
    gsProsaZuletzt = JSON.stringify(liste);
    const voll = gsZeilen.filter(z => z.text.trim());
    const prompts = (GESCHICHTE && GESCHICHTE.prompts) || [];
    liste.forEach(x => {
      const z = voll[(x.nr || 0) - 1];
      if (!z || !(x.text || "").trim()) return;
      z.prosa = x.text;
      // Ein neuer Autor aendert die Stimme, nicht das Sichtbare. Der Prompt
      // gilt deshalb weiter -- sonst staende hinter jeder Szene "geaendert"
      // und man rechnete Bilder neu, die genauso aussehen wuerden.
      const p = prompts.find(q => q.nr === x.nr);
      if (p) p.prosa_quelle = x.text;
    });
    zeigeSelbstszenen();
    gsMerken();
    say(`${liste.filter(x => x.text).length} Absätze geschrieben — `
        + "in jeder Szene unter „Prosa“. Bausteine, Kamera und Bildprompts "
        + "sind unberührt.", "ok");
    return;
  }
  // Stufe 1 bringt Rahmen und Abschnitte, aber noch keine Szenen.
  if (e && e.nur_rahmen) {
    if (e.kurz && e.kurz !== $("gsKurz").value) $("gsKurz").value = e.kurz;
    GSRAHMEN = {anfang: e.anfang || "", ende: e.ende || "",
                kapitel: e.kapitel || []};
    zeigeRahmen();
    gsMerken();
    say(`„${e.titel || "Geschichte"}“ gelesen: Anfang und Ende stehen, `
        + `${GSRAHMEN.kapitel.length} Abschnitte. Jetzt „Szenen schreiben“.`,
        "ok");
    return;
  }
  if (e && e.nur_szenen) {
    const neu = (e.szenen || []).filter(t => (t || "").trim());
    if (!neu.length || gsErgaenztZuletzt === JSON.stringify(neu)) return;
    gsErgaenztZuletzt = JSON.stringify(neu);
    gsZeilen = neu.map(t => ({text: t, bilder: 1}));
    zeigeSelbstszenen();
    gsMerken();
    say(`${neu.length} Szenen geschrieben — die letzte ist das Ende.`, "ok");
    return;
  }
  // Eine Ergaenzung bringt keine Kurzfassung mit, nur neue Zeilen. Sie
  // werden angehaengt, nicht eingesetzt -- das Vorhandene bleibt stehen.
  if (e && e.nur_ergaenzung) {
    const neu = (e.szenen || []).filter(t => t !== undefined);
    if (!neu.length || gsErgaenztZuletzt === JSON.stringify(neu)) return;
    gsErgaenztZuletzt = JSON.stringify(neu);
    gsZeilen = gsZeilen.filter(z => z.text.trim())
      .concat(neu.map(t => ({text: t, bilder: 1})));
    zeigeSelbstszenen();
    gsMerken();
    say(`${neu.filter(t => t).length} Szenen ergänzt.`, "ok");
    return;
  }
  if (!e || !e.kurz || e.kurz === $("gsKurz").value) return;
  $("gsKurz").value = e.kurz;
  if (e.stil) $("gsStil").value = e.stil;
  if (e.welt) {
    $("gsWelt").value = e.welt;
    // Den Regler nur nachziehen, wenn er noch auf Anschlag steht -- eine
    // bewusst gewaehlte Zwischenstellung soll nicht ueberschrieben werden.
    const jetzt = +$("gsFiktion").value;
    if (jetzt === 0 || jetzt === 10) {
      $("gsFiktion").value = {wirklich: 0, scifi: 6, fantasie: 8, maerchen: 10}[e.welt] ?? jetzt;
      zeigeGrad();
    }
  }
  if (e.szenen && e.szenen.length) {
    gsZeilen = e.szenen.map(t => ({text: t, bilder: 1}));
    zeigeSelbstszenen();
  }
  say(`„${e.titel || "Geschichte"}“ umrissen — Stil und Welt sind gesetzt, `
      + "das Inhaltsverzeichnis ist ein Vorschlag.", "ok");
}

// --- Schritt 3: Prompts schreiben lassen ---
$("gsErzeugen").onclick = async e => {
  e.preventDefault();
  const zeilen = gsZeilen.filter(z => z.text.trim());
  if (!zeilen.length) return say("Erst das Inhaltsverzeichnis füllen.", "err");
  const res = await fetch("/api/gliederung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, stil: $("gsStil").value, welt: $("gsWelt").value,
                          kurz: $("gsKurz").value, fiktion: +$("gsFiktion").value,
                          modell: $("gsModell").value,
                          schluessel: GSAKTUELL, band: gsBandNr,
                          prosa: $("gsProsa").checked})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Die Prompts ließen sich nicht schreiben.", "err");
  }
  buttonState("busy");
  poll();
  say("Die Prompts werden geschrieben …");
};

let gsLetztePrompts = "";

// Der fertige Prompt haengt nicht nur an den geschriebenen Prompts, sondern
// auch an den Bausteinen der Zeile. Wer einen herausnimmt, will ihn sofort
// verschwinden sehen -- bisher blieb er stehen, bis irgendwann ein Prompt
// neu geschrieben wurde. Kurz verzoegert, damit nicht jeder Tastendruck
// einen Rundlauf ausloest.
let gsVorschauUhr = null;

function gsVorschau() {
  clearTimeout(gsVorschauUhr);
  gsVorschauUhr = setTimeout(gsVorschauHolen, 400);
}

async function gsVorschauHolen() {
  const prompts = (GESCHICHTE && GESCHICHTE.prompts) || [];
  if (!prompts.length) return;
  const zeilen = zeilenFuerServer();
  if (!zeilen.length) return;
  const g = await fetch("/api/szenen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, prompts, stil: $("gsStil").value})
  }).then(r => r.json()).catch(() => null);
  if (!g) return;
  GESCHICHTE = {...g, prompts};
  zeigeSelbstszenen();
  zeigeSzenenliste();
}

async function zeigeGliederung(prompts) {
  if (!prompts || !prompts.length) return;
  // Genau vergleichen, nicht nur Laenge und erster Prompt: wird eine einzelne
  // Szene nachgeschrieben, bleibt beides gleich und die Aenderung fiele unter
  // den Tisch.
  const jetzt = JSON.stringify(prompts);
  if (jetzt === gsLetztePrompts) return;
  gsLetztePrompts = jetzt;
  const zeilen = zeilenFuerServer();
  const g = await fetch("/api/szenen", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({zeilen, prompts, stil: $("gsStil").value})
  }).then(r => r.json()).catch(() => null);
  if (!g) return;
  GESCHICHTE = {...g, prompts};
  // Die Prosa gehoert zur Szene, nicht zum Prompt: dort laesst sie sich
  // lesen und aendern, und sie ueberlebt das naechste Prompt-Schreiben.
  prompts.forEach(p => {
    const z = gsZeilen[(p.nr || 0) - 1];
    if (z && (p.prosa || "").trim() && !(z.prosa || "").trim()) z.prosa = p.prosa;
  });
  zeigeSelbstszenen();
  gsMerken();
  zeigeSzenenliste();
  $("gsHinweis").textContent = `${g.bilder} Bild(er) entstehen daraus.`;
  $("gsKnoepfe").style.display = "block";
}

// Die Liste unter Schritt 3. Sie zeigte den Text des Sprachmodells -- darin
// steht ein Baustein auch dann noch, wenn man ihn aus der Szene genommen
// hat. Jetzt steht dort derselbe fertige Prompt wie in der Szene selbst,
// und wo er nicht mehr passt, steht es daneben.
function zeigeSzenenliste() {
  const prompts = (GESCHICHTE && GESCHICHTE.prompts) || [];
  const name = (liste, k) => (liste.find(x => x.key === k) || {}).label || "";
  $("gsSzenen").innerHTML = prompts.map(p => {
    const i = (p.nr || 0) - 1;
    const fertig = ((GESCHICHTE && GESCHICHTE.je_szene) || [])
      .filter(x => x.nr === p.nr).flatMap(x => x.texte || []);
    const z = gsZeilen[i] || {};
    return `
    <div class="szene"><span class="nr">${p.nr}</span>
      <div class="sztext"><b>${esc(p.zeile)}</b>
        ${p.mimik ? `<span class="art">${esc(name(MIMIKLISTE, p.mimik))}</span>` : ""}
        ${i >= 0 && veraltet(i)
          ? `<span class="wink">geändert — „Prompt ↻“ in der Szene</span>` : ""}
        ${(fertig.length ? fertig : [p.prompt]).map(t =>
            `<br><code>${esc(t)}</code>`).join("")}
        ${(z.prosa || p.prosa) ? `<br><i>${esc(z.prosa || p.prosa)}</i>` : ""}</div>
    </div>`;
  }).join("");
}

// --- Schritt 4: in den Ablauf oder gleich erzeugen ---
async function geschichteInAblauf() {
  if (!GESCHICHTE) return false;
  bloecke = JSON.parse(JSON.stringify(GESCHICHTE.bloecke));
  if (GESCHICHTE.startbild) {
    const antwort = await fetch("/outputs/" + GESCHICHTE.startbild).catch(() => null);
    if (antwort && antwort.ok) {
      const blob = await antwort.blob();
      demoRef = await new Promise(fertig => {
        const leser = new FileReader();
        leser.onload = () => fertig(leser.result);
        leser.readAsDataURL(blob);
      });
      $("demoPreview").src = demoRef;
      $("demoPreview").style.display = "block";
      $("demoRefNote").textContent = "Startbild aus dem Baustein übernommen.";
    }
  }
  return true;
}

$("gsUebernehmen").onclick = async e => {
  e.preventDefault();
  if (!await geschichteInAblauf()) return;
  setMode("demo");
  blockZeichnen();
  demoDauer();
  say("In den Ablauf übernommen. Dort prüfen und starten.", "ok");
};

$("gsSofort").onclick = async e => {
  e.preventDefault();
  if (!await geschichteInAblauf()) return;
  blockZeichnen();
  await starteDemo();
};

// ---------- Katalog ----------
// Alle Bausteine aus allen Projekten. Die Bibliothek waechst ueber ein
// Projekt hinaus: wer eine Person einmal beschrieben hat, will sie im
// naechsten Vorhaben wiedersehen, ohne sie neu zu bauen.
let KATALOG = [], KATPROJEKTE = [], KATFEHLT = [];

async function katalogHolen() {
  const g = await bausteinRuf({tu: "katalog"});
  if (!g) return;
  KATALOG = g.bausteine;
  KATPROJEKTE = g.projekte;
  KATFEHLT = g.fehlend || [];
  if ($("katArt").options.length <= 1) {
    $("katArt").innerHTML = '<option value="">alle</option>'
      + BSARTEN.map(a => `<option value="${a.key}">${esc(a.label)}</option>`).join("");
  }
  katalogZeigen();
}

function katalogZeigen() {
  const art = $("katArt").value;
  const suche = $("katSuche").value.trim().toLowerCase();
  const passt = b => (!art || b.art === art)
    && (!suche || (b.name + " " + b.prompt).toLowerCase().includes(suche));
  const gefunden = KATALOG.filter(passt);
  $("katZahl").textContent = gefunden.length === 1
    ? "1 Baustein" : `${gefunden.length} Bausteine`;

  const label = k => (BSARTEN.find(a => a.key === k) || {}).label || k;
  const nach = KATPROJEKTE.map(p => p.key);
  $("katListe").innerHTML = KATPROJEKTE.map(p => {
    const eigene = gefunden.filter(b => b.projekt === p.key);
    if (!eigene.length) return "";
    return `<div class="katgruppe"><h3>${esc(p.label)}</h3>` + eigene.map(b => {
      const ziele = nach.filter(k => k !== b.projekt);
      return `<div class="baustein katzeile">
        ${b.bild ? `<img src="/bilder/${b.projekt}/${b.bild}" alt="${esc(b.name)}">`
                 : `<span class="ohnebild">?</span>`}
        <div class="bstext"><b>${esc(b.name)}</b>
          <span class="art">${esc(label(b.art))}</span><br>
          <code>${esc(b.prompt)}</code></div>
        ${ziele.length ? `<select onchange="katalogKopieren('${b.projekt}','${b.id}',this)">
            <option value="">kopieren nach …</option>
            ${ziele.map(k => `<option value="${k}">${esc(
                (KATPROJEKTE.find(x => x.key === k) || {}).label || k)}</option>`).join("")}
          </select>` : ""}
      </div>`;
    }).join("") + "</div>";
  }).join("") || `<p class="hint">Noch keine Bausteine — im Reiter
      <b>Bausteine</b> legst du welche an.</p>`;

  // Was eine Geschichte mit /Name verlangt, aber noch nicht gibt.
  const offen = KATFEHLT.filter(f => !suche
    || f.name.toLowerCase().includes(suche));
  $("katListe").innerHTML += offen.length
    ? `<div class="katgruppe"><h3>Noch anzulegen</h3>` + offen.map(f =>
        `<div class="baustein katzeile"><span class="ohnebild">!</span>
          <div class="bstext"><b>${esc(f.name)}</b>
            <span class="art">in „${esc(f.projektname)}“ verlangt</span><br>
            <code>mit /${esc(f.name)} in der Geschichte erwähnt, aber nicht angelegt</code></div>
          <span class="knopf" onclick="bausteinAnlegen('${esc(f.name)}')"
            title="jetzt anlegen">+</span>
        </div>`).join("") + "</div>"
    : "";
}

// Aus dem Katalog heraus einen fehlenden Baustein anlegen.
function bausteinAnlegen(name) {
  setMode("bausteine");
  bausteinLeeren();
  $("bsName").value = name;
  $("bsText").focus();
  say(`„${name}“ beschreiben und Prompt erzeugen lassen.`);
}

async function katalogKopieren(von, id, feld) {
  const nach = feld.value;
  feld.value = "";
  if (!nach) return;
  const b = await bausteinRuf({tu: "kopieren", von, nach, id});
  if (!b) return;
  await katalogHolen();
  await bausteineHolen();
  const ziel = (KATPROJEKTE.find(x => x.key === nach) || {}).label || nach;
  say(`„${b.name}“ nach „${ziel}“ kopiert.`, "ok");
}

$("katArt").onchange = katalogZeigen;
$("katSuche").addEventListener("input", katalogZeigen);

// ---------- Sechs Seiten ----------
// Ein Gegenstand, sechsmal gerade von einer Seite. Die Bilder liegen im
// Katalogverzeichnis und nicht in outputs/ -- deshalb hat dieser Reiter
// seine eigene Liste und seine eigenen Verweise, /katalog/... statt
// /outputs/...
let SEITENNAMEN = [], SEITENKATALOG = [];

async function seitenRuf(daten) {
  const res = await fetch("/api/sechsseiten", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(daten)
  }).then(r => r.json()).catch(() => null);
  if (!res || res.error) {
    say(res ? res.error : "Der Server ist nicht erreichbar.", "err");
    return null;
  }
  return res;
}

// Die Gegenstaende aus den Bausteinen. Wer einen angelegt hat, soll ihn
// nicht ein zweites Mal beschreiben muessen.
function seitenGegenstandFuellen() {
  const vorher = $("seitenGegenstand").value;
  const dinge = BAUSTEINE.filter(b => b.art === "gegenstand");
  $("seitenGegenstand").innerHTML = `<option value="">— frei beschreiben —</option>`
    + dinge.map(b => `<option value="${b.id}">${esc(b.name)}</option>`).join("");
  if (vorher) $("seitenGegenstand").value = vorher;
  seitenQuelle();
}

// Ein Baustein bringt seinen Prompt mit; das Beschreibungsfeld haette dann
// keine Wirkung. Lieber gesperrt als wirkungslos -- sonst tippt man einen
// Satz hinein und sucht ihn hinterher im Bild.
function seitenQuelle() {
  const eigen = !$("seitenGegenstand").value;
  $("seitenText").disabled = !eigen;
  $("seitenAusformulieren").disabled = !eigen;
}
$("seitenGegenstand").addEventListener("change", seitenQuelle);

// Die sechs Plaetze. Was noch fehlt, bleibt als leeres Feld stehen -- so ist
// zu sehen, wie viele Ansichten noch kommen.
function seitenMosaik(projekt, id, bilder, sichten) {
  return `<div class="mosaic">` + SEITENNAMEN.map(s => {
    const datei = (bilder || {})[s.key];
    const url = `/katalog/${projekt}/${id}/${datei}`;
    // Was das Sprachmodell ueber diese Ansicht gesagt hat, haengt am Bild:
    // bei einer schiefen Ansicht steht sonst nirgends, woran es lag.
    const satz = ((sichten || {})[s.key] || "").trim();
    return datei
      ? `<figure class="tile">
           <img src="${url}" alt="${esc(s.label)}" title="${esc(satz)}">
           <figcaption><span>${esc(s.label)}</span>
             <a href="${url}" download title="Herunterladen">&darr;</a></figcaption>
         </figure>`
      : `<div class="slot" title="${esc(satz)}">${esc(s.label)}</div>`;
  }).join("") + `</div>`;
}

// Der Eintrag, waehrend er entsteht.
function zeigeSeiten(st) {
  if (!st || !st.id) { $("seitenJetzt").innerHTML = ""; return; }
  // So hat das Sprachmodell den Gegenstand von jeder Seite gelesen. Das ist
  // die Stelle, an der eine danebengegangene Ansicht erklaerbar wird.
  const sichten = st.sichten || {};
  const gelesen = SEITENNAMEN.filter(s => (sichten[s.key] || "").trim())
    .map(s => `<b>${esc(s.label)}:</b> ${esc(sichten[s.key])}`).join("<br>");
  $("seitenJetzt").innerHTML =
    `<p class="hint">Im Katalog entsteht: <b>${esc(st.name || "")}</b><br>`
    + `<code>${esc(st.prompt || "")}</code></p>`
    + (gelesen ? `<p class="hint">${gelesen}</p>` : "")
    + seitenMosaik(st.projekt, st.id, st.bilder, sichten);
}

async function seitenHolen() {
  const g = await seitenRuf({tu: "liste"});
  if (!g) return;
  if (!SEITENNAMEN.length) SEITENNAMEN = g.seiten || [];
  SEITENKATALOG = g.katalog || [];
  zeigeSeitenKatalog();
}

function zeigeSeitenKatalog() {
  const n = SEITENKATALOG.length;
  $("seitenZahl").textContent = n === 1 ? "1 Gegenstand" : `${n} Gegenstände`;
  $("seitenListe").innerHTML = n
    ? SEITENKATALOG.map(e => {
      const fehlt = SEITENNAMEN.length - Object.keys(e.bilder || {}).length;
      return `<div class="katgruppe">
        <h3>${esc(e.name)} <span class="art">${esc(e.projektname)}</span>
          <span class="knopf" onclick="seitenWeg('${e.projekt}','${e.id}')"
            title="Eintrag mit allen Bildern löschen">×</span></h3>
        <p class="hint">${esc(e.angelegt || "")}${
          fehlt > 0 ? ` · noch ${fehlt} ohne Bild` : ""}<br>
          <code>${esc(e.prompt || "")}</code><br>
          <a href="#" onclick="seitenPrompt('${e.id}');return false">Prompt
            übernehmen</a> ·
          <a href="#" onclick="seitenVorlage('${e.projekt}','${e.id}');return false">Vorderansicht
            als Vorlage</a> — für <code>/magazine cover</code>,
          <code>/ptexplosion</code>, <code>/cad</code>, <code>/blueprint</code></p>
        ${seitenMosaik(e.projekt, e.id, e.bilder, e.sichten)}
      </div>`;
    }).join("")
    : `<p class="hint">Noch kein Gegenstand im Katalog.</p>`;
}

async function seitenWeg(projekt, id) {
  if (!confirm("Diesen Katalogeintrag mit allen sechs Bildern endgültig "
               + "löschen? Einen Papierkorb gibt es nicht.")) return;
  const erg = await seitenRuf({tu: "loeschen", projekt: projekt, id: id});
  if (!erg) return;
  say("Katalogeintrag gelöscht.", "ok");
  seitenHolen();
}

// Der Gegenstandsprompt in Text->Bild. Er ist das, was den Gegenstand
// ausmacht -- aus ihm laesst sich alles Weitere bauen.
function seitenPrompt(id) {
  const e = SEITENKATALOG.find(x => x.id === id);
  if (!e) return;
  setMode("t2i");
  $("prompt").value = e.prompt || "";
  say("Prompt übernommen — jetzt lässt sich daraus Neues bauen.", "ok");
}

// Die Vorderansicht als Referenzbild in Bearbeiten. Das ist der Weg zu
// Cover, Explosionszeichnung, CAD und Bauplan: alle vier setzen auf einem
// Bild auf, nicht auf frischem Text -- sonst waere es ein anderer
// Gegenstand.
async function seitenVorlage(projekt, id) {
  const e = SEITENKATALOG.find(x => x.id === id);
  const datei = ((e || {}).bilder || {}).vorne;
  if (!datei) return say("Dieser Eintrag hat noch keine Vorderansicht.", "err");
  if (refs.length >= maxRefs) return say(`Schon ${maxRefs} Vorlagen geladen.`, "err");
  const antwort = await fetch(`/katalog/${projekt}/${id}/${datei}`)
    .then(r => r.blob()).catch(() => null);
  if (!antwort) return say("Das Bild ließ sich nicht laden.", "err");
  const leser = new FileReader();
  leser.onload = () => {
    refs.push(leser.result);
    refPrompts.push("");
    setMode("edit");
    drawThumbs();
    say("Vorderansicht als Vorlage geladen — jetzt einen Effekt wählen.", "ok");
  };
  leser.readAsDataURL(antwort);
}

async function seitenStarten() {
  const text = $("seitenText").value.trim();
  const gegenstand = $("seitenGegenstand").value;
  if (!text && !gegenstand) {
    return say("Bitte den Gegenstand beschreiben oder einen Baustein wählen.", "err");
  }
  let seed = parseInt($("seed").value, 10);
  if (isNaN(seed) || seed < 0) {
    seed = Math.floor(Math.random() * 2 ** 31);
    $("seed").value = seed;
  }
  buttonState("busy");
  const res = await seitenRuf({
    text: text, gegenstand: gegenstand,
    name: $("seitenName").value.trim(), stil: $("seitenStil").value,
    ausformulieren: $("seitenAusformulieren").checked,
    base: parseInt($("base").value, 10),
    steps: parseInt($("steps").value, 10),
    seed: seed, modell: $("gsModell").value});
  if (!res) return buttonState("idle");
  say("Die sechs Seiten werden gerechnet …", "ok");
  poll();
}
$("seitenGo").onclick = e => { e.preventDefault(); seitenStarten(); };

// Erst der Vorschlag, dann das Nachbessern, dann die Bilder. Das
// Sprachmodell schreibt den ganzen Satz Befehle ins Feld -- es ist dasselbe,
// das sonst beim Erzeugen im Verborgenen liefe, nur sichtbar und aenderbar.
async function seitenVorschlagen() {
  const text = $("seitenText").value.trim();
  if (!text) return say("Bitte zuerst beschreiben, was zu sehen sein soll.", "err");
  $("seitenVorschlag").textContent = "schreibt …";
  const res = await seitenRuf({tu: "vorschlag", text: text,
                               modell: $("gsModell").value});
  $("seitenVorschlag").innerHTML = "<b>Vorschlag schreiben lassen</b>";
  if (!res) return;
  $("seitenText").value = res.text;
  seitenQuelle();
  say("Vorschlag steht — durchlesen, ändern, dann erzeugen.", "ok");
}
$("seitenVorschlag").onclick = e => { e.preventDefault(); seitenVorschlagen(); };

// ---------- Projekte ----------
// Ein Projekt bestimmt, wohin neue Bilder gehen und welche die Galerie zeigt.
// "Allgemein" ist das alte outputs/ -- die Bilder von frueher bleiben dort.
function zeigeProjekte(liste, aktiv) {
  if (!Array.isArray(liste)) return meldeLuecke("projekt");
  $("projekt").innerHTML = liste.map(x =>
    `<option value="${x.key}"${x.key === aktiv ? " selected" : ""}>`
    + `${esc(x.label)} (${x.bilder})</option>`).join("");
  const eigenes = aktiv !== "allgemein";
  $("projektUm").style.display = eigenes ? "inline" : "none";
  $("projektWeg").style.display = eigenes ? "inline" : "none";
}

async function projektTun(rumpf) {
  const res = await fetch("/api/projekt", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(rumpf)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Das hat nicht geklappt.", "err");
    return null;
  }
  const info = await fetch("/api/info").then(r => r.json()).catch(() => null);
  if (info) { zeigeProjekte(info.projekte, info.projekt); zeigeBausteine(info.bausteine); }
  loadGallery();
  return res.json();
}

$("projekt").onchange = async () => {
  await projektTun({tu: "waehlen", key: $("projekt").value});
  say(`Projekt gewechselt: ${$("projekt").selectedOptions[0].textContent}`, "ok");
};

$("projektNeu").onclick = async e => {
  e.preventDefault();
  const name = prompt("Wie soll das Projekt heißen?");
  if (!name) return;
  await projektTun({tu: "anlegen", name});
  say(`Projekt „${name}“ angelegt und ausgewählt.`, "ok");
};

$("projektUm").onclick = async e => {
  e.preventDefault();
  const alt = $("projekt").selectedOptions[0].textContent.replace(/ \(\d+\)$/, "");
  const name = prompt("Neuer Name:", alt);
  if (!name) return;
  await projektTun({tu: "umbenennen", key: $("projekt").value, name});
};

$("projektWeg").onclick = async e => {
  e.preventDefault();
  const wahl = $("projekt").selectedOptions[0];
  if (!confirm(`„${wahl.textContent}“ mit allen Bildern endgültig löschen?`)) return;
  const erg = await projektTun({tu: "loeschen", key: $("projekt").value});
  if (erg) say("Projekt gelöscht.", "ok");
};

// ---------- Fortschritt ----------
// Welcher Auftrag gerade laeuft -- am Wechsel erkennt die Seite, dass der
// vorige fertig ist.
let laufendeNummer = 0;

// Versehentlich zugemacht: der Server laeuft weiter, die Arbeit geht also
// nicht verloren -- nur zusehen kann man dann nicht mehr. Deshalb nachfragen,
// solange etwas laeuft oder wartet.
let laufendeArbeit = false, wartendeAnzahl = 0, beendetGewollt = false;
window.addEventListener("beforeunload", e => {
  if (beendetGewollt || (!laufendeArbeit && !wartendeAnzahl)) return;
  e.preventDefault();
  e.returnValue = "";
});

function poll() {
  clearInterval(polling);
  polling = setInterval(async () => {
    const s = await fetch("/api/status").then(r => r.json()).catch(() => null);
    if (!s) return;

    const done = (s.results || []).length;
    // Anzeigen duerfen scheitern, ohne die Abfrage mitzureissen: sonst
    // bleibt der Knopf stehen, obwohl der Auftrag laengst fertig ist.
    try {
      zeigeUebersetzung(s.translated);
      zeigeGelesen(s.gelesen);
      // Was der Torwaechter gestrichen hat, soll man sehen.
      $("torNote").textContent = (s.tor || []).length
        ? "Aus dem Prompt gestrichen: " + s.tor.join(" · ") : "";
      const f = s.fortschritt || {};
      if (f.von && !done) {
        // Ein Auftrag ohne Bilder -- Prompts schreiben, umreissen. Der Balken
        // zaehlt dann die Szenen, sonst staende er die ganze Zeit auf null.
        $("fill").style.width = (100 * f.ist / f.von) + "%";
      } else {
        const perImage = s.total ? s.step / s.total : 0;
        $("fill").style.width =
          (100 * (done + (s.busy ? perImage : 0)) / Math.max(s.count, 1)) + "%";
      }
      paintSeries(s.results || [], s.count, s.image);
      zeigeWarteschlange(s);
      zeigeExpose(s.expose);
      zeigeGliederung(s.gliederung);
      zeigeBau(s.bau);
      zeigeSeiten(s.seiten);
      laufendeArbeit = !!(s.busy && s.titel);
      wartendeAnzahl = (s.wartend || []).length;
      // Wechselt der laufende Auftrag, ist der vorige fertig -- seine Bilder
      // sollen dann sofort in der Galerie stehen, nicht erst ganz am Ende.
      if (s.nummer && s.nummer !== laufendeNummer) {
        if (laufendeNummer) loadGallery();
        laufendeNummer = s.nummer;
      }
    } catch (e) {
      console.error(e);
    }

    if (s.busy) return say((s.stage ? s.stage + " · " : "") + s.message
                          + " · " + fmt(s.elapsed) + karteText(s));

    clearInterval(polling);
    if (s.error) { buttonState("idle"); $("fill").style.width = "0"; return say(s.error, "err"); }
    buttonState(done ? "done" : "idle");
    if (s.video) zeigeVideo(s.video);
    if (done) say(`${s.message} in ${fmt(s.elapsed)}`, "ok");
    else { $("fill").style.width = "0"; say(s.message); }
    // Der Katalog liegt ausserhalb von outputs/ -- loadGallery() sieht ihn
    // nicht, er muss eigens nachgeladen werden.
    if (mode === "seiten") seitenHolen();
    loadGallery();
  }, 900);
}
// Die Stufen eines Szenenaufbaus, waehrend sie entstehen. Ohne diese Liste
// sieht ein Aufbau aus wie ein haengender Auftrag: acht Bilder lang
// passiert scheinbar nichts, und das Ergebnis kommt erst ganz zum Schluss.
function zeigeBau(bau) {
  const stufen = (bau || {}).stufen || [];
  if (!stufen.length) { $("bauStufen").innerHTML = ""; return; }
  const plan = bau.plan || {};
  const spiegel = plan.spiegelung || {};
  const kopf = [];
  if ((plan.kulisse || "").trim()) kopf.push("Raum: " + plan.kulisse);
  (plan.figuren || []).forEach(f => {
    const was = [f.pose, f.platz].filter(t => (t || "").trim()).join(", ");
    if (was) kopf.push(`${f.name}: ${was}`);
  });
  if ((spiegel.wo || "").trim()) {
    kopf.push(`Spiegelung${spiegel.name ? " von " + spiegel.name : ""}: ${
      spiegel.wo}`);
  }
  $("bauStufen").innerHTML =
    `<p class="hint">So hat das Sprachmodell die Szene gelesen — ${
      esc(kopf.join(" · "))}</p>`
    + `<ol class="baustufen">` + stufen.map(st =>
      `<li class="${esc(st.art)}${st.ergebnis ? " ergebnis" : ""}">${
        esc(st.titel)}${st.ergebnis ? " — das fertige Bild" : ""}</li>`)
      .join("") + `</ol>`;
}

// Der laufende Auftrag und die wartenden darunter. Wartende lassen sich
// verschieben und herausnehmen; der laufende nur abbrechen, er hat schon
// Rechenzeit verbraucht.
function zeigeWarteschlange(s) {
  const zeilen = [];
  if (s.busy && s.titel) {
    zeilen.push(`<div class="zeile laeuft"><span class="nr">#${s.nummer}</span>`
      + `<span class="was">${esc(s.titel)}</span><span>läuft</span></div>`);
  }
  (s.wartend || []).forEach((a, i, alle) => {
    zeilen.push(`<div class="zeile"><span class="nr">#${a.nummer}</span>`
      + `<span class="was">${esc(a.titel)}</span>`
      + (i > 0 ? `<span class="knopf" onclick="auftragSchieben(${a.nummer},'hoch')" title="nach vorn">↑</span>` : "")
      + (i < alle.length - 1 ? `<span class="knopf" onclick="auftragSchieben(${a.nummer},'runter')" title="nach hinten">↓</span>` : "")
      + `<span class="knopf" onclick="auftragWeg(${a.nummer})" title="entfernen">×</span></div>`);
  });
  (s.verlauf || []).slice(0, 3).forEach(a => {
    const wie = a.zustand === "fertig" ? `${a.bilder} Bild(er)` : a.zustand;
    zeilen.push(`<div class="zeile fertig"><span class="nr">#${a.nummer}</span>`
      + `<span class="was">${esc(a.titel)}</span><span>${wie}</span></div>`);
  });
  if ((s.wartend || []).length > 1) {
    zeilen.push(`<p class="hint"><a href="#" onclick="listeLeeren();return false">`
      + `Warteliste leeren</a> — der laufende Auftrag bleibt.</p>`);
  }
  $("warteschlange").innerHTML = zeilen.join("");
}

async function auftragWeg(nummer) {
  await fetch("/api/cancel", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({nummer})}).catch(() => null);
}

async function auftragSchieben(nummer, richtung) {
  await fetch("/api/verschieben", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({nummer, richtung})}).catch(() => null);
}

async function listeLeeren() {
  if (!confirm("Alle wartenden Aufträge verwerfen?")) return;
  await fetch("/api/cancel", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({alles: true})}).catch(() => null);
}

const fmt = sec => sec < 90 ? `${Math.round(sec)}s` : `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")} min`;

// Was der Server im Startbild erkannt hat. Die Beschreibung landet in den
// Bewahrungsklauseln, deshalb soll sichtbar sein, was dort gelesen wurde.
function zeigeGelesen(g) {
  if (!g || !g.beschreibung) return;
  $("demoRefNote").textContent = "Im Startbild erkannt: " + g.beschreibung
    + (g.geschlecht && g.geschlecht !== "unklar" ? ` (${g.geschlecht})` : "");
}

// Was der Server vor dem Auftrag übersetzt hat — damit nachvollziehbar ist,
// was das Bildmodell tatsächlich gelesen hat.
const FELDNAME = {prompt: "Prompt", keep: "Unverändert", paint_target: "Umgefärbt",
                  negative_prompt: "Negativ"};
function zeigeUebersetzung(t) {
  const el = $("transNote");
  if (!t || !Object.keys(t).length) { el.style.display = "none"; return; }
  el.style.display = "block";
  el.innerHTML = "Ins Englische übersetzt — "
    + Object.entries(t).map(([k, v]) => `<b>${FELDNAME[k] || k}:</b> ${esc(v)}`).join(" · ");
}

// ---------- Mosaik der Serie ----------
let seriesFiles = [];

// Leere Plaetze fuer einen angekuendigten Ablauf: so ist von Anfang an zu
// sehen, wie viele Bilder noch kommen.
function startSlots(anzahl) { paintSeries([], anzahl, 1); }
function paintSeries(files, count, active) {
  const cells = [];
  for (let i = 0; i < Math.max(count, files.length); i++) {
    const f = files[i];
    cells.push(f
      ? `<figure class="tile">
           <img src="/outputs/${f}" alt="${f}" onclick="show('${f}')"
                onload="this.closest('.tile').querySelector('.px').textContent=this.naturalWidth+'×'+this.naturalHeight">
           <figcaption><span class="px"></span><span class="cam" id="cam-${i}"></span>
             <a href="/outputs/${f}" download title="Herunterladen">&darr;</a></figcaption>
         </figure>`
      : `<div class="slot${i === active - 1 ? " now" : ""}">${i === active - 1 ? "…" : ""}</div>`);
  }
  const html = cells.join("");
  if ($("series").innerHTML === html) return;
  $("series").innerHTML = html;
  seriesFiles = files;
  $("seriesHead").style.display = files.length > 1 ? "flex" : "none";
  $("zip").href = "/api/zip?files=" + encodeURIComponent(files.join(","));
  files.forEach((f, i) => fetch("/api/meta?file=" + encodeURIComponent(f))
    .then(r => r.json()).then(m => {
      const el = $("cam-" + i);
      if (el) el.textContent = [m.paint, m.scene].filter(Boolean).join(" · ")
                              || m.view || m.camera || m.style || "";
    }).catch(() => {}));
  if (files.length && !$("stage").dataset.file) show(files[0]);
}

function zeigeVideo(datei) {
  $("stage").dataset.file = "";
  $("stage").innerHTML = `<video src="/outputs/${datei}" controls autoplay muted loop`
    + ` style="max-width:100%;max-height:68vh;border-radius:6px"></video>`;
  $("meta").innerHTML = `<div><a href="/outputs/${datei}" download>${esc(datei)}</a>`
    + ` · Video der Vorführung</div>`;
}

// ---------- Große Anzeige ----------
async function show(file) {
  $("stage").dataset.file = file;
  $("stage").innerHTML = `<img src="/outputs/${file}" alt="Erzeugtes Bild">`;
  [...document.querySelectorAll(".grid img, .tile img")].forEach(
    img => img.classList.toggle("sel", img.alt === file));
  const m = await fetch("/api/meta?file=" + encodeURIComponent(file)).then(r => r.json()).catch(() => ({}));
  const tags = ["scenario", "paint", "material", "scene", "angle", "device", "effect", "form",
                "view", "style", "light", "camera"].filter(k => m[k]).map(k => `<span>${esc(m[k])}</span>`).join("");
  $("meta").innerHTML =
    `<div><a href="/outputs/${file}" download>${esc(file)}</a>`
    + (m.size ? ` · ${m.size[0]} × ${m.size[1]} px` : "")
    + (m.seed ? ` · Seed ${esc(m.seed)}` : "")
    + (hasGimp ? ` · <a href="#" onclick="openInGimp('${file}');return false">In GIMP öffnen</a>` : "")
    + `</div>`
    + (tags ? `<div class="tags">${tags}</div>` : "")
    + (m.prompt ? `<div style="margin-top:7px"><code>${esc(m.prompt)}</code></div>` : "")
    + sterneZeigen(file);
}

// Öffnet das Bild in GIMP auf dem Rechner, auf dem der Server läuft.
async function openInGimp(file) {
  say("GIMP wird gestartet …");
  const res = await fetch("/api/open-in-gimp", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({file})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "GIMP ließ sich nicht starten.", "err");
  }
  say("In GIMP geöffnet. Der erste Start dauert einen Moment.", "ok");
}

// ---------- Video aus ausgewaehlten Bildern ----------
// Die Reihenfolge ist die der Auswahl, nicht die der Galerie -- so laesst
// sich die Abfolge bestimmen, ohne etwas zu verschieben.
let filmModus = false, filmWahl = [];

function filmUmschalten(an) {
  filmModus = an;
  filmWahl = [];
  $("filmLeiste").style.display = an ? "flex" : "none";
  $("gallery").classList.toggle("waehlen", an);
  filmZeigen();
  loadGallery();
}

function filmZeigen() {
  $("filmZahl").textContent = filmWahl.length === 1
    ? "1 Bild gewählt" : `${filmWahl.length} Bilder gewählt`;
  $("gallery").querySelectorAll(".kachel").forEach(el => {
    const platz = filmWahl.indexOf(el.dataset.f);
    const alt = el.querySelector(".nr");
    if (alt) alt.remove();
    if (platz >= 0) {
      const marke = document.createElement("span");
      marke.className = "nr";
      marke.textContent = platz + 1;
      el.appendChild(marke);
    }
  });
}

function filmWaehlen(datei) {
  const platz = filmWahl.indexOf(datei);
  if (platz >= 0) filmWahl.splice(platz, 1);
  else filmWahl.push(datei);
  filmZeigen();
}

$("filmAn").onclick = e => { e.preventDefault(); filmUmschalten(true); };
$("filmAus").onclick = e => { e.preventDefault(); filmUmschalten(false); };

$("filmBauen").onclick = async e => {
  e.preventDefault();
  if (filmWahl.length < 2) return say("Mindestens zwei Bilder wählen.", "err");
  const dauer = parseFloat($("filmDauer").value) || 20;
  say(`Video aus ${filmWahl.length} Bildern wird gebaut …`);
  const res = await fetch("/api/video", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({files: filmWahl, duration: dauer})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Das Video ließ sich nicht bauen.", "err");
  }
  const g = await res.json();
  filmUmschalten(false);
  zeigeVideo(g.video);
  say(`Video fertig: ${g.bilder} Bilder in ${g.dauer} s.`, "ok");
};

async function loadGallery() {
  const antwort = await fetch("/api/gallery").then(r => r.json()).catch(() => null);
  if (!antwort) return;
  await notenHolen();
  $("gallery").innerHTML = antwort.files.map(f => {
    const n = (NOTEN[f] || {}).note || 0;
    return `<figure class="kachel" data-f="${f}"><img src="/outputs/${f}" title="${f}"
       alt="${f}" onclick="${filmModus ? `filmWaehlen('${f}')` : `show('${f}')`}">`
      + (filmModus ? "" : `<b onclick="loeschen('${f}')" title="Löschen">×</b>`)
      + (n ? `<span class="note">${"★".repeat(n)}</span>` : "")
      + `</figure>`;
  }).join("");
  if (filmModus) filmZeigen();
}

// ---------- Noten ----------
// Bewertet wird, damit gute Prompts wiederkommen: ein Bild mit Namen laesst
// sich in einer Szene mit \Name wieder aufrufen. Alles liegt im Projekt in
// bewertung.json -- lesbar, zum Weiterreichen.
let NOTEN = {}, GEMERKTE = [];

async function notenHolen() {
  const b = await fetch("/api/bewertung").then(r => r.json()).catch(() => null);
  if (!b) return;
  NOTEN = b.bilder || {};
  GEMERKTE = b.gemerkte || [];
}

function sterneZeigen(datei) {
  const e = NOTEN[datei] || {};
  const n = e.note || 0;
  return `<div class="noten">
    <div class="sterne">${[1, 2, 3, 4, 5].map(i =>
      `<span class="${i <= n ? "voll" : ""}" title="${i} von 5"
         onclick="benoten('${datei}', ${i === n ? 0 : i})">★</span>`).join("")}</div>
    <input class="name" placeholder="Prompt merken als …"
      value="${esc(e.name || "")}" onchange="merken('${datei}', this.value)">
    ${e.nr ? `<span class="nr">\\${esc(e.name)} oder \\${e.nr}</span>` : ""}
    <input class="notiz" placeholder="Was daran gut oder schlecht ist"
      value="${esc(e.notiz || "")}" onchange="notieren('${datei}', this.value)">
  </div>`;
}

async function notenRuf(daten) {
  const res = await fetch("/api/bewertung", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(daten)
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    say(err.error || "Die Bewertung ließ sich nicht speichern.", "err");
    return null;
  }
  return res.json();
}

async function benoten(datei, note) {
  const e = await notenRuf({file: datei, note});
  if (e === null) return;
  NOTEN[datei] = e;
  if ($("stage").dataset.file === datei) show(datei);
  loadGallery();
}

async function merken(datei, name) {
  const e = await notenRuf({file: datei, name});
  if (e === null) return;
  NOTEN[datei] = e;
  await notenHolen();
  zeigeSelbstszenen();             // die Liste unter den Szenen waechst mit
  if (e.name) {
    say(`Gemerkt. In einer Szene mit \\${e.name} oder \\${e.nr} aufrufbar.`, "ok");
  } else {
    say("Der Name ist weg, der Prompt damit auch.", "ok");
  }
  if ($("stage").dataset.file === datei) show(datei);
}

async function notieren(datei, notiz) {
  const e = await notenRuf({file: datei, notiz});
  if (e !== null) NOTEN[datei] = e;
}

// Endgueltig, ohne Papierkorb -- deshalb die Rueckfrage.
async function loeschen(datei) {
  if (!confirm(`„${datei}“ wirklich löschen?`)) return;
  const res = await fetch("/api/delete", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({file: datei})
  }).catch(() => null);
  if (!res || !res.ok) {
    const err = res ? await res.json().catch(() => ({})) : {};
    return say(err.error || "Löschen ist fehlgeschlagen.", "err");
  }
  if ($("stage").dataset.file === datei) {
    $("stage").dataset.file = "";
    $("stage").innerHTML = "<p>Bild gelöscht.</p>";
    $("meta").innerHTML = "";
  }
  say(`${datei} gelöscht.`, "ok");
  loadGallery();
}

// Haelt den Server an. Danach ist die Seite tot -- das muss sie auch sagen.
async function programmBeenden() {
  const offen = (laufendeArbeit ? 1 : 0) + wartendeAnzahl;
  const frage = offen
    ? `Es ${offen === 1 ? "ist noch ein Auftrag" : `sind noch ${offen} Aufträge`} `
      + "offen. Trotzdem beenden?"
    : "Das Programm beenden?";
  if (!confirm(frage)) return;
  beendetGewollt = true;                 // die Warnung beim Schliessen aus
  await fetch("/api/shutdown", {method: "POST"}).catch(() => null);
  // Den Reiter schliessen darf nur, wer ihn selbst geoeffnet hat. start.sh
  // oeffnet ihn ueber den Browser, also schlaegt das meistens fehl -- dann
  // bleibt die Abschiedsseite stehen.
  document.body.innerHTML = "<main><section class=\"panel\"><h1>Beendet</h1>"
    + "<p>Der Server ist angehalten, die Grafikkarte ist frei. "
    + "Dieser Reiter kann zu. Zum Weitermachen im Terminal wieder "
    + "<code>./start.sh</code> starten.</p></section></main>";
  window.close();
}


// ---------- Splitter zwischen den beiden Spalten ----------
// Die Breite steckt in --links auf <main> und bleibt im Browser stehen.
// Sie gehoert dem Bildschirm, nicht dem Projekt, deshalb localStorage und
// nicht der Server.
const SPLIT_STD = 430, SPLIT_MIN = 320;

function splitSetzen(px) {
  const platz = document.querySelector("main").clientWidth;
  // Rechts muessen mindestens 300 px bleiben, sonst ist die Galerie ein
  // Streifen und man kommt nicht mehr zurueck.
  const max = Math.max(SPLIT_MIN, platz - 320);
  const breit = Math.round(Math.min(Math.max(px, SPLIT_MIN), max));
  document.querySelector("main").style.setProperty("--links", breit + "px");
  try { localStorage.setItem("splitter", breit); } catch (e) { /* egal */ }
}

(function splitterAufbauen() {
  const griff = $("splitter");
  if (!griff) return;
  try {
    const gemerkt = parseInt(localStorage.getItem("splitter"), 10);
    if (gemerkt > 0) splitSetzen(gemerkt);
  } catch (e) { /* ohne Speicher eben die Vorgabe */ }

  let zieht = false;
  griff.addEventListener("pointerdown", e => {
    zieht = true;
    griff.setPointerCapture(e.pointerId);
    griff.classList.add("zieht");
    document.body.classList.add("zieht");
    e.preventDefault();
  });
  griff.addEventListener("pointermove", e => {
    if (!zieht) return;
    const links = document.querySelector("main").getBoundingClientRect().left;
    splitSetzen(e.clientX - links);
  });
  const fertig = e => {
    if (!zieht) return;
    zieht = false;
    try { griff.releasePointerCapture(e.pointerId); } catch (err) { /* egal */ }
    griff.classList.remove("zieht");
    document.body.classList.remove("zieht");
  };
  griff.addEventListener("pointerup", fertig);
  griff.addEventListener("pointercancel", fertig);
  griff.addEventListener("dblclick", () => splitSetzen(SPLIT_STD));
})();


fetch("/api/status").then(r => r.json()).then(s => {
  if (s.busy) { buttonState("busy"); poll(); }
});
loadGallery();
