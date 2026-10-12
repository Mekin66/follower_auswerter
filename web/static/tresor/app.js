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
import * as AK from "./aktivitaet.js";
import { beispieleLesen, bewerte, KommentarNetz, KRITISCH, PRUEFEN, HARMLOS } from "./netz.js";
import { ExportFormatFehler, hatFollowerDaten, ladeExport, ladeListe, leseTxt, schreibeTxt, usernamesAusText } from "./parser.js";
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
  const exportFeld = el("input", { type: "file", accept: ".zip,.json,.html" });
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
    exportUebernehmen(inhalt);
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
          hinweis("Die ZIP-Datei von Instagram oder TikTok – nicht entpacken. Das Programm erkennt automatisch, was drin ist: " +
                  "Follower/Following, Kommentare, Likes (JSON oder HTML). Einzelne Kommentar-/Like-Dateien gehen auch."),
          el("label", {}, "Export-Datei (.zip, .json oder .html)", exportFeld),
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

/** Ein ganzer Export: Follower-Listen als Auswertung, Kommentare/Likes in den Kommentar-/Like-Modus. */
function exportUebernehmen(inhalt) {
  const b = bereich();
  const [neuK, neuL] = AK.importieren(b.aktivitaet, inhalt.kommentare || [], inhalt.likes || []);
  if ((inhalt.kommentare || []).length || (inhalt.likes || []).length) {
    meldung(`Aus dem Export übernommen: ${neuK} neue Kommentare, ${neuL} neue Likes ` +
            `(Kommentar- und Like-Modus im Menü).`);
  }
  if (hatFollowerDaten(inhalt)) {
    return auswertungAnlegen(inhalt.follower, inhalt.following, null, inhalt.blockiert, inhalt.enge_freunde);
  }
  wechseln(inhalt.kommentare?.length ? "kommentare" : "likes");
  geaendert();
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

// ================================================================ Ansicht: Kommentare & Likes
// Das neuronale Netz (netz.js) läuft hier im Browser. Gewichte und Grund-Beispiele kommen als
// statische Dateien vom Server (/netz/...), die Kommentare selbst verlassen den Browser nie.
const netzZustand = { netz: null, beispiele: null, laedt: false, fehler: "" };

function netzLaden() {
  if (netzZustand.netz || netzZustand.laedt) return netzZustand.netz;
  netzZustand.laedt = true;
  Promise.all([fetch("/netz/kommentar_netz.json").then((r) => r.json()),
               fetch("/netz/kommentar_beispiele.tsv").then((r) => r.text())])
    .then(([gewichte, tsv]) => {
      netzZustand.netz = new KommentarNetz(gewichte);
      netzZustand.beispiele = beispieleLesen(tsv);
    })
    .catch((e) => { netzZustand.fehler = `Das Bewertungs-Netz konnte nicht geladen werden (${e.message}).`; })
    .finally(() => { netzZustand.laedt = false; zeichnen(); });
  return null;
}

/** Ab 5 eigenen Entscheidungen: Netz mit diesen nachtrainieren (nur im Speicher). */
function persoenlichesNetz(aktivitaet) {
  const eigene = AK.eigeneBeispiele(aktivitaet);
  if (eigene.length < AK.MIN_EIGENE_ENTSCHEIDUNGEN) return netzZustand.netz;
  return netzZustand.netz.angepasst(eigene, netzZustand.beispiele);
}

const STUFEN_BADGE = { [KRITISCH]: "badge-rot", [PRUEFEN]: "badge-gelb", [HARMLOS]: "badge-gruen" };

/** Kommentartext mit gelb markierten Treffer-Wörtern – ohne innerHTML. */
function markierterText(text, treffer) {
  if (!treffer.length) return el("blockquote", { class: "kommentar-text", text });
  const muster = new RegExp(`(${treffer.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "giu");
  return el("blockquote", { class: "kommentar-text" },
            text.split(muster).map((teil, i) => (i % 2 ? el("mark", { text: teil }) : teil)));
}

function aktivitaetsAnsicht(art) {
  const ak = bereich().aktivitaet;
  const istK = art === AK.KOMMENTAR;
  const name = istK ? "kommentare" : "likes";
  const titel = istK ? "💬 Kommentar-Modus" : "❤️ Like-Modus";
  const eintraege = Object.values(istK ? ak.kommentare : ak.likes);
  const z = (zustand.akt ??= {});
  const lauf = z[art];

  if (zustand.plattform !== "instagram") {
    return [el("h1", { text: titel }), karte(el("p", { text: "Kommentare und Likes gibt es nur für Instagram." }),
            knopf("Zu Instagram wechseln", () => { plattformSetzen("instagram"); zeichnen(); }))];
  }
  if (!eintraege.length) {
    return [el("h1", { text: titel }), karte(
      el("p", { text: `Noch keine ${istK ? "Kommentare" : "Likes"} geladen.` }),
      hinweis(`Fordere bei Instagram einen Export an, der „${istK ? "Kommentare" : "Likes"}“ enthält, und lade ihn unter „Laden“ – ` +
              "das Programm erkennt ihn automatisch (JSON oder HTML)."),
      el("a", { class: "knopf", href: "#laden", text: "Daten laden" }))];
  }

  // ---- Liste "Zum Entfernen"
  if (lauf?.modus === "liste") {
    const liste = AK.alleZumEntfernen(ak, art);
    return [el("h1", { text: titel }), karte(
      el("h2", { text: `${liste.length} zum Entfernen markiert` }),
      hinweis("Das Programm löscht nichts selbst. Öffne die Einträge über die Links oder gesammelt auf der ",
              el("a", { href: AK.AKTIVITAET_URL[art], target: "_blank", rel: "noopener noreferrer", text: "Instagram-Aktivitätsseite" }),
              " (App: Profil → Menü → Deine Aktivität → Interaktionen)."),
      el("ul", { class: "liste" }, liste.map((e) => el("li", { "data-initiale": istK ? "💬" : "❤" },
        el("span", {}, el("b", { text: e.datum }), istK ? ` · bei @${e.medien_owner || "?"}` : ` · ${e.art} von @${e.owner || "?"}`,
           istK && el("br"), istK && el("span", { class: "hinweis inline", text: `„${e.text.slice(0, 160)}${e.text.length > 160 ? "…" : ""}“` })),
        AK.suchLink(e) && el("span", { class: "rechts" }, el("a", { class: "knopf knopf-dezent klein", href: AK.suchLink(e),
                                                                    target: "_blank", rel: "noopener noreferrer", text: "Öffnen" }))))),
      el("p", {},
         knopf("⬇ Als Textdatei", () => herunterladen(AK.aktivitaetBericht(art, liste), `${name}_zum_entfernen.txt`)), " ",
         knopf("Zur Übersicht", () => { z[art] = null; zeichnen(); }, "knopf-dezent")))];
  }

  // ---- Durchgang
  if (lauf?.modus === "durchgang") {
    const a = lauf.ablauf;
    const e = a.aktueller();
    if (!e) { z[art] = { modus: "liste" }; return aktivitaetsAnsicht(art); }
    const [erledigt, gesamt] = a.fortschritt();
    const b = a.bewertung(e);
    const entscheiden = (wert) => { a.entscheide(wert); geaendert(); };
    return [el("h1", { text: titel }), el("div", { class: "karte" },
      el("p", { class: "wizard-fortschritt", text: `${erledigt} von ${gesamt} bearbeitet` }),
      el("div", { class: "wizard-fortschrittsbalken" }, el("div", { style: `width:${Math.round(100 * erledigt / gesamt)}%` })),
      istK ? [
        el("p", {}, el("span", { class: `badge ${STUFEN_BADGE[b.stufe]}`, text: `${b.stufe} · ${b.empfehlung}` }),
           el("span", { class: "hinweis inline", text: `  ${e.datum} · ${e.quelle} von @${e.medien_owner || "?"}` })),
        hinweis(`Warum: ${b.gruende.join("; ")}`),
        markierterText(e.text, b.treffer),
      ] : [
        el("div", { class: "wizard-name", text: `@${e.owner || "?"}` }),
        el("p", { class: "wizard-seit", text: `${e.art} geliked am ${e.datum}` }),
      ],
      el("p", {},
         AK.suchLink(e) && el("a", { class: "hilfe-link", href: AK.suchLink(e), target: "_blank", rel: "noopener noreferrer", text: `🔗 ${AK.suchLink(e)}` }),
         " · ", el("a", { class: "hilfe-link", href: AK.AKTIVITAET_URL[art], target: "_blank", rel: "noopener noreferrer", text: "Instagram-Aktivitätsseite" }),
         istK && [" · ", knopf("Text kopieren", () => navigator.clipboard?.writeText(e.text), "knopf-dezent klein")]),
      el("p", { style: "text-align:center" },
         knopf(istK ? "🗑 Löschen" : "💔 Like entfernen", () => entscheiden(AK.ENTFERNEN), "knopf-rot"), " ",
         knopf("✓ Behalten", () => entscheiden(AK.BEHALTEN), "knopf-gruen"), el("br"),
         knopf("← Zurück", () => { a.zurueck(); geaendert(); }, "knopf-dezent", { disabled: !a.kannZurueck() }), " ",
         knopf("Beenden", () => { z[art] = { modus: "liste" }; zeichnen(); }, "knopf-dezent")))];
  }

  // ---- Übersicht / Start
  const erneut = el("input", { type: "checkbox" });
  const entschieden = Object.keys(ak.entscheidungen[art]).length;
  const zuEntfernen = AK.alleZumEntfernen(ak, art).length;
  const unten = [
    el("label", { class: "checkzeile" }, erneut, el("span", { text: "Schon entschiedene erneut zeigen" })),
  ];
  const listeKnopf = knopf(`Liste „Zum Entfernen“ (${zuEntfernen})`, () => { z[art] = { modus: "liste" }; zeichnen(); }, "knopf-dezent");
  const leeren = knopf(`Geladene ${istK ? "Kommentare" : "Likes"} löschen`, () => {
    if (!confirm("Alle geladenen Daten und Entscheidungen hier löschen?")) return;
    if (istK) { ak.kommentare = {}; ak.entscheidungen[AK.KOMMENTAR] = {}; } else { ak.likes = {}; ak.entscheidungen[AK.LIKE] = {}; }
    z[art] = null;
    geaendert();
  }, "knopf-dezent klein");
  const starten = (ablauf) => {
    if (!ablauf.reihenfolge.length) { meldung("Mit dieser Auswahl gibt es keine offenen Einträge."); return zeichnen(); }
    z[art] = { modus: "durchgang", ablauf };
    zeichnen();
  };

  if (!istK) {
    const top = AK.likeStatistik(eintraege).slice(0, 50);
    return [el("h1", { text: titel }), karte(
      el("h2", { text: `${eintraege.length} Likes – wem du am meisten Likes gibst` }),
      el("div", { class: "tabelle-scroll" }, el("table", { class: "tabelle" },
        el("tr", {}, el("th", { text: "Account" }), el("th", { text: "Likes" }), el("th", { text: "letzter Like" }), el("th")),
        top.map(([konto, n, letzter]) => el("tr", {},
          el("td", {}, konto === "(unbekannt)" ? konto : profilLink(konto)), el("td", {}, el("b", { text: n })), el("td", { text: letzter }),
          el("td", {}, knopf("nur diese durchgehen", () => starten(AK.AktivitaetAblauf.fuerLikes(ak, konto, erneut.checked)), "knopf-dezent klein")))))),
      unten,
      el("p", {}, knopf("Alle Likes durchgehen", () => starten(AK.AktivitaetAblauf.fuerLikes(ak, null, erneut.checked))), " ", listeKnopf),
      hinweis(`${entschieden} schon entschieden.`)), leeren];
  }

  const netz = netzLaden();
  if (netzZustand.fehler) return [el("h1", { text: titel }), karte(el("p", { class: "rot", text: netzZustand.fehler }))];
  if (!netz) return [el("h1", { text: titel }), karte(el("p", { class: "laedt", text: "Bewertungs-Netz wird geladen …" }))];
  if (zustand.kommentarStatistik?.anzahl !== eintraege.length) {     // nur neu rechnen, wenn sich etwas geändert hat
    zustand.kommentarStatistik = { anzahl: eintraege.length, stat: AK.kommentarStatistik(eintraege, netz) };
  }
  const stat = zustand.kommentarStatistik.stat;
  let filter = AK.FILTER_RISKANT;
  const radio = (wert, text, klein) => el("label", { class: "checkzeile" },
    el("input", { type: "radio", name: "filter", value: wert, checked: wert === filter, onchange: () => { filter = wert; } }),
    el("span", {}, text, klein && el("small", { text: ` ${klein}` })));
  return [
    el("h1", { text: titel }),
    el("div", { class: "kacheln" },
       [[stat[KRITISCH], "kritisch – Löschen empfohlen", "wert rot"], [stat[PRUEFEN], "prüfen", "wert"],
        [stat[HARMLOS], "harmlos", "wert gruen"], [entschieden, "schon entschieden", "wert"]].map(([wert, t, k]) =>
         el("div", { class: "kachel" }, el("div", { class: k, text: wert }), el("div", { class: "titel", text: t })))),
    karte(
      el("h2", { text: `${eintraege.length} eigene Kommentare durchgehen` }),
      hinweis("Die Einstufung macht ein kleines neuronales Netz direkt in deinem Browser – die Kommentare verlassen dein Gerät nicht. " +
              `Ab ${AK.MIN_EIGENE_ENTSCHEIDUNGEN} eigenen Entscheidungen lernt es dazu und sortiert ähnliche Kommentare so ein wie du. ` +
              "Es nennt die Wörter, die den Ausschlag gegeben haben. Ironie und Zusammenhang erkennt es nicht – du entscheidest selbst."),
      radio(AK.FILTER_KRITISCH, "Nur kritische (Löschen empfohlen)"),
      radio(AK.FILTER_RISKANT, "Kritische + zu prüfende", "empfohlen – heikelste zuerst"),
      radio(AK.FILTER_ALLE, "Alle Kommentare nacheinander"),
      unten,
      el("p", {}, knopf("Start", () => mitLadeanzeige("Netz lernt aus deinen Entscheidungen …", async () => {
        starten(AK.AktivitaetAblauf.fuerKommentare(ak, persoenlichesNetz(ak), filter, erneut.checked));
      })), " ", listeKnopf)),
    leeren,
  ];
}

const ansichtKommentare = () => aktivitaetsAnsicht(AK.KOMMENTAR);
const ansichtLikes = () => aktivitaetsAnsicht(AK.LIKE);

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
  zustand.akt = null;
  merken("plattform", p);
  for (const b of document.querySelectorAll("#plattform-wahl button")) b.classList.toggle("aktiv", b.dataset.plattform === p);
}

const ANSICHTEN = { laden: ansichtLaden, ergebnis: ansichtErgebnis, verlauf: ansichtVerlauf, entfolgen: ansichtEntfolgen,
                    kommentare: ansichtKommentare, likes: ansichtLikes,
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
