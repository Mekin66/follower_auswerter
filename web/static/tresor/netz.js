// Neuronales Netz zur Kommentar-Bewertung – JavaScript-Gegenstück zu core/kommentar_netz.py
// und core/kommentar_bewertung.py. Läuft komplett im Browser (Tresor-Modus).
//
// Die Gewichte sind DIESELBEN wie in Python (core/daten/kommentar_netz.json, ausgeliefert unter
// /netz/kommentar_netz.json). Damit beide Seiten exakt gleich rechnen, ist jeder Schritt 1:1
// übernommen – Unicode-Normalisierung, Wort-Zerlegung, Feature-Hashing (CRC32 der UTF-8-Bytes),
// Reihenfolge der Summen. tests/test_js.py prüft, dass Python und JS dieselben Wahrscheinlichkeiten liefern.
//
// Wichtig beim Portieren: Python-Strings zählen Unicode-Codepunkte, JavaScript-Strings UTF-16-Einheiten
// ("😍".length === 2). Deshalb wird hier überall mit Array.from(text) gearbeitet.

export const KLASSEN = ["harmlos", "prüfen", "kritisch"];
export const [HARMLOS, PRUEFEN, KRITISCH] = KLASSEN;
export const STIL = ["laenge", "gross", "ausrufe", "kontakt", "nur_zeichen", "link"];
export const DIM = 16384;
export const FORMAT = 1;
export const EMPFEHLUNG = { [HARMLOS]: "Behalten", [PRUEFEN]: "Ansehen", [KRITISCH]: "Löschen empfohlen" };
const STIL_TEXTE = {
  "#laenge": "sehr langer Text", "#gross": "überwiegend GROSSBUCHSTABEN", "#ausrufe": "mehrere !!/??",
  "#kontakt": "enthält Telefonnummer/E-Mail", "#nur_zeichen": "nur Emojis/Zeichen", "#link": "enthält einen Link",
};
const MIN_ANTEIL = 0.15;

const WORT = /[\p{L}\p{N}_]+/gu;                       // = Pythons \w+ bei Unicode-Text
const WIEDERHOLUNG = /(.)\1{2,}/gu;
const TELEFON = /\+?\p{Nd}[\p{Nd} /-]{7,}\p{Nd}/u;
const EMAIL = /[\p{L}\p{N}_.+-]+@[\p{L}\p{N}_-]+\.[\p{L}\p{N}_.]+/u;
const LINK = /https?:\/\/|www\./i;
const BUCHSTABE = /\p{L}/u;
const GROSS = /\p{Lu}/u;
const EMOJI = /^[\p{So}\p{Sk}]$/u;

// ================================================================ Merkmale
export const normalisieren = (text) => String(text ?? "").normalize("NFKC");

/** Annäherung an Pythons str.casefold(): toLowerCase + die wichtigsten Unterschiede. */
const casefold = (text) => text.toLowerCase().replace(/ß/g, "ss").replace(/ς/g, "σ");

export function istEmoji(zeichen) {
  const cp = zeichen.codePointAt(0);
  return EMOJI.test(zeichen) || (cp >= 0x1f000 && cp <= 0x1faff);
}

export function woerter(text) {
  return (casefold(normalisieren(text)).match(WORT) || []).map((w) => w.replace(WIEDERHOLUNG, "$1$1"));
}

const CRC_TABELLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
const UTF8 = new TextEncoder();

