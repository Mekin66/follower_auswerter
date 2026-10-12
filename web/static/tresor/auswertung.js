// Auswertung und Datenmodell des Tresors – reine Logik, kein DOM.
//
// JavaScript-Gegenstück zu core/diff_engine.py, core/freunde.py und
// core/removal_session.py. Alles, was hier passiert, passiert im Browser.
//
// Aufbau des Tresor-Inhalts (wird als Ganzes verschlüsselt):
// {
//   format: 1,
//   geaendert_am: "2026-10-12T10:00:00",
//   plattformen: {
//     instagram: {
//       snapshots:    [{id, erstellt_am, label, follower: {name: datum}, following: {name: datum}}],
//       markierungen: {name: {m: "behalten"|"entfernt"|"deaktiviert", am: ISO-Zeit}},
//       listen:       {freunde: {name: ISO-Zeit}, blockiert_von_mir: {...}, blockiert_mich: {...}}
//     },
//     tiktok: { ...gleich... }
//   }
// }

export const FORMAT = 1;
export const PLATTFORMEN = { instagram: "Instagram", tiktok: "TikTok" };
export const ENTSCHEIDUNGEN = {
  behalten: "Behalten (ok, dass sie mir nicht folgen)",
  deaktiviert: "Scheint deaktiviert",
  entfernt: "Entfolgen / entfolgt",
};
export const LISTEN = {
  freunde: "Freunde (manuell)",
  blockiert_von_mir: "Von mir blockiert",
  blockiert_mich: "Hat mich blockiert",
};
// Kategorien für "Welche Gruppen erneut abfragen?" (wie core/removal_session.py::KATEGORIEN)
export const KATEGORIEN = [
  ["behalten", "„Behalten“ (ok, dass sie mir nicht folgen)"],
  ["deaktiviert", "„Scheint deaktiviert“"],
  ["entfernt", "„Entfolgen“ markiert, aber ich folge noch"],
  ["freunde", "In meiner Freunde-Liste"],
];

export const jetzt = () => new Date().toISOString().slice(0, 19);

// ---------------------------------------------------------------- Datenmodell
export function leererBereich() {
  return { snapshots: [], markierungen: {}, listen: { freunde: {}, blockiert_von_mir: {}, blockiert_mich: {} } };
}

export function leererTresor() {
  return { format: FORMAT, geaendert_am: jetzt(),
           plattformen: Object.fromEntries(Object.keys(PLATTFORMEN).map((p) => [p, leererBereich()])) };
}

/** Bringt einen geladenen Tresor auf den aktuellen Stand (fehlende Teile ergänzen = "Migration"). */
export function normalisieren(daten) {
  if (!daten || typeof daten !== "object" || !daten.plattformen) throw new Error("Unbekannter Tresor-Inhalt.");
  if (daten.format > FORMAT) throw new Error("Dieser Tresor stammt aus einer neueren App-Version. Bitte Seite neu laden.");
  for (const p of Object.keys(PLATTFORMEN)) {
    const b = (daten.plattformen[p] ??= leererBereich());
    b.snapshots ??= [];
    b.markierungen ??= {};
    b.listen ??= {};
    for (const l of Object.keys(LISTEN)) b.listen[l] ??= {};
  }
  daten.format = FORMAT;
  return daten;
}

