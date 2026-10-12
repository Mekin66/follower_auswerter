# Lektion 9 – SQLite mit Python

**Lernziele:** Verbindung, Abfragen mit Parametern (Schutz vor SQL-Injection), `executemany`,
Transaktionen, Upserts, Indizes, Migrationen beim Start, Datenbank in Tests.

## 9.1 Verbinden und abfragen

```python
import sqlite3
conn = sqlite3.connect("test.sqlite3")         # Datei wird angelegt, falls nicht vorhanden
conn.execute("CREATE TABLE IF NOT EXISTS konten (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
conn.execute("INSERT INTO konten (name) VALUES (?)", ("anna",))
conn.commit()                                   # erst jetzt dauerhaft gespeichert!

zeile = conn.execute("SELECT id, name FROM konten WHERE name = ?", ("anna",)).fetchone()   # (1, 'anna') oder None
alle  = conn.execute("SELECT id, name FROM konten").fetchall()                              # Liste von Tupeln
for kid, name in conn.execute("SELECT id, name FROM konten"):                               # zeilenweise
    ...
conn.close()
```

`("anna",)` – das Komma macht ein Tupel mit einem Element. Ohne Komma wäre es nur ein String
in Klammern, und SQLite würde jeden Buchstaben als eigenen Parameter sehen.

## 9.2 Niemals Werte in SQL-Text einbauen

```python
# FALSCH – SQL-Injection:
conn.execute(f"SELECT * FROM konten WHERE name = '{eingabe}'")
# eingabe = "x' OR '1'='1"  -> liefert ALLE Konten

# RICHTIG – Platzhalter, SQLite trennt Code und Daten:
conn.execute("SELECT * FROM konten WHERE name = ?", (eingabe,))
```

Platzhalter gehen nur für **Werte**, nicht für Tabellen-/Spaltennamen. Wo das Projekt
Spaltennamen per f-String einsetzt, kommen sie **nie vom Nutzer**, sondern aus festen Listen:

```python
spalte = "email" if "@" in eingabe else "benutzername"      # nur zwei feste Möglichkeiten
conn.execute(f"SELECT id FROM konten WHERE {spalte} = ? COLLATE NOCASE", (eingabe,))

for tabelle in ("snapshots", "account_markierungen", "personen_listen"):   # feste Liste
    conn.execute(f"DELETE FROM {tabelle} WHERE besitzer = ?", (besitzer,))
```

## 9.3 Viele Zeilen auf einmal

```python
zeilen = [(snapshot_id, user, "follower", datum) for user, datum in follower.items()]
conn.executemany("INSERT INTO eintraege (snapshot_id, username, liste, seit_datum) VALUES (?, ?, ?, ?)", zeilen)
conn.commit()
```

`executemany` ist bei 10 000 Followern um ein Vielfaches schneller als 10 000 einzelne
`execute` mit je einem `commit`.

## 9.4 Upsert: einfügen oder aktualisieren

```python
conn.execute("""
    INSERT INTO account_markierungen (besitzer, username, markierung, gesetzt_am)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(besitzer, username) DO UPDATE SET markierung = excluded.markierung,
                                                  gesetzt_am = excluded.gesetzt_am
""", (besitzer, username, wert, jetzt))
```

`excluded` = die Werte, die gerade eingefügt werden sollten. Verwandte Formen:
`INSERT OR IGNORE` (Duplikate still überspringen, `liste_hinzufuegen`) und `UPDATE OR IGNORE`.

## 9.5 Wie viele Zeilen wurden geändert?

```python
cur = conn.execute("DELETE FROM tresore WHERE konto_id = ?", (konto_id,))
cur.rowcount            # 1 = gelöscht, 0 = gab es nicht
cur.lastrowid           # nach INSERT: die neue id

vorher = conn.total_changes
conn.executemany("INSERT OR IGNORE …", zeilen)
neu = conn.total_changes - vorher      # so zählt history_store "neu hinzugefügt"
```

## 9.6 Transaktionen und Optimistic Locking

Alles zwischen zwei `commit()` ist eine Transaktion – entweder ganz oder gar nicht. Für
„gleichzeitig bearbeitet?“ nutzt `web/tresor.py` eine Versionsnummer:

```python
cur = conn.execute("UPDATE tresore SET inhalt = ?, version = ? WHERE konto_id = ? AND version = ?",
                   (inhalt, neu, konto_id, aktuell))
if cur.rowcount != 1:
    raise VersionsKonflikt(...)       # jemand war schneller
```

