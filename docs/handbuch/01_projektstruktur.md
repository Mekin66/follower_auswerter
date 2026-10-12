# 1. Projektstruktur und Ordnerbaum

## 1.1 Die Grundidee in einem Satz

**Alle Logik steht in `core/`, jede Oberfläche (Desktop, Web, Handy) ist nur eine dünne Hülle
darum.** Seit dem Tresor-Modus gibt es eine Ausnahme: Die Web-Auswertung läuft im Browser und
ist deshalb in JavaScript (`web/static/tresor/`) noch einmal umgesetzt – als 1:1-Port der
Python-Funktionen, abgesichert durch einen Test, der beide Ergebnisse vergleicht.

## 1.2 Ordnerbaum

```
follower_auswerter/
├── main.py                     Startpunkt Desktop-App (Tkinter): python main.py
├── README.md                   Kurzbeschreibung, Neuerungen je Version
├── Dockerfile                  Container für die Web-App (gunicorn)
├── render.yaml                 "Blueprint" für Render.com (Hosting per Klick)
├── .gitignore / .dockerignore  Was nicht ins Git bzw. ins Docker-Image kommt
│
├── core/                       ★ Gemeinsame Logik – KEIN GUI-Code, kein Flask
│   ├── models.py               Datenklassen + Enums: Snapshot, Aenderung, Entscheidung, PersonenListe
│   ├── parser.py               Instagram-JSON → {name: datum}; Nutzernamen normalisieren
│   ├── instagram_export.py     Generischer Leser für Instagram-JSON/HTML (auch Kommentare, Likes)
│   ├── archive_reader.py       ZIP öffnen, Instagram/TikTok erkennen → ArchivInhalt
│   ├── tiktok_parser.py        TikTok-Export (JSON/TXT)
│   ├── txt_format.py           Eigenes TXT-Listenformat lesen/schreiben
│   ├── plattform.py            Instagram/TikTok, "Bereich" (Datentrennung), Profil-URLs
│   ├── diff_engine.py          Zwei Snapshots vergleichen, Blockier-Verdacht
│   ├── freunde.py              Freunde = gegenseitig + manuell
│   ├── removal_session.py      Entfolgen-Modus (Ablauf, Kategorien, Zurück)
│   ├── konto_pruefer.py        "Scheint deaktiviert"-Prüfung per HTTP (nur lokal/klassisch)
│   ├── instagram_checker.py    Altes Modul, leitet auf konto_pruefer um
│   ├── kommentar_bewertung.py  Einstufung von Kommentaren (nutzt das Netz, liefert Gründe)
│   ├── kommentar_netz.py       ★ Neuronales Netz in reinem Python: Merkmale, Training, Erklärung
│   ├── daten/
│   │   ├── kommentar_beispiele.tsv   ★ Trainingsbeispiele (UTF-8, klasse<TAB>text)
│   │   └── kommentar_netz.json       ★ trainierte Gewichte (UTF-8-JSON)
│   ├── aktivitaet.py           Kommentar-/Like-Modus (Ablauf)
│   ├── export.py               TXT/CSV-Berichte
│   ├── anleitungen.py          Hilfetexte für alle drei Oberflächen
│   ├── config.py               Liste der Datenkategorien (Erweiterungspunkt)
│   └── history_store.py        SQLite: Tabellen anlegen, migrieren, lesen, schreiben
│
├── gui/                        Desktop-Oberfläche (Tkinter) – ein Fenster pro Datei
│   ├── main_window.py          Hauptfenster
│   ├── removal_view.py, history_view.py, listen_view.py, freunde_view.py,
│   ├── editor_view.py, aktivitaet_view.py, hilfe_view.py
│   ├── theme.py                Farben, Button-Stile, Mausrad-Scrollen
│   └── logo.png
│
├── web/                        Web-Version (Flask)
│   ├── app.py                  App-Factory create_app(), alle Routen
│   ├── einstellungen.py        ★ Alle Schalter (BETRIEBSMODUS, ACCOUNTS_AKTIVIERT, SMTP, …)
│   ├── konten.py               Registrierung, Login, E-Mail-Bestätigung, AVV-Zustimmung
│   ├── tresor.py               ★ Verschlüsselten Tresor speichern/laden (Server-Seite)
│   ├── mail.py                 E-Mail-Versand (SMTP) + Mail-Texte
│   ├── verwaltung.py           Konsolen-Befehle für den Betreiber
│   ├── requirements.txt        Flask, gunicorn
│   ├── templates/              Jinja2-HTML-Vorlagen
│   │   ├── basis.html          Grundgerüst (Navigation, Fußzeile, Cookie-Banner)
│   │   ├── tresor.html         ★ Gerüst der Browser-App (Tresor-Modus)
│   │   ├── avv.html            ★ Auftragsverarbeitungsvertrag + Zustimmung
│   │   ├── datenschutz.html, impressum.html, cookies.html
│   │   ├── konto*.html         Login, Registrierung, Konto-Seite, Hinweise
│   │   └── index.html, ergebnis.html, verlauf.html, … (nur Modus "klassisch")
│   └── static/
│       ├── style.css, logo*.png/svg
│       └── tresor/             ★ Browser-App (JavaScript-Module)
│           ├── app.js          Oberfläche (Ansichten Laden/Ergebnis/Verlauf/Entfolgen/Listen/Tresor)
│           ├── auswertung.js   Datenmodell + Logik (Port von diff_engine, freunde, removal_session)
│           ├── parser.js       Export-Leser (Port von parser, txt_format, tiktok_parser, archive_reader)
│           ├── zip.js          ZIP-Leser ohne Bibliothek
│           ├── netz.js         ★ Kommentar-Netz im Browser (Port von core/kommentar_netz.py)
│           ├── aktivitaet.js   ★ Kommentar-/Like-Modus (Port von core/aktivitaet.py)
│           ├── krypto.js       PBKDF2 + AES-256-GCM
│           └── speicher.js     Kommunikation mit /api/tresor
│
├── mobile/                     Handy-App (Kivy) → Android über buildozer
│   ├── main.py, instagramauswerter.kv, buildozer.spec, requirements.txt
│
├── packaging/                  Bauen & Ausliefern
│   ├── build_exe.spec          PyInstaller → Windows-.exe
│   ├── build_android.sh        Android-Build
│   └── server/                 docker-compose.yml, Caddyfile (HTTPS), .env.beispiel
│
├── tests/                      pytest (+ Node für die JS-Tests)
│   ├── conftest.py             Test-Hilfen (Export-ZIP erzeugen, DB-Fixture)
│   ├── test_core.py            Logik
│   ├── test_web.py             Web, Modus "klassisch"
│   ├── test_tresor.py          Web, Modus "tresor"
│   ├── test_js.py              startet tests/js/*.mjs und vergleicht JS- mit Python-Parser
│   └── js/tresor.test.mjs
│
├── assets/                     Logo in allen Größen
└── docs/
    ├── ARCHITEKTUR.md          Entwicklungsgeschichte, Entscheidungen je Version
    ├── VEROEFFENTLICHEN.md     Stores, Hosting, DSGVO-Checkliste
    └── handbuch/               ★ dieses Handbuch
```

