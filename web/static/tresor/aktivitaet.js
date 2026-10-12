// Kommentar- und Like-Modus im Browser – Port von core/aktivitaet.py und core/export.py.
//
// Eigene Kommentare/Likes Schritt für Schritt durchgehen: "Entfernen" oder "Behalten",
// "Zurück" macht die letzte Entscheidung rückgängig. Entscheidungen landen sofort im Tresor
// (bereich.aktivitaet.entscheidungen) und werden mit ihm verschlüsselt gespeichert.
// Das Programm löscht NICHTS selbst auf Instagram.

import { bewerte, HARMLOS, KRITISCH, PRUEFEN } from "./netz.js";

export const KOMMENTAR = "kommentar";
export const LIKE = "like";
export const ENTFERNEN = "entfernen";
export const BEHALTEN = "behalten";
export const FILTER_RISKANT = "riskant";
export const FILTER_KRITISCH = "kritisch";
export const FILTER_ALLE = "alle";
export const MIN_EIGENE_ENTSCHEIDUNGEN = 5;
export const AKTIVITAET_URL = {
  [KOMMENTAR]: "https://www.instagram.com/your_activity/interactions/comments/",
  [LIKE]: "https://www.instagram.com/your_activity/interactions/likes/",
};

export function leereAktivitaet() {
  return { kommentare: {}, likes: {}, entscheidungen: { [KOMMENTAR]: {}, [LIKE]: {} } };
}

/** Neue Kommentare/Likes in den Tresor übernehmen (gleiche ID = schon vorhanden). Gibt [neuK, neuL] zurück. */
export function importieren(aktivitaet, kommentare, likes) {
  let neuK = 0, neuL = 0;
  for (const k of kommentare) if (!(k.id in aktivitaet.kommentare)) { aktivitaet.kommentare[k.id] = k; neuK++; }
  for (const l of likes) if (!(l.id in aktivitaet.likes)) { aktivitaet.likes[l.id] = l; neuL++; }
  return [neuK, neuL];
}

export const nachZeit = (liste) => [...liste].sort((a, b) => (b.zeitstempel || 0) - (a.zeitstempel || 0));

export function kommentarStatistik(kommentare, netz) {
  const z = { [KRITISCH]: 0, [PRUEFEN]: 0, [HARMLOS]: 0 };
  for (const k of kommentare) z[bewerte(k.text, netz, { erklaeren: false }).stufe]++;
  return z;
}

/** [[account, anzahl, letzter Like]] – wem du am häufigsten Likes gibst, absteigend. */
export function likeStatistik(likes) {
  const anzahl = new Map();
  const letzter = new Map();
  for (const l of likes) {
    const name = l.owner || "(unbekannt)";
    anzahl.set(name, (anzahl.get(name) || 0) + 1);
    if (l.zeitstempel && l.zeitstempel > (letzter.get(name)?.[0] || 0)) letzter.set(name, [l.zeitstempel, l.datum]);
  }
  return [...anzahl].sort((a, b) => b[1] - a[1]).map(([name, n]) => [name, n, letzter.get(name)?.[1] ?? "Unbekannt"]);
}

export function suchLink(e) {
  if (e.link) return e.link;
  const owner = e.medien_owner ?? e.owner ?? "";
  return owner ? `https://www.instagram.com/${owner}/` : "";
}

/** Eigene Entscheidungen als Trainingsbeispiele: Entfernen = kritisch, Behalten = harmlos. */
export function eigeneBeispiele(aktivitaet) {
  const ergebnis = [];
  for (const [id, e] of Object.entries(aktivitaet.entscheidungen[KOMMENTAR])) {
    const k = aktivitaet.kommentare[id];
    if (k) ergebnis.push([k.text, e === ENTFERNEN ? KRITISCH : HARMLOS]);
  }
  return ergebnis;
}

export class AktivitaetAblauf {
  constructor(art, eintraege, reihenfolge, entscheidungen, uebersprungen, bewertungen = {}, netz = null) {
    this.art = art;
    this.eintraege = eintraege;             // id -> Kommentar/Like
    this.reihenfolge = reihenfolge;         // abzufragende IDs
    this.entscheidungen = entscheidungen;   // Verweis auf aktivitaet.entscheidungen[art] (wird direkt geändert)
    this.vorher = { ...entscheidungen };     // Stand vor dem Start (für "Zurück")
    this.uebersprungen = uebersprungen;
    this.verlauf = [];
    this.bewertungen = bewertungen;
    this.netz = netz;
  }

