# 2. Der Code erklärt – Modul für Modul

Dieses Kapitel geht alle wichtigen Dateien durch: **was sie tun, welche Klassen und Funktionen
es gibt und wie die kniffligen Stellen funktionieren.** Die Python-Grundlagen dahinter
(Dataclasses, Enums, Closures, Generatoren …) erklärt der [Python-Kurs](python_kurs/README.md);
an den passenden Stellen steht ein Verweis „→ Kurs L3“.

---

## 2.1 `core/models.py` – die Datenklassen

| Name | Art | Zweck |
|---|---|---|
| `ListTyp` | `str, Enum` | `FOLLOWER` / `FOLLOWING` |
| `Account` | `@dataclass` | ein Name + Datum (kaum noch genutzt; Listen sind `dict[str, str]`) |
| `Snapshot` | `@dataclass` | Momentaufnahme: `id, erstellt_am, label, follower, following` |
| `Aenderung` | `@dataclass` | eine Zeile im Vergleich: `username, liste, art ("neu"/"entfernt")` |
| `Entscheidung` | `str, Enum` | `BEHALTEN`, `ENTFERNT`, `DEAKTIVIERT` |
| `PersonenListe` | `str, Enum` | `FREUNDE`, `BLOCKIERT_VON_MIR`, `BLOCKIERT_MICH` |
| `ENTSCHEIDUNG_TEXTE`, `LISTEN_TEXTE` | `dict` | Anzeigetexte zu den Enums |

**Warum `class Entscheidung(str, Enum)`?** Durch das zusätzliche `str` ist jedes Mitglied
gleichzeitig ein String: `Entscheidung.BEHALTEN == "behalten"` ist `True`. So kann man den Wert
direkt in SQL und HTML verwenden und trotzdem Tippfehler vermeiden. (→ Kurs L3)

Die wichtigste Datenstruktur im ganzen Projekt ist übrigens schlicht:

```python
follower: dict[str, str] = {"anna": "14.11.2023", "ben": "Unbekannt"}
```

Nutzername → Datum. Mengenoperationen darauf (`set(follower) - set(following)`) ergeben fast
alle Auswertungen.

## 2.2 `core/parser.py` – Instagram-JSON lesen

- `normalisiere_username(text)` macht aus `" @Anna.M "`, `https://instagram.com/_u/anna.m/` oder
  `https://www.tiktok.com/@anna.m` immer `"anna.m"`. Ablauf: Profil-Link per Regex erkennen
  (`_HREF_MUSTER`) → `@` und `/` abschneiden → alle unerlaubten Zeichen entfernen → klein.
- `usernames_aus_text(text)` zerlegt Freitext an Leerzeichen, Komma, Semikolon, Zeilenumbruch
  (`re.split(r"[\s,;]+", …)`) und entfernt Duplikate **unter Beibehaltung der Reihenfolge**.
- `extrahiere_daten(daten)` ist robust gegen die vielen Instagram-Formate:
  der Name steckt mal in `title`, mal in `string_list_data[0]["value"]`, mal nur im Link `href`.
  Die innere Funktion `verarbeite_eintrag()` probiert die Quellen der Reihe nach. (→ Kurs L5: verschachtelte Funktionen)

## 2.3 `core/instagram_export.py` – ein Leser für alles

Statt pro Dateityp einen Parser zu schreiben, wird zuerst **jeder** Eintrag (JSON oder HTML) in
eine einheitliche Zwischenform `Eintrag(titel, felder, links, zeitstempel, texte)` übersetzt:

- `_json_eintrag(obj)` erkennt die drei bekannten JSON-Formen (`string_list_data`,
  `string_map_data`, `label_values`).
- `eintraege_aus_json(daten)` läuft **rekursiv** durch beliebig verschachtelte Daten (`durchlaufen()`).
- `_ExportHTML(HTMLParser)` ist ein *Zustandsautomat*: `handle_starttag`/`handle_endtag`/`handle_data`
  werden vom Python-`HTMLParser` aufgerufen; die Klasse merkt sich, ob sie gerade in einem
  Eintrags-Block, einer Tabellenzeile oder einer Überschrift steckt. (→ Kurs L4: Vererbung)
