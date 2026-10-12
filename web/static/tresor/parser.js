// Liest Instagram-/TikTok-Exporte und eigene TXT-Listen – im Browser.
//
// JavaScript-Gegenstück zu core/parser.py, core/txt_format.py, core/tiktok_parser.py,
// core/instagram_export.py (JSON-/HTML-Einträge, Kommentare, Likes) und core/archive_reader.py.
// Die Funktionsnamen entsprechen den Python-Namen in camelCase, damit man beide
// Seiten leicht nebeneinander lesen kann. Ändert sich ein Exportformat, müssen
// BEIDE Seiten angepasst werden (Tests: tests/js/tresor.test.mjs und tests/test_js.py).

import { istZip, ZipLeser } from "./zip.js";

export const UNBEKANNT = "Unbekannt";
const HREF_MUSTER = /(?:instagram\.com\/(?:_u\/)?|tiktok\.com\/@)([A-Za-z0-9._]+)\/?/i;

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

/** Port von core/instagram_export.py::datei_art */
export function dateiArt(pfad) {
  const ordner = String(pfad).toLowerCase();
  const name = ordner.split("/").pop();
  if (!/\.(json|html)$/.test(name)) return null;
  const stamm = name.replace(/(_\d+)?\.(json|html)$/, "");
  if (stamm === "followers") return "follower";
  if (stamm === "following") return "following";
  if (/^blocked_(profiles|accounts|users)$/.test(stamm)) return "blockiert";
  if (stamm === "close_friends") return "enge_freunde";
  if (stamm.startsWith("liked_") || ((ordner.includes("/likes/") || ordner.startsWith("likes/")) && stamm.includes("like"))) {
    return "likes";
  }
  if (["post_comments", "reels_comments", "comments", "comments_reels"].includes(stamm) ||
      ((ordner.includes("/comments/") || ordner.startsWith("comments/")) && stamm.includes("comment"))) {
    return "kommentare";
  }
  return null;
}

// ---------------------------------------------------------------- Einheitliche Einträge (JSON + HTML)
// Port von core/instagram_export.py: Jeder Eintrag – egal ob JSON oder HTML – wird zuerst zu
// {titel, felder, links, zeitstempel, datumText, texte}. Daraus entstehen Accounts, Kommentare, Likes.

const neuerEintrag = (titel = "") => ({ titel, felder: {}, links: [], zeitstempel: null, datumText: "", texte: [] });

function feldUebernehmen(e, label, daten) {
  label = String(label).trim().toLowerCase();
  if (daten.value !== undefined && daten.value !== null && daten.value !== "") e.felder[label] = String(daten.value);
  if (daten.href) e.links.push(String(daten.href));
  if (typeof daten.timestamp === "number" && daten.timestamp > 0) e.zeitstempel ||= daten.timestamp;
}

function jsonEintrag(obj) {
  if (!["string_list_data", "string_map_data", "label_values"].some((k) => k in obj)) return null;
  const e = neuerEintrag(String(obj.title || ""));
  if (typeof obj.timestamp === "number" && obj.timestamp > 0) e.zeitstempel = obj.timestamp;
  for (const teil of obj.string_list_data || []) if (teil && typeof teil === "object") feldUebernehmen(e, "value", teil);
  for (const [label, teil] of Object.entries(obj.string_map_data || {})) {
    if (teil && typeof teil === "object") feldUebernehmen(e, label, teil);
  }
  for (const teil of obj.label_values || []) {
    if (!teil || typeof teil !== "object") continue;
    feldUebernehmen(e, String(teil.label || ""), teil);
    for (const unter of teil.dict || []) {
      if (!unter || typeof unter !== "object") continue;
      for (const unter2 of unter.dict || [unter]) {
        if (unter2 && typeof unter2 === "object" && unter2.label) feldUebernehmen(e, String(unter2.label), unter2);
      }
    }
  }
  for (const medium of obj.media_list_data || []) {
    if (medium && String(medium.uri || "").startsWith("http")) e.links.push(medium.uri);
  }
  return e;
}

