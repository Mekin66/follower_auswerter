import io
import re
import time

import pytest

from conftest import export_zip
from core.instagram_checker import AccountStatus, PruefErgebnis


def _app(tmp_path, **cfg):
    """Die bisherigen Tests prüfen den klassischen Modus (Server wertet aus). Tresor-Tests: tests/test_tresor.py"""
    from web.app import create_app
    cfg.setdefault("BETRIEBSMODUS", "klassisch")
    app = create_app(DATENBANK_PFAD=tmp_path / "web.sqlite3", SECRET_KEY="x", **cfg)
    app.config["TESTING"] = True
    return app


def _csrf(client, pfad="/"):
    html = client.get(pfad).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def _hochladen(client, follower, following, **kw):
    token = _csrf(client)
    daten = {"_csrf": token, "zip_datei": (io.BytesIO(export_zip(follower, following, **kw)), "export.zip")}
    antwort = client.post("/laden", data=daten, content_type="multipart/form-data")
    assert antwort.status_code == 302, antwort.get_data(as_text=True)
    return int(antwort.headers["Location"].rsplit("/", 1)[1]), token


def test_anonym_upload_ergebnis_freunde_und_keine_listen(tmp_path):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=False, AUTO_CHECK_AKTIVIERT=False)
    c = app.test_client()
    sid, token = _hochladen(c, ["anna", "ben"], ["anna", "carl"], blockiert=["troll"])
    html = c.get(f"/ergebnis/{sid}").get_data(as_text=True)
    assert "carl" in html and "hashtag_fake" not in html
    assert "anna" in c.get(f"/freunde/{sid}").get_data(as_text=True)
    assert "anna" in c.get(f"/freunde/{sid}/export.csv").get_data(as_text=True)
    # Funktionen, die es ohne Konten nicht geben soll:
    assert c.get("/listen").status_code == 404
    assert c.get("/registrieren").status_code == 404
    assert c.get("/anmelden").status_code == 404
    assert "Meine Listen" not in html and "Anmelden" not in html
    # Entfolgen ohne Kategorie-Auswahl, direkt Wizard
    html = c.get(f"/entfolgen/{sid}").get_data(as_text=True)
    assert "Welche Gruppen" not in html and "carl" in html
    c.post(f"/entfolgen/{sid}/entscheiden", data={"_csrf": token, "entscheidung": "entfernt", "kandidat": "carl"})
    assert "Fertig" in c.get(f"/entfolgen/{sid}").get_data(as_text=True)
    assert "carl" in c.get(f"/entfolgen/{sid}/export").get_data(as_text=True)


def test_anonyme_besucher_sehen_sich_nicht(tmp_path):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=False)
    a, b = app.test_client(), app.test_client()
    sid, _ = _hochladen(a, ["x"], ["y"])
    assert b.get(f"/ergebnis/{sid}").status_code == 404
    assert "Export vom" not in b.get("/verlauf").get_data(as_text=True)


def test_csrf_pflicht(tmp_path):
    c = _app(tmp_path).test_client()
    assert c.post("/laden", data={}).status_code == 400


def _letzter_link(c, pfad_teil):
    """Link aus der zuletzt 'verschickten' Mail (Testmodus: Postausgang in app.config)."""
    text = c.application.config["MAIL_POSTAUSGANG"][-1]["text"]
    return re.search(r"https?://[^\s]*" + pfad_teil + r"[^\s]+", text).group(0).split("localhost", 1)[1]


def _registrieren(c, name="tester"):
    """Registrieren + Bestätigungs-Link anklicken (Standard: E-Mail-Bestätigung ist an)."""
    token = _csrf(c, "/registrieren")
    r = c.post("/registrieren", data={"_csrf": token, "benutzername": name, "email": f"{name}@example.org",
                                      "passwort": "geheim123", "passwort2": "geheim123", "zustimmung": "1"})
    assert r.status_code == 200 and "Postfach" in r.get_data(as_text=True), r.get_data(as_text=True)
    r = c.get(_letzter_link(c, "/bestaetigen/"))
    assert r.status_code == 302, r.get_data(as_text=True)


