# Lektion 12 – Testen und das Projekt erweitern

**Lernziele:** pytest sicher bedienen (Fixtures, `tmp_path`, `monkeypatch`, `parametrize`),
Tests für neue Funktionen schreiben, und mit einem Abschlussprojekt alles Gelernte anwenden.

## 12.1 pytest-Grundlagen

```bash
python -m pytest tests                 # alle
python -m pytest tests/test_tresor.py  # eine Datei
python -m pytest -k avv                # nur Tests mit "avv" im Namen
python -m pytest -x                    # beim ersten Fehler stoppen
python -m pytest -q                    # kurze Ausgabe
python -m pytest --lf                  # nur die zuletzt fehlgeschlagenen
```

Ein Test ist eine Funktion `test_…` mit `assert`:

```python
from core.parser import normalisiere_username

def test_normalisieren():
    assert normalisiere_username(" @Anna.M ") == "anna.m"
    assert normalisiere_username("https://www.tiktok.com/@carl") == "carl"
```

Ausnahmen erwarten:

```python
import pytest
from web import tresor

def test_klartext_wird_abgelehnt():
    with pytest.raises(tresor.TresorFehler):
        tresor.pruefen('{"follower": ["anna"]}', 8192)
```

## 12.2 Fixtures

Fixtures stellen Testzutaten bereit; pytest übergibt sie anhand des **Parameternamens**:

```python
# tests/conftest.py – gilt für alle Tests im Ordner
@pytest.fixture
def conn(tmp_path):                                   # tmp_path: eingebaute Fixture, frischer Ordner pro Test
    c = history_store.init_db(tmp_path / "t.sqlite3")
    yield c                                           # Test läuft hier
    c.close()                                         # danach aufräumen

# im Test
def test_snapshot(conn):
    sid = history_store.snapshot_speichern(conn, {"a": "-"}, {"b": "-"})
    assert history_store.snapshot_laden(conn, sid).following == {"b": "-"}
```

Weitere eingebaute Fixtures: `monkeypatch`, `capsys` (Ausgaben abfangen), `tmp_path`.

## 12.3 `monkeypatch` – Teile ersetzen

```python
def test_auto_pruefung(tmp_path, monkeypatch):
    import web.app as webapp
    monkeypatch.setattr(webapp, "pruefe_mehrere",
        lambda namen, pause, abbrechen=None, plattform=None: iter(
            [PruefErgebnis(n, AccountStatus.NICHT_ERREICHBAR if n == "c" else AccountStatus.AKTIV) for n in namen]))
    ...
```

Statt Instagram abzufragen, liefert die Attrappe feste Ergebnisse. Nach dem Test stellt
`monkeypatch` das Original automatisch wieder her. Auch nützlich:
`monkeypatch.setenv("BETRIEBSMODUS", "klassisch")`.

## 12.4 `parametrize` – ein Test, viele Fälle

```python
@pytest.mark.parametrize("eingabe, erwartet", [
    ("anna", "anna"),
    ("@Anna", "anna"),
    ("https://instagram.com/_u/anna/", "anna"),
    ("", ""),
])
def test_namen(eingabe, erwartet):
    assert normalisiere_username(eingabe) == erwartet
```

## 12.5 Gute Tests im Projekt – Muster

- **Eine App pro Test** mit eigener DB (`_app(tmp_path, …)` in `test_web.py`/`test_tresor.py`).
- **Ganze Abläufe** testen (registrieren → bestätigen → speichern → Konflikt → löschen), nicht nur Einzelfunktionen.
- **Sicherheitseigenschaften** als Tests festhalten: „Klartext wird abgelehnt“, „anderes Konto sieht nichts“,
  „klassische Routen sind im Tresor-Modus 404“. So fällt es sofort auf, wenn eine Änderung sie bricht.
- **Zwei Implementierungen vergleichen**: `test_js.py` lässt Python und JavaScript denselben Export lesen.

## 12.6 Arbeitsablauf für jede Erweiterung

1. Kurz aufschreiben, *was* die Funktion tun soll und *wo* sie hingehört (`core/`? `web/`? JS?).
2. Test schreiben, der jetzt fehlschlägt.
3. Umsetzen, bis der Test grün ist.
4. Alle Tests laufen lassen.
5. Doku ergänzen (Docstring, ggf. Handbuch, Datenschutz/AVV bei neuen Daten).
6. Commit mit verständlicher Nachricht.

---

## 12.7 Abschlussprojekte

Jeweils mit Ziel, Hinweisen und Lösungsskizze. Schwierigkeit: ★ leicht bis ★★★ anspruchsvoll.

### A ★ – Statistik-Befehl für den Betreiber

`python -m web.verwaltung statistik` zeigt: Konten gesamt, privat/geschäftlich/unbekannt,
Tresore, Gesamtgröße, Konten ohne aktuelle AVV-Zustimmung.
*Hinweise:* Lektion 9 (GROUP BY), 10 (argparse). Test mit `capsys`.

### B ★ – Python-Werkzeug: Tresor-Sicherung öffnen