- Danach machen `zu_accounts`, `zu_kommentaren`, `zu_likes` aus den Einträgen die fertigen Objekte.
- `datei_art(pfad)` entscheidet **nur am Dateinamen**, was eine Datei enthält.
  Detail: `following_hashtags.json` darf *nicht* als Following erkannt werden – deshalb wird
  der „Stamm“ exakt verglichen (`stamm == "following"`), nicht mit `startswith`.

## 2.4 `core/archive_reader.py` – ZIP öffnen und erkennen

- `ArchivInhalt` (Dataclass) sammelt alles: Follower, Following, Blockierte, enge Freunde,
  Kommentare, Likes, erkannte Plattform. `field(default_factory=dict)` ist nötig, weil ein
  veränderliches Standardobjekt sonst von allen Instanzen geteilt würde. (→ Kurs L3)
- `lade_archiv(zip_pfad)`: `zipfile.ZipFile` öffnen, Einträge **JSON vor HTML** sortiert
  (`sorted(namen, key=lambda n: n.lower().endswith(".html"))` – `False < True`), jede passende
  Datei mit `_datei_lesen()` einlesen. Nichts gefunden → `_tiktok_aus_zip()`.
- `lade_export(quelle, dateiname)`: ZIP? → `lade_archiv`. Sonst einzelne Instagram-Datei oder
  TikTok-JSON. Wichtig: `zipfile.is_zipfile()` liest schon im Dateiobjekt, deshalb danach
  `quelle.seek(0)` („zurückspulen“).
- `ExportFormatFehler(ValueError)` – eigene Ausnahme mit verständlicher Meldung für den Nutzer.

## 2.5 `core/tiktok_parser.py` und `core/txt_format.py`

- `extrahiere_tiktok_json` läuft durch die ganze Datei und nimmt **jede** Liste, deren Einträge
  einen Nutzernamen haben; ob Follower/Following/Blockiert, verrät der Pfad
  (`liste_einordnen("Activity / Following List / Following")` → `"following"`).
  Reihenfolge der `if`s beachten: `"following"` vor `"follower"` prüfen.
- `lese_txt` erkennt das TikTok-TXT-Format (`Username: anna`) und sonst das eigene Format
  (`name` oder `name;TT.MM.JJJJ`, `#` = Kommentar). Der Walross-Operator
  `if treffer := _TIKTOK_DATUM.match(zeile):` weist zu und prüft in einem Schritt. (→ Kurs L2)

## 2.6 `core/plattform.py` – Datentrennung

`bereich("konto:5", Plattform.TIKTOK)` → `"konto:5#tiktok"`. Instagram behält den alten
Besitzer (`"konto:5"`), damit Daten aus Zeiten vor TikTok gültig bleiben. Alle DB-Abfragen filtern
nach diesem Schlüssel – so mischen sich die Plattformen nie.

## 2.7 `core/diff_engine.py` – Vergleich

```python
neu_dazugekommen = set(neu) - set(alt)
weggefallen      = set(alt) - set(neu)
```

`vergleiche_snapshots(alt, neu)` tauscht die Argumente, falls sie verkehrt herum kommen, und
liefert eine Liste von `Aenderung`. `moegliche_blockierungen()` findet Accounts, die vorher
**gegenseitig** verbunden waren und jetzt in **beiden** Listen fehlen.

## 2.8 `core/removal_session.py` – der Entfolgen-Modus

Zwei Ebenen:

1. **`RemovalSession`** (Dataclass, *reiner Zustand*, keine DB): Kandidatenliste,
   `entscheidungen: dict`, `verlauf: list` (Reihenfolge für „Zurück“). Methoden:
   `aktueller_kandidat()`, `entscheide()`, `zurueck()`, `fortschritt()`, `zusammenfassung()`.