def test_konten_volle_funktionen_und_kategorie_auswahl(tmp_path, monkeypatch):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=True, AUTO_CHECK_AKTIVIERT=True, AUTO_CHECK_PAUSE_SEKUNDEN=0)
    c = app.test_client()
    # anonym hochladen, dann registrieren -> Auswertung wird übernommen
    sid, _ = _hochladen(c, ["a"], ["a", "b", "c"], blockiert=["troll"], enge=["a"])
    _registrieren(c)
    assert c.get(f"/ergebnis/{sid}").status_code == 200
    token = _csrf(c)

    # Erster Durchlauf: keine Markierungen -> keine Auswahl, sondern Angebot Auto-Prüfung
    html = c.get(f"/entfolgen/{sid}").get_data(as_text=True)
    assert "Automatische Vorprüfung" in html

    import web.app as webapp
    monkeypatch.setattr(webapp, "pruefe_mehrere", lambda namen, pause, abbrechen=None, plattform=None: iter(
        [PruefErgebnis(n, AccountStatus.NICHT_ERREICHBAR if n == "c" else AccountStatus.AKTIV) for n in namen]))
    c.post(f"/entfolgen/{sid}/automatisch", data={"_csrf": token})
    for _ in range(50):
        html = c.get(f"/entfolgen/{sid}").get_data(as_text=True)
        if "Prüfe Accounts" not in html:
            break
        time.sleep(0.05)
    # Ergebnisse sind jetzt Vorschläge, die bestätigt werden müssen
    assert "scheinen nicht mehr zu existieren" in html and 'value="c"' in html
    c.post(f"/entfolgen/{sid}/vorschlaege", data={"_csrf": token, "auswahl": ["c"]})
    html = c.get(f"/entfolgen/{sid}").get_data(as_text=True)
    assert ">b<" in html
    c.post(f"/entfolgen/{sid}/entscheiden", data={"_csrf": token, "entscheidung": "behalten", "kandidat": "b"})
    assert "Fertig" in c.get(f"/entfolgen/{sid}").get_data(as_text=True)

    # Zweiter Export: b (behalten) und c (deaktiviert) sind markiert -> Auswahl erscheint
    sid2, _ = _hochladen(c, ["a"], ["a", "b", "c", "d"], blockiert=["troll"], enge=["a"])
    html = c.get(f"/entfolgen/{sid2}").get_data(as_text=True)
    assert "Welche Gruppen" in html
    c.post(f"/entfolgen/{sid2}/start", data={"_csrf": token, "erneut": ["deaktiviert"]})
    c.post(f"/entfolgen/{sid2}/ueberspringen", data={"_csrf": token})
    html = c.get(f"/entfolgen/{sid2}").get_data(as_text=True)
    assert ">c<" in html and "bisher:" in html      # c wird erneut abgefragt, b übersprungen
    c.post(f"/entfolgen/{sid2}/entscheiden", data={"_csrf": token, "entscheidung": "entfernt", "kandidat": "c"})
    html = c.get(f"/entfolgen/{sid2}").get_data(as_text=True)
    assert ">d<" in html
    c.post(f"/entfolgen/{sid2}/zurueck", data={"_csrf": token})
    assert ">c<" in c.get(f"/entfolgen/{sid2}").get_data(as_text=True)

    # Listen: Export-Import von blockiert + enge Freunde, manuelles Hinzufügen
    html = c.get("/listen?tab=blockiert_von_mir").get_data(as_text=True)
    assert "troll" in html
    c.post("/listen/blockiert_mich/hinzufuegen", data={"_csrf": token, "namen": "@Boeser.Mensch, https://instagram.com/nochwer/"})
    html = c.get("/listen?tab=blockiert_mich").get_data(as_text=True)
    assert "boeser.mensch" in html and "nochwer" in html
    assert "b" in c.get("/listen?tab=markierungen").get_data(as_text=True)
    assert c.get("/listen?tab=unsinn").status_code == 200


