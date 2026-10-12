"""Tests für den Tresor-Modus (Server = reiner, verschlüsselter Speicher)."""

import json
import re

import pytest

from test_web import _csrf, _letzter_link

# Sieht aus wie ein echter, im Browser verschlüsselter Block (Salt 16 B, IV 12 B als Base64url)
BLOCK = "FA1." + "A" * 22 + "." + "B" * 16 + "." + "C" * 64
BLOCK2 = "FA1." + "A" * 22 + "." + "D" * 16 + "." + "E" * 80


def _app(tmp_path, **cfg):
    from web.app import create_app
    cfg.setdefault("BETRIEBSMODUS", "tresor")
    app = create_app(DATENBANK_PFAD=tmp_path / "web.sqlite3", SECRET_KEY="x", **cfg)
    app.config["TESTING"] = True
    return app


def _registrieren(c, name="tester", avv=True, nutzung="privat"):
    token = _csrf(c, "/registrieren")
    daten = {"_csrf": token, "benutzername": name, "email": f"{name}@example.org", "passwort": "geheim123",
             "passwort2": "geheim123", "zustimmung": "1"}
    if avv:
        daten["avv"] = "1"
    if nutzung:
        daten["nutzung"] = nutzung
    r = c.post("/registrieren", data=daten)
    if not avv or not nutzung:
        return r
    assert "Postfach" in r.get_data(as_text=True), r.get_data(as_text=True)
    assert c.get(_letzter_link(c, "/bestaetigen/")).status_code == 302
    return r


def _api(c, methode, token, **json_daten):
    return c.open("/api/tresor", method=methode, json=json_daten or None, headers={"X-CSRF-Token": token})


def _token(c):
    html = c.get("/").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_startseite_ist_browser_app_und_server_wertet_nichts_aus(tmp_path):
    c = _app(tmp_path).test_client()
    r = c.get("/")
    html = r.get_data(as_text=True)
    assert 'id="app"' in html and "tresor/app.js" in html
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    # Alle Routen, in denen der Server Listen lesen würde, sind weg
    for pfad in ("/ergebnis/1", "/verlauf", "/editor", "/listen", "/entfolgen/1", "/aktivitaet/kommentare"):
        assert c.get(pfad).status_code == 404, pfad
    assert c.post("/laden", data={}).status_code == 404
    # Die Browser-App selbst wird ausgeliefert
    for datei in ("app.js", "krypto.js", "zip.js", "parser.js", "auswertung.js", "speicher.js"):
        assert c.get(f"/static/tresor/{datei}").status_code == 200, datei


def test_api_nur_mit_anmeldung_und_csrf(tmp_path):
    c = _app(tmp_path).test_client()
    token = _token(c)
    assert _api(c, "GET", token).status_code == 401
    assert _api(c, "PUT", token, inhalt=BLOCK, basis_version=0).status_code == 401
    _registrieren(c)
    assert c.put("/api/tresor", json={"inhalt": BLOCK, "basis_version": 0}).status_code == 400   # ohne CSRF-Header


def test_registrierung_verlangt_avv_und_nutzungsart(tmp_path):
    c = _app(tmp_path).test_client()
    assert "Auftragsverarbeitungsvertrag" in _registrieren(c, "ohneavv", avv=False).get_data(as_text=True)
    assert "privat oder geschäftlich" in _registrieren(c, "ohnenutzung", nutzung=None).get_data(as_text=True)
    _registrieren(c, "mitavv", nutzung="geschaeftlich")
    from web import konten
    import sqlite3
    conn = sqlite3.connect(tmp_path / "web.sqlite3")
    nutzung, version, am = conn.execute("SELECT nutzung, avv_version, avv_akzeptiert_am FROM konten "
                                        "WHERE benutzername = 'mitavv'").fetchone()
    assert nutzung == konten.NUTZUNG_GESCHAEFTLICH and version and am
    assert conn.execute("SELECT COUNT(*) FROM konten WHERE benutzername LIKE 'ohne%'").fetchone()[0] == 0