2. **`EntfolgenAblauf`** verbindet den Zustand mit der Datenbank: jede Entscheidung wird
   **sofort** gespeichert (`history_store.markierung_setzen`). `zurueck()` stellt die *vorherige*
   Markierung wieder her (`_markierungen_vorher`), statt sie nur zu löschen.

`kategorien_ermitteln()` teilt die Nicht-Zurückfolger in „neu“ und die Gruppen
behalten/deaktiviert/entfernt/freunde (Freunde haben Vorrang). Der Parameter
`erneut_pruefen` steuert, welche Gruppen wieder abgefragt werden; `None` = alle.

Warum bekommen die Schreib-Methoden `conn` übergeben? Im Web lebt ein Ablauf über mehrere
Requests, aber jeder Request hat seine **eigene** DB-Verbindung (SQLite-Verbindungen dürfen
nicht zwischen Threads geteilt werden).

## 2.9 `core/konto_pruefer.py` – „Scheint deaktiviert“

Klassisches Beispiel für *Kalibrierung statt fester Regeln*: Vor der Prüfung ruft
`KontoPruefer.kalibrieren()` ein sicher existierendes Profil und einen zufälligen Fantasienamen
(`"zz" + secrets.token_hex(10)`) ab und merkt sich, wie „gibt es“ und „gibt es nicht“ gerade
aussehen. Sind beide gleich (Sperre, Login-Pflicht), bricht es mit `PruefungNichtMoeglich` ab.
`pruefe_mehrere()` ist ein **Generator** (`yield`): Er liefert jedes Ergebnis sofort, damit die
Oberfläche einen Fortschritt zeigen kann, und bricht nach mehreren unklaren Antworten ab.
(→ Kurs L6). Die HTTP-Funktion ist als Parameter `abrufen=` austauschbar – so können Tests
ohne Internet laufen (*Dependency Injection*).

Im Tresor-Modus ist die Prüfung abgeschaltet (der Server kennt keine Namen).

## 2.10 Kommentar-Bewertung: `core/kommentar_netz.py` und `core/kommentar_bewertung.py`

Statt fester Wortlisten entscheidet ein **kleines neuronales Netz**, das an beschrifteten
Beispielen trainiert wurde (`core/daten/kommentar_beispiele.tsv`, UTF-8). Ausführlich, mit
Mathematik und Übungen: [Kurs-Lektion 13](python_kurs/13_neuronales_netz.md).

```
Text ─► Merkmale (Hashing, 16384 + 6 Stil) ─► 24 Neuronen (tanh) ─► 3 Klassen (Softmax)
```

| Teil | Funktion/Klasse | Aufgabe |
|---|---|---|
| Unicode | `normalisieren()`, `woerter()` | NFKC + `casefold()` – jede Sprache/Schrift; „𝐈𝐝𝐢𝐨𝐭“ → „idiot“, „GROẞ“ → „gross“, „idiooooot“ → „idioot“ |
| Merkmale | `merkmale()`, `_platz()` | Wörter, Zeichen-3/4/5-Gramme, Emojis → per CRC32 (der UTF-8-Bytes) auf 16 384 Plätze; dazu Stil: Länge, Großbuchstaben, „!!“, Kontaktdaten, nur Emojis, Link |
| Netz | `KommentarNetz` | `_vorwaerts()` rechnet dünn besetzt (nur vorhandene Merkmale), `wahrscheinlichkeiten()`, `risiko()` |
| Training | `trainieren()`, `_schritt()` | Rückpropagation, Klassengewichte, Label-Smoothing, L2, sinkende Lernrate |
| Prüfen | `kreuzvalidierung()` | ehrliche Trefferquote auf ungesehenen Beispielen (aktuell ca. 72 %, Raten = 33 %) |
| Erklären | `erklaeren()` | jedes Wort einmal weglassen, Änderung in Log-Chancen messen → Anteil am Risiko |
| Anpassen | `angepasst()` | Kopie mit den Entscheidungen des Nutzers nachtrainiert (in `core/aktivitaet.py::persoenliches_netz`, ab 5 Entscheidungen) |
| Speichern | `speichern()`, `laden()` | JSON in UTF-8, nur benutzte Zeilen der ersten Schicht |

