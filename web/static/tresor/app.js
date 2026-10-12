// Oberfläche der Tresor-App (BETRIEBSMODUS "tresor").
//
// Eine "Single-Page-App" ohne Framework: Jede Ansicht ist eine Funktion, die
// DOM-Elemente baut (ansichtLaden, ansichtErgebnis, ...). Welche Ansicht gezeigt
// wird, steht im #-Teil der Adresse (…/#verlauf). Nach jeder Änderung wird die
// aktuelle Ansicht komplett neu gezeichnet – einfach und für diese Datenmengen schnell genug.
//
// Sicherheit: Texte werden IMMER über textContent eingesetzt (nie innerHTML), damit
// Inhalte aus Exportdateien keinen Code einschleusen können (XSS).

import * as A from "./auswertung.js";
import { ExportFormatFehler, ladeExport, ladeListe, leseTxt, schreibeTxt, usernamesAusText } from "./parser.js";
import { FalschesPasswort } from "./krypto.js";
import { ApiFehler, TresorSpeicher } from "./speicher.js";

const wurzel = document.getElementById("app");
const seite = wurzel.dataset;                     // data-*-Attribute aus templates/tresor.html
const MIT_KONTO = seite.angemeldet === "1";
const MIN_PASSWORT = 10;

const speicher = new TresorSpeicher({ mitKonto: MIT_KONTO });
const zustand = {
  plattform: gemerkt("plattform", "instagram"),
  ansicht: "laden",
  snapshotId: null,       // in "Ergebnis" gewählte Auswertung
  ablauf: null,           // laufender Entfolgen-Durchgang
  vergleich: null,
  listenTab: "freunde",
  filter: "",
  meldungen: [],
  konflikt: false,
  laedt: "",              // Text einer laufenden Aktion ("Wird entschlüsselt …")
  bereit: false,
};

// ================================================================ kleine Helfer
function el(tag, attrs = {}, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") e.textContent = v;
    else if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") e[k] = Boolean(v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kind of kinder.flat(Infinity)) {
    if (kind === null || kind === undefined || kind === false) continue;
    e.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }
  return e;
}

function gemerkt(schluessel, standard) {
  try { return localStorage.getItem("fa_" + schluessel) || standard; } catch { return standard; }
}
function merken(schluessel, wert) {
  try { localStorage.setItem("fa_" + schluessel, wert); } catch { /* privater Modus o. Ä. */ }
}

function meldung(text, art = "info") {
  // Meldungen bleiben ein paar Sekunden stehen, auch wenn zwischendurch neu gezeichnet wird
  zustand.meldungen.push({ text, art, bis: Date.now() + 8000 });
}