def test_konten_getrennt_und_loeschen(tmp_path):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=True)
    a, b = app.test_client(), app.test_client()
    _registrieren(a, "alice")
    _registrieren(b, "bob")
    sid, token_a = _hochladen(a, ["x"], ["y"])
    assert b.get(f"/ergebnis/{sid}").status_code == 404
    a.post("/listen/freunde/hinzufuegen", data={"_csrf": token_a, "namen": "geheimfreund"})
    assert "geheimfreund" not in b.get("/listen").get_data(as_text=True)
    # Konto löschen
    r = a.post("/konto/loeschen", data={"_csrf": _csrf(a, "/konto"), "passwort": "geheim123"})
    assert r.status_code == 302
    assert a.get("/listen").status_code == 404
    # Doppelter Name, Login
    c = app.test_client()
    token = _csrf(c, "/registrieren")
    html = c.post("/registrieren", data={"_csrf": token, "benutzername": "BOB", "passwort": "geheim123",
                                         "passwort2": "geheim123", "zustimmung": "1"}).get_data(as_text=True)
    assert "bereits vergeben" in html
    r = c.post("/anmelden", data={"_csrf": token, "benutzername": "bob", "passwort": "geheim123"})
    assert r.status_code == 302


def test_registrierung_geschlossen(tmp_path):
    c = _app(tmp_path, ACCOUNTS_AKTIVIERT=True, REGISTRIERUNG_OFFEN=False).test_client()
    assert c.get("/registrieren").status_code == 302


def test_massenauswahl_listen_und_markierungen(tmp_path):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=True)
    c = app.test_client()
    _registrieren(c)
    token = _csrf(c, "/listen")
    c.post("/listen/blockiert_von_mir/hinzufuegen", data={"_csrf": token, "namen": "a, b, c, d"})
    # zwei entfernen, einen verschieben, einer bleibt
    c.post("/listen/blockiert_von_mir/sammel", data={"_csrf": token, "auswahl": ["a", "b"], "aktion": "entfernen"})
    c.post("/listen/blockiert_von_mir/sammel", data={"_csrf": token, "auswahl": ["c"], "aktion": "verschieben:blockiert_mich"})
    c.post("/listen/blockiert_von_mir/sammel", data={"_csrf": token, "auswahl": ["d"], "aktion": "kopieren:freunde"})
    von_mir = c.get("/listen?tab=blockiert_von_mir").get_data(as_text=True)
    assert 'value="d"' in von_mir and 'value="a"' not in von_mir and 'value="c"' not in von_mir
    assert 'value="c"' in c.get("/listen?tab=blockiert_mich").get_data(as_text=True)
    assert 'value="d"' in c.get("/listen?tab=freunde").get_data(as_text=True)
    # Einzel-Knopf in der Sammel-Form
    c.post("/listen/blockiert_von_mir/sammel", data={"_csrf": token, "nur": "d", "auswahl": ["x"], "aktion": "entfernen"})
    assert 'value="d"' not in c.get("/listen?tab=blockiert_von_mir").get_data(as_text=True)
    # Markierungen gesammelt setzen und entfernen
    from core import history_store
    from core.models import Entscheidung
    c.post("/markierungen/sammel", data={"_csrf": token, "auswahl": ["p", "q", "r"], "markierung": "behalten"})
    html = c.get("/listen?tab=markierungen").get_data(as_text=True)
    assert html.count("badge-gruen") == 3
    c.post("/markierungen/sammel", data={"_csrf": token, "auswahl": ["p", "q"], "markierung": "entfernen"})
    html = c.get("/listen?tab=markierungen").get_data(as_text=True)
    assert 'value="r"' in html and 'value="p"' not in html
    assert c.post("/markierungen/sammel", data={"_csrf": token, "auswahl": ["r"], "markierung": "quatsch"}).status_code == 400