def test_tresor_speichern_laden_konflikt_und_formatpruefung(tmp_path):
    c = _app(tmp_path).test_client()
    _registrieren(c)
    token = _token(c)

    r = _api(c, "GET", token)
    assert r.status_code == 200 and r.json["vorhanden"] is False and r.json["version"] == 0
    assert r.headers["Cache-Control"] == "no-store"

    # Klartext wird abgelehnt – der Server soll nie lesbare Listen speichern
    for falsch in ('{"follower": ["anna"]}', "anna\nben", "FA1.kurz", BLOCK + " "):
        r = _api(c, "PUT", token, inhalt=falsch, basis_version=0)
        assert r.status_code == 400 and r.json["grund"] == "format", falsch

    r = _api(c, "PUT", token, inhalt=BLOCK, basis_version=0)
    assert r.status_code == 200 and r.json["version"] == 1
    r = _api(c, "GET", token)
    assert r.json["inhalt"] == BLOCK and r.json["version"] == 1

    # Zweiter Tab speichert auf Basis einer alten Version -> Konflikt statt Überschreiben
    r = _api(c, "PUT", token, inhalt=BLOCK2, basis_version=0)
    assert r.status_code == 409 and r.json["version"] == 1
    assert _api(c, "PUT", token, inhalt=BLOCK2, basis_version=1).json["version"] == 2

    # Zu groß
    app2 = _app(tmp_path / "zwei", TRESOR_MAX_KB=1)
    c2 = app2.test_client()
    _registrieren(c2)
    r = _api(c2, "PUT", _token(c2), inhalt=BLOCK + "C" * 2000, basis_version=0)
    assert r.status_code == 400 and "zu groß" in r.json["fehler"]


def test_konten_sehen_nur_eigenen_tresor_und_loeschen(tmp_path):
    app = _app(tmp_path)
    a, b = app.test_client(), app.test_client()
    _registrieren(a, "anna")
    _registrieren(b, "ben")
    _api(a, "PUT", _token(a), inhalt=BLOCK, basis_version=0)
    assert _api(b, "GET", _token(b)).json["vorhanden"] is False

    # Datenexport enthält den (verschlüsselten) Tresor
    export = json.loads(a.get("/konto/export").get_data(as_text=True))
    assert export["tresor_verschluesselt"]["inhalt"] == BLOCK

    assert _api(a, "DELETE", _token(a)).json["geloescht"] is True
    assert _api(a, "GET", _token(a)).json["vorhanden"] is False

    # Konto löschen nimmt den Tresor mit
    _api(b, "PUT", _token(b), inhalt=BLOCK, basis_version=0)
    token = _csrf(b, "/konto")
    b.post("/konto/loeschen", data={"_csrf": token, "passwort": "geheim123"})
    import sqlite3
    assert sqlite3.connect(tmp_path / "web.sqlite3").execute("SELECT COUNT(*) FROM tresore").fetchone()[0] == 0


def test_alte_konten_muessen_avv_nachtraeglich_zustimmen(tmp_path):
    # Konto aus dem klassischen Modus (ohne AVV) …
    from test_web import _app as klassisch, _registrieren as alt_registrieren
    alt_registrieren(klassisch(tmp_path).test_client(), "altnutzer")
    # … meldet sich im Tresor-Modus an
    c = _app(tmp_path).test_client()
    token = _csrf(c, "/anmelden")
    c.post("/anmelden", data={"_csrf": token, "benutzername": "altnutzer", "passwort": "geheim123"})
    token = _token(c)
    r = _api(c, "GET", token)
    assert r.status_code == 200 and r.json["avv_aktuell"] is False      # lesen/löschen geht immer
    r = _api(c, "PUT", token, inhalt=BLOCK, basis_version=0)
    assert r.status_code == 403 and r.json["grund"] == "avv"

    assert "Zustimmen" in c.get("/avv").get_data(as_text=True)
    c.post("/avv", data={"_csrf": _csrf(c, "/avv"), "avv": "1", "nutzung": "privat"})
    assert _api(c, "PUT", token, inhalt=BLOCK, basis_version=0).status_code == 200
    html = c.get("/konto").get_data(as_text=True)
    assert "zugestimmt am" in html and "privat" in html


def test_neue_avv_fassung_verlangt_neue_zustimmung(tmp_path):
    c = _app(tmp_path, AVV_VERSION="v1").test_client()
    _registrieren(c)
    c2 = _app(tmp_path, AVV_VERSION="v2").test_client()
    token = _csrf(c2, "/anmelden")
    c2.post("/anmelden", data={"_csrf": token, "benutzername": "tester", "passwort": "geheim123"})
    assert _api(c2, "PUT", _token(c2), inhalt=BLOCK, basis_version=0).status_code == 403


def test_datenschutz_und_avv_seite_beschreiben_tresor(tmp_path):
    c = _app(tmp_path).test_client()
    html = c.get("/datenschutz").get_data(as_text=True)
    assert "nicht hochgeladen" in html and "Auftragsverarbeitung" in html
    html = c.get("/avv").get_data(as_text=True)
    assert "Art. 28" in html and "AES-256-GCM" in html


@pytest.mark.parametrize("modus", ["tresor", "klassisch"])
def test_auto_check_nur_im_klassischen_modus(tmp_path, modus):
    app = _app(tmp_path, BETRIEBSMODUS=modus, AUTO_CHECK_AKTIVIERT=True)
    assert app.config["APP_EINSTELLUNGEN"]["AUTO_CHECK_AKTIVIERT"] is (modus == "klassisch")