export function crc32(text) {
  let c = 0xffffffff;
  for (const b of UTF8.encode(text)) c = CRC_TABELLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function platz(merkmal) {
  const h = crc32(merkmal);
  return [h % DIM, (h >>> 16) & 1 ? 1.0 : -1.0];
}

function textMerkmale(woerterListe, emojis) {
  const roh = new Map();                                // Map behält die Einfüge-Reihenfolge (wie Python-dict)
  const plus = (k, v) => roh.set(k, (roh.get(k) ?? 0) + v);
  for (const w of woerterListe) {
    plus("w:" + w, 1.0);
    const rand = Array.from(`<${w}>`);
    for (const n of [3, 4, 5]) {
      for (let i = 0; i + n <= rand.length; i++) plus("c:" + rand.slice(i, i + n).join(""), 0.5);
    }
  }
  for (const e of emojis) plus("e:" + e, 1.0);
  const vektor = new Map();
  for (const [merkmal, wert] of roh) {
    const [p, vorzeichen] = platz(merkmal);
    vektor.set(p, (vektor.get(p) ?? 0) + vorzeichen * wert);
  }
  let summe = 0;
  for (const v of vektor.values()) summe += v * v;
  const norm = Math.sqrt(summe) || 1.0;
  const ergebnis = new Map();
  for (const [k, v] of vektor) if (v) ergebnis.set(k, v / norm);
  return ergebnis;
}

export function stilMerkmale(text) {
  text = normalisieren(text);
  const zeichen = Array.from(text);
  const buchstaben = zeichen.filter((z) => BUCHSTABE.test(z));
  const gross = buchstaben.length >= 8 ? buchstaben.filter((z) => GROSS.test(z)).length / buchstaben.length : 0.0;
  return [
    Math.min(zeichen.length / 250, 1.6),
    gross,
    Math.min((text.match(/[!?]{2,}/g) || []).length, 3) / 3,
    TELEFON.test(text) || EMAIL.test(text) ? 1.0 : 0.0,
    text.trim() && !buchstaben.length ? 1.0 : 0.0,
    LINK.test(text) ? 1.0 : 0.0,
  ];
}

export function merkmale(text, { ohneWort = null, ohneStil = null } = {}) {
  const w = woerter(text).filter((x) => x !== ohneWort);
  const emojis = Array.from(normalisieren(text)).filter((z) => istEmoji(z) && z !== ohneWort);
  const stil = stilMerkmale(text);
  if (ohneStil !== null) stil[ohneStil] = 0.0;
  return [textMerkmale(w, emojis), stil];
}

function softmax(werte) {
  const m = Math.max(...werte);
  const e = werte.map((v) => Math.exp(v - m));
  let s = 0;
  for (const v of e) s += v;
  return e.map((v) => v / s);
}

const logChance = (r) => {
  r = Math.min(Math.max(r, 1e-6), 1 - 1e-6);
  return Math.log(r / (1 - r));
};

// ================================================================ Netz
export class KommentarNetz {
  constructor(daten) {
    if (daten.format !== FORMAT || daten.dim !== DIM || daten.stil.join() !== STIL.join()) {
      throw new Error("Die Netz-Datei passt nicht zu dieser Programmversion.");
    }
    this.versteckt = daten.versteckt;
    this.w1 = new Map(Object.entries(daten.w1).map(([i, z]) => [Number(i), Float64Array.from(z)]));
    this.b1 = Float64Array.from(daten.b1);
    this.w2 = daten.w2.map((z) => Float64Array.from(z));
    this.b2 = Float64Array.from(daten.b2);
    this.info = daten.info || {};
  }

  kopie() {
    const k = Object.create(KommentarNetz.prototype);
    k.versteckt = this.versteckt;
    k.w1 = new Map([...this.w1].map(([i, z]) => [i, Float64Array.from(z)]));
    k.b1 = Float64Array.from(this.b1);
    k.w2 = this.w2.map((z) => Float64Array.from(z));
    k.b2 = Float64Array.from(this.b2);
    k.info = { ...this.info };
    return k;
  }

  eingaben(textVektor, stil) {
    const e = [...textVektor];
    stil.forEach((v, i) => { if (v) e.push([DIM + i, v]); });
    return e;
  }

  vorwaerts(eingaben) {
    const H = this.versteckt;
    const h = Array.from(this.b1);
    for (const [i, x] of eingaben) {
      const zeile = this.w1.get(i);
      if (!zeile) continue;                              // nie benutzter Platz = Gewichte 0
      for (let j = 0; j < H; j++) h[j] += zeile[j] * x;
    }
    for (let j = 0; j < H; j++) h[j] = Math.tanh(h[j]);
    const z = Array.from(this.b2);
    for (let j = 0; j < H; j++) for (let k = 0; k < 3; k++) z[k] += h[j] * this.w2[j][k];
    return [h, softmax(z)];
  }

  wahrscheinlichkeiten(text, ohne = {}) {
    const [, p] = this.vorwaerts(this.eingaben(...merkmale(text, ohne)));
    return Object.fromEntries(KLASSEN.map((k, i) => [k, p[i]]));
  }

  static risiko(p) { return p[KRITISCH] + 0.5 * p[PRUEFEN]; }

  erklaeren(text, maxWoerter = 40) {
    const basis = logChance(KommentarNetz.risiko(this.wahrscheinlichkeiten(text)));
    const kandidaten = [];
    for (const w of [...woerter(text), ...Array.from(normalisieren(text)).filter(istEmoji)]) {
      if (!kandidaten.includes(w)) kandidaten.push(w);
    }
    const einfluss = kandidaten.slice(0, maxWoerter).map((w) =>
      [w, basis - logChance(KommentarNetz.risiko(this.wahrscheinlichkeiten(text, { ohneWort: w })))]);
    const stil = stilMerkmale(text);
    STIL.forEach((name, i) => {
      if (stil[i] >= 0.3) {
        einfluss.push([`#${name}`, basis - logChance(KommentarNetz.risiko(this.wahrscheinlichkeiten(text, { ohneStil: i })))]);
      }
    });
    const positiv = einfluss.filter(([, d]) => d > 0);
    const summe = positiv.reduce((s, [, d]) => s + d, 0) || 1.0;
    return positiv.map(([m, d]) => [m, d / summe]).sort((a, b) => b[1] - a[1]);
  }

  // ---------------------------------------------------------------- Nachtrainieren (Lernen aus Entscheidungen)
  schritt(eingaben, ziel, lernrate, gewicht, l2, glaettung = 0.1) {
    const H = this.versteckt;
    const [h, p] = this.vorwaerts(eingaben);
    const soll = [0, 1, 2].map((k) => glaettung / 3 + (k === ziel ? 1 - glaettung : 0));
    const dZ = [0, 1, 2].map((k) => (p[k] - soll[k]) * gewicht);
    const dH = [];
    for (let j = 0; j < H; j++) {
      let s = 0;
      for (let k = 0; k < 3; k++) s += this.w2[j][k] * dZ[k];
      dH.push(s * (1 - h[j] * h[j]));
    }
    for (let j = 0; j < H; j++) for (let k = 0; k < 3; k++) {
      this.w2[j][k] -= lernrate * (dZ[k] * h[j] + l2 * this.w2[j][k]);
    }
    for (let k = 0; k < 3; k++) this.b2[k] -= lernrate * dZ[k];
    for (const [i, x] of eingaben) {
      let zeile = this.w1.get(i);
      if (!zeile) { zeile = new Float64Array(H); this.w1.set(i, zeile); }
      for (let j = 0; j < H; j++) zeile[j] -= lernrate * (dH[j] * x + l2 * zeile[j]);
    }
    for (let j = 0; j < H; j++) this.b1[j] -= lernrate * dH[j];
  }

  trainieren(beispiele, { epochen = 40, lernrate = 0.15, l2 = 5e-4, seed = 7 } = {}) {
    const daten = beispiele.map(([t, k]) => [this.eingaben(...merkmale(t)), KLASSEN.indexOf(k)]);
    if (!daten.length) return;
    const anzahl = [0, 1, 2].map((k) => daten.filter(([, z]) => z === k).length);
    const gewichte = anzahl.map((a) => (a ? daten.length / (3 * a) : 0));
    const zufall = zufallsgenerator(seed);
    for (let epoche = 0; epoche < epochen; epoche++) {
      mischen(daten, zufall);
      const rate = lernrate / (1 + epoche * 0.05);
      for (const [e, z] of daten) this.schritt(e, z, rate, gewichte[z], l2);
    }
  }

  /** Kopie, nachtrainiert mit eigenen Entscheidungen (3-fach) + Stichprobe der Grundbeispiele. */
  angepasst(eigene, basis, epochen = 8) {
    const kopie = this.kopie();
    const zufall = zufallsgenerator(eigene.length);
    const stichprobe = mischen([...basis], zufall).slice(0, 80);
    kopie.trainieren([...stichprobe, ...eigene, ...eigene, ...eigene], { epochen, lernrate: 0.05 });
    kopie.info = { ...this.info, angepasst_mit: eigene.length };
    return kopie;
  }
}

function zufallsgenerator(seed) {                       // mulberry32 – klein, reproduzierbar
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function mischen(liste, zufall) {
  for (let i = liste.length - 1; i > 0; i--) {
    const j = Math.floor(zufall() * (i + 1));
    [liste[i], liste[j]] = [liste[j], liste[i]];
  }
  return liste;
}

/** Port von core/kommentar_netz.py::beispiele_laden – "klasse<TAB>text" je Zeile, UTF-8. */
export function beispieleLesen(text) {
  const ergebnis = [];
  for (const zeile of text.replace(/^\uFEFF/, "").split(/\r?\n/)) {
    if (!zeile.trim() || zeile.startsWith("#")) continue;
    const tab = zeile.indexOf("\t");
    if (tab < 0) continue;
    const klasse = zeile.slice(0, tab).trim().replace("pruefen", "prüfen");
    if (KLASSEN.includes(klasse)) ergebnis.push([zeile.slice(tab + 1).replace(/\\n/g, "\n"), klasse]);
  }
  return ergebnis;
}

// ================================================================ Bewertung (Port von kommentar_bewertung.py)
function originalSchreibweise(text, wort) {
  for (const k of normalisieren(text).match(WORT) || []) {
    const klein = casefold(k);
    if (klein === wort || klein.replace(WIEDERHOLUNG, "$1$1") === wort) return k;
  }
  return wort;
}

/** {stufe, punkte, gruende, treffer, wahrscheinlichkeiten, erklaert, empfehlung} */
export function bewerte(text, netz, { erklaeren = true } = {}) {
  text = String(text ?? "").trim();
  if (!text) {
    return { stufe: HARMLOS, punkte: 0, gruende: ["leer"], treffer: [], erklaert: erklaeren,
             wahrscheinlichkeiten: { [HARMLOS]: 1, [PRUEFEN]: 0, [KRITISCH]: 0 }, empfehlung: EMPFEHLUNG[HARMLOS] };
  }
  const p = netz.wahrscheinlichkeiten(text);
  const stufe = KLASSEN.reduce((a, b) => (p[b] > p[a] ? b : a));
  const prozent = (x) => `${Math.round(x * 100)}%`;
  const gruende = [`Netz: ${prozent(p[KRITISCH])} kritisch, ${prozent(p[PRUEFEN])} prüfen, ${prozent(p[HARMLOS])} harmlos`];
  const treffer = [];
  if (erklaeren && stufe !== HARMLOS) {
    for (const [merkmal, anteil] of netz.erklaeren(text)) {
      if (anteil < MIN_ANTEIL || gruende.length > 3) break;
      if (merkmal.startsWith("#")) gruende.push(`${STIL_TEXTE[merkmal] ?? merkmal} (${prozent(anteil)})`);
      else {
        const wort = originalSchreibweise(text, merkmal);
        treffer.push(wort);
        gruende.push(`„${wort}“ (${prozent(anteil)})`);
      }
    }
  }
  return { stufe, punkte: Math.round(100 * KommentarNetz.risiko(p)), gruende, treffer, wahrscheinlichkeiten: p,
           erklaert: erklaeren, empfehlung: EMPFEHLUNG[stufe] };
}