def test_tiktok_export_plattform_trennung_und_editor(tmp_path):
    import json
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=False, AUTO_CHECK_AKTIVIERT=False)
    c = app.test_client()
    token = _csrf(c)
    # Instagram-Auswertung
    sid_ig, _ = _hochladen(c, ["anna"], ["anna", "ig_only"])
    # TikTok-JSON -> Plattform wird automatisch umgestellt
    tt = {"Activity": {"Follower List": {"FansList": [{"Date": "2024-01-05 18:22:10", "UserName": "Tina"}]},
                       "Following List": {"Following": [{"Date": "2024-01-05 18:22:10", "UserName": "tina"},
                                                        {"Date": "2024-01-06 10:00:00", "UserName": "tt_only"}]}}}
    r = c.post("/laden", data={"_csrf": token, "zip_datei": (io.BytesIO(json.dumps(tt).encode()), "user_data.json")},
               content_type="multipart/form-data")
    sid_tt = int(r.headers["Location"].rsplit("/", 1)[1])
    html = c.get(f"/ergebnis/{sid_tt}").get_data(as_text=True)
    assert "tt_only" in html and "TikTok-Export erkannt" in html
    assert c.get(f"/ergebnis/{sid_ig}").status_code == 404          # Instagram-Daten im TikTok-Bereich unsichtbar
    assert "tiktok.com/@tt_only" in c.get(f"/entfolgen/{sid_tt}").get_data(as_text=True)
    # zurück zu Instagram
    c.post("/plattform", data={"_csrf": token, "plattform": "instagram"})
    assert "ig_only" in c.get(f"/ergebnis/{sid_ig}").get_data(as_text=True)
    # Editor: eintippen, TXT herunterladen, auswerten
    felder = {"_csrf": token, "follower": "# Kommentar\nanna\n@Ben;14.11.2023", "following": "anna, carl\nhttps://www.instagram.com/dora/"}
    txt = c.post("/editor", data={**felder, "aktion": "txt_follower"}).get_data(as_text=True)
    assert "ben;14.11.2023" in txt and "anna" in txt
    r = c.post("/editor", data={**felder, "aktion": "auswerten", "label": "Meine Liste"})
    sid_ed = int(r.headers["Location"].rsplit("/", 1)[1])
    html = c.get(f"/ergebnis/{sid_ed}").get_data(as_text=True)
    assert "Meine Liste" in html and "dora" in html and "carl" in html
    assert "carl" in c.get(f"/editor?von={sid_ed}").get_data(as_text=True)
    # TXT-Upload als einzelne Liste
    r = c.post("/laden", data={"_csrf": token, "follower_datei": (io.BytesIO(b"x1\nx2"), "f.txt"),
                               "following_datei": (io.BytesIO(b"x1\nx3"), "g.txt")}, content_type="multipart/form-data")
    assert r.status_code == 302 and "/ergebnis/" in r.headers["Location"]


def test_anleitungen_erreichbar(tmp_path):
    from core.anleitungen import ANLEITUNGEN
    c = _app(tmp_path).test_client()
    assert "Anleitungen" in c.get("/anleitung").get_data(as_text=True)
    for a in ANLEITUNGEN:
        html = c.get(f"/anleitung/{a.id}").get_data(as_text=True)
        assert a.titel.replace("&", "&amp;") in html
    assert c.get("/anleitung/gibtsnicht").status_code == 404


def test_cookie_banner_modi(tmp_path):
    # aus: kein Banner, keine Einstellungs-Verlinkung
    c = _app(tmp_path, COOKIE_BANNER="aus").test_client()
    html = c.get("/").get_data(as_text=True)
    assert "cookie-banner" not in html and "Cookie-Einstellungen" not in html
    # hinweis: Banner mit einem Knopf, verschwindet nach "Verstanden"
    c = _app(tmp_path, COOKIE_BANNER="hinweis").test_client()
    html = c.get("/").get_data(as_text=True)
    assert "cookie-banner" in html and "Verstanden" in html and "Alle akzeptieren" not in html
    c.post("/cookies", data={"_csrf": _csrf(c), "wahl": "notwendig"})
    assert "cookie-banner" not in c.get("/").get_data(as_text=True)
    # einwilligung: gleichwertige Knöpfe, optionale Dienste nur nach Zustimmung, Widerruf möglich
    app = _app(tmp_path, COOKIE_BANNER="einwilligung")
    import pathlib
    vorlage = pathlib.Path(app.root_path) / "templates" / "optionale_dienste.html"
    original = vorlage.read_text()
    vorlage.write_text("<!--OPTIONAL-GELADEN-->")
    try:
        c = app.test_client()
        html = c.get("/").get_data(as_text=True)
        assert "Nur notwendige" in html and "Alle akzeptieren" in html and "OPTIONAL-GELADEN" not in html
        token = _csrf(c)
        c.post("/cookies", data={"_csrf": token, "wahl": "alle"})
        assert "OPTIONAL-GELADEN" in c.get("/").get_data(as_text=True)
        c.post("/cookies", data={"_csrf": token, "wahl": "notwendig"})           # Widerruf
        assert "OPTIONAL-GELADEN" not in c.get("/").get_data(as_text=True)
    finally:
        vorlage.write_text(original)