export function neueId() {
  return "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

export function snapshotHinzufuegen(bereich, follower, following, label) {
  const s = { id: neueId(), erstellt_am: jetzt(), label: label || `Export vom ${new Date().toLocaleString("de-DE")}`,
              follower, following };
  bereich.snapshots.push(s);
  return s;
}

/** Snapshots nach Datum, neueste zuerst */
export const sortiert = (bereich) => [...bereich.snapshots].sort((a, b) => b.erstellt_am.localeCompare(a.erstellt_am));
export const neuester = (bereich) => sortiert(bereich)[0] || null;

// ---------------------------------------------------------------- Auswertung
const namen = (obj) => Object.keys(obj || {});

export function kennzahlen(snapshot) {
  const follower = new Set(namen(snapshot.follower));
  const following = new Set(namen(snapshot.following));
  const gegenseitig = [...following].filter((n) => follower.has(n)).sort();
  return {
    follower: follower.size,
    following: following.size,
    gegenseitig,
    nichtZurueck: [...following].filter((n) => !follower.has(n)).sort(),   // ich folge, sie nicht zurück
    fans: [...follower].filter((n) => !following.has(n)).sort(),           // sie folgen, ich nicht zurück
  };
}

/** Port von core/diff_engine.py::vergleiche_snapshots + moegliche_blockierungen */
export function vergleichen(a, b) {
  const [alt, neu] = a.erstellt_am <= b.erstellt_am ? [a, b] : [b, a];
  const differenz = (x, y) => namen(x).filter((n) => !(n in y)).sort();
  const vorherGegenseitig = namen(alt.follower).filter((n) => n in alt.following);
  return {
    alt, neu,
    followerNeu: differenz(neu.follower, alt.follower),
    followerWeg: differenz(alt.follower, neu.follower),
    followingNeu: differenz(neu.following, alt.following),
    followingWeg: differenz(alt.following, neu.following),
    blockVerdacht: vorherGegenseitig.filter((n) => !(n in neu.follower) && !(n in neu.following)).sort(),
  };
}

/** Port von core/freunde.py::freunde_ermitteln */
export function freundeErmitteln(snapshot, manuell) {
  const gegenseitig = new Set(namen(snapshot.follower).filter((n) => n in snapshot.following));
  const man = new Set(namen(manuell));
  return [...new Set([...gegenseitig, ...man])].sort().map((n) => ({
    username: n,
    quelle: gegenseitig.has(n) && man.has(n) ? "gegenseitig + manuell" : gegenseitig.has(n) ? "gegenseitig" : "manuell",
    folgtMirSeit: snapshot.follower[n] ?? "–",
    ichFolgeSeit: snapshot.following[n] ?? "–",
  }));
}

/** Port von core/removal_session.py::kategorien_ermitteln */
export function kategorienErmitteln(snapshot, bereich) {
  const alle = kennzahlen(snapshot).nichtZurueck;
  const gruppen = Object.fromEntries(KATEGORIEN.map(([k]) => [k, []]));
  const neu = [];
  for (const n of alle) {
    if (n in bereich.listen.freunde) gruppen.freunde.push(n);          // Freunde haben Vorrang
    else if (bereich.markierungen[n]) gruppen[bereich.markierungen[n].m].push(n);
    else neu.push(n);
  }
  return { alle, neu, gruppen };
}

// ---------------------------------------------------------------- Entfolgen-Durchgang
/**
 * Port von core/removal_session.py::EntfolgenAblauf (ohne automatische Prüfung –
 * die würde Nutzernamen an einen Server schicken).
 * Jede Entscheidung wird sofort in bereich.markierungen geschrieben.
 */
export class EntfolgenAblauf {
  constructor(bereich, snapshot, erneut) {
    this.bereich = bereich;
    this.snapshotId = snapshot.id;
    this.seitDaten = snapshot.following;
    const u = kategorienErmitteln(snapshot, bereich);
    this.kandidaten = [...u.neu];
    this.uebersprungen = {};
    for (const [k, liste] of Object.entries(u.gruppen)) {
      if (erneut.has(k)) this.kandidaten.push(...liste);
      else if (liste.length) this.uebersprungen[k] = liste;
    }
    this.kandidaten.sort();
    this.entscheidungen = {};
    this.verlauf = [];                       // [[name, vorherigeMarkierung|null]] für "Zurück"
  }

  aktueller() { return this.kandidaten.find((n) => !(n in this.entscheidungen)) ?? null; }
  istFertig() { return this.aktueller() === null; }
  fortschritt() { return [Object.keys(this.entscheidungen).length, this.kandidaten.length]; }
  seit(name) { return this.seitDaten[name] ?? "Unbekannt"; }
  kannZurueck() { return this.verlauf.length > 0; }

  entscheide(wert) {
    const name = this.aktueller();
    if (name === null || !(wert in ENTSCHEIDUNGEN)) return null;
    this.verlauf.push([name, this.bereich.markierungen[name] ?? null]);
    this.entscheidungen[name] = wert;
    this.bereich.markierungen[name] = { m: wert, am: jetzt() };
    return name;
  }

  zurueck() {
    const letzter = this.verlauf.pop();
    if (!letzter) return null;
    const [name, vorher] = letzter;
    delete this.entscheidungen[name];
    if (vorher) this.bereich.markierungen[name] = vorher;
    else delete this.bereich.markierungen[name];
    return name;
  }

  zusammenfassung() {
    const z = Object.fromEntries(Object.keys(ENTSCHEIDUNGEN).map((k) => [k, []]));
    for (const [n, w] of Object.entries(this.entscheidungen)) z[w].push(n);
    for (const l of Object.values(z)) l.sort();
    return z;
  }

  nochZuEntfolgen() { return this.uebersprungen.entfernt ?? []; }
}

// ---------------------------------------------------------------- Texte zum Herunterladen
export function entfolgenBericht(zusammenfassung, nochZuEntfolgen = []) {
  const zeilen = [];
  for (const k of ["entfernt", "behalten", "deaktiviert"]) {
    const liste = zusammenfassung[k] || [];
    zeilen.push(`${ENTSCHEIDUNGEN[k]} (${liste.length}):`, ...liste.map((n) => `  - ${n}`), "");
  }
  if (nochZuEntfolgen.length) {
    zeilen.push(`Früher als 'Entfolgen' markiert, aber du folgst noch (${nochZuEntfolgen.length}):`,
                ...nochZuEntfolgen.map((n) => `  - ${n}`), "");
  }
  return zeilen.join("\n");
}

export function namenslisteText(titel, liste) {
  return [`${titel} (${liste.length}):`, ...liste.map((n) => `  - ${n}`)].join("\n") + "\n";
}

export function freundeCsv(freunde, plattform) {
  const profil = (n) => plattform === "tiktok" ? `https://www.tiktok.com/@${n}` : `https://www.instagram.com/${n}/`;
  const zeilen = [["username", "quelle", "folgt_mir_seit", "ich_folge_seit", "profil"].join(";")];
  for (const f of freunde) zeilen.push([f.username, f.quelle, f.folgtMirSeit, f.ichFolgeSeit, profil(f.username)].join(";"));
  return "﻿" + zeilen.join("\r\n") + "\r\n";
}

export function profilUrl(plattform, name) {
  return plattform === "tiktok" ? `https://www.tiktok.com/@${name}` : `https://www.instagram.com/${name}/`;
}