  /** filter: "kritisch", "riskant" (kritisch + prüfen) oder "alle". Heikelste zuerst. */
  static fuerKommentare(aktivitaet, netz, filter = FILTER_RISKANT, erneut = false) {
    const kommentare = Object.values(aktivitaet.kommentare);
    const vorher = aktivitaet.entscheidungen[KOMMENTAR];
    const bewertungen = Object.fromEntries(kommentare.map((k) => [k.id, bewerte(k.text, netz, { erklaeren: false })]));
    const erlaubt = { [FILTER_KRITISCH]: [KRITISCH], [FILTER_RISKANT]: [KRITISCH, PRUEFEN] }[filter] ?? [KRITISCH, PRUEFEN, HARMLOS];
    const auswahl = kommentare.filter((k) => erlaubt.includes(bewertungen[k.id].stufe) && (erneut || !(k.id in vorher)));
    auswahl.sort((a, b) => bewertungen[b.id].punkte - bewertungen[a.id].punkte || (b.zeitstempel || 0) - (a.zeitstempel || 0));
    return new AktivitaetAblauf(KOMMENTAR, aktivitaet.kommentare, auswahl.map((k) => k.id), vorher,
                                kommentare.length - auswahl.length, bewertungen, netz);
  }

  /** account: nur Likes bei diesem Account. Neueste zuerst. */
  static fuerLikes(aktivitaet, account = null, erneut = false) {
    const likes = Object.values(aktivitaet.likes);
    const vorher = aktivitaet.entscheidungen[LIKE];
    const auswahl = nachZeit(likes.filter((l) => (!account || l.owner === account) && (erneut || !(l.id in vorher))));
    return new AktivitaetAblauf(LIKE, aktivitaet.likes, auswahl.map((l) => l.id), vorher, likes.length - auswahl.length);
  }

  /** Erster Eintrag, der in DIESEM Durchgang noch nicht entschieden wurde (verlauf = Entscheidungen dieses Durchgangs). */
  aktueller() {
    const erledigt = new Set(this.verlauf);
    const id = this.reihenfolge.find((i) => !erledigt.has(i));
    return id === undefined ? null : this.eintraege[id];
  }

  /** Bewertung MIT Begründung – erst beim Anzeigen berechnet. */
  bewertung(eintrag) {
    if (this.art !== KOMMENTAR || !eintrag) return null;
    let b = this.bewertungen[eintrag.id];
    if (!b || !b.erklaert) b = this.bewertungen[eintrag.id] = bewerte(eintrag.text, this.netz);
    return b;
  }

  fortschritt() { return [this.verlauf.length, this.reihenfolge.length]; }
  istFertig() { return this.aktueller() === null; }
  kannZurueck() { return this.verlauf.length > 0; }

  entscheide(wert) {
    const e = this.aktueller();
    if (!e || ![ENTFERNEN, BEHALTEN].includes(wert)) return null;
    this.entscheidungen[e.id] = wert;
    this.verlauf.push(e.id);
    return e;
  }

  zurueck() {
    const id = this.verlauf.pop();
    if (!id) return null;
    if (id in this.vorher) this.entscheidungen[id] = this.vorher[id];
    else delete this.entscheidungen[id];
    return this.eintraege[id];
  }
}

/** Alles, was (in irgendeinem Durchgang) als "Entfernen" markiert wurde. */
export function alleZumEntfernen(aktivitaet, art) {
  const quelle = art === KOMMENTAR ? aktivitaet.kommentare : aktivitaet.likes;
  return nachZeit(Object.values(quelle).filter((e) => aktivitaet.entscheidungen[art][e.id] === ENTFERNEN));
}

/** Port von core/export.py::aktivitaet_bericht */
export function aktivitaetBericht(art, eintraege) {
  const titel = art === KOMMENTAR ? "Kommentare zum Löschen" : "Likes zum Entfernen";
  const zeilen = [`${titel} (${eintraege.length})`, `Alle gesammelt auf Instagram: ${AKTIVITAET_URL[art]}`,
                  "(App: Profil > Menü > Deine Aktivität > Interaktionen)", ""];
  for (const e of nachZeit(eintraege)) {
    if (art === KOMMENTAR) {
      zeilen.push(`- ${e.datum} · bei @${e.medien_owner || "?"} · ${suchLink(e)}`, `    „${e.text}“`);
    } else {
      zeilen.push(`- ${e.datum} · ${e.art} von @${e.owner || "?"} · ${suchLink(e)}`);
    }
  }
  return zeilen.join("\n") + "\n";
}
