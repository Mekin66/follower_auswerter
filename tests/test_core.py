import io
import sqlite3

import pytest

from conftest import export_zip
from core import history_store
from core.archive_reader import ExportFormatFehler, lade_archiv
from core.diff_engine import moegliche_blockierungen
from core.freunde import freunde_ermitteln, QUELLE_MANUELL
from core.instagram_checker import AccountStatus, PruefErgebnis
from core.models import Entscheidung, PersonenListe
from core.parser import normalisiere_username, usernames_aus_text
from core.removal_session import EntfolgenAblauf, KATEGORIE_FREUNDE


def test_normalisieren():
    assert normalisiere_username(" @Anna.M ") == "anna.m"
    assert normalisiere_username("https://www.instagram.com/_u/max_1/") == "max_1"
    assert usernames_aus_text("a, @b\nhttps://instagram.com/c ,a") == ["a", "b", "c"]


def test_zip_formate_und_hashtags_ignoriert():
    daten = export_zip(["anna", "ben"], ["anna", "carl"], blockiert=["troll"], enge=["ben"])
    inhalt = lade_archiv(io.BytesIO(daten))
    assert set(inhalt.follower) == {"anna", "ben"}
    assert set(inhalt.following) == {"anna", "carl"}   # hashtag_fake NICHT enthalten
    assert set(inhalt.blockiert) == {"troll"}
    assert set(inhalt.enge_freunde) == {"ben"}


def test_html_export_klare_meldung():
    import zipfile
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("connections/followers_and_following/followers_1.html", "<html></html>")
    with pytest.raises(ExportFormatFehler):
        lade_archiv(io.BytesIO(puffer.getvalue()))


def _snapshot(conn, follower, following, besitzer="lokal"):
    sid = history_store.snapshot_speichern(conn, {u: "01.01.2024" for u in follower},
                                           {u: "01.01.2024" for u in following}, besitzer=besitzer)
    return history_store.snapshot_laden(conn, sid, besitzer)


def test_markierungen_bleiben_ueber_snapshots_und_kategorien_werden_uebersprungen(conn):
    snap1 = _snapshot(conn, ["a"], ["a", "b", "c", "d", "e"])
    ablauf = EntfolgenAblauf("lokal", snap1, {}, set(), erneut_pruefen=set())
    assert ablauf.session.kandidaten == ["b", "c", "d", "e"]
    ablauf.entscheide(conn, Entscheidung.BEHALTEN)      # b
    ablauf.entscheide(conn, Entscheidung.DEAKTIVIERT)   # c
    ablauf.entscheide(conn, Entscheidung.ENTFERNT)      # d
    history_store.liste_hinzufuegen(conn, "lokal", PersonenListe.FREUNDE, ["e"])

    # Neuer Export, zusätzlich neuer Nicht-Zurückfolger "f"
    snap2 = _snapshot(conn, ["a"], ["a", "b", "c", "d", "e", "f"])
    mk = history_store.markierungen_laden(conn, "lokal")
    fr = set(history_store.liste_laden(conn, "lokal", PersonenListe.FREUNDE))

    # Standard: nichts erneut -> nur "f"
    ablauf2 = EntfolgenAblauf("lokal", snap2, mk, fr, erneut_pruefen=set())
    assert ablauf2.session.kandidaten == ["f"]
    assert ablauf2.noch_zu_entfolgen() == ["d"]
    assert set(ablauf2.uebersprungen) == {"behalten", "deaktiviert", "entfernt", KATEGORIE_FREUNDE}

    # Nur Deaktivierte erneut prüfen
    ablauf3 = EntfolgenAblauf("lokal", snap2, mk, fr, erneut_pruefen={"deaktiviert"})
    assert ablauf3.session.kandidaten == ["c", "f"]
    assert ablauf3.bisherige_markierung("c") == Entscheidung.DEAKTIVIERT

    # Anonym (None): alles abfragen
    ablauf4 = EntfolgenAblauf("lokal", snap2, mk, fr, erneut_pruefen=None)
    assert ablauf4.session.kandidaten == ["b", "c", "d", "e", "f"]


