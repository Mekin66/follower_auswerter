// Ende-zu-Ende-Verschlüsselung des Tresors – läuft NUR im Browser.
//
// Ablauf:
//   Tresor-Passwort --PBKDF2-SHA-256 (600 000 Runden, zufälliges Salt)--> AES-256-Schlüssel
//   Daten (JSON) --gzip--> --AES-256-GCM (zufälliger IV)--> Geheimtext
//   Ergebnis-Text:  "FA1.<salt>.<iv>.<geheimtext>"  (Base64url)
//
// Das Passwort und der Schlüssel verlassen den Browser nie. Der Server bekommt nur
// den Ergebnis-Text und prüft lediglich, ob er dieses Format hat (web/tresor.py).
// GCM ist "authentifizierte" Verschlüsselung: Wird der Block auf dem Server verändert
// oder ist das Passwort falsch, schlägt das Entschlüsseln fehl, statt Unsinn zu liefern.

export const PRAEFIX = "FA1";
export const RUNDEN = 600000;           // Empfehlung OWASP 2023 für PBKDF2-SHA-256
const ZUSATZDATEN = new TextEncoder().encode(PRAEFIX);   // bindet den Geheimtext an die Formatversion

export class FalschesPasswort extends Error {
  constructor() { super("Das Tresor-Passwort ist falsch (oder der Tresor ist beschädigt)."); }
}

// ---------------------------------------------------------------- Base64url
export function b64url(bytes) {
  let binaer = "";
  const teil = 0x8000;                                  // in Stücken, sonst "Maximum call stack size exceeded"
  for (let i = 0; i < bytes.length; i += teil) {
    binaer += String.fromCharCode.apply(null, bytes.subarray(i, i + teil));
  }
  return btoa(binaer).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function vonB64url(text) {
  const b64 = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  const binaer = atob(b64);
  const bytes = new Uint8Array(binaer.length);
  for (let i = 0; i < binaer.length; i++) bytes[i] = binaer.charCodeAt(i);
  return bytes;
}

// ---------------------------------------------------------------- gzip
async function durchStrom(bytes, strom) {
  const antwort = new Response(new Blob([bytes]).stream().pipeThrough(strom));
  return new Uint8Array(await antwort.arrayBuffer());
}
const packen = (bytes) => durchStrom(bytes, new CompressionStream("gzip"));
const entpacken = (bytes) => durchStrom(bytes, new DecompressionStream("gzip"));

// ---------------------------------------------------------------- Schlüssel
export async function schluesselAbleiten(passwort, salt) {
  const basis = await crypto.subtle.importKey("raw", new TextEncoder().encode(passwort), "PBKDF2", false,
                                              ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: RUNDEN, hash: "SHA-256" }, basis,
                                 { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

/** Neuer Schlüssel mit neuem, zufälligem Salt (neuer Tresor oder Passwort ändern). */
export async function neuerSchluessel(passwort) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return { key: await schluesselAbleiten(passwort, salt), salt };
}

// ---------------------------------------------------------------- ver-/entschlüsseln
export async function verschluesseln(daten, schluessel) {
  const iv = crypto.getRandomValues(new Uint8Array(12));   // bei JEDEM Speichern neu – nie wiederverwenden!
  const klar = await packen(new TextEncoder().encode(JSON.stringify(daten)));
  const geheim = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: ZUSATZDATEN }, schluessel.key, klar));
  return [PRAEFIX, b64url(schluessel.salt), b64url(iv), b64url(geheim)].join(".");
}

function zerlegen(block) {
  const teile = String(block || "").split(".");
  if (teile.length !== 4 || teile[0] !== PRAEFIX) throw new Error("Das ist keine Tresor-Datei.");
  return { salt: vonB64url(teile[1]), iv: vonB64url(teile[2]), geheim: vonB64url(teile[3]) };
}

/** Öffnet einen Block mit dem Passwort. Gibt {daten, schluessel} zurück (Schlüssel für späteres Speichern). */
export async function oeffnen(block, passwort) {
  const { salt } = zerlegen(block);
  const schluessel = { key: await schluesselAbleiten(passwort, salt), salt };
  return { daten: await entschluesseln(block, schluessel), schluessel };
}

export async function entschluesseln(block, schluessel) {
  const { iv, geheim } = zerlegen(block);
  let klar;
  try {
    klar = await crypto.subtle.decrypt({ name: "AES-GCM", iv, additionalData: ZUSATZDATEN }, schluessel.key, geheim);
  } catch {
    throw new FalschesPasswort();
  }
  return JSON.parse(new TextDecoder().decode(await entpacken(new Uint8Array(klar))));
}
