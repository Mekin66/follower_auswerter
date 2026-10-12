# 3. Die Datenbank – Aufbau, Verwaltung, Erweiterung

## 3.1 Welche Datenbank liegt wo?

Das Projekt nutzt **SQLite**: eine einzige Datei, kein Datenbankserver, in Python eingebaut
(`import sqlite3`). Für dieses Projekt reicht das völlig – SQLite schafft problemlos Tausende
Nutzer mit wenigen Schreibzugriffen pro Sekunde.

| Oberfläche | Datei | Inhalt |
|---|---|---|
| Desktop | `~/.instagram_auswerter/verlauf.sqlite3` (Windows: `C:\Users\<Name>\…`) | Listen im Klartext, Besitzer `lokal` |
| Mobile | App-Datenordner, gleiches Schema | wie Desktop |
| Web | `DATENBANK_PFAD`, Standard `web/daten/web.sqlite3`, im Docker `/data/web.sqlite3` | Konten, Tresore (Modus tresor) bzw. Listen (Modus klassisch) |

Die Web-Datei enthält **beide** Schemata; welche Tabellen gefüllt werden, hängt vom
`BETRIEBSMODUS` ab.

## 3.2 Tabellen

### Konten und Tresor (Web)

```
konten                                   tresore
──────────────────────────────           ──────────────────────────────
id               INTEGER PK  ◄──────────  konto_id        INTEGER PK
benutzername     TEXT UNIQUE NOCASE       inhalt          TEXT  "FA1.…" (verschlüsselt)
passwort_hash    TEXT                     version         INTEGER  (Konflikterkennung)
erstellt_am      TEXT (ISO)               groesse         INTEGER  (Bytes)
letzter_login    TEXT                     aktualisiert_am TEXT
email            TEXT UNIQUE (wenn gesetzt)
email_bestaetigt_am, email_neu, newsletter_am TEXT
freigeschaltet   INTEGER 0/1
nutzung          TEXT  privat|geschaeftlich        ← neu (Tresor)
avv_version      TEXT  z. B. "2026-10"             ← neu (Tresor)
avv_akzeptiert_am TEXT                             ← neu (Tresor)
```

### Listen (Desktop, Mobile, Web „klassisch“)

```
snapshots (id PK, erstellt_am, label, besitzer)
   └── eintraege (id PK, snapshot_id → snapshots.id, username, liste 'follower'|'following', seit_datum)
account_markierungen (besitzer, username, markierung, gesetzt_am)        PK (besitzer, username)
personen_listen      (besitzer, liste, username, hinzugefuegt_am)        PK (besitzer, liste, username)
kommentare           (besitzer, id, text, medien_owner, zeitstempel, datum, link, quelle, importiert_am)
likes                (besitzer, id, owner, zeitstempel, datum, link, art, importiert_am)
aktivitaet_entscheidungen (besitzer, art, id, entscheidung, gesetzt_am)
workflow_entscheidungen   (alt, Version 1 – nur noch für die Migration)
schema_info (schluessel PK, wert)       ← merkt sich erledigte Einmal-Migrationen
```

**`besitzer`** trennt die Daten: `lokal`, `lokal#tiktok`, `konto:5`, `konto:5#tiktok`,
`anon:<zufall>`. Jede Abfrage enthält `WHERE besitzer = ?`.

**Datumsfelder** sind Text im ISO-Format (`2026-10-12T14:03:00`). Vorteil: Text-Vergleich =
zeitlicher Vergleich (`erstellt_am < '2026-01-01'` funktioniert).

### Der Tresor-Inhalt

Was *im* verschlüsselten Block steht, ist ein JSON-Objekt (Aufbau oben in
`web/static/tresor/auswertung.js`). Den sieht nur der Browser – auf dem Server kannst du ihn
weder abfragen noch ändern. Änderungen am Tresor-Format passieren deshalb in JavaScript
(siehe 3.6).

## 3.3 Datenbank ansehen

