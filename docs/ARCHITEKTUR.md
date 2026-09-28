# Architektur – Instagram Follower Auswertung

Dieses Dokument erklärt, wie das Projekt aufgebaut ist und warum. Es wird
mit jedem neuen Feature erweitert.

## Grundidee: Trennung von Logik und Darstellung

```
instagram_auswerter/
├── core/                   # Alle Logik, KEIN Tkinter-Import erlaubt
│   ├── models.py           # Datenklassen (Account, Snapshot, Aenderung)
│   ├── parser.py           # Instagram-JSON -> {username: datum}
│   ├── config.py           # Welche Datenkategorien werden getrackt?
│   ├── history_store.py    # SQLite: Snapshots speichern & laden
│   └── diff_engine.py      # Zwei Snapshots vergleichen
├── gui/                    # Nur Darstellung, ruft core/ auf
│   ├── main_window.py      # Hauptfenster (laden, auswerten)
│   └── history_view.py     # Verlaufs-/Vergleichsfenster
├── docs/
│   └── ARCHITEKTUR.md       # dieses Dokument
└── main.py                  # Startpunkt: erstellt nur das Tk-Fenster
```

**Warum diese Trennung?** `core/` weiß nichts von Tkinter. Das bedeutet:
Wenn wir später (Punkt f) eine Web- oder Mobile-Oberfläche bauen, muss nur
ein neuer Ordner (z. B. `web/`) hinzukommen, der `core/` wiederverwendet.
Die komplette Parsing-, Speicher- und Vergleichslogik bleibt unverändert.

## Datenfluss

1. **Laden**: `gui/main_window.py` liest eine JSON-Datei ein und ruft
   `core/parser.py::extrahiere_daten()` auf. Ergebnis: `{username: "DD.MM.YYYY"}`.
2. **Auswerten**: Beim Klick auf "Auswerten" werden Follower/Following
   angezeigt UND automatisch als neuer **Snapshot** in der SQLite-Datenbank
   gespeichert (`core/history_store.py::snapshot_speichern()`).
3. **Verlauf ansehen**: Im Verlaufsfenster (`gui/history_view.py`) wählst
   du zwei gespeicherte Snapshots aus. `core/diff_engine.py::vergleiche_snapshots()`
   berechnet, wer zwischen diesen beiden Zeitpunkten neu dazugekommen bzw.
   weggefallen ist – getrennt nach Follower und Following.

## Die Datenbank

Standardmäßig liegt die Datenbank unter:

- Windows: `C:\Users\<Name>\.instagram_auswerter\verlauf.sqlite3`
- Linux/Mac: `~/.instagram_auswerter/verlauf.sqlite3`

Zwei Tabellen:

- `snapshots(id, erstellt_am, label)` – ein Eintrag pro Auswertung
- `eintraege(id, snapshot_id, username, liste, seit_datum)` – die einzelnen
  Accounts, die zu einem Snapshot gehören (liste = "follower" oder "following")

Das ist bewusst simpel gehalten: keine komplizierten Beziehungen, leicht
mit jedem SQLite-Tool (z. B. "DB Browser for SQLite") von Hand einsehbar,
falls du mal nachschauen willst, was gespeichert wurde.

## Erweiterbarkeit (Punkt d)

`core/config.py` enthält eine Liste `VERFUEGBARE_KATEGORIEN`. Aktuell sind
nur `follower` und `following` aktiv. Wenn später weitere Instagram-
Datenkategorien (personenbezogene Daten, Aktivitäten, ...) unterstützt
werden sollen, wird dort einfach ein neuer Eintrag mit `aktiv=True`
ergänzt, plus ein passender Parser (analog zu `parser.py`) und eine
Erweiterung von `Snapshot`, um die neue Kategorie mitzuspeichern.

## Entfolgen-Modus (Punkt c)

- `core/removal_session.py::ermittle_kandidaten()` bestimmt alle Accounts,
  denen ich folge, die mir aber nicht zurückfolgen.
- `RemovalSession` verwaltet den Ablauf: aktueller Kandidat, Fortschritt,
  Entscheidungen, "Zurück"-Funktion.
- `gui/removal_view.py::RemovalFenster` ist der eigentliche Wizard: pro
  Kandidat drei Buttons (Behalten / Entfernen / Scheint deaktiviert).
