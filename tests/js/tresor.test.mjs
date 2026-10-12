// Tests der Browser-Logik mit Node (node --test tests/js). Node >= 20 bringt
// WebCrypto, Blob/File und (De-)CompressionStream mit – wie ein Browser.
// Aufruf normalerweise über pytest (tests/test_js.py), das auch die ZIP-Testdatei erzeugt.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import * as krypto from "../../web/static/tresor/krypto.js";
import * as P from "../../web/static/tresor/parser.js";
import * as A from "../../web/static/tresor/auswertung.js";

// Dasselbe Muster wie web/tresor.py::_FORMAT – der Server muss jeden Block annehmen
const SERVER_FORMAT = /^FA1\.[A-Za-z0-9_-]{16,64}\.[A-Za-z0-9_-]{12,32}\.[A-Za-z0-9_-]{16,}$/;

test("Verschlüsseln und Entschlüsseln", async () => {
  const daten = A.leererTresor();
  A.snapshotHinzufuegen(daten.plattformen.instagram, { anna: "01.01.2024" }, { ben: "Unbekannt" }, "Test");
  const schluessel = await krypto.neuerSchluessel("richtig-langes-passwort");
  const block = await krypto.verschluesseln(daten, schluessel);
  assert.match(block, SERVER_FORMAT);
  assert.ok(!block.includes("anna"), "Klartext darf nicht im Block stehen");
  const { daten: zurueck } = await krypto.oeffnen(block, "richtig-langes-passwort");
  assert.deepEqual(zurueck, daten);
  await assert.rejects(krypto.oeffnen(block, "falsch"), krypto.FalschesPasswort);
  // Jedes Speichern nutzt einen neuen IV -> anderer Geheimtext
  assert.notEqual(await krypto.verschluesseln(daten, schluessel), block);
});

test("Manipulierter Block wird erkannt", async () => {
  const schluessel = await krypto.neuerSchluessel("richtig-langes-passwort");
  const block = await krypto.verschluesseln({ a: 1 }, schluessel);
  const teile = block.split(".");
  const geheim = krypto.vonB64url(teile[3]);
  geheim[5] ^= 1;
  teile[3] = krypto.b64url(geheim);
  await assert.rejects(krypto.entschluesseln(teile.join("."), schluessel), krypto.FalschesPasswort);
});

test("Nutzernamen und TXT wie in Python", () => {
  assert.equal(P.normalisiereUsername(" @Anna.M "), "anna.m");
  assert.equal(P.normalisiereUsername("https://www.instagram.com/_u/Ben_1/"), "ben_1");
  assert.equal(P.normalisiereUsername("https://www.tiktok.com/@carl"), "carl");
  assert.deepEqual(P.usernamesAusText("anna, @ben\ncarl anna"), ["anna", "ben", "carl"]);
  assert.deepEqual(P.leseTxt("# Kommentar\nanna\nben;14.11.2023\ncarl;2023-11-14\ndora, eva"),
    { anna: "Unbekannt", ben: "14.11.2023", carl: "14.11.2023", dora: "Unbekannt", eva: "Unbekannt" });
  assert.deepEqual(P.leseTxt("Date: 2024-01-05 18:22:10\nUsername: anna\n\nDate: 2024-02-01 10:00:00\nUserName: Ben"),
    { anna: "05.01.2024", ben: "01.02.2024" });
  assert.equal(P.dateiArt("connections/followers_and_following/followers_2.json"), "follower");
  assert.equal(P.dateiArt("x/following_hashtags.json"), null);
  assert.equal(P.dateiArt("x/blocked_profiles.html"), "blockiert");
});

test("TikTok-JSON", () => {
  const daten = { Activity: { "Follower List": { FansList: [{ Date: "2024-01-05 18:22:10", UserName: "anna" }] },
                              "Following List": { Following: [{ Date: "2024-02-01", UserName: "Ben" }] } } };
  const t = P.extrahiereTiktokJson(daten);
  assert.deepEqual(t.follower, { anna: "05.01.2024" });
  assert.deepEqual(t.following, { ben: "01.02.2024" });
});