**Grafisch:** [DB Browser for SQLite](https://sqlitebrowser.org) (kostenlos) → Datei öffnen →
„Daten durchsuchen“. Vorher eine **Kopie** ziehen, nicht die laufende Datei bearbeiten.

**Konsole:**

```bash
sqlite3 web/daten/web.sqlite3
sqlite> .tables
sqlite> .schema konten
sqlite> .headers on
sqlite> .mode column
sqlite> SELECT id, benutzername, nutzung, avv_version FROM konten;
sqlite> SELECT konto_id, groesse, version, aktualisiert_am FROM tresore;
sqlite> .quit
```

**Mit Docker** (Datei liegt im Volume):

```bash
docker compose -f packaging/server/docker-compose.yml exec app python -m web.verwaltung konten
docker compose -f packaging/server/docker-compose.yml exec app sqlite3 /data/web.sqlite3   # falls sqlite3 im Image
```

**Mit Python** (funktioniert immer, auch ohne `sqlite3`-Programm):

```python
import sqlite3
conn = sqlite3.connect("web/daten/web.sqlite3")
for zeile in conn.execute("SELECT benutzername, erstellt_am FROM konten ORDER BY erstellt_am DESC LIMIT 10"):
    print(zeile)
```

## 3.4 Verwalten: die Betreiber-Befehle

```bash
python -m web.verwaltung konten                  # alle Konten
python -m web.verwaltung emails --newsletter     # nur Adressen mit Newsletter-Einwilligung
python -m web.verwaltung loeschen BENUTZERNAME   # Konto + Tresor löschen (fragt nach)
python -m web.verwaltung tresore                 # Größe/Stand der Tresore – ohne Inhalte
python -m web.verwaltung avv                     # AVV-Zustimmungen (Nachweis)
python -m web.verwaltung mailtest DU@EXAMPLE.DE
```

Automatisch (beim Betrieb, höchstens alle 10 Minuten):
- Konten ohne Login seit `KONTO_LOESCHEN_NACH_TAGEN` → gelöscht (samt Tresor),
- unbestätigte Registrierungen nach `BESTAETIGUNG_GUELTIG_STUNDEN` → gelöscht,
- (klassisch) anonyme Daten nach `ANONYM_AUFBEWAHRUNG_STUNDEN` → gelöscht.

## 3.5 Sichern und Wiederherstellen

SQLite läuft im WAL-Modus (`PRAGMA journal_mode = WAL`). Eine einfache Dateikopie *während*
des Betriebs kann daher unvollständig sein. Richtig ist die eingebaute Backup-Funktion:

```bash
sqlite3 /data/web.sqlite3 ".backup '/data/backup/web-$(date +%F).sqlite3'"
```

oder in Python:

```python
import sqlite3, datetime
quelle = sqlite3.connect("/data/web.sqlite3")
ziel = sqlite3.connect(f"/data/backup/web-{datetime.date.today()}.sqlite3")
quelle.backup(ziel)       # konsistente Kopie, auch während die App läuft
ziel.close()
```

Täglich per `cron`, alte Sicherungen nach `BACKUP_LOESCHFRIST_TAGE` löschen
(`find /data/backup -name 'web-*.sqlite3' -mtime +30 -delete`). Diese Frist steht im AVV –
**sie muss zur Wirklichkeit passen.** Wiederherstellen: App stoppen, Datei zurückkopieren, starten.

## 3.6 Die Datenbank erweitern – Schritt für Schritt

Das Projekt hat bewusst **kein** Migrations-Werkzeug (wie Alembic). Stattdessen prüft der Code
beim Start, was fehlt, und ergänzt es. Drei Muster kommen vor:

### Muster A: neue Tabelle

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS notizen (
        konto_id INTEGER NOT NULL,
        text     TEXT NOT NULL,
        erstellt_am TEXT NOT NULL
    )
""")
```

`IF NOT EXISTS` macht den Befehl wiederholbar („idempotent“) – er darf bei jedem Start laufen.

### Muster B: neue Spalte in bestehender Tabelle

```python
spalten = {z[1] for z in conn.execute("PRAGMA table_info(konten)")}
if "sprache" not in spalten:
    conn.execute("ALTER TABLE konten ADD COLUMN sprache TEXT NOT NULL DEFAULT 'de'")
```

So sind die Spalten `nutzung`, `avv_version`, `avv_akzeptiert_am` dazugekommen
(`web/konten.py::init_konten`). Neue Spalten brauchen einen `DEFAULT` oder müssen `NULL` erlauben,
weil alte Zeilen sonst keinen Wert hätten.

### Muster C: Daten einmalig umbauen

```python
erledigt = conn.execute("SELECT 1 FROM schema_info WHERE schluessel = 'migration_xyz'").fetchone()
if not erledigt:
    ...  # Daten umbauen
    conn.execute("INSERT INTO schema_info VALUES ('migration_xyz', ?)", (jetzt,))
```

Beispiel im Code: `history_store._alte_entscheidungen_uebernehmen()`.

### Beispiel komplett: „Letzte Tresor-Größe pro Monat“ als Statistik

1. **Schema** in `web/tresor.py::init_tresor` ergänzen (Muster A):
   ```python
   conn.execute("CREATE TABLE IF NOT EXISTS tresor_statistik (monat TEXT PRIMARY KEY, anzahl INTEGER, bytes INTEGER)")
   ```
2. **Funktion** daneben schreiben:
   ```python
   def statistik_merken(conn):
       anzahl, summe = statistik(conn)
       monat = datetime.date.today().strftime("%Y-%m")
       conn.execute("INSERT INTO tresor_statistik VALUES (?, ?, ?) "
                    "ON CONFLICT(monat) DO UPDATE SET anzahl = excluded.anzahl, bytes = excluded.bytes",
                    (monat, anzahl, summe))
       conn.commit()
   ```
3. **Aufrufen**, z. B. im Aufräum-Block von `_vor_jedem_request` in `web/app.py`.
4. **Test** in `tests/test_tresor.py` schreiben.
5. **Verwaltungsbefehl** in `web/verwaltung.py` ergänzen, falls du es ansehen willst.
6. **Datenschutz prüfen:** neue personenbezogene Daten? → Datenschutzerklärung/AVV anpassen.

### Den Tresor-Inhalt erweitern (JavaScript)

Beispiel: eine Notiz pro Account.

1. `auswertung.js`: in `leererBereich()` `notizen: {}` ergänzen **und** in `normalisieren()`
   `b.notizen ??= {};` – damit alte Tresore das Feld bekommen.
2. Bei grundlegenden Umbauten `FORMAT` hochzählen und in `normalisieren()` alte Formate umbauen.
3. `app.js`: Anzeige/Eingabe bauen, nach Änderungen `geaendert()` aufrufen (speichert automatisch).
4. Test in `tests/js/tresor.test.mjs`.

Der Server muss dafür **nicht** geändert werden – er speichert ja nur den Block.

## 3.7 Wann SQLite nicht mehr reicht

Grob ab vielen gleichzeitigen *Schreibzugriffen* oder wenn mehrere Server-Instanzen dieselben
Daten brauchen. Dann PostgreSQL: Die SQL-Befehle sind fast identisch, nur die Platzhalter
(`?` → `%s` mit `psycopg`) und `PRAGMA`-Befehle ändern sich. Für dieses Projekt ist das auf
absehbare Zeit nicht nötig – ein Tresor ist ein einziger `UPDATE` pro Speicherung.