- Jede Entscheidung wird **sofort** in der Tabelle `workflow_entscheidungen`
  gespeichert (verknüpft mit dem Snapshot). Dadurch geht nichts verloren,
  wenn das Fenster zwischendurch geschlossen wird – beim nächsten Start des
  Entfolgen-Modus für denselben Snapshot wird automatisch dort weitergemacht,
  wo man aufgehört hat.
- Am Ende gibt es eine Zusammenfassung mit den drei Listen und einen
  Export als `.txt`-Datei.
- Wichtig: Das Programm entfolgt **niemandem automatisch** auf Instagram
  selbst – das würde eine Anmeldung + automatisierte Aktionen im eigenen
  Account erfordern, was gegen Instagrams Nutzungsbedingungen verstößt und
  Sperrungsrisiko birgt. Das Tool erstellt dir stattdessen die Liste, die
  du dann selbst manuell in der Instagram-App abarbeitest.

## ZIP-Import ohne Entpacken (Punkt h)

- `core/archive_reader.py::lade_aus_zip()` öffnet die vom Nutzer
  heruntergeladene Instagram-Export-ZIP-Datei direkt mit dem `zipfile`-
  Modul und sucht darin nach `.json`-Dateien unter
  `.../followers_and_following/...` – ganz ohne die Datei vorher auf die
  Festplatte zu entpacken.
- Es werden automatisch alle `followers_*.json`-Dateien (Instagram teilt
  große Follower-Listen auf mehrere Dateien auf) sowie `following.json`
  eingelesen und zusammengeführt.
- Im Hauptfenster gibt es dafür den Button "Alternativ: komplettes Archiv
  als ZIP laden" – als Alternative zu den beiden einzelnen JSON-Buttons.

## Deaktiviert-Checker (Punkt b)

- `core/instagram_checker.py::pruefe_account()` ruft die öffentliche
  Profilseite `https://www.instagram.com/<username>/` ab (kein Login) und
  wertet aus, ob die Seite existiert bzw. einen "nicht verfügbar"-Hinweis
  zeigt.
- `pruefe_mehrere()` ist ein Generator, der mehrere Accounts nacheinander
  mit Pause (Standard: 3 Sekunden) prüft, um das Risiko einer Rate-Limit-
  Sperre durch Instagram zu senken.
- Drei mögliche Ergebnisse: `AKTIV`, `NICHT_ERREICHBAR` (deaktiviert/
  gelöscht/falscher Name), `UNSICHER` (Netzwerkfehler, Rate-Limit – bewusst
  NICHT automatisch als "deaktiviert" gewertet, um Falsch-Positive zu
  vermeiden).
- Im Entfolgen-Modus (`gui/removal_view.py`) wird vor dem manuellen Wizard
  optional eine automatische Vorprüfung angeboten (läuft in einem
  Hintergrund-Thread, damit die Oberfläche währenddessen nicht einfriert).
  Automatisch als `NICHT_ERREICHBAR` erkannte Accounts werden direkt als
  "Scheint deaktiviert" gespeichert und tauchen im manuellen Wizard nicht
  mehr auf. Alles andere (aktiv oder unsicher) landet ganz normal in der
  manuellen Abfrage.
- **Grenzen, die man kennen sollte**: Diese Prüfung ist ein Hilfsmittel,
  keine Garantie. Instagram kann automatisierte Anfragen blockieren, das
  HTML-Format ändern, oder ein Profil kann z. B. auch bei privaten Konten
  ohne Login nicht vollständig einsehbar sein. Deswegen bleibt die
  manuelle Option "Scheint deaktiviert" im Wizard als Fallback bestehen.

## Drei GUI-Varianten (Punkt f)

Alle drei nutzen ausschließlich `core/` – keine der drei Oberflächen
enthält eigene Geschäftslogik, nur Darstellung.

```
instagram_auswerter/
├── core/            # gemeinsame Logik (unverändert von allen 3 genutzt)
├── gui/             # Variante 1: Desktop (Tkinter)
├── web/             # Variante 2: Web-App (Flask)
├── mobile/          # Variante 3: Mobile (Kivy)
└── packaging/       # Build-Anleitungen für alle drei
```

### Variante 1: Desktop (Tkinter) → .exe
Wie bisher. `packaging/build_exe.spec` + `pyinstaller` erzeugen daraus eine
einzelne .exe-Datei. Kein Server, keine Internetverbindung nötig.