test("Auswertung, Vergleich und Entfolgen-Durchgang", () => {
  const t = A.leererTresor();
  const b = t.plattformen.instagram;
  const alt = A.snapshotHinzufuegen(b, { anna: "-", ben: "-", carl: "-" }, { anna: "-", ben: "-", dora: "-" });
  alt.erstellt_am = "2026-01-01T00:00:00";
  const neu = A.snapshotHinzufuegen(b, { anna: "-", eva: "-" }, { anna: "-", dora: "-", fritz: "-" });
  const k = A.kennzahlen(neu);
  assert.deepEqual(k.nichtZurueck, ["dora", "fritz"]);
  assert.deepEqual(k.fans, ["eva"]);
  const v = A.vergleichen(neu, alt);              // Reihenfolge egal
  assert.deepEqual(v.followerNeu, ["eva"]);
  assert.deepEqual(v.followerWeg, ["ben", "carl"]);
  assert.deepEqual(v.blockVerdacht, ["ben"]);      // vorher gegenseitig, jetzt beides weg

  b.listen.freunde.fritz = A.jetzt();
  let ablauf = new A.EntfolgenAblauf(b, neu, new Set());
  assert.deepEqual(ablauf.kandidaten, ["dora"]);   // fritz ist Freund -> übersprungen
  ablauf.entscheide("entfernt");
  assert.ok(ablauf.istFertig());
  assert.equal(b.markierungen.dora.m, "entfernt");
  ablauf.zurueck();
  assert.equal(b.markierungen.dora, undefined);
  ablauf.entscheide("behalten");

  // Nächster Durchgang: "behalten" nur, wenn ausgewählt
  assert.deepEqual(new A.EntfolgenAblauf(b, neu, new Set()).kandidaten, []);
  assert.deepEqual(new A.EntfolgenAblauf(b, neu, new Set(["behalten", "freunde"])).kandidaten, ["dora", "fritz"]);
  assert.match(A.entfolgenBericht(ablauf.zusammenfassung()), /Behalten.*\(1\):\n  - dora/);
});

test("Alter Tresor wird ergänzt (Migration)", () => {
  const t = A.normalisieren({ format: 1, plattformen: { instagram: { snapshots: [] } } });
  assert.deepEqual(Object.keys(t.plattformen.tiktok.listen), ["freunde", "blockiert_von_mir", "blockiert_mich"]);
  assert.throws(() => A.normalisieren({ format: 99, plattformen: {} }));
});

test("ZIP-Export lesen (Testdatei aus pytest)", { skip: !process.env.FA_TEST_ZIP }, async () => {
  const roh = await readFile(process.env.FA_TEST_ZIP);
  const inhalt = await P.ladeExport(new File([roh], "export.zip"));
  const erwartet = JSON.parse(process.env.FA_TEST_ERWARTET);
  assert.equal(inhalt.plattform, erwartet.plattform);
  assert.deepEqual(inhalt.follower, erwartet.follower);
  assert.deepEqual(inhalt.following, erwartet.following);
  assert.deepEqual(inhalt.blockiert, erwartet.blockiert);
  assert.deepEqual(inhalt.enge_freunde, erwartet.enge_freunde);
});

// ------------------------------------------------------------------ Kommentar-Netz und Kommentar-Modus
import * as N from "../../web/static/tresor/netz.js";
import * as AK from "../../web/static/tresor/aktivitaet.js";

const gewichte = JSON.parse(await readFile(new URL("../../core/daten/kommentar_netz.json", import.meta.url), "utf-8"));
const netz = new N.KommentarNetz(gewichte);

test("Netz: Unicode-Merkmale wie in Python", () => {
  assert.deepEqual(N.woerter("𝐈𝐝𝐢𝐨𝐭!! Du bist sooooo DUMM 😂"), ["idiot", "du", "bist", "soo", "dumm"]);
  assert.deepEqual(N.woerter("GROẞ Straße"), ["gross", "strasse"]);
  assert.deepEqual(N.woerter("Ты идиот"), ["ты", "идиот"]);
  assert.equal(N.crc32("w:idiot"), 0x0 + N.crc32("w:idiot"));
  assert.equal(N.crc32("abc"), 0x352441c2);                     // bekannter CRC32-Wert
  assert.ok(N.istEmoji("😍") && !N.istEmoji("a"));
});

test("Netz: gleiche Wahrscheinlichkeiten wie Python", { skip: !process.env.FA_TEST_NETZ }, () => {
  const erwartet = JSON.parse(process.env.FA_TEST_NETZ);
  for (const { text, p, top } of erwartet) {
    const js = netz.wahrscheinlichkeiten(text);
    for (const k of N.KLASSEN) assert.ok(Math.abs(js[k] - p[k]) < 1e-9, `${text}: ${k} ${js[k]} != ${p[k]}`);
    if (top) assert.equal(netz.erklaeren(text)[0][0], top, text);
  }
});