def test_zurueck_stellt_alte_markierung_wieder_her_und_ignoriert_auto(conn):
    snap = _snapshot(conn, [], ["x", "y", "z"])
    history_store.markierung_setzen(conn, "lokal", "x", Entscheidung.BEHALTEN)
    mk = history_store.markierungen_laden(conn, "lokal")
    ablauf = EntfolgenAblauf("lokal", snap, mk, set(), erneut_pruefen={"behalten"})
    # automatisch: z deaktiviert
    assert ablauf.auto_ergebnis_uebernehmen(conn, PruefErgebnis("z", AccountStatus.NICHT_ERREICHBAR))
    assert not ablauf.auto_ergebnis_uebernehmen(conn, PruefErgebnis("y", AccountStatus.UNSICHER))
    assert "z" not in history_store.markierungen_laden(conn, "lokal")   # nur Vorschlag, noch nicht gespeichert
    assert ablauf.vorschlaege_offen and list(ablauf.vorschlaege) == ["z"]
    assert ablauf.vorschlaege_bestaetigen(conn, ["z"]) == 1
    ablauf.entscheide(conn, Entscheidung.ENTFERNT)  # x
    assert history_store.markierungen_laden(conn, "lokal")["x"] == Entscheidung.ENTFERNT
    ablauf.entscheide(conn, Entscheidung.ENTFERNT)  # y
    assert ablauf.ist_fertig()
    assert ablauf.zurueck(conn) == "y"               # nicht z (auto)!
    assert "y" not in history_store.markierungen_laden(conn, "lokal")
    assert ablauf.zurueck(conn) == "x"
    assert history_store.markierungen_laden(conn, "lokal")["x"] == Entscheidung.BEHALTEN  # wiederhergestellt
    assert ablauf.zurueck(conn) is None
    assert history_store.markierungen_laden(conn, "lokal")["z"] == Entscheidung.DEAKTIVIERT


def test_besitzer_getrennt(conn):
    s = _snapshot(conn, ["a"], ["b"], besitzer="konto:1")
    with pytest.raises(ValueError):
        history_store.snapshot_laden(conn, s.id, "konto:2")
    assert history_store.snapshots_auflisten(conn, "konto:2") == []
    assert not history_store.snapshot_loeschen(conn, s.id, "konto:2")
    assert history_store.snapshot_loeschen(conn, s.id, "konto:1")


def test_migration_alter_datenbank(tmp_path):
    pfad = tmp_path / "alt.sqlite3"
    alt = sqlite3.connect(pfad)
    alt.executescript("""
        CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, erstellt_am TEXT NOT NULL, label TEXT NOT NULL);
        CREATE TABLE eintraege (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL, username TEXT NOT NULL,
            liste TEXT NOT NULL CHECK (liste IN ('follower','following')), seit_datum TEXT NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id));
        CREATE TABLE workflow_entscheidungen (id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL,
            username TEXT NOT NULL, entscheidung TEXT NOT NULL, entschieden_am TEXT NOT NULL,
            UNIQUE(snapshot_id, username), FOREIGN KEY (snapshot_id) REFERENCES snapshots(id));
        INSERT INTO snapshots VALUES (1, '2026-01-01T10:00:00', 'alt1'), (2, '2026-02-01T10:00:00', 'alt2');
        INSERT INTO eintraege VALUES (1, 1, 'x', 'following', '01.01.2025');
        INSERT INTO workflow_entscheidungen VALUES (1, 1, 'x', 'behalten', '2026-01-01T10:01:00'),
                                                   (2, 2, 'x', 'entfernt', '2026-02-01T10:01:00');
    """)
    alt.commit(); alt.close()
    conn = history_store.init_db(pfad)
    assert [s[2] for s in history_store.snapshots_auflisten(conn)] == ["alt2", "alt1"]
    assert history_store.markierungen_laden(conn, "lokal") == {"x": Entscheidung.ENTFERNT}
    assert history_store.snapshot_loeschen(conn, 1)   # darf trotz alter FKs nicht scheitern
    conn.close()
    history_store.init_db(pfad).close()                 # zweiter Start: Migration nicht doppelt