### Variante 2: Web-App (Flask) → Basis für Google Play & App Store
`web/app.py` bildet dieselben Kernfunktionen als Webseite ab: Daten laden
(JSON oder ZIP), Auswertung ansehen, Verlauf vergleichen. Nutzt **dieselbe**
SQLite-Datenbank wie die Desktop-Version (`core/history_store`), Verlauf
ist also plattformübergreifend geteilt, wenn beide auf demselben Rechner
laufen. Getestet mit Flask's Test-Client (Upload, ZIP-Upload, Verlauf,
Vergleich – alles grün). Der Weg in die Stores führt darüber via
Capacitor/Bubblewrap, siehe `packaging/README.md`.

Aktuell **nicht** in der Web-Variante enthalten: der Entfolgen-Wizard und
der automatische Deaktiviert-Check waren zunächst offen – **sind inzwischen
ergänzt**, siehe Abschnitt "Entfolgen-Modus in Web & Mobile" unten.

### Variante 3: Mobile (Kivy) → Android/iOS
`mobile/main.py` + `mobile/instagramauswerter.kv` bilden Laden (JSON
einzeln oder ZIP) und Auswerten nativ mit Kivy-Widgets ab (Farbmarkierung
rot = kein Zurückfolgen, Speicherung im selben Verlauf). Getestet headless
unter Xvfb (virtuelles Display) – App baut sich auf, lädt Testdaten, wertet
aus, befüllt die Scroll-Listen korrekt.

Build nach Android: `buildozer.spec` liegt bereit (siehe
`packaging/README.md` für die genauen Schritte). iOS ist mit Kivy deutlich
aufwändiger (eigener Mac + Xcode nötig) – für iOS ist Weg 2 (Web-App)
meist der pragmatischere Weg in den Store.

Für Details zu Buildozer, Capacitor, Store-Voraussetzungen (Kosten, Review-
Prozess) siehe `packaging/README.md`.

## Entfolgen-Modus in Web & Mobile

Sowohl die Web- als auch die Mobile-Variante haben jetzt denselben
Entfolgen-Modus (c) inkl. automatischer Deaktiviert-Prüfung (b) wie die
Desktop-Version – alle drei nutzen dafür exakt dieselben `core/`-Module
(`removal_session.py`, `instagram_checker.py`), nur die Darstellung
unterscheidet sich je Plattform.

**Web (`web/app.py`)**: Die RemovalSession lebt pro Snapshot im
Arbeitsspeicher des Servers (`_removal_sessions`-Dictionary), Entscheidungen
werden aber sofort in die SQLite-DB geschrieben. Ablauf über eigene Routen:
`/entfolgen/<id>` (zeigt je nach Zustand Angebot/Wizard/Zusammenfassung),
`/entfolgen/<id>/automatisch` (führt die Prüfung synchron aus – bei sehr
vielen offenen Accounts kann das im Browser spürbar dauern, siehe Kommentar
im Code), `/entfolgen/<id>/entscheiden`, `/entfolgen/<id>/zurueck`,
`/entfolgen/<id>/export` (Download als .txt). Getestet mit dem Flask-
Testclient inkl. gemocktem Instagram-Check.

**Mobile (`mobile/main.py`)**: Aus der bisherigen Einzel-Screen-App wurde
eine App mit `ScreenManager` (zwei Screens: `haupt` und `entfolgen`).
`EntfolgenScreen` baut seinen Inhalt komplett dynamisch in Python auf
(genau wie das Tkinter-Pendant `gui/removal_view.py`) und führt die
automatische Prüfung in einem Hintergrund-Thread aus, der seine Ergebnisse
über `Clock.schedule_once()` sicher an den Hauptthread zurückmeldet (Kivy-
UI darf nicht direkt aus einem Fremd-Thread verändert werden). Getestet
unter Xvfb (virtuelles Display) mit gemocktem Instagram-Check – Screen-
Wechsel, automatische Erkennung, manueller Wizard und DB-Persistenz laufen
alle grün durch.

## Design (Punkt "professioneller wirken")

Alle drei Oberflächen teilen sich jetzt eine gemeinsame Design-Sprache
statt Standard-Grau bzw. Kivys Standard-Dunkelgrau:

- **Farbschema**: helle Karten (Weiß) auf hellgrauem Hintergrund
  (`#f0f2f5`), dunkle Kopfzeile mit orangem "Marken"-Schriftzug, klare
  Signalfarben (Blau = primäre Aktion, Grün = Behalten/Erfolg, Rot =
  Entfernen/Gefahr, Gelb/Orange = Achtung/Entfolgen-Modus).