export function eintraegeAusJson(daten) {
  const ergebnis = [];
  const durchlaufen = (obj) => {
    if (Array.isArray(obj)) { for (const w of obj) durchlaufen(w); return; }
    if (obj && typeof obj === "object") {
      const e = jsonEintrag(obj);
      if (e) { ergebnis.push(e); return; }
      for (const w of Object.values(obj)) durchlaufen(w);
    }
  };
  durchlaufen(daten);
  return ergebnis;
}

const ENTITAETEN = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
function entitaetenAufloesen(text) {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (ganz, n) => {
    if (n[0] === "#") {
      const cp = n[1] === "x" || n[1] === "X" ? parseInt(n.slice(2), 16) : parseInt(n.slice(1), 10);
      try { return String.fromCodePoint(cp); } catch { return ganz; }
    }
    return ENTITAETEN[n.toLowerCase()] ?? ganz;
  });
}

/** Port von core/instagram_export.py::_ExportHTML – kleiner HTML-Tokenizer statt DOMParser (läuft auch in Node). */
export function eintraegeAusHtml(html) {
  const BLOCK_KLASSEN = ["uibox", "_a6-g", "pam"];
  const eintraege = [];
  const alleLinks = [];
  let tiefeBlock = null, tiefe = 0, aktuell = null, zellen = null, zelle = null, titelModus = false;
  let link = null, linkText = [];

  const start = (tag, attrs) => {
    if (tag === "div") {
      tiefe += 1;
      const klasse = (attrs.class || "").toLowerCase();
      if (tiefeBlock === null && BLOCK_KLASSEN.some((k) => klasse.includes(k))) { tiefeBlock = tiefe; aktuell = neuerEintrag(); }
    } else if (tag === "tr") zellen = [];
    else if (tag === "td" && zellen !== null) zelle = [];
    else if ((tag === "h2" || tag === "h3") && aktuell !== null) titelModus = true;
    else if (tag === "a" && attrs.href) {
      link = attrs.href; linkText = [];
      if (aktuell !== null) aktuell.links.push(attrs.href);
    }
  };
  const ende = (tag) => {
    if (tag === "div") {
      if (tiefeBlock !== null && tiefe === tiefeBlock) {
        if (aktuell && (aktuell.texte.length || aktuell.links.length)) eintraege.push(aktuell);
        aktuell = null; tiefeBlock = null;
      }
      tiefe -= 1;
    } else if (tag === "td" && zelle !== null && zellen !== null) {
      zellen.push(zelle.join(" ").trim()); zelle = null;
    } else if (tag === "tr" && zellen !== null) {
      if (aktuell !== null && zellen.length >= 2 && zellen[0]) aktuell.felder[zellen[0].trim().toLowerCase()] = zellen[1];
      zellen = null;
    } else if (tag === "h2" || tag === "h3") titelModus = false;
    else if (tag === "a" && link !== null) { alleLinks.push([link, linkText.join(" ").trim()]); link = null; }
  };
  const daten = (roh) => {
    const text = entitaetenAufloesen(roh).split(/\s+/).filter(Boolean).join(" ");
    if (!text) return;
    if (zelle !== null) zelle.push(text);
    if (link !== null) linkText.push(text);
    if (aktuell !== null) {
      aktuell.texte.push(text);
      if (titelModus && !aktuell.titel) aktuell.titel = text;
    }
  };

  const TOKEN = /<!--[\s\S]*?-->|<![^>]*>|<\?[^>]*>|<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^'">])*)>/g;
  const ATTR = /([^\s=/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  let pos = 0, m, inStil = null;
  while ((m = TOKEN.exec(html)) !== null) {
    if (m.index > pos && !inStil) daten(html.slice(pos, m.index));
    pos = TOKEN.lastIndex;
    if (!m[2]) continue;                                            // Kommentar, Doctype …
    const tag = m[2].toLowerCase();
    if (inStil) { if (m[1] && tag === inStil) inStil = null; continue; }   // <style>/<script>-Inhalt überspringen
    if (m[1]) { ende(tag); continue; }
    const attrs = {};
    let a;
    ATTR.lastIndex = 0;
    while ((a = ATTR.exec(m[3])) !== null) attrs[a[1].toLowerCase()] = entitaetenAufloesen(a[2] ?? a[3] ?? a[4] ?? "");
    start(tag, attrs);
    if (/\/\s*$/.test(m[3])) ende(tag);
    if (tag === "style" || tag === "script") inStil = tag;
  }
  if (pos < html.length && !inStil) daten(html.slice(pos));

  if (eintraege.length) {
    for (const e of eintraege) e.datumText = [...e.texte].reverse().find((t) => datumAusText(t)) || "";
    return eintraege;
  }
  return alleLinks.filter(([h]) => h.includes("instagram.com")).map(([h, t]) => ({ ...neuerEintrag(t), links: [h], texte: [t] }));
}

// ---------------------------------------------------------------- Datum aus HTML (Port von datum_aus_text / _zeit)
const MONATE = { jan: 1, feb: 2, mar: 3, "mär": 3, mrz: 3, apr: 4, may: 5, mai: 5, jun: 6, jul: 7, aug: 8, sep: 9,
                 oct: 10, okt: 10, nov: 11, dec: 12, dez: 12 };
const DATUM_EN = /([A-Za-zä]{3})[a-z]*\.? (\d{1,2}), (\d{4})(?:,? (\d{1,2}):(\d{2}) ?([ap]m)?)?/i;
const DATUM_DE = /(\d{1,2})\. ?([A-Za-zä]{3})[a-zä]*\.? (\d{4})(?:,? (\d{1,2}):(\d{2}))?/i;
const DATUM_NUM = /(\d{1,2})\.(\d{1,2})\.(\d{4})(?:,? (\d{1,2}):(\d{2}))?/;

function gueltig(j, mo, t, h, mi) {
  if (h > 23 || mi > 59) return null;
  const d = new Date(j, mo - 1, t, h, mi);
  return d.getFullYear() === j && d.getMonth() === mo - 1 && d.getDate() === t ? d : null;
}

export function datumAusText(text) {
  text = String(text).trim();
  let m;
  if ((m = text.match(DATUM_EN))) {
    const mon = MONATE[m[1].toLowerCase().slice(0, 3)];
    if (mon) {
      let std = Number(m[4] || 0);
      if (m[6]) std = (std % 12) + (m[6].toLowerCase() === "pm" ? 12 : 0);
      return gueltig(Number(m[3]), mon, Number(m[2]), std, Number(m[5] || 0));
    }
  }
  if ((m = text.match(DATUM_DE))) {
    const mon = MONATE[m[2].toLowerCase().slice(0, 3)];
    if (mon) return gueltig(Number(m[3]), mon, Number(m[1]), Number(m[4] || 0), Number(m[5] || 0));
  }
  if ((m = text.match(DATUM_NUM))) {
    return gueltig(Number(m[3]), Number(m[2]), Number(m[1]), Number(m[4] || 0), Number(m[5] || 0));
  }
  return null;
}

const mitUhrzeit = (d) => `${datumText(d)} ${zwei(d.getHours())}:${zwei(d.getMinutes())}`;

/** [zeitstempel, "TT.MM.JJJJ", "TT.MM.JJJJ HH:MM"] */
function zeitVon(e) {
  if (e.zeitstempel) {
    const d = new Date(e.zeitstempel * 1000);
    if (!isNaN(d)) return [e.zeitstempel, datumText(d), mitUhrzeit(d)];
  }
  const d = e.datumText ? datumAusText(e.datumText) : null;
  if (d) return [d.getTime() / 1000, datumText(d), mitUhrzeit(d)];
  return [null, UNBEKANNT, UNBEKANNT];
}

// ---------------------------------------------------------------- Einträge -> Accounts, Kommentare, Likes
function feld(e, ...stichworte) {
  for (const [label, wert] of Object.entries(e.felder)) if (stichworte.some((s) => label.includes(s))) return wert;
  return "";
}
function profilAusLinks(e) {
  const l = e.links.find((x) => /instagram\.com\/(?:_u\/)?[A-Za-z0-9._]+\/?$/.test(x));
  return l ? normalisiereUsername(l) : "";
}
const beitragLink = (e) => e.links.find((l) => /instagram\.com\/(p|reel|reels|tv)\//.test(l)) || "";

export function zuAccounts(eintraege) {
  const ergebnis = {};
  for (const e of eintraege) {
    const name = normalisiereUsername(e.titel || e.felder.value || profilAusLinks(e) || (e.texte[0] ?? ""));
    if (name) ergebnis[name] = zeitVon(e)[1];
  }
  return ergebnis;
}

/** Wie Pythons str(): 1700000000 -> "1700000000.0", null -> "None" – damit die IDs wie in Python entstehen. */
function pyText(x) {
  if (x === null || x === undefined) return "None";
  if (typeof x === "number") return Number.isInteger(x) ? `${x}.0` : String(x);
  return String(x);
}

/** Port von _kurz_id: erste 16 Hex-Zeichen von SHA-1("a|b|c"). */
async function kurzId(...teile) {
  const roh = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(teile.map(pyText).join("|")));
  return Array.from(new Uint8Array(roh), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

export async function zuKommentaren(eintraege, quelle = "Beitrag") {
  const ergebnis = [];
  for (const e of eintraege) {
    let text = feld(e, "comment", "kommentar") || e.felder.value || "";
    if (!text && e.texte.length) {                     // HTML ohne Tabelle: längster Text ist der Kommentar
      const kandidaten = e.texte.filter((t) => !datumAusText(t) && t !== e.titel);
      text = kandidaten.reduce((a, b) => (b.length > a.length ? b : a), "");
    }
    if (!text) continue;
    const owner = normalisiereUsername(feld(e, "owner", "inhaber", "besitzer", "eigentümer") || e.titel);
    const [zs, , datum] = zeitVon(e);
    ergebnis.push({ id: await kurzId(zs, owner, text), text, medien_owner: owner, zeitstempel: zs, datum,
                    link: beitragLink(e), quelle });
  }
  return ergebnis;
}

export async function zuLikes(eintraege, art = "Beitrag") {
  const ergebnis = [];
  for (const e of eintraege) {
    const owner = normalisiereUsername(e.titel || feld(e, "owner", "inhaber", "user", "nutzer") || profilAusLinks(e));
    const link = beitragLink(e) || e.links.find((l) => l.includes("instagram.com")) || "";
    if (!owner && !link) continue;
    const [zs, , datum] = zeitVon(e);
    ergebnis.push({ id: await kurzId(zs, owner, link, art), owner, zeitstempel: zs, datum, link, art });
  }
  return ergebnis;
}

const quelleAusPfad = (pfad) => (pfad.toLowerCase().includes("reel") ? "Reel" : "Beitrag");
const likeArtAusPfad = (pfad) => (pfad.toLowerCase().split("/").pop().includes("comment") ? "Kommentar" : "Beitrag");

/** Liest EINE Export-Datei (JSON oder HTML) in `inhalt`. true, wenn sie etwas Brauchbares war. */
async function dateiLesen(pfad, text, inhalt) {
  const art = dateiArt(pfad);
  if (!art) return false;
  const istHtml = pfad.toLowerCase().endsWith(".html");
  let json = null;
  let eintraege;
  if (istHtml) eintraege = eintraegeAusHtml(text);
  else {
    json = jsonOderNull(text);
    if (json === null) return false;
    eintraege = eintraegeAusJson(json);
  }
  if (["follower", "following", "blockiert", "enge_freunde"].includes(art)) {
    Object.assign(inhalt[art], istHtml ? zuAccounts(eintraege) : extrahiereDaten(json));
  } else if (art === "kommentare") inhalt.kommentare.push(...await zuKommentaren(eintraege, quelleAusPfad(pfad)));
  else if (art === "likes") inhalt.likes.push(...await zuLikes(eintraege, likeArtAusPfad(pfad)));
  return true;
}

function doppelteEntfernen(inhalt) {
  inhalt.kommentare = [...new Map(inhalt.kommentare.map((k) => [k.id, k])).values()];
  inhalt.likes = [...new Map(inhalt.likes.map((l) => [l.id, l])).values()];
}

/** Follower-/Following-Liste im HTML-Format (für ladeListe). */
export function accountsAusHtml(html) {
  return zuAccounts(eintraegeAusHtml(html));
}

// ---------------------------------------------------------------- TXT (eigenes Format + TikTok-TXT)
const TIKTOK_NAME = /^\s*user\s*name\s*:\s*(\S+)/i;
const TIKTOK_DATUM = /^\s*date\s*:\s*(.+)$/i;

/** Port von core/txt_format.py::lese_txt */
export function leseTxt(text) {
  const zeilen = String(text ?? "").replace(/^\uFEFF/, "").split(/\r?\n/);
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
  return { plattform, follower: {}, following: {}, blockiert: {}, enge_freunde: {}, kommentare: [], likes: [] };
}

const hatDaten = (i) => Object.keys(i.follower).length || Object.keys(i.following).length ||
                        Object.keys(i.blockiert).length;
export const hatFollowerDaten = (i) => Boolean(Object.keys(i.follower).length || Object.keys(i.following).length);
const hatIrgendwas = (i) => hatDaten(i) || i.kommentare.length || i.likes.length;

function jsonOderNull(text) {
  try { return JSON.parse(text); } catch { return null; }
}

/**
 * Port von core/archive_reader.py::lade_export.
 * datei = File/Blob mit .name. Ergebnis: {plattform, follower, following, blockiert, enge_freunde, kommentare, likes}
 */
export async function ladeExport(datei) {
  const dateiname = datei.name || "";
  if (await istZip(datei)) return ladeArchiv(await ZipLeser.oeffnen(datei));
  const text = (await datei.text()).replace(/^\uFEFF/, "");
  const art = dateiArt(dateiname);
  if (art === "kommentare" || art === "likes") {          // einzelne Datei, z. B. post_comments_1.json
    const inhalt = leererInhalt("instagram");
    await dateiLesen(dateiname, text, inhalt);
    doppelteEntfernen(inhalt);
    if (hatIrgendwas(inhalt)) return inhalt;
  }
  if (art) {
    throw new ExportFormatFehler("Diese Datei enthält nur EINE Liste. Einzelne Dateien bitte in die Felder " +
                                 "„Follower“ bzw. „Following“ laden – oder gleich die ganze ZIP-Datei.");
  }
  const json = jsonOderNull(text);
  if (json !== null) {
    const inhalt = extrahiereTiktokJson(json);
    if (hatDaten(inhalt)) return inhalt;
  }
  throw new ExportFormatFehler("Unbekanntes Dateiformat. Erwartet: die ZIP-Datei des Exports (nicht entpacken), " +
                               "eine Kommentar-/Like-Datei daraus oder die JSON-Datei von TikTok.");
}

export async function ladeArchiv(zip) {
  const inhalt = leererInhalt("instagram");
  let gefunden = false;
  // JSON vor HTML: enthält ein Export beides, liefert JSON die genaueren Daten
  const eintraege = [...zip.eintraege].sort((a, b) => a.name.toLowerCase().endsWith(".html") -
                                                       b.name.toLowerCase().endsWith(".html"));
  for (const e of eintraege) {
    if (!dateiArt(e.name)) continue;
    gefunden = (await dateiLesen(e.name, await zip.text(e), inhalt)) || gefunden;
  }
  doppelteEntfernen(inhalt);
  if (gefunden && hatIrgendwas(inhalt)) return inhalt;

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
  throw new ExportFormatFehler("In dieser ZIP-Datei wurden weder Follower, Kommentare noch Likes gefunden. Beim " +
                               "Export bitte diese Bereiche auswählen, am besten im Format JSON (siehe Anleitung).");
}

/** Port von core/archive_reader.py::lade_liste – eine einzelne Liste (JSON, HTML oder TXT). */
export async function ladeListe(datei) {
  const name = (datei.name || "").toLowerCase();
  const text = (await datei.text()).replace(/^\uFEFF/, "");
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