`kommentar_bewertung.bewerte(text, netz=None, erklaeren=True)` liefert wie bisher
`Bewertung(stufe, punkte, gruende, treffer)` – deshalb mussten Desktop, App und Web nicht
geändert werden. Neu: `wahrscheinlichkeiten` und `erklaert`. Mit `erklaeren=False` geht es
etwa 6× schneller (zum Sortieren tausender Kommentare); die Gründe berechnet
`AktivitaetAblauf.bewertung()` erst, wenn ein Kommentar angezeigt wird.

**Neu trainieren** nach Änderungen an den Beispielen:

```bash
python -m core.kommentar_netz trainieren          # ca. 30 s inkl. Kreuzvalidierung
python -m core.kommentar_netz testen "Du bist so ein Idiot!!!"
```

Ein Test (`tests/test_kommentar_netz.py`) schlägt fehl, wenn die Beispiele geändert, aber nicht
neu trainiert wurden (Fingerabdruck der TSV-Datei steht in der JSON).

## 2.11 `core/history_store.py`

Alle SQL-Befehle des Projekts (Modus klassisch, Desktop, Mobile). Ausführlich in
[Kapitel 3](03_datenbank.md).

---

## 2.12 `web/app.py` – die Flask-App

### App-Factory

```python
def create_app(**ueberschreiben) -> Flask:
    cfg = {name: getattr(standard_einstellungen, name) for name in dir(standard_einstellungen) if name.isupper()}
    cfg.update(ueberschreiben)
    ...
    return app

app = create_app()
```

Alle Einstellungen in GROSSBUCHSTABEN aus `einstellungen.py` landen im dict `cfg`. Tests rufen
`create_app(BETRIEBSMODUS="klassisch", DATENBANK_PFAD=tmp)` auf und bekommen eine eigene,
unabhängige App. Alle Routen und Helfer sind **innere Funktionen** von `create_app` und greifen
über die *Closure* auf `cfg`, `lock`, `ablaeufe` zu. (→ Kurs L5)

### Wichtige Helfer

| Funktion | Aufgabe |
|---|---|
| `db()` | eine SQLite-Verbindung pro Request (in `flask.g`), am Ende geschlossen (`teardown_appcontext`) |
| `konto_id()`, `besitzer()` | wer ist angemeldet, unter welchem Schlüssel liegen seine Daten |
| `csrf_token()` | Zufallstoken pro Sitzung gegen Cross-Site-Request-Forgery |
| `_vor_jedem_request()` | `@app.before_request`: Tresor-Modus-Sperre, CSRF-Prüfung, Aufräumen alle 10 min |
| `_vorlagen_variablen()` | `@app.context_processor`: Variablen für **alle** Templates |

### CSRF – wie es funktioniert

Jede Seite bettet `csrf_token()` ein (als `<input type="hidden" name="_csrf">` bzw. im Tresor
als `<meta name="csrf-token">`). Bei POST/PUT/DELETE vergleicht `_vor_jedem_request` das
mitgeschickte Token mit dem in der Sitzung – mit `secrets.compare_digest` (zeitkonstant, verrät
nichts über Teilübereinstimmungen). Eine fremde Webseite kennt das Token nicht.

### Tresor-Routen

| Route | Methode | Funktion |
|---|---|---|
| `/` | GET | im Tresor-Modus `tresor.html` + Header `Content-Security-Policy` |
| `/api/tresor` | GET | verschlüsselten Block + Version + AVV-Status liefern |
| `/api/tresor` | PUT | Block speichern (`basis_version` für Konflikterkennung, nur mit aktuellem AVV) |
| `/api/tresor` | DELETE | Tresor löschen |
| `/avv` | GET/POST | Vertrag anzeigen / zustimmen + Nutzungsart |

`_tresor_zugang(schreiben=False)` bündelt die Prüfungen (Modus, Anmeldung, AVV) und gibt
entweder `None` oder eine fertige JSON-Fehlerantwort zurück:

```python
if (fehler := _tresor_zugang(schreiben=True)) is not None:
    return fehler
```

### Klassische Routen

`/laden` (Upload) → `/ergebnis/<id>` → `/verlauf` → `/entfolgen/<id>` … Sie sind im
Tresor-Modus über `KLASSISCHE_ENDPUNKTE` abgeschaltet (404). Die automatische Prüfung läuft dort
in einem `threading.Thread`; laufende Abläufe liegen im Arbeitsspeicher (`ablaeufe`,
`OrderedDict` mit Obergrenze) → **gunicorn mit genau 1 Worker** betreiben.

## 2.13 `web/tresor.py`

| Funktion | Aufgabe |
|---|---|
| `init_tresor(conn)` | Tabelle `tresore` anlegen |
| `pruefen(inhalt, max_kb)` | nur `FA1.<salt>.<iv>.<geheimtext>` annehmen (Regex `_FORMAT`), Größe begrenzen |
| `speichern(conn, konto_id, inhalt, basis_version, max_kb)` | Version vergleichen, `UPDATE … WHERE version = ?` (atomar), neue Version zurück |
| `laden`, `info`, `loeschen`, `statistik` | lesen (mit/ohne Inhalt), löschen, Summen für den Betreiber |
| `VersionsKonflikt(TresorFehler)` | trägt `aktuelle_version`, wird zu HTTP 409 |

**Optimistic Locking:** Das `WHERE konto_id = ? AND version = ?` sorgt dafür, dass von zwei
gleichzeitigen Speicherungen nur eine gewinnt (`cur.rowcount` = 0 bei der anderen).

## 2.14 `web/konten.py`

Registrierung (`registrieren`), Login mit Name **oder** E-Mail (`anmelden`), Double-Opt-in
(`email_bestaetigen`), Passwort-Reset (`passwort_fingerabdruck` macht den Link einmalig),
`avv_zustimmen`/`avv_aktuell`, Löschung (`konto_loeschen` → auch Tresor). Passwörter nur als
Hash (`werkzeug.security.generate_password_hash`, aktuell scrypt). `init_konten` migriert die
Tabelle (neue Spalten per `ALTER TABLE`).

Die Links in E-Mails sind **signierte Tokens** (`itsdangerous.URLSafeTimedSerializer` in
`app.py`): Inhalt `{"id": 5, "email": "…"}`, mit `SECRET_KEY` unterschrieben, mit Ablaufzeit.
Dafür braucht es keine eigene Tabelle.

## 2.15 `web/mail.py`, `web/verwaltung.py`, `web/einstellungen.py`

- `mail.senden()` baut eine `EmailMessage` und schickt sie per `smtplib` (STARTTLS oder SSL).
  Ohne `SMTP_HOST` → **Testmodus**: Mail wird nur ins Log geschrieben.
- `verwaltung.py` nutzt `argparse` mit Unterbefehlen (`konten`, `emails`, `loeschen`,
  `mailtest`, `tresore`, `avv`). (→ Kurs L10)
- `einstellungen.py`: jede Einstellung = Standardwert, per Umgebungsvariable überschreibbar
  (`_bool("ACCOUNTS_AKTIVIERT", True)`).

---

## 2.16 Die Browser-App `web/static/tresor/`

JavaScript-**Module** (`import`/`export`), kein Framework, kein Build-Schritt.

### `krypto.js`

```js
schluessel = PBKDF2(passwort, salt, 600000 Runden, SHA-256) → AES-GCM-256
block      = "FA1." + b64url(salt) + "." + b64url(iv) + "." + b64url(AES-GCM(gzip(JSON)))
```

- `neuerSchluessel(passwort)` – neues zufälliges Salt (neuer Tresor, Passwortwechsel).
- `verschluesseln(daten, schluessel)` – **neuer IV bei jedem Aufruf** (bei GCM ist ein
  wiederverwendeter IV ein schwerer Fehler).