- **Web** (`web/static/style.css`): Karten mit Schatten, abgerundete
  Pill-Buttons, kleine Farbkreis-"Avatare" vor jedem Usernamen, Fortschritts-
  balken im Entfolgen-Wizard.
- **Desktop** (`gui/theme.py`): ttk mit dem plattformunabhängigen
  "clam"-Theme, damit sich Farben zuverlässig überschreiben lassen (anders
  als bei den nativen Windows-/Mac-Themes). Definiert wiederverwendbare
  Styles (`Primaer.TButton`, `Erfolg.TButton`, `Gefahr.TButton`,
  `Warnung.TButton`, `Dezent.TButton`, `Karte.TFrame`, ...), die in
  `main_window.py`, `history_view.py` und `removal_view.py` genutzt werden.
- **Mobile** (`mobile/instagramauswerter.kv`): eigene Button-Templates
  (`PrimaerKnopf`, `ErfolgKnopf`, `GefahrKnopf`, `WarnungKnopf`,
  `DezentKnopf`) und ein `Karte`-Template mit `RoundedRectangle` im
  `canvas.before` für die weißen Kartenflächen, dazu `Window.clearcolor`-
  äquivalent über eine Hintergrund-`Rectangle` je Screen. Die dynamisch in
  Python gebauten Wizard-Widgets (`EntfolgenScreen`) nutzen dieselben
  Templates über `kivy.factory.Factory`, statt eigene Farben zu erfinden.
  Emojis wurden hier bewusst durch Text ersetzt, weil Kivys Standard-
  Schriftart (DejaVuSans) keine Farb-Emojis darstellen kann (führte zu
  leeren Kästchen) – Web und Desktop rendern Emojis dagegen über die
  System-Schriftart korrekt.

Getestet: Tkinter- und Kivy-Oberfläche wurden unter Xvfb (virtuellem
Display) gerendert und per Screenshot visuell geprüft; die Web-App wurde
weiterhin über den Flask-Testclient (HTML-Inhalt, keine Optik) getestet.

## Version 2: dauerhafte Markierungen, Listen, Konten

### Neue/geänderte Module

```
core/
├── removal_session.py  # + EntfolgenAblauf, KATEGORIEN, kategorien_ermitteln()
├── history_store.py    # + besitzer-Spalte, account_markierungen, personen_listen, Migration
├── freunde.py          # NEU: Freunde = gegenseitig + manuell
├── export.py           # NEU: Text/CSV-Exporte für alle Oberflächen
├── archive_reader.py   # lade_archiv(): + blockierte Profile, enge Freunde, HTML-Erkennung
├── diff_engine.py      # + moegliche_blockierungen()
└── instagram_checker.py# robustere Erkennung (Profil-API + Fallback), abbrechbar
gui/   listen_view.py, freunde_view.py (NEU), removal_view.py (neu geschrieben)
web/   einstellungen.py (Schalter), konten.py (NEU), app.py (neu geschrieben)
tests/ pytest für core + web
```

### Datenbank

- `account_markierungen(besitzer, username, markierung, gesetzt_am)` – EINE Markierung
  pro Account, unabhängig vom Snapshot. Beim ersten Start mit Version 2 werden die alten
  Einträge aus `workflow_entscheidungen` (pro Snapshot) übernommen (neueste gewinnt).
- `personen_listen(besitzer, liste, username, hinzugefuegt_am)` – freunde,
  blockiert_von_mir, blockiert_mich.
- `snapshots.besitzer` – Desktop/Mobile: `lokal`; Web: `konto:<id>` oder `anon:<zufall>`.
  Jede Abfrage filtert nach Besitzer, niemand sieht fremde Daten.
- `konten` (nur Web) – Benutzername + Passwort-Hash, keine E-Mail.

### Ablauf Entfolgen-Modus

1. `kategorien_ermitteln()` teilt alle Nicht-Zurückfolger in „neu“ und die Gruppen
   behalten / deaktiviert / entfernt / freunde (Freunde haben Vorrang).
2. Die Oberfläche fragt, welche Gruppen erneut abgefragt werden (`erneut_pruefen`).
   `None` = alles abfragen (anonyme Web-Nutzung ohne dauerhafte Markierungen).