def test_freunde_und_blockverdacht(conn):
    alt = _snapshot(conn, ["a", "b", "c"], ["a", "b", "d"])
    neu = _snapshot(conn, ["a", "c"], ["a", "d"])
    assert moegliche_blockierungen(alt, neu) == ["b"]
    freunde = freunde_ermitteln(neu.follower, neu.following, ["z"])
    assert [f.username for f in freunde] == ["a", "z"]
    assert freunde[1].quelle == QUELLE_MANUELL


def test_anonyme_daten_werden_aufgeraeumt(conn):
    _snapshot(conn, ["a"], ["b"], besitzer="anon:xyz")
    conn.execute("UPDATE snapshots SET erstellt_am = '2000-01-01T00:00:00' WHERE besitzer = 'anon:xyz'")
    _snapshot(conn, ["a"], ["b"], besitzer="konto:1")
    assert history_store.anonyme_daten_aufraeumen(conn, 24) == 1
    assert history_store.snapshots_auflisten(conn, "konto:1")


# ---------------------------------------------------------------- Version 3
from core.konto_pruefer import Antwort, KontoPruefer, PruefungNichtMoeglich, pruefe_mehrere
from core.txt_format import lese_txt, schreibe_txt
from core.archive_reader import lade_export, lade_liste
from core.plattform import Plattform, bereich


def _instagram_attrappe(existierend):
    def abrufen(url):
        name = url.rstrip("/").rsplit("/", 1)[1]
        # Diese Fehlermeldung steht (wie im echten Instagram) auf JEDER Seite in den Sprachdaten
        sprachdaten = "sorry, this page isn't available"
        if name in existierend:
            return Antwort(200, url, f"<title>{name} (@{name}) &bull; instagram</title> {sprachdaten}")
        return Antwort(200, url, f"<title>instagram</title> {sprachdaten}")
    return abrufen


def test_pruefer_keine_falsch_positiven_und_kalibrierung():
    p = KontoPruefer("instagram", abrufen=_instagram_attrappe({"instagram", "anna"}))
    ergebnis = {e.username: e.status.value for e in pruefe_mehrere(["anna", "geloescht"], 0, pruefer=p)}
    assert ergebnis == {"anna": "aktiv", "geloescht": "nicht_erreichbar"}


def test_pruefer_bricht_bei_sperre_und_gleichen_seiten_ab():
    login = KontoPruefer("instagram", abrufen=lambda url: Antwort(200, "https://www.instagram.com/accounts/login/", ""))
    with pytest.raises(PruefungNichtMoeglich):
        list(pruefe_mehrere(["anna"], 0, pruefer=login))
    gleich = KontoPruefer("instagram", abrufen=lambda url: Antwort(200, url, "<title>Instagram</title>"))
    with pytest.raises(PruefungNichtMoeglich):
        list(pruefe_mehrere(["anna"], 0, pruefer=gleich))


def test_tiktok_pruefer_404():
    def abrufen(url):
        n = url.rsplit("@", 1)[1]
        if n in ("tiktok", "eva"):
            return Antwort(200, url, f'<title>{n}</title> "uniqueid":"{n}" "followercount":3')
        return Antwort(404, url, "<title>tiktok</title>")
    erg = list(pruefe_mehrere(["eva", "weg"], 0, pruefer=KontoPruefer("tiktok", abrufen=abrufen)))
    assert [e.status.value for e in erg] == ["aktiv", "nicht_erreichbar"]


def test_txt_format_rundreise():
    daten = lese_txt("﻿# Kommentar\nanna\n@Ben;2023-11-14\ncarl, dora\nhttps://www.tiktok.com/@eva\n")
    assert daten == {"anna": "Unbekannt", "ben": "14.11.2023", "carl": "Unbekannt", "dora": "Unbekannt", "eva": "Unbekannt"}
    assert lese_txt(schreibe_txt(daten, "Test")) == daten
    tiktok_txt = "Date: 2024-01-05 18:22:10\nUsername: Tina\n\nDate: 2024-02-01 09:00:00\nUsername: tom\n"
    assert lese_txt(tiktok_txt) == {"tina": "05.01.2024", "tom": "01.02.2024"}