def test_inaktive_konten_werden_geloescht(tmp_path):
    import sqlite3
    from web import konten
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=True)
    c = app.test_client()
    _registrieren(c, "schlaefer")
    _hochladen(c, ["a"], ["b"])
    conn = sqlite3.connect(tmp_path / "web.sqlite3")
    conn.execute("UPDATE konten SET letzter_login = '2000-01-01T00:00:00'")
    conn.commit()
    assert konten.inaktive_konten_loeschen(conn, 365) == 1
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0
    assert konten.inaktive_konten_loeschen(conn, 0) == 0


def test_import_erkennung_und_kommentar_modus(tmp_path):
    from test_core import _gemischtes_zip
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=False, AUTO_CHECK_AKTIVIERT=False)
    a, b = app.test_client(), app.test_client()
    token = _csrf(a)
    r = a.post("/laden", data={"_csrf": token, "zip_datei": (io.BytesIO(_gemischtes_zip()), "export.zip")},
               content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("/import")
    html = a.get("/import").get_data(as_text=True)
    assert "Kommentare" in html and "Likes" in html and "Follower" in html
    # Kommentar-Übersicht + Anleitungslink funktioniert
    html = a.get("/aktivitaet/kommentare").get_data(as_text=True)
    assert "kritisch" in html.lower()
    assert a.get("/anleitung/kommentare-likes").status_code == 200
    assert a.get("/aktivitaet/unsinn").status_code == 404
    # Durchgang: nur der heikle Kommentar, mit Begründung
    a.post("/aktivitaet/kommentare/start", data={"_csrf": token, "filter": "riskant"})
    html = a.get("/aktivitaet/kommentare/durchgang").get_data(as_text=True)
    assert "Idiot" in html and "Löschen empfohlen" in html and "😍" not in html
    kid = re.search(r'name="id" value="([^"]+)"', html).group(1)
    a.post("/aktivitaet/kommentare/entscheiden", data={"_csrf": token, "id": kid, "entscheidung": "entfernen"})
    assert a.get("/aktivitaet/kommentare/durchgang").status_code == 302          # fertig -> Liste
    assert "Idiot" in a.get("/aktivitaet/kommentare/liste").get_data(as_text=True)
    bericht = a.get("/aktivitaet/kommentare/export").get_data(as_text=True)
    assert "Idiot" in bericht and "your_activity/interactions/comments" in bericht
    # anderer Besucher sieht nichts
    assert "Idiot" not in b.get("/aktivitaet/kommentare/liste").get_data(as_text=True)
    # Likes: nur ein Account
    a.post("/aktivitaet/likes/start", data={"_csrf": token, "account": "dora"})
    html = a.get("/aktivitaet/likes/durchgang").get_data(as_text=True)
    assert "dora" in html and "/p/X2/" in html
    # Leeren
    a.post("/aktivitaet/kommentare/leeren", data={"_csrf": token})
    assert "Idiot" not in a.get("/aktivitaet/kommentare/export").get_data(as_text=True)


def test_email_bestaetigung_und_passwort_vergessen(tmp_path):
    app = _app(tmp_path, ACCOUNTS_AKTIVIERT=True, AUTO_CHECK_AKTIVIERT=False, NEWSLETTER_ABFRAGEN=True)
    c = app.test_client()
    postausgang = app.config["MAIL_POSTAUSGANG"]
    token = _csrf(c, "/registrieren")
    daten = {"_csrf": token, "benutzername": "neu", "email": " Neu@Example.org ", "passwort": "geheim123",
             "passwort2": "geheim123", "zustimmung": "1", "newsletter": "1"}
    # ohne E-Mail geht es nicht
    r = c.post("/registrieren", data={**daten, "email": ""})
    assert "gültige E-Mail" in r.get_data(as_text=True) and not postausgang
    r = c.post("/registrieren", data=daten)
    assert "Postfach" in r.get_data(as_text=True) and postausgang[-1]["an"] == "neu@example.org"
    # vor der Bestätigung: kein Login
    r = c.post("/anmelden", data={"_csrf": token, "benutzername": "neu", "passwort": "geheim123"})
    assert "noch nicht bestätigt" in r.get_data(as_text=True)
    assert c.get("/konto").status_code == 302
    # gefälschter Link -> ungültig
    assert c.get("/bestaetigen/unsinn").status_code == 400
    link = _letzter_link(c, "/bestaetigen/")
    assert c.get(link).status_code == 302
    html = c.get("/konto").get_data(as_text=True)
    assert "neu@example.org" in html and "bestätigt" in html and "eingewilligt am" in html
    assert c.get(link).status_code == 302 and "bereits bestätigt" in c.get("/anmelden").get_data(as_text=True)
    # zweite Registrierung mit gleicher Adresse: gleiche Antwort, Info-Mail an Inhaber, kein neues Konto
    c2 = app.test_client()
    t2 = _csrf(c2, "/registrieren")
    r = c2.post("/registrieren", data={**daten, "_csrf": t2, "benutzername": "anderer", "email": "NEU@example.org"})
    assert "Postfach" in r.get_data(as_text=True) and "bereits ein Konto" in postausgang[-1]["betreff"]
    # Login per E-Mail
    c.post("/abmelden", data={"_csrf": _csrf(c)})
    token = _csrf(c, "/anmelden")
    r = c.post("/anmelden", data={"_csrf": token, "benutzername": "neu@example.org", "passwort": "geheim123"})
    assert r.status_code == 302
    c.post("/abmelden", data={"_csrf": _csrf(c)})
    # Passwort vergessen: Antwort verrät nichts, Link funktioniert genau einmal
    token = _csrf(c, "/passwort-vergessen")
    anzahl = len(postausgang)
    r = c.post("/passwort-vergessen", data={"_csrf": token, "eingabe": "gibtsnicht@example.org"})
    assert "Postfach" in r.get_data(as_text=True) and len(postausgang) == anzahl
    c.post("/passwort-vergessen", data={"_csrf": token, "eingabe": "neu"})
    link = _letzter_link(c, "/passwort-neu/")
    r = c.post(link, data={"_csrf": token, "neu": "anders12345", "neu2": "anders12345"})
    assert r.status_code == 302
    assert c.get(link).status_code == 400                                  # schon benutzt
    c.post("/abmelden", data={"_csrf": _csrf(c)})
    token = _csrf(c, "/anmelden")
    assert c.post("/anmelden", data={"_csrf": token, "benutzername": "neu", "passwort": "anders12345"}).status_code == 302
    # E-Mail ändern: erst nach Bestätigung übernommen
    token = _csrf(c, "/konto")
    c.post("/konto", data={"_csrf": token, "aktion": "email", "email": "zweite@example.org", "passwort": "anders12345"})
    assert "wartet auf Bestätigung" in c.get("/konto").get_data(as_text=True)
    c.get(_letzter_link(c, "/bestaetigen/"))
    html = c.get("/konto").get_data(as_text=True)
    assert "zweite@example.org" in html and "wartet" not in html
    # Newsletter abbestellen
    c.post("/konto", data={"_csrf": token, "aktion": "newsletter"})
    assert "eingewilligt am" not in c.get("/konto").get_data(as_text=True)


def test_unbestaetigte_konten_werden_geloescht_und_alte_konten_bleiben(tmp_path):
    import sqlite3
    from web import konten
    conn = sqlite3.connect(tmp_path / "k.sqlite3")
    conn.execute("CREATE TABLE konten (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzername TEXT NOT NULL UNIQUE "
                 "COLLATE NOCASE, passwort_hash TEXT NOT NULL, erstellt_am TEXT NOT NULL)")
    conn.execute("INSERT INTO konten (benutzername, passwort_hash, erstellt_am) VALUES ('alt', 'x', '2020-01-01T00:00:00')")
    conn.commit()
    from core import history_store
    history_store.init_db(tmp_path / "k.sqlite3").close()
    konten.init_konten(conn)
    assert konten.ist_freigeschaltet(conn, 1)                       # Altkonto ohne E-Mail bleibt nutzbar
    kid = konten.registrieren(conn, "offen", "geheim123", "geheim123", email="o@example.org",
                              email_pflicht=True, freigeschaltet=False)
    conn.execute("UPDATE konten SET erstellt_am = '2020-01-01T00:00:00' WHERE id = ?", (kid,))
    assert konten.unbestaetigte_konten_loeschen(conn, 48) == 1
    assert konten.konto_info(conn, 1) and konten.konto_info(conn, kid) is None