function herunterladen(inhalt, dateiname, typ = "text/plain;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([inhalt], { type: typ }));
  const a = el("a", { href: url, download: dateiname });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const bereich = () => speicher.daten.plattformen[zustand.plattform];
const plattformName = () => A.PLATTFORMEN[zustand.plattform];
const profilLink = (name) => el("a", { href: A.profilUrl(zustand.plattform, name), target: "_blank",
                                       rel: "noopener noreferrer", text: name });
const knopf = (text, onclick, klasse = "", extra = {}) => el("button", { type: "button", class: klasse, onclick, ...extra }, text);
const karte = (...kinder) => el("section", { class: "karte" }, ...kinder);
const hinweis = (...kinder) => el("p", { class: "hinweis" }, ...kinder);

function aktuellerSnapshot() {
  const b = bereich();
  return b.snapshots.find((s) => s.id === zustand.snapshotId) || A.neuester(b);
}

// ================================================================ Speichern
let speicherTimer = null;
/** Nach jeder Änderung aufrufen: zeichnet neu und speichert (mit Konto) kurz danach automatisch. */
function geaendert() {
  speicher.ungespeichert = true;
  zeichnen();
  if (!MIT_KONTO) return;
  clearTimeout(speicherTimer);
  speicherTimer = setTimeout(jetztSpeichern, 800);
}

function statusText() {
  if (!MIT_KONTO) return speicher.ungespeichert ? "Nur in diesem Tab – unter „Tresor“ als Datei sichern" : "";
  if (speicher.ungespeichert) return "Wird verschlüsselt gespeichert …";
  return `🔒 Verschlüsselt gespeichert ${(speicher.zuletztGespeichert || "").slice(11, 16)}`;
}

async function jetztSpeichern() {
  clearTimeout(speicherTimer);
  if (!MIT_KONTO || !speicher.entsperrt || zustand.konflikt) return;
  try {
    await speicher.speichern();
  } catch (e) {
    if (e instanceof ApiFehler && e.status === 409) zustand.konflikt = true;
    else if (e instanceof ApiFehler && e.daten.grund === "avv") speicher.avvAktuell = false;
    else meldung(`Speichern fehlgeschlagen: ${e.message}`, "fehler");
    return zeichnen();
  }
  // Nur die Statuszeile aktualisieren – ein komplettes Neuzeichnen würde halb
  // ausgefüllte Eingabefelder leeren.
  const status = document.getElementById("speicher-status");
  if (status) status.textContent = statusText();
}

async function mitLadeanzeige(text, aufgabe) {
  zustand.laedt = text;
  zeichnen();
  await new Promise((r) => setTimeout(r, 30));        // Browser die Anzeige zeichnen lassen
  try {
    await aufgabe();
  } catch (e) {
    meldung(e instanceof FalschesPasswort || e instanceof ExportFormatFehler || e instanceof ApiFehler
      ? e.message : `Fehler: ${e.message}`, "fehler");
  } finally {
    zustand.laedt = "";
    zeichnen();
  }
}

// ================================================================ Ansicht: Laden
function ansichtLaden() {
  const exportFeld = el("input", { type: "file", accept: ".zip,.json" });
  const followerFeld = el("input", { type: "file", accept: ".json,.html,.txt" });
  const followingFeld = el("input", { type: "file", accept: ".json,.html,.txt" });
  const letzter = A.neuester(bereich());
  const editorFollower = el("textarea", { rows: 10, placeholder: "anna\n@ben.m\ncarl;14.11.2023" });
  const editorFollowing = el("textarea", { rows: 10, placeholder: "anna\ndora" });
  const editorName = el("input", { type: "text", maxlength: 80, placeholder: "z. B. „Liste vom Handy“" });

  const exportLaden = () => mitLadeanzeige("Export wird gelesen …", async () => {
    const datei = exportFeld.files[0];
    if (!datei) throw new ExportFormatFehler("Bitte zuerst eine Datei auswählen.");
    const inhalt = await ladeExport(datei);
    if (inhalt.plattform !== zustand.plattform) {
      plattformSetzen(inhalt.plattform);
      meldung(`${A.PLATTFORMEN[inhalt.plattform]}-Export erkannt – umgestellt auf ${A.PLATTFORMEN[inhalt.plattform]}.`);
    }
    auswertungAnlegen(inhalt.follower, inhalt.following, null, inhalt.blockiert, inhalt.enge_freunde);
  });

  const listenLaden = () => mitLadeanzeige("Listen werden gelesen …", async () => {
    const follower = followerFeld.files[0] ? await ladeListe(followerFeld.files[0]) : {};
    const following = followingFeld.files[0] ? await ladeListe(followingFeld.files[0]) : {};
    if (!Object.keys(follower).length && !Object.keys(following).length) {
      throw new ExportFormatFehler("In den gewählten Dateien wurden keine Nutzernamen gefunden.");
    }
    auswertungAnlegen(follower, following);
  });

  const editorAuswerten = () => {
    const follower = leseTxt(editorFollower.value);
    const following = leseTxt(editorFollowing.value);
    if (!Object.keys(follower).length && !Object.keys(following).length) {
      meldung("Bitte mindestens eine Liste ausfüllen.", "fehler");
      return zeichnen();
    }
    auswertungAnlegen(follower, following, editorName.value.trim() || `Eigene Liste vom ${new Date().toLocaleString("de-DE")}`);
  };

  const txtLaden = (feld) => el("label", { class: "datei-knopf knopf knopf-dezent klein" }, "TXT laden",
    el("input", { type: "file", accept: ".txt", onchange: async (e) => {
      if (e.target.files[0]) feld.value = await e.target.files[0].text();
    } }));

  return [
    el("h1", { text: `Wer folgt dir auf ${plattformName()} nicht zurück?` }),
    el("div", { class: "info" }, "🔒 Deine Dateien werden ", el("b", { text: "nicht hochgeladen" }),
       ". Das Programm läuft in deinem Browser. ",
       MIT_KONTO ? "Gespeichert wird nur dein verschlüsselter Tresor – lesen kann ihn nur, wer das Tresor-Passwort kennt."
                 : "Ohne Konto sind die Daten beim Schließen des Tabs weg (außer du sicherst sie unter „Tresor“ als Datei)."),
    hinweis("Neu hier? ", el("a", { class: "hilfe-link", href: `${seite.anleitungUrl}/${zustand.plattform}-export`,
                                    text: "So bekommst du die Export-Datei (2 Minuten)" })),
    karte(el("h2", { text: "📦 Export-Datei auswerten" }),
          hinweis("Die ZIP-Datei von Instagram oder TikTok – nicht entpacken. Das Programm erkennt automatisch, was drin ist."),
          el("label", {}, "Export-Datei (.zip oder TikTok-.json)", exportFeld),
          knopf("Auswerten", exportLaden)),
    karte(el("h2", { text: "📄 Einzelne Listen (JSON, HTML oder TXT)" }),
          el("label", {}, "Follower – wer dir folgt", followerFeld),
          el("label", {}, "Following – wem du folgst", followingFeld),
          knopf("Auswerten", listenLaden)),
    karte(el("h2", { text: "✏️ Listen-Editor" }),
          hinweis("Ein Name pro Zeile, optional mit Datum: name;TT.MM.JJJJ. Zeilen mit # sind Kommentare."),
          letzter && knopf("Letzte Auswertung hier einfügen", () => {
            editorFollower.value = schreibeTxt(letzter.follower, "Follower");
            editorFollowing.value = schreibeTxt(letzter.following, "Following");
          }, "knopf-dezent klein"),
          el("div", { class: "editor-spalten" },
             el("div", {}, el("div", { class: "editor-kopf" }, el("b", { text: "Follower" }), txtLaden(editorFollower),
                              knopf("TXT speichern", () => herunterladen(schreibeTxt(leseTxt(editorFollower.value), "Follower"), "follower.txt"), "knopf-dezent klein")),
                editorFollower),
             el("div", {}, el("div", { class: "editor-kopf" }, el("b", { text: "Following" }), txtLaden(editorFollowing),
                              knopf("TXT speichern", () => herunterladen(schreibeTxt(leseTxt(editorFollowing.value), "Following"), "following.txt"), "knopf-dezent klein")),
                editorFollowing)),
          el("label", {}, "Name der Auswertung (freiwillig)", editorName),
          knopf("Auswerten", editorAuswerten, "knopf-gruen")),
  ];
}

function auswertungAnlegen(follower, following, label = null, blockiert = {}, engeFreunde = {}) {
  const b = bereich();
  const s = A.snapshotHinzufuegen(b, follower, following, label);
  let neuB = 0, neuF = 0;
  for (const n of Object.keys(blockiert || {})) if (!(n in b.listen.blockiert_von_mir)) { b.listen.blockiert_von_mir[n] = A.jetzt(); neuB++; }
  for (const n of Object.keys(engeFreunde || {})) if (!(n in b.listen.freunde)) { b.listen.freunde[n] = A.jetzt(); neuF++; }
  if (neuB || neuF) meldung(`Aus dem Export übernommen: ${neuB} blockierte Profile, ${neuF} enge Freunde.`);
  zustand.snapshotId = s.id;
  zustand.ablauf = null;
  wechseln("ergebnis");
  geaendert();
}

// ================================================================ Ansicht: Ergebnis
function filterFeld() {
  return el("input", { type: "text", placeholder: "Namen filtern …", value: zustand.filter, class: "filter-feld",
                       oninput: (e) => { zustand.filter = e.target.value; filterAnwenden(); } });
}

function filterAnwenden() {
  const f = zustand.filter.trim().toLowerCase();
  for (const li of wurzel.querySelectorAll("li[data-name]")) li.hidden = Boolean(f) && !li.dataset.name.includes(f);
}

function keineDaten() {
  return [el("h1", { text: "Noch keine Auswertung" }),
          karte(el("p", { text: `Für ${plattformName()} ist noch nichts geladen.` }),
                el("a", { class: "knopf", href: "#laden", text: "Daten laden" }))];
}

function ansichtErgebnis() {
  const b = bereich();
  const s = aktuellerSnapshot();
  if (!s) return keineDaten();
  const k = A.kennzahlen(s);
  const freunde = A.freundeErmitteln(s, b.listen.freunde);
  const badgeKlasse = { behalten: "badge-gruen", entfernt: "badge-rot", deaktiviert: "badge-gelb" };
  const auswahl = el("select", { onchange: (e) => { zustand.snapshotId = e.target.value; zeichnen(); } },
    A.sortiert(b).map((x) => el("option", { value: x.id, selected: x.id === s.id, text: `${x.label} (${x.erstellt_am.slice(0, 10)})` })));

  const zeile = (name, datum, rot, badge) => el("li", { "data-name": name, "data-initiale": name[0], class: rot ? "rot" : "" },
    el("span", {}, profilLink(name), " ", el("span", { class: "hinweis inline", text: `(seit ${datum})` })),
    badge && el("span", { class: "rechts" }, el("span", { class: `badge ${badgeKlasse[badge]}`, text: badge })));

  return [
    el("h1", { text: s.label }),
    b.snapshots.length > 1 && el("label", {}, "Andere Auswertung anzeigen", auswahl),
    el("div", { class: "kacheln" },
       [[k.following, "Ich folge"], [k.follower, "Folgen mir"], [k.gegenseitig.length, "Freunde (gegenseitig)"],
        [k.nichtZurueck.length, "Folgen nicht zurück"]].map(([wert, titel], i) =>
         el("div", { class: "kachel" }, el("div", { class: i === 3 ? "wert rot" : "wert", text: wert }), el("div", { class: "titel", text: titel })))),
    el("p", {},
       el("a", { class: "knopf knopf-gelb", href: "#entfolgen", text: "🧹 Entfolgen-Modus" }), " ",
       knopf("👥 Freunde als CSV", () => herunterladen(A.freundeCsv(freunde, zustand.plattform), "freunde.csv", "text/csv;charset=utf-8"), "knopf-gruen"), " ",
       knopf("Nicht-Zurückfolger als TXT", () => herunterladen(A.namenslisteText("Folgen mir nicht zurück", k.nichtZurueck), "nicht_zurueck.txt"), "knopf-dezent"), " ",
       knopf("Auswertung löschen", () => {
         if (!confirm(`„${s.label}“ endgültig löschen?`)) return;
         b.snapshots = b.snapshots.filter((x) => x.id !== s.id);
         zustand.snapshotId = null;
         geaendert();
       }, "knopf-rot")),
    filterFeld(),
    el("p", { class: "hinweis", text: "Rot markiert = kein gegenseitiges Folgen" }),
    el("div", { class: "zwei_spalten" },
       el("div", {}, el("h2", { text: `Ich folge (${k.following})` }),
          el("ul", { class: "liste" }, Object.keys(s.following).sort().map((n) =>
            zeile(n, s.following[n], !(n in s.follower), b.markierungen[n]?.m)))),
       el("div", {}, el("h2", { text: `Folgen mir (${k.follower})` }),
          el("ul", { class: "liste" }, Object.keys(s.follower).sort().map((n) =>
            zeile(n, s.follower[n], !(n in s.following)))))),
    el("h2", { text: `Freunde (${freunde.length})` }),
    hinweis("Gegenseitige Follows und deine manuelle Freunde-Liste."),
    el("ul", { class: "liste" }, freunde.map((f) => el("li", { "data-name": f.username, "data-initiale": f.username[0] },
      el("span", {}, profilLink(f.username), " ", el("span", { class: "hinweis inline", text: f.quelle }))))),
  ];
}

// ================================================================ Ansicht: Verlauf
function ansichtVerlauf() {
  const b = bereich();
  const liste = A.sortiert(b);
  if (!liste.length) return keineDaten();
  const auswahlAlt = el("select", {}, liste.map((s, i) => el("option", { value: s.id, selected: i === 1, text: `${s.label} (${s.erstellt_am.slice(0, 16).replace("T", " ")})` })));
  const auswahlNeu = el("select", {}, liste.map((s, i) => el("option", { value: s.id, selected: i === 0, text: `${s.label} (${s.erstellt_am.slice(0, 16).replace("T", " ")})` })));
  const vergleichen = () => {
    if (auswahlAlt.value === auswahlNeu.value) { meldung("Bitte zwei unterschiedliche Zeitpunkte auswählen.", "fehler"); return zeichnen(); }
    zustand.vergleich = A.vergleichen(b.snapshots.find((s) => s.id === auswahlAlt.value),
                                      b.snapshots.find((s) => s.id === auswahlNeu.value));
    zeichnen();
  };
  const v = zustand.vergleich;
  const bekannt = new Set([...Object.keys(b.listen.blockiert_mich), ...Object.keys(b.listen.blockiert_von_mir)]);
  const block = (titel, namen, klasse = "") => el("div", {}, el("h3", { text: `${titel} (${namen.length})` }),
    namen.length ? el("ul", { class: "liste" }, namen.map((n) => el("li", { class: klasse, "data-initiale": n[0] }, profilLink(n))))
                 : hinweis("–"));
  return [
    el("h1", { text: "Verlauf" }),
    karte(el("h2", { text: "Zwei Zeitpunkte vergleichen" }),
          liste.length < 2 ? hinweis("Für einen Vergleich brauchst du mindestens zwei Auswertungen.")
                           : [el("label", {}, "Älterer Stand", auswahlAlt), el("label", {}, "Neuerer Stand", auswahlNeu), knopf("Vergleichen", vergleichen)]),
    v && karte(el("h2", { text: `${v.alt.label} → ${v.neu.label}` }),
      el("div", { class: "zwei_spalten" },
         el("div", {}, block("Neue Follower", v.followerNeu, "gruen"), block("Folgen mir nicht mehr", v.followerWeg, "rot")),
         el("div", {}, block("Ich folge neu", v.followingNeu, "gruen"), block("Ich folge nicht mehr", v.followingWeg, "rot"))),
      v.blockVerdacht.length > 0 && el("div", { class: "info" },
        el("b", { text: `Blockier-Verdacht (${v.blockVerdacht.length}): ` }),
        "Vorher gegenseitig gefolgt, jetzt beide Verbindungen weg – kann auch Deaktivierung oder Namensänderung sein.",
        el("ul", { class: "liste" }, v.blockVerdacht.map((n) => el("li", { "data-initiale": n[0] }, profilLink(n),
          bekannt.has(n) ? el("span", { class: "rechts badge badge-blau", text: "schon in Blockiert-Liste" })
                         : el("span", { class: "rechts" }, knopf("→ „Hat mich blockiert“", () => {
                             b.listen.blockiert_mich[n] = A.jetzt(); geaendert(); }, "klein knopf-dezent"))))))),
    karte(el("h2", { text: `Gespeicherte Auswertungen (${liste.length})` }),
      el("ul", { class: "liste" }, liste.map((s) => el("li", { "data-initiale": "#" },
        el("span", {}, `${s.label} · ${s.erstellt_am.slice(0, 16).replace("T", " ")} · ${Object.keys(s.follower).length} Follower / ${Object.keys(s.following).length} Following`),
        el("span", { class: "rechts" },
           knopf("Ansehen", () => { zustand.snapshotId = s.id; wechseln("ergebnis"); zeichnen(); }, "klein knopf-dezent"), " ",
           knopf("Löschen", () => {
             if (!confirm(`„${s.label}“ endgültig löschen?`)) return;
             b.snapshots = b.snapshots.filter((x) => x.id !== s.id);
             zustand.vergleich = null;
             geaendert();
           }, "klein knopf-rot")))))),
  ];
}

// ================================================================ Ansicht: Entfolgen
function ansichtEntfolgen() {
  const b = bereich();
  const s = A.neuester(b);
  if (!s) return keineDaten();
  const a = zustand.ablauf;

  if (!a || a.snapshotId !== s.id || a.bereich !== b) {
    const u = A.kategorienErmitteln(s, b);
    const haken = {};
    const starten = () => {
      const erneut = new Set(Object.entries(haken).filter(([, h]) => h.checked).map(([k]) => k));
      zustand.ablauf = new A.EntfolgenAblauf(b, s, erneut);
      zeichnen();
    };
    if (!A.KATEGORIEN.some(([k]) => u.gruppen[k].length)) {
      zustand.ablauf = new A.EntfolgenAblauf(b, s, new Set());
      return ansichtEntfolgen();
    }
    return [
      el("h1", { text: "Entfolgen-Modus" }),
      karte(el("h2", { text: "Welche Gruppen sollen erneut abgefragt werden?" }),
        hinweis(`${u.alle.length} Accounts folgen dir nicht zurück. ${u.neu.length} davon sind neu und werden auf jeden Fall abgefragt.`),
        A.KATEGORIEN.map(([k, text]) => {
          haken[k] = el("input", { type: "checkbox", value: k });
          return el("label", { class: "checkzeile" }, haken[k], el("span", {}, text, " ", el("span", { class: "anzahl", text: `(${u.gruppen[k].length})` })));
        }),
        knopf("Starten", starten, "knopf-gelb")),
    ];
  }

  if (!a.kandidaten.length) {
    return [el("h1", { text: "Entfolgen-Modus" }),
            karte(el("p", { text: "🎉 Es gibt keine offenen Accounts – alle folgen dir zurück oder sind schon markiert." }),
                  knopf("Gruppen neu wählen", () => { zustand.ablauf = null; zeichnen(); }, "knopf-dezent"))];
  }

  if (a.istFertig()) {
    const z = a.zusammenfassung();
    return [
      el("h1", { text: "Fertig!" }),
      karte(Object.entries(A.ENTSCHEIDUNGEN).map(([k, text]) => el("div", {},
              el("h3", { text: `${text} (${z[k].length})` }),
              el("ul", { class: "liste" }, z[k].map((n) => el("li", { "data-initiale": n[0] }, profilLink(n)))))),
            a.nochZuEntfolgen().length > 0 && el("div", { class: "info" },
              el("b", { text: `Früher als „Entfolgen“ markiert, aber du folgst noch (${a.nochZuEntfolgen().length}): ` }),
              a.nochZuEntfolgen().join(", ")),
            el("p", {},
               knopf("⬇ Ergebnis als TXT", () => herunterladen(A.entfolgenBericht(z, a.nochZuEntfolgen()), "entfolgen_ergebnis.txt")), " ",
               a.kannZurueck() && knopf("↶ Zurück", () => { a.zurueck(); geaendert(); }, "knopf-dezent"), " ",
               knopf("Neu starten", () => { zustand.ablauf = null; zeichnen(); }, "knopf-dezent")),
            hinweis("Das Programm entfolgt niemandem automatisch. Arbeite die Liste selbst in der App ab.")),
    ];
  }

  const name = a.aktueller();
  const [erledigt, gesamt] = a.fortschritt();
  const vorher = b.markierungen[name];
  const entscheiden = (wert) => { a.entscheide(wert); geaendert(); };
  return [
    el("h1", { text: "Entfolgen-Modus" }),
    el("div", { class: "karte wizard-karte" },
       el("div", { class: "wizard-fortschritt", text: `${erledigt + 1} von ${gesamt}` }),
       el("div", { class: "wizard-fortschrittsbalken" }, el("div", { style: `width:${Math.round(100 * erledigt / gesamt)}%` })),
       el("div", { class: "wizard-name" }, profilLink(name)),
       el("div", { class: "wizard-seit", text: `Du folgst seit: ${a.seit(name)}` }),
       vorher && hinweis(`Bisher markiert als: ${A.ENTSCHEIDUNGEN[vorher.m]}`),
       el("p", {},
          knopf("✔ Behalten", () => entscheiden("behalten"), "knopf-gruen"), " ",
          knopf("✖ Entfolgen", () => entscheiden("entfernt"), "knopf-rot"), " ",
          knopf("Scheint deaktiviert", () => entscheiden("deaktiviert"), "knopf-gelb")),
       el("p", {},
          knopf("↶ Zurück", () => { a.zurueck(); geaendert(); }, "knopf-dezent", { disabled: !a.kannZurueck() }), " ",
          knopf("Abbrechen", () => { zustand.ablauf = null; zeichnen(); }, "knopf-dezent"))),
    hinweis("Jede Entscheidung wird sofort gemerkt. Du kannst jederzeit aufhören und später weitermachen."),
  ];
}

// ================================================================ Ansicht: Listen
function ansichtListen() {
  const b = bereich();
  const tab = zustand.listenTab;
  const tabs = el("div", { class: "tabs" },
    [...Object.entries(A.LISTEN), ["markierungen", "Markierungen"]].map(([k, text]) =>
      el("a", { href: "#listen", class: k === tab ? "aktiv" : "", text,
                onclick: (e) => { e.preventDefault(); zustand.listenTab = k; zeichnen(); } })));

  if (tab === "markierungen") {
    const eintraege = Object.entries(b.markierungen).sort(([x], [y]) => x.localeCompare(y));
    return [el("h1", { text: "Meine Listen" }), tabs, filterFeld(),
      karte(hinweis("Markierungen aus dem Entfolgen-Modus. Sie gelten dauerhaft, bis du sie änderst."),
        el("ul", { class: "liste" }, eintraege.map(([n, { m, am }]) => el("li", { "data-name": n, "data-initiale": n[0] },
          el("span", {}, profilLink(n), " ", el("span", { class: "hinweis inline", text: `seit ${am.slice(0, 10)}` })),
          el("span", { class: "rechts" }, el("select", { onchange: (e) => {
            if (e.target.value === "") delete b.markierungen[n];
            else b.markierungen[n] = { m: e.target.value, am: A.jetzt() };
            geaendert();
          } }, Object.entries(A.ENTSCHEIDUNGEN).map(([k, t]) => el("option", { value: k, selected: k === m, text: t })),
             el("option", { value: "", text: "Markierung entfernen" })))))))];
  }

  const liste = b.listen[tab];
  const namen = Object.keys(liste).sort();
  const eingabe = el("textarea", { rows: 3, placeholder: "Namen, Profil-Links oder @namen – durch Komma, Leerzeichen oder Zeilen getrennt" });
  const haken = new Map();
  const ausgewaehlt = () => [...haken].filter(([, h]) => h.checked).map(([n]) => n);
  const ziel = el("select", {}, Object.entries(A.LISTEN).filter(([k]) => k !== tab).map(([k, t]) => el("option", { value: k, text: t })));
  const sammel = (art) => {
    const auswahl = ausgewaehlt();
    if (!auswahl.length) { meldung("Keine Accounts ausgewählt.", "fehler"); return zeichnen(); }
    for (const n of auswahl) {
      if (art !== "entfernen") b.listen[ziel.value][n] ??= A.jetzt();
      if (art !== "kopieren") delete liste[n];
    }
    meldung(`${auswahl.length} Account(s) ${art === "entfernen" ? "entfernt" : art === "kopieren" ? "kopiert" : "verschoben"}.`);
    geaendert();
  };

  return [
    el("h1", { text: "Meine Listen" }), tabs,
    karte(el("h2", { text: `${A.LISTEN[tab]} (${namen.length})` }),
      eingabe,
      el("p", {}, knopf("Hinzufügen", () => {
        let neu = 0;
        for (const n of usernamesAusText(eingabe.value)) if (!(n in liste)) { liste[n] = A.jetzt(); neu++; }
        meldung(neu ? `${neu} Account(s) hinzugefügt.` : "Keine neuen Accounts hinzugefügt.");
        geaendert();
      }), " ", knopf("Als TXT herunterladen", () => herunterladen(A.namenslisteText(A.LISTEN[tab], namen), `${tab}.txt`), "knopf-dezent"))),
    namen.length > 0 && karte(
      el("div", { class: "sammelleiste" },
         el("label", { class: "alle" }, el("input", { type: "checkbox", onchange: (e) => {
           for (const [n, h] of haken) if (!wurzel.querySelector(`li[data-name="${CSS.escape(n)}"]`)?.hidden) h.checked = e.target.checked;
         } }), " Alle"),
         filterFeld(),
         knopf("Entfernen", () => sammel("entfernen"), "klein knopf-rot"),
         " nach ", ziel, " ",
         knopf("verschieben", () => sammel("verschieben"), "klein knopf-dezent"),
         knopf("kopieren", () => sammel("kopieren"), "klein knopf-dezent")),
      el("ul", { class: "liste" }, namen.map((n) => {
        const h = el("input", { type: "checkbox" });
        haken.set(n, h);
        return el("li", { "data-name": n }, h, el("span", {}, profilLink(n), " ",
                  el("span", { class: "hinweis inline", text: `seit ${liste[n].slice(0, 10)}` })));
      }))),
  ];
}

// ================================================================ Ansicht: Tresor
function passwortFelder(mitWiederholung) {
  const p1 = el("input", { type: "password", autocomplete: mitWiederholung ? "new-password" : "current-password", required: true });
  const p2 = mitWiederholung ? el("input", { type: "password", autocomplete: "new-password", required: true }) : null;
  const pruefen = () => {
    if (mitWiederholung && p1.value.length < MIN_PASSWORT) throw new Error(`Das Tresor-Passwort muss mindestens ${MIN_PASSWORT} Zeichen haben.`);
    if (mitWiederholung && p1.value !== p2.value) throw new Error("Die beiden Passwörter stimmen nicht überein.");
    if (!p1.value) throw new Error("Bitte das Tresor-Passwort eingeben.");
    return p1.value;
  };
  return { p1, p2, pruefen };
}

function tresorAnlegen() {
  const f = passwortFelder(true);
  return [
    el("h1", { text: "🔒 Tresor anlegen" }),
    karte(
      el("p", {}, "Deine Listen werden ", el("b", { text: "in deinem Browser verschlüsselt" }),
         ", bevor sie gespeichert werden. Dafür brauchst du ein eigenes ", el("b", { text: "Tresor-Passwort" }), "."),
      el("ul", { class: "tipps" },
         el("li", { text: "Es wird nie an den Server geschickt – wir können deine Listen nicht lesen." }),
         el("li", { text: "Nimm ein anderes Passwort als für die Anmeldung." }),
         el("li", { text: "Vergisst du es, sind die Daten im Tresor verloren. Niemand kann es zurücksetzen." })),
      el("form", { onsubmit: (e) => { e.preventDefault(); mitLadeanzeige("Tresor wird angelegt …", async () => {
          await speicher.anlegen(f.pruefen());
          meldung("Tresor angelegt. Alles, was du jetzt auswertest, wird verschlüsselt gespeichert.");
          wechseln("laden");
        }); } },
        el("label", {}, `Tresor-Passwort (mind. ${MIN_PASSWORT} Zeichen)`, f.p1),
        el("label", {}, "Tresor-Passwort wiederholen", f.p2),
        el("button", { type: "submit", text: "Tresor anlegen" }))),
  ];
}

function tresorEntsperren() {
  const f = passwortFelder(false);
  return [
    el("h1", { text: "🔒 Tresor entsperren" }),
    karte(
      hinweis(`Zuletzt gespeichert: ${(speicher.zuletztGespeichert || "").replace("T", " ")}`),
      el("form", { onsubmit: (e) => { e.preventDefault(); mitLadeanzeige("Wird entschlüsselt …", async () => {
          await speicher.entsperren(f.pruefen());
          if (["tresor", "laden"].includes(zustand.ansicht)) wechseln(A.neuester(bereich()) ? "ergebnis" : "laden");
        }); } },
        el("label", {}, "Tresor-Passwort", f.p1),
        el("button", { type: "submit", text: "Entsperren" })),
      el("details", {}, el("summary", { text: "Passwort vergessen?" }),
         hinweis("Das Tresor-Passwort kennt nur du – wir können es nicht zurücksetzen. Du kannst den Tresor löschen und neu anfangen."),
         knopf("Tresor löschen und neu anlegen", () => {
           if (!confirm("Tresor mit allen Auswertungen, Markierungen und Listen endgültig löschen?")) return;
           mitLadeanzeige("Wird gelöscht …", async () => { await speicher.loeschen(); meldung("Tresor gelöscht."); });
         }, "knopf-rot klein"))),
  ];
}

function ansichtTresor() {
  const d = speicher.daten;
  const anzahl = Object.values(d.plattformen).reduce((n, b) => n + b.snapshots.length, 0);
  const sicherungLaden = el("input", { type: "file", accept: ".fatresor,.txt", onchange: async (e) => {
    const datei = e.target.files[0];
    if (!datei) return;
    const passwort = prompt("Passwort der Sicherungsdatei:");
    if (!passwort) return;
    await mitLadeanzeige("Sicherung wird geöffnet …", async () => {
      const daten = await speicher.sicherungLesen(await datei.text(), passwort);
      if (anzahl && !confirm("Die Sicherung ersetzt den aktuellen Inhalt. Fortfahren?")) return;
      speicher.daten = daten;
      zustand.ablauf = null;
      meldung("Sicherung geladen.");
      geaendert();
    });
  } });

  return [
    el("h1", { text: MIT_KONTO ? "🔒 Dein Tresor" : "💾 Daten sichern" }),
    karte(
      MIT_KONTO
        ? [el("p", {}, el("b", { text: "Entsperrt. " }), "Jede Änderung wird automatisch verschlüsselt gespeichert (Stand: siehe oben rechts)."),
           hinweis("Der Server speichert nur den verschlüsselten Block. Schlüssel und Passwort bleiben in diesem Browser-Tab.")]
        : [el("p", {}, "Du nutzt die App ", el("b", { text: "ohne Konto" }), ": Alles liegt nur in diesem Browser-Tab."),
           seite.kontenAktiv === "1" && hinweis("Mit einem ", el("a", { href: seite.registrierenUrl, text: "Konto" }),
             " wird dein Tresor verschlüsselt gespeichert und ist auf allen Geräten verfügbar.")],
      el("p", {}, `${anzahl} Auswertung(en) · ${Object.values(d.plattformen).reduce((n, b) => n + Object.keys(b.markierungen).length, 0)} Markierung(en)`),
      el("p", {},
         MIT_KONTO && knopf("Jetzt speichern", jetztSpeichern), " ",
         MIT_KONTO && knopf("Sperren", () => { speicher.sperren(); zustand.ablauf = null; meldung("Tresor gesperrt."); zeichnen(); }, "knopf-dezent"))),
    karte(el("h2", { text: "Sicherungsdatei" }),
      hinweis("Eine verschlüsselte Datei auf deinem Gerät – unabhängig vom Server. Zum Öffnen brauchst du das Passwort."),
      el("p", {},
         knopf("⬇ Verschlüsselte Sicherung herunterladen", async () => {
           let passwort = null;
           if (!MIT_KONTO) {
             passwort = prompt(`Passwort für die Sicherungsdatei (mind. ${MIN_PASSWORT} Zeichen):`);
             if (!passwort) return;
             if (passwort.length < MIN_PASSWORT) { meldung(`Mindestens ${MIN_PASSWORT} Zeichen.`, "fehler"); return zeichnen(); }
           }
           herunterladen(await speicher.sicherungErstellen(passwort), `follower_tresor_${A.jetzt().slice(0, 10)}.fatresor`);
           if (!MIT_KONTO) speicher.ungespeichert = false;
         }), " ",
         el("label", { class: "datei-knopf knopf knopf-dezent" }, "Sicherung laden", sicherungLaden)),
      knopf("Klartext-Export (JSON, unverschlüsselt)", () =>
        herunterladen(JSON.stringify(d, null, 2), "meine_listen.json", "application/json"), "knopf-dezent klein")),
    MIT_KONTO && karte(el("h2", { text: "Tresor-Passwort ändern" }), (() => {
      const f = passwortFelder(true);
      return el("form", { onsubmit: (e) => { e.preventDefault(); mitLadeanzeige("Wird neu verschlüsselt …", async () => {
          await speicher.passwortAendern(f.pruefen());
          meldung("Tresor-Passwort geändert.");
        }); } },
        el("label", {}, "Neues Tresor-Passwort", f.p1), el("label", {}, "Wiederholen", f.p2),
        el("button", { type: "submit", text: "Ändern" }));
    })()),
    el("section", { class: "karte gefahrzone" }, el("h2", { text: "Alles löschen" }),
      hinweis(MIT_KONTO ? "Löscht den Tresor mit allen Auswertungen, Markierungen und Listen – auch auf dem Server."
                        : "Leert alle Daten in diesem Tab."),
      knopf(MIT_KONTO ? "Tresor endgültig löschen" : "Alles leeren", () => {
        if (!confirm("Wirklich alles endgültig löschen?")) return;
        mitLadeanzeige("Wird gelöscht …", async () => {
          await speicher.loeschen();
          zustand.ablauf = null;
          if (!MIT_KONTO) speicher.lokalStarten();
          meldung("Gelöscht.");
        });
      }, "knopf-rot")),
  ];
}

// ================================================================ Rahmen
function konfliktHinweis() {
  return el("div", { class: "info warnung" },
    el("b", { text: "Der Tresor wurde in einem anderen Fenster oder Gerät geändert. " }),
    "Welchen Stand möchtest du behalten?",
    el("p", {},
       knopf("Anderen Stand laden (meine letzten Änderungen verwerfen)", () => mitLadeanzeige("Wird geladen …", async () => {
         zustand.konflikt = false;
         zustand.ablauf = null;
         await speicher.abrufen();
         speicher.sperren();
         meldung("Bitte den Tresor erneut entsperren.");
       }), "knopf-dezent klein"), " ",
       knopf("Meinen Stand behalten (anderen überschreiben)", () => mitLadeanzeige("Wird gespeichert …", async () => {
         zustand.konflikt = false;
         await speicher.ueberschreiben();
       }), "klein")));
}

function avvHinweis() {
  return el("div", { class: "info warnung" },
    "Speichern ist erst möglich, wenn du dem aktuellen ",
    el("a", { href: speicher.avvLink, text: "Auftragsverarbeitungsvertrag" }), " zugestimmt hast.");
}

/** Ansicht wechseln, ohne dass "hashchange" feuert (sonst wären gerade gesetzte Meldungen gleich wieder weg). */
function wechseln(ansicht) {
  history.pushState(null, "", "#" + ansicht);
  zustand.ansicht = ansicht;
  zustand.filter = "";
  window.scrollTo(0, 0);
}

function plattformSetzen(p) {
  if (!(p in A.PLATTFORMEN)) return;
  zustand.plattform = p;
  zustand.snapshotId = null;
  zustand.vergleich = null;
  zustand.ablauf = null;
  merken("plattform", p);
  for (const b of document.querySelectorAll("#plattform-wahl button")) b.classList.toggle("aktiv", b.dataset.plattform === p);
}

const ANSICHTEN = { laden: ansichtLaden, ergebnis: ansichtErgebnis, verlauf: ansichtVerlauf, entfolgen: ansichtEntfolgen,
                    listen: ansichtListen, tresor: ansichtTresor };

function zeichnen() {
  const inhalt = [];
  zustand.meldungen = zustand.meldungen.filter((m) => m.bis > Date.now());
  if (zustand.meldungen.length) {
    inhalt.push(el("ul", { class: "flash" }, zustand.meldungen.map((m) => el("li", { class: m.art === "fehler" ? "fehler" : "", text: m.text }))));
  }
  if (zustand.bereit && speicher.entsperrt) inhalt.push(el("div", { id: "speicher-status", class: "speicher-status", text: statusText() }));
  if (zustand.konflikt) inhalt.push(konfliktHinweis());
  if (MIT_KONTO && !speicher.avvAktuell) inhalt.push(avvHinweis());

  if (!zustand.bereit) inhalt.push(karte(el("p", { text: "Wird geladen …" })));
  else if (zustand.laedt) inhalt.push(karte(el("p", { class: "laedt", text: zustand.laedt })));
  else if (!speicher.entsperrt) inhalt.push(...(speicher.block ? tresorEntsperren() : tresorAnlegen()));
  else inhalt.push(...[].concat(ANSICHTEN[zustand.ansicht]?.() ?? ansichtLaden()));

  wurzel.replaceChildren(...inhalt.flat(Infinity).filter(Boolean));
  for (const a of document.querySelectorAll("nav a[href*='#']")) {
    a.classList.toggle("aktiv", a.getAttribute("href").endsWith("#" + zustand.ansicht));
  }
  if (zustand.filter) filterAnwenden();
}

async function starten() {
  window.addEventListener("hashchange", () => {
    zustand.ansicht = location.hash.slice(1) || "laden";
    zustand.filter = "";
    zeichnen();
    window.scrollTo(0, 0);
  });
  for (const b of document.querySelectorAll("#plattform-wahl button")) {
    b.addEventListener("click", () => { plattformSetzen(b.dataset.plattform); zeichnen(); });
  }
  window.addEventListener("beforeunload", (e) => {
    // Mit Konto: noch nicht gespeichert. Ohne Konto: Änderungen seit der letzten Sicherungsdatei.
    if (speicher.ungespeichert) { e.preventDefault(); e.returnValue = ""; }
  });
  plattformSetzen(zustand.plattform);
  zustand.ansicht = location.hash.slice(1) || "laden";
  try {
    if (MIT_KONTO) await speicher.abrufen();
    else speicher.lokalStarten();
  } catch (e) {
    meldung(`Der Tresor konnte nicht geladen werden: ${e.message}`, "fehler");
  }
  zustand.bereit = true;
  zeichnen();
}

starten();