Ein Skript, das eine `.fatresor`-Datei (aus „Tresor → Sicherung herunterladen“) mit dem Passwort
entschlüsselt und als JSON ausgibt. Nützlich, falls jemand seine Daten ohne Browser braucht.
*Hinweise:* Lektion 8 (Base64, gzip, json), 11 (PBKDF2, AES-GCM). Paket `cryptography`.

<details><summary>Lösung (getestet mit einem Block aus der Browser-App)</summary>

```python
"""Öffnet einen Tresor-Block (oder eine .fatresor-Sicherung) in Python.
Aufruf: python tresor_oeffnen.py meine_sicherung.fatresor"""
import base64, getpass, gzip, hashlib, json, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def b64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def oeffnen(block: str, passwort: str) -> dict:
    praefix, salt, iv, geheim = block.strip().split(".")
    if praefix != "FA1":
        raise ValueError("Kein Tresor-Block")
    schluessel = hashlib.pbkdf2_hmac("sha256", passwort.encode(), b64url(salt), 600_000, dklen=32)
    klar = AESGCM(schluessel).decrypt(b64url(iv), b64url(geheim), b"FA1")   # InvalidTag bei falschem Passwort
    return json.loads(gzip.decompress(klar))

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as datei:
        daten = oeffnen(datei.read(), getpass.getpass("Tresor-Passwort: "))
    print(json.dumps(daten, ensure_ascii=False, indent=2))
```
</details>

### C ★★ – Neue Liste „Stummgeschaltet“

Eine vierte Personenliste. Im **Tresor-Modus** nur JavaScript: `LISTEN` in `auswertung.js`
ergänzen, `normalisieren()` ergänzt sie bei alten Tresoren automatisch (die Schleife über
`Object.keys(LISTEN)`), Test in `tests/js/tresor.test.mjs`. Im **klassischen Modus/Desktop**:
`PersonenListe` in `core/models.py` + `LISTEN_TEXTE`, und – Achtung – der `CHECK`-Constraint der
Tabelle `personen_listen` erlaubt nur die drei alten Werte. SQLite kann `CHECK` nicht per
`ALTER TABLE` ändern: Tabelle neu anlegen, Daten kopieren, alte löschen, umbenennen (als
Einmal-Migration mit `schema_info`, Kapitel 3.6 Muster C).

### D ★★ – Verlauf als Diagramm

Im Tresor-Modus unter „Verlauf“ eine Linie „Follower-Anzahl über die Zeit“. Ohne fremde
Bibliothek als `<svg>` mit `<polyline>` in `app.js` bauen (CSP erlaubt keine CDNs).
Datenquelle: `A.sortiert(bereich()).reverse().map(s => [s.erstellt_am, Object.keys(s.follower).length])`.

### E ★★ – „Neu seit letztem Mal“ direkt im Ergebnis

Nach dem Laden eines Exports automatisch mit dem vorherigen vergleichen und oben anzeigen:
„+3 neue Follower, −2 entfolgt“. Logik: `A.vergleichen(vorletzter, neuester)`.
Python-Gegenstück für Desktop: `vergleiche_snapshots` in `gui/main_window.py::auswerten` aufrufen.

### F ★★★ – Eigene Entscheidungen dauerhaft lernen

Im Moment wird das Netz bei jedem Durchgang neu aus den eigenen Entscheidungen nachtrainiert
(`persoenliches_netz` in Python, `persoenlichesNetz` in `app.js`) und danach verworfen.
Speichere stattdessen nur die **Differenz** der Gewichte zum Standard-Netz (Desktop: in einer
Tabelle `netz_anpassung(besitzer, json)`; Tresor: als Feld im verschlüsselten Tresor) und lade sie
beim nächsten Mal. *Hinweise:* Lektion 13.8 (`angepasst`), Kapitel 3.6 (Tabelle anlegen).
Achte darauf, dass die Differenz klein bleibt (nur geänderte Zeilen von W1 speichern) und dass
ein neu trainiertes Standard-Netz alte Differenzen ungültig macht (Fingerabdruck mitspeichern).
*So wurde der Kommentar-Modus selbst in den Browser gebracht:* `web/static/tresor/netz.js`,
`aktivitaet.js` und der Paritätstest in `tests/test_js.py` sind ein gutes Vorbild für jeden Port
von Python nach JavaScript.

### G ★★★ – Mehrere Worker im Tresor-Modus

Im Tresor-Modus liegt kein Zustand mehr im Arbeitsspeicher – außer den Login-Fehlversuchen
(`fehlversuche`-dict). Verschiebe sie in eine SQLite-Tabelle
(`login_versuche(ip, zeitpunkt)`, alte Einträge beim Aufräumen löschen), dann kann gunicorn mit
`--workers 4` laufen. Test: zwei `create_app()`-Instanzen auf **derselben** DB-Datei – Fehlversuche
in App 1 müssen in App 2 zählen.

---

## 12.8 Wie geht es weiter?

- **Typprüfung:** `pip install mypy` → `mypy core web`
- **Formatierung/Linting:** `pip install ruff` → `ruff check .` und `ruff format .`
- **Automatische Tests bei jedem Push:** GitHub Actions mit `python -m pytest tests`
- **Lesen:** die Python-Doku zu `dataclasses`, `sqlite3`, `itertools`; Flask-Tutorial („Flaskr“);
  „Fluent Python“ (L. Ramalho) für die Tiefe.