★ = für den Tresor-Modus neu oder wesentlich.

## 1.3 Datenfluss – welcher Weg für welche Oberfläche?

```
                 ┌───────────── core/ (Python) ─────────────┐
 Desktop  ──────►│ archive_reader → parser → history_store  │──► ~/.instagram_auswerter/verlauf.sqlite3
 Mobile   ──────►│ diff_engine, removal_session, freunde    │──► App-Datenordner (SQLite)
                 └──────────────────────────────────────────┘
 Web "klassisch" ►  dieselben core/-Module auf dem SERVER   ──► web/daten/web.sqlite3 (Klartext)

 Web "tresor"    ►  web/static/tresor/*.js im BROWSER        ──► /api/tresor ──► Tabelle tresore (verschlüsselt)
```

## 1.4 Konventionen im Code

- **Deutsche Namen** für eigene Funktionen/Variablen (`snapshot_speichern`, `lade_export`),
  englische nur, wo Python/Flask sie vorgeben (`def __init__`, `@app.route`).
- **Typ-Hinweise** überall (`def laden(conn: sqlite3.Connection, konto_id: int) -> dict | None`).
- **Kein Import von GUI-Bibliotheken in `core/`** – sonst ließe sich der Kern nicht im Web/Handy nutzen.
- **Jede Zeile in der DB hat einen `besitzer`** (Modus klassisch) – alle Abfragen filtern danach.
- **Migrationen im Code:** `init_db()`/`init_konten()` ergänzen fehlende Spalten beim Start
  (siehe [Kapitel 3](03_datenbank.md)).
- **Jede neue Funktion bekommt einen Test** in `tests/`.

## 1.5 Starten (Kurzreferenz)

```bash
pip install -r web/requirements.txt pytest

python main.py                         # Desktop
python web/app.py                      # Web → http://localhost:5000 (Modus aus einstellungen.py)
BETRIEBSMODUS=klassisch python web/app.py
COOKIES_NUR_HTTPS=0 ACCOUNTS_AKTIVIERT=1 python web/app.py   # lokal mit Konten (Mails im Log)
python -m pytest tests                 # alle Tests (JS-Tests nur mit Node.js ≥ 20)
```

> Lokal über `http://` muss `COOKIES_NUR_HTTPS=0` gesetzt sein, sonst schickt der Browser das
> Sitzungs-Cookie nicht zurück und Login/Formulare schlagen fehl.
