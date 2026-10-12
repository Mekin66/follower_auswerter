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