def test_tiktok_export_erkennung_json_und_zip():
    import json, zipfile
    neu = {"Your Activity": {"Follower": {"FansList": [{"Date": "2024-01-05 18:22:10", "UserName": "a"}]},
                             "Following": {"Following": [{"Date": "2024-01-05 18:22:10", "UserName": "b"}]}}}
    inhalt = lade_export(io.BytesIO(json.dumps(neu).encode()))
    assert inhalt.plattform == Plattform.TIKTOK and set(inhalt.follower) == {"a"} and set(inhalt.following) == {"b"}
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("Activity/Following.txt", "Date: 2024-01-05 18:22:10\nUsername: x\n")
        z.writestr("Activity/Follower.txt", "Date: 2024-01-05 18:22:10\nUsername: y\n")
    inhalt = lade_export(io.BytesIO(puffer.getvalue()))
    assert inhalt.plattform == Plattform.TIKTOK and set(inhalt.following) == {"x"} and set(inhalt.follower) == {"y"}
    assert lade_liste(b"a\nb", "liste.txt") == {"a": "Unbekannt", "b": "Unbekannt"}


def test_plattform_bereiche_getrennt(conn):
    history_store.markierung_setzen(conn, bereich("lokal", "tiktok"), "anna", Entscheidung.BEHALTEN)
    assert history_store.markierungen_laden(conn, "lokal") == {}
    history_store.besitzer_daten_loeschen(conn, "lokal")
    assert history_store.markierungen_laden(conn, "lokal#tiktok") == {}


# ---------------------------------------------------------------- Version 4: Kommentare, Likes, HTML
from core.aktivitaet import (BEHALTEN, ENTFERNEN, KOMMENTAR, LIKE, AktivitaetAblauf, alle_zum_entfernen,
                             kommentar_statistik, like_statistik)
from core.instagram_export import datei_art
from core.kommentar_bewertung import bewerte

HTML_FOLLOWER = ('<html><body><div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder"><div class="_a6-p"><div><div>'
                 '<a target="_blank" href="https://www.instagram.com/anna">anna</a></div><div>Nov 14, 2023, 10:00 AM</div>'
                 '</div></div></div></body></html>')
HTML_KOMMENTAR = ('<html><body><div class="pam _3-95 _2ph- _a6-g uiBoxWhite noborder"><table>'
                  '<tr><td>Comment</td><td>Du bist ein Idiot!!!</td></tr><tr><td>Media Owner</td><td>ben</td></tr>'
                  '<tr><td>Time</td><td>Dec 1, 2023 8:30 pm</td></tr></table></div></body></html>')


def _gemischtes_zip():
    import json, zipfile
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("connections/followers_and_following/followers_1.html", HTML_FOLLOWER)
        z.writestr("your_instagram_activity/comments/reels_comments.html", HTML_KOMMENTAR)
        z.writestr("your_instagram_activity/comments/post_comments_1.json", json.dumps([
            {"string_map_data": {"Comment": {"value": "😍"}, "Media Owner": {"value": "carl"},
                                 "Time": {"timestamp": 1700000000}}}]))
        z.writestr("your_instagram_activity/likes/liked_posts.json", json.dumps({"likes_media_likes": [
            {"title": "dora", "string_list_data": [{"href": "https://www.instagram.com/p/X1/", "value": "👍", "timestamp": 1700000000}]},
            {"title": "dora", "string_list_data": [{"href": "https://www.instagram.com/p/X2/", "value": "👍", "timestamp": 1700100000}]},
            {"title": "eva", "string_list_data": [{"href": "https://www.instagram.com/p/X3/", "value": "👍", "timestamp": 1700200000}]}]}))
        z.writestr("your_instagram_activity/likes/liked_comments.json", json.dumps({"likes_comment_likes": [
            {"title": "fritz", "string_list_data": [{"href": "https://www.instagram.com/p/X4/", "timestamp": 1700300000}]}]}))
        z.writestr("connections/followers_and_following/following_hashtags.json", "{}")
    return puffer.getvalue()