test("Netz: Bewertung mit Begründung", () => {
  const b = N.bewerte("Was für ein dummer Trottel", netz);
  assert.equal(b.stufe, N.KRITISCH);
  assert.ok(b.treffer.includes("Trottel"));
  assert.equal(N.bewerte("😍🔥", netz).stufe, N.HARMLOS);
  assert.equal(N.bewerte("Was für ein dummer Trottel", netz, { erklaeren: false }).treffer.length, 0);
});

test("Netz lernt aus Entscheidungen (im Browser)", async () => {
  const basis = N.beispieleLesen(await readFile(new URL("../../core/daten/kommentar_beispiele.tsv", import.meta.url), "utf-8"));
  assert.ok(basis.length > 300);
  const eigene = ["Bayern verliert eh wieder", "Dortmund ist so peinlich", "Schalke steigt ab haha",
                  "Bayern-Fans sind alle gleich", "Dortmund kann nix", "Schalke ist ein Witz"].map((t) => [t, N.KRITISCH]);
  const neu = "Bayern ist so peinlich, Schalke auch";
  const vorher = N.KommentarNetz.risiko(netz.wahrscheinlichkeiten(neu));
  const angepasst = netz.angepasst(eigene, basis);
  assert.ok(N.KommentarNetz.risiko(angepasst.wahrscheinlichkeiten(neu)) > vorher + 0.1);
  assert.equal(N.KommentarNetz.risiko(netz.wahrscheinlichkeiten(neu)), vorher, "Original bleibt unverändert");
});

test("Kommentar-Modus: Ablauf, Zurück, Liste, Likes", () => {
  const ak = AK.leereAktivitaet();
  const k = (id, text, zs) => ({ id, text, medien_owner: "ben", zeitstempel: zs, datum: "-", link: "", quelle: "Beitrag" });
  AK.importieren(ak, [k("a", "Du bist so ein Idiot!!!", 2), k("b", "😍", 1), k("c", "Die Regierung hat versagt", 3)],
                 [{ id: "l1", owner: "dora", zeitstempel: 5, datum: "x", link: "", art: "Beitrag" },
                  { id: "l2", owner: "dora", zeitstempel: 6, datum: "y", link: "", art: "Beitrag" },
                  { id: "l3", owner: "eva", zeitstempel: 7, datum: "z", link: "", art: "Beitrag" }]);
  assert.deepEqual(AK.importieren(ak, [k("a", "x", 1)], []), [0, 0]);          // kein Doppel-Import
  const ablauf = AK.AktivitaetAblauf.fuerKommentare(ak, netz, AK.FILTER_RISKANT);
  assert.equal(ablauf.reihenfolge[0], "a");                                    // heikelster zuerst
  assert.ok(!ablauf.reihenfolge.includes("b"));                                // harmlos nicht im Filter
  assert.ok(ablauf.bewertung(ablauf.aktueller()).erklaert);
  ablauf.entscheide(AK.ENTFERNEN);
  assert.equal(ak.entscheidungen.kommentar.a, AK.ENTFERNEN);
  ablauf.zurueck();
  assert.equal(ak.entscheidungen.kommentar.a, undefined);
  ablauf.entscheide(AK.ENTFERNEN);
  assert.deepEqual(AK.alleZumEntfernen(ak, AK.KOMMENTAR).map((e) => e.id), ["a"]);
  assert.match(AK.aktivitaetBericht(AK.KOMMENTAR, AK.alleZumEntfernen(ak, AK.KOMMENTAR)), /Idiot/);
  assert.deepEqual(AK.likeStatistik(Object.values(ak.likes))[0], ["dora", 2, "y"]);
  assert.deepEqual(AK.AktivitaetAblauf.fuerLikes(ak, "dora").reihenfolge, ["l2", "l1"]);
});

test("Kommentare/Likes aus Export wie in Python", { skip: !process.env.FA_TEST_AKT_ZIP }, async () => {
  const roh = await readFile(process.env.FA_TEST_AKT_ZIP);
  const inhalt = await P.ladeExport(new File([roh], "export.zip"));
  const erwartet = JSON.parse(process.env.FA_TEST_AKT_ERWARTET);
  const sortiert = (l) => [...l].sort((a, b) => a.id.localeCompare(b.id));
  assert.deepEqual(sortiert(inhalt.kommentare), sortiert(erwartet.kommentare));
  assert.deepEqual(sortiert(inhalt.likes), sortiert(erwartet.likes));
  assert.deepEqual(inhalt.follower, erwartet.follower);
});
