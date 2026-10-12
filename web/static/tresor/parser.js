// Liest Instagram-/TikTok-Exporte und eigene TXT-Listen – im Browser.
//
// JavaScript-Gegenstück zu core/parser.py, core/txt_format.py, core/tiktok_parser.py
// und core/archive_reader.py (nur Follower/Following/Blockierte/Enge Freunde).
// Die Funktionsnamen entsprechen den Python-Namen in camelCase, damit man beide
// Seiten leicht nebeneinander lesen kann. Ändert sich ein Exportformat, müssen
// BEIDE Seiten angepasst werden (Tests: tests/js/parser.test.mjs und tests/test_core.py).

import { istZip, ZipLeser } from "./zip.js";

export const UNBEKANNT = "Unbekannt";
const HREF_MUSTER = /(?:instagram\.com\/(?:_u\/)?|tiktok\.com\/@)([A-Za-z0-9._]+)\/?/i;
// Pfade auf instagram.com, die keine Profile sind
const KEINE_PROFILE = new Set(["p", "reel", "reels", "stories", "explore", "accounts", "direct", "tv", "about",
                               "legal", "web", "developer", "_u"]);

export class ExportFormatFehler extends Error {}

// ---------------------------------------------------------------- Nutzernamen
export function normalisiereUsername(text) {
  text = String(text ?? "").trim();
  const treffer = text.match(HREF_MUSTER);
  if (treffer) text = treffer[1];
  text = text.replace(/^@+/, "").trim().replace(/^\/+|\/+$/g, "");
  return text.replace(/[^A-Za-z0-9._]/g, "").toLowerCase();
}

export function usernamesAusText(text) {
  const ergebnis = [];
  for (const teil of String(text ?? "").split(/[\s,;]+/)) {
    const name = normalisiereUsername(teil);
    if (name && !ergebnis.includes(name)) ergebnis.push(name);
  }
  return ergebnis;
}

// ---------------------------------------------------------------- Datum
const zwei = (n) => String(n).padStart(2, "0");
export const datumText = (d) => `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.${d.getFullYear()}`;

/** '14.11.2023', '2023-11-14' oder '2023-11-14 18:22:10' -> '14.11.2023'. Sonst 'Unbekannt'. */
export function datumLesen(text) {
  text = String(text ?? "").trim();
  let m = text.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
  if (m) return `${zwei(m[1])}.${zwei(m[2])}.${m[3]}`;
  m = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return UNBEKANNT;
}

// ---------------------------------------------------------------- Instagram-JSON
/** Port von core/parser.py::extrahiere_daten – {name: "TT.MM.JJJJ"} */
export function extrahiereDaten(daten) {
  const ergebnis = {};
  const verarbeite = (eintrag) => {
    let name = eintrag.title ? String(eintrag.title) : "";
    let zeit = 0;
    const sld = eintrag.string_list_data;
    if (Array.isArray(sld) && sld.length && sld[0] && typeof sld[0] === "object") {
      const d = sld[0];
      if (!name && d.value) name = String(d.value);
      if (!name && d.href) name = normalisiereUsername(String(d.href));
      if (typeof d.timestamp === "number") zeit = d.timestamp;
    }
    name = normalisiereUsername(name);
    if (!name) return;
    ergebnis[name] = zeit > 0 ? datumText(new Date(zeit * 1000)) : UNBEKANNT;
  };
  const liste = Array.isArray(daten) ? daten
    : (daten && typeof daten === "object") ? Object.values(daten).filter(Array.isArray).flat() : [];
  for (const eintrag of liste) if (eintrag && typeof eintrag === "object") verarbeite(eintrag);
  return ergebnis;
}

/** Port von core/instagram_export.py::datei_art (nur die Listen, die der Tresor braucht). */
export function dateiArt(pfad) {
  const name = String(pfad).toLowerCase().split("/").pop();
  if (!/\.(json|html)$/.test(name)) return null;
  const stamm = name.replace(/(_\d+)?\.(json|html)$/, "");
  if (stamm === "followers") return "follower";
  if (stamm === "following") return "following";
  if (/^blocked_(profiles|accounts|users)$/.test(stamm)) return "blockiert";
  if (stamm === "close_friends") return "enge_freunde";
  return null;
}