3. `EntfolgenAblauf` hält die Kandidaten, schreibt jede Entscheidung sofort in
   `account_markierungen` und stellt bei „Zurück“ die vorherige Markierung wieder her.
   „Zurück“ merkt sich die Reihenfolge der manuellen Entscheidungen – automatisch
   erkannte Accounts werden dabei übersprungen (behebt die frühere Einschränkung).
4. Accounts, die als „Entfolgen“ markiert sind, denen man laut neuem Export aber noch
   folgt, erscheinen in der Zusammenfassung als Erinnerung.

### Web: Threads und Speicher

- Eine SQLite-Verbindung **pro Request** (vorher: eine globale Verbindung → Fehler 500,
  weil SQLite-Verbindungen nicht zwischen Threads geteilt werden dürfen).
- Die automatische Prüfung läuft in einem Hintergrund-Thread mit eigener Verbindung;
  die Seite aktualisiert sich alle 2 Sekunden. Laufende Abläufe liegen im Arbeitsspeicher
  → gunicorn mit genau 1 Worker betreiben.
- CSRF-Token in jedem Formular, Session-Cookie HttpOnly/SameSite, Login-Sperre nach
  10 Fehlversuchen/15 min, Konto-Löschung und Datenexport (DSGVO).
- Anonyme Daten werden nach `ANONYM_AUFBEWAHRUNG_STUNDEN` gelöscht. Beim Anmelden werden
  die Auswertungen der anonymen Sitzung ins Konto übernommen.

## Version 3: TikTok, TXT-Listen, Editor, zuverlässige Prüfung, Anleitungen

- `core/plattform.py`: Instagram/TikTok. Daten werden über den Besitzer getrennt
  (`lokal` = Instagram, `lokal#tiktok` = TikTok; im Web `konto:5#tiktok`).
- `core/tiktok_parser.py` + `archive_reader.lade_export()`: erkennt Instagram-ZIP,
  TikTok-ZIP (JSON oder TXT) und TikTok-JSON automatisch. `lade_liste()` liest einzelne
  Listen (Instagram-JSON, TikTok-JSON, eigene TXT).
- `core/txt_format.py`: eigenes TXT-Format (`name` oder `name;TT.MM.JJJJ`, `#` = Kommentar).
- `core/konto_pruefer.py` (ersetzt `instagram_checker.py`): Kalibrierung mit einem sicher
  existierenden und einem zufälligen, sicher nicht existierenden Account; Abbruch bei Sperre
  oder wenn beide Seiten gleich aussehen; Abbruch nach 5 unklaren Antworten in Folge.
  Ergebnisse sind Vorschläge (`EntfolgenAblauf.vorschlaege`), erst `vorschlaege_bestaetigen()`
  speichert sie.
- `core/anleitungen.py`: How-to-Texte, von Web (`/anleitung`), Desktop (`gui/hilfe_view.py`)
  und App (`HilfeScreen`) gleich angezeigt.
- Editor: Web `/editor`, Desktop `gui/editor_view.py`, App `EditorScreen`.


## Version 4: Kommentare, Likes, HTML, Logo, E-Mail-Konten

- `core/instagram_export.py`: generischer Leser für Instagram-Exportdateien (JSON und HTML).
  `datei_art()` erkennt am Dateinamen, was eine Datei enthält (follower, following, blockiert,
  enge_freunde, kommentare, likes). Daraus werden `Kommentar`- und `Like`-Objekte.
- `core/archive_reader.lade_archiv()`: geht alle Dateien im ZIP durch und sammelt alles in
  `ArchivInhalt` (Follower/Following/Kommentare/Likes …). `enthaelt()` sagt, was gefunden wurde.
- `core/kommentar_bewertung.py`: nachvollziehbare Regel-Bewertung (Wortlisten + Länge + Stil).
- `core/aktivitaet.py`: `AktivitaetAblauf` – Durchgang Löschen/Behalten/Zurück wie beim Entfolgen.
- Datenbank: Tabellen `kommentare`, `likes`, `aktivitaet_entscheidungen`.
- Oberflächen: Web `/import`, `/aktivitaet/<kommentare|likes>`; Desktop `gui/aktivitaet_view.py`;
  App `AktivitaetScreen`.
- Web-Konten: `web/konten.py` (E-Mail, Freischaltung, Passwort-Reset), `web/mail.py` (SMTP),
  `web/verwaltung.py` (Konsolen-Befehle für den Betreiber). Bestätigungs- und Passwort-Links sind
  signierte Tokens (`itsdangerous`), keine zusätzliche Tabelle nötig.