- `oeffnen(block, passwort)` – Salt aus dem Block lesen, Schlüssel ableiten, entschlüsseln.
- `additionalData: "FA1"` bindet den Geheimtext an die Formatversion.
- Falsches Passwort → `FalschesPasswort` (GCM-Prüfsumme passt nicht).

### `zip.js`

Liest das ZIP-Inhaltsverzeichnis vom Dateiende her (`EOCD` → Zentralverzeichnis) und
entpackt nur benötigte Dateien mit `DecompressionStream("deflate-raw")`. Dank `Blob.slice()`
wird nie die ganze Datei in den Speicher geladen. Die Byte-Offsets (z. B. `+28` = Länge des
Dateinamens) stammen aus der ZIP-Spezifikation (PKWARE APPNOTE).

### `parser.js` und `auswertung.js`

1:1-Ports der Python-Funktionen, gleiche Namen in camelCase:

| Python | JavaScript |
|---|---|
| `normalisiere_username` | `normalisiereUsername` |
| `extrahiere_daten` | `extrahiereDaten` |
| `lese_txt` / `schreibe_txt` | `leseTxt` / `schreibeTxt` |
| `extrahiere_tiktok_json` | `extrahiereTiktokJson` |
| `lade_export` / `lade_liste` | `ladeExport` / `ladeListe` |
| `vergleiche_snapshots` + `moegliche_blockierungen` | `vergleichen` |
| `freunde_ermitteln` | `freundeErmitteln` |
| `kategorien_ermitteln`, `EntfolgenAblauf` | `kategorienErmitteln`, `EntfolgenAblauf` |

`tests/test_js.py` erzeugt ein Export-ZIP, liest es mit **beiden** Parsern und vergleicht.
Wer einen Parser ändert, sieht so sofort, wenn der andere abweicht.

Das Tresor-Datenmodell steht oben in `auswertung.js`; `normalisieren()` ist die „Migration“
für ältere Tresore (fehlende Teile ergänzen) – das Gegenstück zu `init_db()` auf dem Server.

### `speicher.js`

Klasse `TresorSpeicher`: `abrufen()`, `anlegen()`, `entsperren()`, `speichern()`,
`ueberschreiben()` (bei Konflikt), `passwortAendern()`, `loeschen()`, `sicherungErstellen()`.
Hält `schluessel` und `daten` **nur im Arbeitsspeicher**.

### `app.js`

- `el(tag, attrs, ...kinder)` baut DOM-Elemente; Texte immer über `textContent` → kein XSS.
- Je Ansicht eine Funktion (`ansichtLaden`, `ansichtErgebnis`, `ansichtVerlauf`,
  `ansichtEntfolgen`, `ansichtListen`, `ansichtTresor`), ausgewählt über den `#`-Teil der URL.
- `zeichnen()` baut die aktuelle Ansicht komplett neu.
- `geaendert()` → neu zeichnen + nach 800 ms automatisch speichern (*Debounce*: viele schnelle
  Änderungen = eine Speicherung). Nach dem Speichern wird nur die Statuszeile aktualisiert,
  damit halb ausgefüllte Felder nicht geleert werden.

---

## 2.17 Desktop (`gui/`) und Mobile (`mobile/`)

- `gui/main_window.py::InstagramAuswerter` baut das Hauptfenster; jede weitere Funktion öffnet
  ein `tk.Toplevel`-Fenster aus einer eigenen Datei. `gui/theme.py` definiert ttk-Stile
  (`Primaer.TButton` …). Lange Aufgaben (Prüfung) laufen in einem Thread; Ergebnisse gehen per
  `root.after()` zurück in den GUI-Thread.
- `mobile/main.py`: Kivy-`ScreenManager` mit `HauptScreen`, `EntfolgenScreen`, `ListenScreen` …;
  Layout in `instagramauswerter.kv`. Thread-Ergebnisse über `Clock.schedule_once()`.
- Beide speichern lokal in SQLite (`history_store`, Besitzer `lokal`) – kein Server beteiligt.
