// Minimaler ZIP-Leser für den Browser – ohne fremde Bibliothek.
//
// Warum selbst geschrieben? Fremde Skripte von CDNs würden IP-Adressen an Dritte
// schicken (DSGVO) und wären ein Einfallstor für Schadcode, der das Tresor-Passwort
// abgreifen könnte. Moderne Browser können "deflate" selbst entpacken
// (DecompressionStream) – der Rest ist nur das Lesen des ZIP-Inhaltsverzeichnisses.
//
// Aufbau einer ZIP-Datei (vereinfacht):
//   [Lokaler Kopf + Daten] [Lokaler Kopf + Daten] ... [Zentralverzeichnis] [Ende-Eintrag]
// Wir lesen zuerst den Ende-Eintrag (EOCD) am Dateiende, darüber das Zentralverzeichnis
// mit allen Dateinamen und Positionen und dann NUR die Dateien, die wir brauchen.
// Dank Blob.slice() wird dabei nie die ganze (evtl. riesige) ZIP-Datei in den Speicher geladen.

const SIG_EOCD = 0x06054b50;
const SIG_ZENTRAL = 0x02014b50;
const SIG_LOKAL = 0x04034b50;

async function bytes(blob, start, ende) {
  return new DataView(await blob.slice(start, ende).arrayBuffer());
}

export async function istZip(blob) {
  if (blob.size < 4) return false;
  return (await bytes(blob, 0, 4)).getUint32(0, true) === SIG_LOKAL;
}

export class ZipFehler extends Error {}

export class ZipLeser {
  constructor(blob, eintraege) {
    this.blob = blob;
    this.eintraege = eintraege;      // [{name, methode, groesseGepackt, groesse, offset}]
  }

  static async oeffnen(blob) {
    // 1. Ende-Eintrag suchen: 22 Bytes + bis zu 65535 Bytes Kommentar am Dateiende
    const suchStart = Math.max(0, blob.size - 22 - 65535);
    const ende = await bytes(blob, suchStart, blob.size);
    let pos = -1;
    for (let i = ende.byteLength - 22; i >= 0; i--) {
      if (ende.getUint32(i, true) === SIG_EOCD) { pos = i; break; }
    }
    if (pos < 0) throw new ZipFehler("Keine gültige ZIP-Datei (Inhaltsverzeichnis fehlt).");
    const anzahl = ende.getUint16(pos + 10, true);
    const zentralGroesse = ende.getUint32(pos + 12, true);
    const zentralOffset = ende.getUint32(pos + 16, true);
    if (anzahl === 0xffff || zentralOffset === 0xffffffff) {
      throw new ZipFehler("Diese ZIP-Datei ist zu groß (ZIP64). Bitte bei Instagram nur „Follower und gefolgte " +
                          "Personen“ exportieren – dann ist die Datei klein.");
    }

    // 2. Zentralverzeichnis lesen
    const zentral = await bytes(blob, zentralOffset, zentralOffset + zentralGroesse);
    const dekoder = new TextDecoder("utf-8");
    const eintraege = [];
    let p = 0;
    for (let n = 0; n < anzahl; n++) {
      if (zentral.getUint32(p, true) !== SIG_ZENTRAL) throw new ZipFehler("ZIP-Inhaltsverzeichnis beschädigt.");
      const namensLaenge = zentral.getUint16(p + 28, true);
      const extraLaenge = zentral.getUint16(p + 30, true);
      const kommentarLaenge = zentral.getUint16(p + 32, true);
      const name = dekoder.decode(new Uint8Array(zentral.buffer, zentral.byteOffset + p + 46, namensLaenge));
      eintraege.push({
        name,
        methode: zentral.getUint16(p + 10, true),         // 0 = gespeichert, 8 = deflate
        groesseGepackt: zentral.getUint32(p + 20, true),
        groesse: zentral.getUint32(p + 24, true),
        offset: zentral.getUint32(p + 42, true),
      });
      p += 46 + namensLaenge + extraLaenge + kommentarLaenge;
    }
    return new ZipLeser(blob, eintraege);
  }

  /** Inhalt eines Eintrags als Uint8Array (entpackt). */
  async lesen(eintrag) {
    const kopf = await bytes(this.blob, eintrag.offset, eintrag.offset + 30);
    if (kopf.getUint32(0, true) !== SIG_LOKAL) throw new ZipFehler(`ZIP-Eintrag beschädigt: ${eintrag.name}`);
    const start = eintrag.offset + 30 + kopf.getUint16(26, true) + kopf.getUint16(28, true);
    const daten = this.blob.slice(start, start + eintrag.groesseGepackt);
    if (eintrag.methode === 0) return new Uint8Array(await daten.arrayBuffer());
    if (eintrag.methode === 8) {
      const strom = daten.stream().pipeThrough(new DecompressionStream("deflate-raw"));
      return new Uint8Array(await new Response(strom).arrayBuffer());
    }
    throw new ZipFehler(`Nicht unterstützte Kompression (${eintrag.methode}) in ${eintrag.name}.`);
  }

  async text(eintrag) {
    return new TextDecoder("utf-8").decode(await this.lesen(eintrag)).replace(/^\uFEFF/, "");
  }
}