/** Profil-Links aus einer HTML-Exportdatei (vereinfachte Fassung von eintraege_aus_html + zu_accounts). */
export function accountsAusHtml(html) {
  const ergebnis = {};
  const muster = /href\s*=\s*["']([^"']+)["']/gi;
  let m;
  while ((m = muster.exec(html)) !== null) {
    const link = m[1];
    const t = link.match(HREF_MUSTER);
    if (!t || KEINE_PROFILE.has(t[1].toLowerCase())) continue;
    const name = normalisiereUsername(t[1]);
    if (name) ergebnis[name] ??= UNBEKANNT;
  }
  return ergebnis;
}

// ---------------------------------------------------------------- TXT (eigenes Format + TikTok-TXT)
const TIKTOK_NAME = /^\s*user\s*name\s*:\s*(\S+)/i;
const TIKTOK_DATUM = /^\s*date\s*:\s*(.+)$/i;

/** Port von core/txt_format.py::lese_txt */
export function leseTxt(text) {
  const zeilen = String(text ?? "").replace(/^﻿/, "").split(/\r?\n/);
  const ergebnis = {};
  if (zeilen.some((z) => TIKTOK_NAME.test(z))) {
    let letztesDatum = UNBEKANNT;
    for (const zeile of zeilen) {
      let t;
      if ((t = zeile.match(TIKTOK_DATUM))) letztesDatum = datumLesen(t[1]);
      else if ((t = zeile.match(TIKTOK_NAME))) {
        const name = normalisiereUsername(t[1]);
        if (name) ergebnis[name] = letztesDatum;
        letztesDatum = UNBEKANNT;
      }
    }
    return ergebnis;
  }
  for (let zeile of zeilen) {
    zeile = zeile.trim();
    if (!zeile || zeile.startsWith("#")) continue;
    if (zeile.includes(";") || zeile.includes("\t")) {
      const [teil1, ...rest] = zeile.split(/[;\t]/);
      const name = normalisiereUsername(teil1);
      if (name) ergebnis[name] = datumLesen(rest.join(";"));
    } else {
      for (const name of usernamesAusText(zeile)) ergebnis[name] ??= UNBEKANNT;
    }
  }
  return ergebnis;
}

/** Port von core/txt_format.py::schreibe_txt */
export function schreibeTxt(daten, titel) {
  const namen = Object.keys(daten).sort();
  const zeilen = [`# ${titel} – ${namen.length} Accounts`, "# Eine Zeile pro Account. Optional mit Datum: name;TT.MM.JJJJ", ""];
  for (const name of namen) {
    const datum = daten[name];
    zeilen.push(datum && datum !== UNBEKANNT && datum !== "Datumsfehler" ? `${name};${datum}` : name);
  }
  return zeilen.join("\n") + "\n";
}

// ---------------------------------------------------------------- TikTok
const NAMENS_SCHLUESSEL = ["UserName", "Username", "username", "userName", "uniqueId", "unique_id"];

export function listeEinordnen(bezeichnung) {
  const b = bezeichnung.toLowerCase();
  if (b.includes("block")) return "blockiert";
  if (b.includes("following")) return "following";
  if (b.includes("fan") || b.includes("follower")) return "follower";
  return null;
}

const nameAus = (e) => {
  for (const s of NAMENS_SCHLUESSEL) if (e[s]) return normalisiereUsername(String(e[s]));
  return "";
};

/** Port von core/tiktok_parser.py::extrahiere_tiktok_json */
export function extrahiereTiktokJson(daten, ergebnis = leererInhalt("tiktok")) {
  const durchlaufen = (obj, pfad) => {
    if (Array.isArray(obj)) {
      if (obj.length && obj.every((e) => e && typeof e === "object" && !Array.isArray(e))) {
        if (obj.slice(0, 5).some(nameAus)) {
          const art = listeEinordnen(pfad.join(" / "));
          if (art) for (const e of obj) {
            const name = nameAus(e);
            if (name) ergebnis[art][name] = datumLesen(e.Date || e.date);
          }
          return;
        }
        for (const e of obj) durchlaufen(e, pfad);
      }
    } else if (obj && typeof obj === "object") {
      for (const [schluessel, wert] of Object.entries(obj)) durchlaufen(wert, [...pfad, schluessel]);
    }
  };
  durchlaufen(daten, []);
  return ergebnis;
}