def test_zip_inhalt_wird_automatisch_erkannt_inkl_html():
    inhalt = lade_export(io.BytesIO(_gemischtes_zip()))
    assert inhalt.plattform == Plattform.INSTAGRAM
    assert inhalt.follower == {"anna": "14.11.2023"}
    assert set(inhalt.enthaelt()) == {"Follower/Following", "Kommentare", "Likes"}
    texte = {k.text: k for k in inhalt.kommentare}
    assert texte["Du bist ein Idiot!!!"].medien_owner == "ben" and texte["Du bist ein Idiot!!!"].quelle == "Reel"
    assert texte["Du bist ein Idiot!!!"].datum == "01.12.2023 20:30"
    assert {l.art for l in inhalt.likes} == {"Beitrag", "Kommentar"} and len(inhalt.likes) == 4
    assert datei_art("x/following_hashtags.json") is None and datei_art("likes/liked_comments.json") == "likes"
    assert like_statistik(inhalt.likes)[0][:2] == ("dora", 2)


def test_kommentar_bewertung():
    assert bewerte("😍🔥").stufe == "harmlos"
    assert bewerte("Du bist so ein Idiot!!!").stufe == "kritisch"
    assert bewerte("Die Migration ist ein politisches Thema").stufe == "prüfen"
    assert bewerte("x" * 320).stufe in ("prüfen", "kritisch")          # lange Kommentare nie harmlos


def test_kommentar_ablauf_filter_zurueck_und_speicherung(conn):
    inhalt = lade_export(io.BytesIO(_gemischtes_zip()))
    history_store.kommentare_speichern(conn, "lokal", inhalt.kommentare)
    assert history_store.kommentare_speichern(conn, "lokal", inhalt.kommentare) == 0      # kein Doppel-Import
    kommentare = history_store.kommentare_laden(conn, "lokal")
    assert kommentar_statistik(kommentare)["kritisch"] == 1
    ablauf = AktivitaetAblauf.fuer_kommentare("lokal", kommentare, {}, filter="riskant")
    assert [k.text for k in [ablauf.eintraege[i] for i in ablauf.reihenfolge]] == ["Du bist ein Idiot!!!"]
    assert ablauf.bewertung(ablauf.aktueller()).empfehlung == "Löschen empfohlen"
    ablauf.entscheide(conn, ENTFERNEN)
    assert ablauf.ist_fertig() and len(alle_zum_entfernen(conn, "lokal", KOMMENTAR)) == 1
    ablauf.zurueck(conn)
    assert alle_zum_entfernen(conn, "lokal", KOMMENTAR) == []
    ablauf.entscheide(conn, BEHALTEN)
    # nächster Durchgang: schon entschiedene werden übersprungen, "alle" zeigt auch harmlose
    vorher = history_store.aktivitaet_entscheidungen_laden(conn, "lokal", KOMMENTAR)
    ablauf2 = AktivitaetAblauf.fuer_kommentare("lokal", kommentare, vorher, filter="alle")
    assert len(ablauf2.reihenfolge) == 1 and ablauf2.uebersprungen == 1


def test_like_ablauf_nach_account(conn):
    inhalt = lade_export(io.BytesIO(_gemischtes_zip()))
    history_store.likes_speichern(conn, "lokal", inhalt.likes)
    likes = history_store.likes_laden(conn, "lokal")
    ablauf = AktivitaetAblauf.fuer_likes("lokal", likes, {}, account="dora")
    assert ablauf.fortschritt() == (0, 2)
    ablauf.entscheide(conn, ENTFERNEN)
    assert ablauf.aktueller().link.endswith("/X1/")                   # neueste zuerst: X2, dann X1
    history_store.besitzer_daten_loeschen(conn, "lokal")
    assert history_store.likes_laden(conn, "lokal") == []