Die Bedingung `version = ?` macht Prüfen und Schreiben zu **einem** atomaren Schritt – es gibt
keine Lücke zwischen „ich habe nachgeschaut“ und „ich schreibe“.

## 9.7 Schema anlegen und migrieren

```python
def init_db(pfad):
    conn = sqlite3.connect(pfad)
    conn.execute("CREATE TABLE IF NOT EXISTS snapshots (...)")
    if "besitzer" not in {z[1] for z in conn.execute("PRAGMA table_info(snapshots)")}:
        conn.execute("ALTER TABLE snapshots ADD COLUMN besitzer TEXT NOT NULL DEFAULT 'lokal'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_besitzer ON snapshots(besitzer, erstellt_am)")
    conn.commit()
    return conn
```

Läuft bei jedem Start, schadet nie (idempotent). Ausführlich in
[Kapitel 3.6](../03_datenbank.md#36-die-datenbank-erweitern--schritt-für-schritt).

**Indizes** beschleunigen `WHERE`/`ORDER BY` auf diesen Spalten. Faustregel: Spalten, nach denen
oft gefiltert wird (`besitzer`, `snapshot_id`), bekommen einen Index. `PRIMARY KEY` und `UNIQUE`
sind automatisch indiziert.

## 9.8 Nützliche Einstellungen

```python
conn = sqlite3.connect(pfad, timeout=15)          # bis zu 15 s warten, wenn gesperrt
conn.execute("PRAGMA busy_timeout = 15000")
conn.execute("PRAGMA journal_mode = WAL")         # Lesen und Schreiben gleichzeitig (Web)
conn.row_factory = sqlite3.Row                    # Zeilen wie dicts: zeile["name"]
```

`check_same_thread=True` (Standard): Eine Verbindung darf nur in dem Thread benutzt werden, der
sie geöffnet hat. Deshalb öffnet die Web-App **pro Request** und der Hintergrund-Thread
**eigene** Verbindungen (Lektion 11).

## 9.9 `COLLATE NOCASE`

```sql
benutzername TEXT NOT NULL UNIQUE COLLATE NOCASE
```

„Anna“ und „anna“ gelten als gleich – beim Vergleich und bei UNIQUE. Hinweis: NOCASE kennt nur
ASCII; „Ä“/„ä“ würden als verschieden gelten. Deshalb erlauben Benutzernamen nur `A–Z, 0–9, . _ -`.

## 9.10 Datenbank in Tests

```python
@pytest.fixture
def conn(tmp_path):
    c = history_store.init_db(tmp_path / "t.sqlite3")   # frische DB pro Test
    yield c
    c.close()
```

Oder ganz im Speicher: `sqlite3.connect(":memory:")`.

## Übungen

1. Lege mit `:memory:` die Tabelle `tresore` über `web.tresor.init_tresor` an und speichere zweimal
   hintereinander – einmal mit richtiger, einmal mit falscher `basis_version`. Was passiert?
2. Schreibe eine Abfrage: Anzahl Konten je `nutzung` (`GROUP BY`).
3. Schreibe eine Funktion `groesste_tresore(conn, n=5)` mit `JOIN` auf `konten`.
4. Zeige, warum `conn.execute("SELECT * FROM konten WHERE name = ?", "anna")` einen Fehler wirft.

<details><summary>Lösungen</summary>

1. ```python
   import sqlite3
   from web import tresor
   c = sqlite3.connect(":memory:"); tresor.init_tresor(c)
   blk = "FA1." + "A"*22 + "." + "B"*16 + "." + "C"*20
   tresor.speichern(c, 1, blk, 0, 8192)   # -> 1
   tresor.speichern(c, 1, blk, 0, 8192)   # -> VersionsKonflikt (aktuelle_version=1)
   ```
2. `SELECT COALESCE(nutzung, 'unbekannt'), COUNT(*) FROM konten GROUP BY nutzung`
3. ```python
   def groesste_tresore(conn, n=5):
       return conn.execute("SELECT k.benutzername, t.groesse FROM tresore t JOIN konten k ON k.id = t.konto_id "
                           "ORDER BY t.groesse DESC LIMIT ?", (n,)).fetchall()
   ```
4. `"anna"` ist eine Sequenz aus 4 Zeichen → „Incorrect number of bindings supplied … 4“. Richtig: `("anna",)`.
</details>
