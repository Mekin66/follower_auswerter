// Verbindung zum Server: verschlüsselten Tresor laden, speichern, löschen.
//
// Hier wird NICHTS ausgewertet. Diese Datei kennt nur zwei Dinge:
//   1. den verschlüsselten Text-Block ("FA1....") – der geht an /api/tresor
//   2. den Schlüssel im Arbeitsspeicher – der bleibt im Browser
// Wird die Seite neu geladen oder abgemeldet, ist der Schlüssel weg (Tresor gesperrt).

import * as krypto from "./krypto.js";
import { jetzt, leererTresor, normalisieren } from "./auswertung.js";

export class ApiFehler extends Error {
  constructor(text, status, daten) { super(text); this.status = status; this.daten = daten || {}; }
}

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

async function anfrage(methode, koerper) {
  const antwort = await fetch("/api/tresor", {
    method: methode,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    body: koerper === undefined ? undefined : JSON.stringify(koerper),
    credentials: "same-origin",
    cache: "no-store",
  });
  let daten = {};
  try { daten = await antwort.json(); } catch { /* z. B. 404-Seite als HTML */ }
  if (!antwort.ok) throw new ApiFehler(daten.fehler || `Serverfehler (${antwort.status})`, antwort.status, daten);
  return daten;
}

export class TresorSpeicher {
  constructor({ mitKonto }) {
    this.mitKonto = mitKonto;      // false = nur im Browser-Tab (anonym)
    this.block = null;             // zuletzt geladener verschlüsselter Text vom Server
    this.version = 0;              // Versionsnummer auf dem Server (für Konflikterkennung)
    this.schluessel = null;        // {key, salt} – nur im Arbeitsspeicher
    this.daten = null;             // entschlüsselter Inhalt
    this.avvAktuell = true;
    this.avvLink = "/avv";
    this.zuletztGespeichert = null;
    this.ungespeichert = false;
  }

  get entsperrt() { return this.daten !== null; }

  /** Holt den (verschlüsselten) Stand vom Server. Gibt true zurück, wenn ein Tresor existiert. */
  async abrufen() {
    if (!this.mitKonto) return false;
    const antwort = await anfrage("GET");
    this.version = antwort.version || 0;
    this.block = antwort.vorhanden ? antwort.inhalt : null;
    this.avvAktuell = antwort.avv_aktuell !== false;
    this.avvLink = antwort.avv_link || this.avvLink;
    this.zuletztGespeichert = antwort.aktualisiert_am || null;
    return antwort.vorhanden;
  }

  /** Ohne Konto: leerer Tresor nur im Arbeitsspeicher. */
  lokalStarten() {
    this.daten = leererTresor();
  }

  async anlegen(passwort) {
    this.schluessel = await krypto.neuerSchluessel(passwort);
    this.daten = leererTresor();
    try {
      await this.speichern();
    } catch (e) {
      this.sperren();              // nicht angelegt -> wieder "gesperrt" anzeigen
      throw e;
    }
  }

  async entsperren(passwort) {
    const { daten, schluessel } = await krypto.oeffnen(this.block, passwort);
    this.daten = normalisieren(daten);
    this.schluessel = schluessel;
  }

  sperren() {
    this.daten = null;
    this.schluessel = null;
  }

  async speichern() {
    if (!this.mitKonto || !this.schluessel) return;
    this.daten.geaendert_am = jetzt();
    const block = await krypto.verschluesseln(this.daten, this.schluessel);
    const antwort = await anfrage("PUT", { inhalt: block, basis_version: this.version });
    this.version = antwort.version;
    this.block = block;
    this.zuletztGespeichert = antwort.aktualisiert_am;
    this.ungespeichert = false;
  }

  /** Bei Konflikt: eigenen Stand trotzdem speichern (überschreibt den Stand des anderen Tabs). */
  async ueberschreiben() {
    const aktuell = await anfrage("GET");
    this.version = aktuell.version || 0;
    await this.speichern();
  }

  async passwortAendern(neuesPasswort) {
    this.schluessel = await krypto.neuerSchluessel(neuesPasswort);
    await this.speichern();
  }

  async loeschen() {
    if (this.mitKonto) await anfrage("DELETE");
    this.block = null;
    this.version = 0;
    this.sperren();
  }

  // ---- Sicherungsdatei (geht nie über den Server)
  async sicherungErstellen(passwort) {
    const schluessel = passwort ? await krypto.neuerSchluessel(passwort) : this.schluessel;
    return krypto.verschluesseln(this.daten, schluessel);
  }

  async sicherungLesen(text, passwort) {
    const { daten } = await krypto.oeffnen(text.trim(), passwort);
    return normalisieren(daten);
  }
}