// ---------------------------------------------------------------- Gesamter Export
export function leererInhalt(plattform = "instagram") {
  return { plattform, follower: {}, following: {}, blockiert: {}, enge_freunde: {} };
}

const hatDaten = (i) => Object.keys(i.follower).length || Object.keys(i.following).length ||
                        Object.keys(i.blockiert).length;

function jsonOderNull(text) {
  try { return JSON.parse(text); } catch { return null; }
}

/**
 * Port von core/archive_reader.py::lade_export.
 * datei = File/Blob mit .name. Ergebnis: {plattform, follower, following, blockiert, enge_freunde}
 */
export async function ladeExport(datei) {
  const dateiname = datei.name || "";
  if (await istZip(datei)) return ladeArchiv(await ZipLeser.oeffnen(datei));
  const text = (await datei.text()).replace(/^﻿/, "");
  const art = dateiArt(dateiname);
  if (art) {
    throw new ExportFormatFehler("Diese Datei enthält nur EINE Liste. Einzelne Dateien bitte in die Felder " +
                                 "„Follower“ bzw. „Following“ laden – oder gleich die ganze ZIP-Datei.");
  }
  const json = jsonOderNull(text);
  if (json !== null) {
    const inhalt = extrahiereTiktokJson(json);
    if (hatDaten(inhalt)) return inhalt;
  }
  throw new ExportFormatFehler("Unbekanntes Dateiformat. Erwartet: die ZIP-Datei des Exports (nicht entpacken) " +
                               "oder die JSON-Datei von TikTok.");
}

export async function ladeArchiv(zip) {
  const inhalt = leererInhalt("instagram");
  let gefunden = false;
  // JSON vor HTML: enthält ein Export beides, liefert JSON die genaueren Daten (mit Datum)
  const eintraege = [...zip.eintraege].sort((a, b) => a.name.toLowerCase().endsWith(".html") -
                                                       b.name.toLowerCase().endsWith(".html"));
  for (const e of eintraege) {
    const art = dateiArt(e.name);
    if (!art) continue;
    const text = await zip.text(e);
    let accounts;
    if (e.name.toLowerCase().endsWith(".html")) accounts = accountsAusHtml(text);
    else {
      const json = jsonOderNull(text);
      if (json === null) continue;
      accounts = extrahiereDaten(json);
    }
    for (const [name, datum] of Object.entries(accounts)) inhalt[art][name] ??= datum;
    gefunden = true;
  }
  if (gefunden && hatDaten(inhalt)) return inhalt;

  // Kein Instagram-Inhalt -> TikTok (eine user_data*.json oder mehrere TXT-Dateien)
  const tiktok = leererInhalt("tiktok");
  for (const e of zip.eintraege) {
    const klein = e.name.toLowerCase();
    if (klein.endsWith(".json")) {
      const json = jsonOderNull(await zip.text(e));
      if (json !== null) extrahiereTiktokJson(json, tiktok);
    } else if (klein.endsWith(".txt")) {
      const art = listeEinordnen(klein.split("/").pop());
      if (art) Object.assign(tiktok[art], leseTxt(await zip.text(e)));
    }
  }
  if (hatDaten(tiktok)) return tiktok;
  throw new ExportFormatFehler("In dieser ZIP-Datei wurden keine Follower-Listen gefunden. Beim Export bitte " +
                               "„Follower und gefolgte Personen“ im Format JSON auswählen (siehe Anleitung).");
}

/** Port von core/archive_reader.py::lade_liste – eine einzelne Liste (JSON, HTML oder TXT). */
export async function ladeListe(datei) {
  const name = (datei.name || "").toLowerCase();
  const text = (await datei.text()).replace(/^﻿/, "");
  if (name.endsWith(".txt")) return leseTxt(text);
  if (/\.html?$/.test(name) || /^\s*<(!doctype|html)/i.test(text)) return accountsAusHtml(text);
  const json = jsonOderNull(text);
  if (json === null) return leseTxt(text);
  const ergebnis = extrahiereDaten(json);
  if (!Object.keys(ergebnis).length) {
    const t = extrahiereTiktokJson(json);
    Object.assign(ergebnis, t.follower, t.following);
  }
  return ergebnis;
}
