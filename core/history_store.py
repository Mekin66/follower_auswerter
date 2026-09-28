"""
Speicherung in einer SQLite-Datenbank.

Gespeichert werden:
- Snapshots (jede Auswertung eines Exports) für den Verlauf/Vergleich
- Dauerhafte Markierungen aus dem Entfolgen-Modus (behalten/entfernt/
  deaktiviert) – pro Account, NICHT pro Snapshot. Dadurch muss man beim
  nächsten Export nicht wieder alle Accounts neu durchgehen.
- Frei pflegbare Personen-Listen (Freunde, von mir blockiert, hat mich
  blockiert)

Jede Zeile gehört einem "besitzer". Desktop- und Mobile-App nutzen immer
den Besitzer "lokal". Die Web-App nutzt "konto:<id>" für angemeldete
Nutzer bzw. "anon:<zufall>" für anonyme Besucher – so sieht niemand die
Daten eines anderen.
"""

import datetime
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from core.models import Snapshot, Entscheidung, PersonenListe

STANDARD_DB_PFAD = Path.home() / ".instagram_auswerter" / "verlauf.sqlite3"
LOKAL = "lokal"


def _jetzt() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _spalten(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    return {zeile[1] for zeile in conn.execute(f"PRAGMA table_info({tabelle})")}


def init_db(db_pfad: Path | str = STANDARD_DB_PFAD, check_same_thread: bool = True) -> sqlite3.Connection:
    """Öffnet die Datenbank (legt sie inkl. Ordner an) und bringt das Schema auf den aktuellen Stand."""
    db_pfad = Path(db_pfad)
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_pfad, check_same_thread=check_same_thread, timeout=15)
    # Bewusst OHNE "PRAGMA foreign_keys": ältere Datenbanken haben Fremdschlüssel
    # ohne ON DELETE CASCADE; abhängige Zeilen werden stattdessen explizit gelöscht.
    try:
        conn.execute("PRAGMA journal_mode = WAL")  # parallele Lese-/Schreibzugriffe (Web)
    except sqlite3.DatabaseError:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erstellt_am TEXT NOT NULL,
            label TEXT NOT NULL,
            besitzer TEXT NOT NULL DEFAULT 'lokal'
        )
    """)
    # Migration: ältere Datenbanken haben noch keine Besitzer-Spalte
    if "besitzer" not in _spalten(conn, "snapshots"):
        conn.execute("ALTER TABLE snapshots ADD COLUMN besitzer TEXT NOT NULL DEFAULT 'lokal'")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS eintraege (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            liste TEXT NOT NULL CHECK (liste IN ('follower', 'following')),
            seit_datum TEXT NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eintraege_snapshot ON eintraege(snapshot_id, liste)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_besitzer ON snapshots(besitzer, erstellt_am)")

    # Alte, pro Snapshot gespeicherte Entscheidungen (Version 1). Wird nur
    # noch für die einmalige Übernahme in account_markierungen gelesen.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_entscheidungen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            entscheidung TEXT NOT NULL CHECK (entscheidung IN ('behalten', 'entfernt', 'deaktiviert')),
            entschieden_am TEXT NOT NULL,
            UNIQUE(snapshot_id, username)
        )
    """)

    # NEU: dauerhafte Markierung pro Account (unabhängig vom Snapshot)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS account_markierungen (
            besitzer TEXT NOT NULL,
            username TEXT NOT NULL,
            markierung TEXT NOT NULL CHECK (markierung IN ('behalten', 'entfernt', 'deaktiviert')),
            gesetzt_am TEXT NOT NULL,
            PRIMARY KEY (besitzer, username)
        )
    """)

    # NEU: frei pflegbare Listen (Freunde, blockiert, ...)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS personen_listen (
            besitzer TEXT NOT NULL,
            liste TEXT NOT NULL CHECK (liste IN ('freunde', 'blockiert_von_mir', 'blockiert_mich')),
            username TEXT NOT NULL,
            hinzugefuegt_am TEXT NOT NULL,
            PRIMARY KEY (besitzer, liste, username)
        )
    """)

    # NEU (Version 4): eigene Kommentare und Likes aus dem Export + Entscheidungen dazu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kommentare (
            besitzer TEXT NOT NULL, id TEXT NOT NULL, text TEXT NOT NULL, medien_owner TEXT NOT NULL,
            zeitstempel REAL, datum TEXT NOT NULL, link TEXT NOT NULL, quelle TEXT NOT NULL,
            importiert_am TEXT NOT NULL,
            PRIMARY KEY (besitzer, id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            besitzer TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL, zeitstempel REAL,
            datum TEXT NOT NULL, link TEXT NOT NULL, art TEXT NOT NULL, importiert_am TEXT NOT NULL,
            PRIMARY KEY (besitzer, id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS aktivitaet_entscheidungen (
            besitzer TEXT NOT NULL, art TEXT NOT NULL CHECK (art IN ('kommentar', 'like')),
            id TEXT NOT NULL, entscheidung TEXT NOT NULL CHECK (entscheidung IN ('entfernen', 'behalten')),
            gesetzt_am TEXT NOT NULL,
            PRIMARY KEY (besitzer, art, id)
        )
    """)

    conn.execute("CREATE TABLE IF NOT EXISTS schema_info (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL)")
    _alte_entscheidungen_uebernehmen(conn)
    conn.commit()
    return conn


def _alte_entscheidungen_uebernehmen(conn: sqlite3.Connection) -> None:
    """Einmalig: Entscheidungen aus Version 1 (pro Snapshot) als dauerhafte Markierungen übernehmen."""
    erledigt = conn.execute(
        "SELECT 1 FROM schema_info WHERE schluessel = 'migration_markierungen_v2'"
    ).fetchone()
    if erledigt:
        return
    # Pro Username gewinnt die jeweils neueste Entscheidung.
    zeilen = conn.execute("""
        SELECT w.username, w.entscheidung, w.entschieden_am, COALESCE(s.besitzer, 'lokal')
        FROM workflow_entscheidungen w
        LEFT JOIN snapshots s ON s.id = w.snapshot_id
        ORDER BY w.entschieden_am ASC
    """).fetchall()
    for username, entscheidung, am, besitzer in zeilen:
        conn.execute("""
            INSERT INTO account_markierungen (besitzer, username, markierung, gesetzt_am)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(besitzer, username) DO UPDATE SET markierung = excluded.markierung,
                                                          gesetzt_am = excluded.gesetzt_am
        """, (besitzer, username, entscheidung, am))
    conn.execute("INSERT INTO schema_info (schluessel, wert) VALUES ('migration_markierungen_v2', ?)", (_jetzt(),))


# ---------------------------------------------------------------- Snapshots

def snapshot_speichern(conn: sqlite3.Connection, follower: dict[str, str], following: dict[str, str],
                       label: str | None = None, besitzer: str = LOKAL) -> int:
    """Speichert einen neuen Snapshot und gibt dessen ID zurück."""
    if not label:
        label = f"Export vom {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"

    cur = conn.execute(
        "INSERT INTO snapshots (erstellt_am, label, besitzer) VALUES (?, ?, ?)",
        (_jetzt(), label, besitzer),
    )
    snapshot_id = cur.lastrowid
    zeilen = [(snapshot_id, user, "follower", datum) for user, datum in follower.items()]
    zeilen += [(snapshot_id, user, "following", datum) for user, datum in following.items()]
    conn.executemany(
        "INSERT INTO eintraege (snapshot_id, username, liste, seit_datum) VALUES (?, ?, ?, ?)", zeilen
    )
    conn.commit()
    return snapshot_id


def snapshots_auflisten(conn: sqlite3.Connection, besitzer: str = LOKAL) -> list[tuple[int, str, str]]:
    """Gibt (id, erstellt_am, label) aller Snapshots dieses Besitzers zurück, neueste zuerst."""
    return conn.execute(
        "SELECT id, erstellt_am, label FROM snapshots WHERE besitzer = ? ORDER BY erstellt_am DESC, id DESC",
        (besitzer,),
    ).fetchall()


def snapshot_laden(conn: sqlite3.Connection, snapshot_id: int, besitzer: str = LOKAL) -> Snapshot:
    """Lädt einen vollständigen Snapshot. Wirft ValueError, wenn er nicht existiert oder jemand anderem gehört."""
    meta = conn.execute(
        "SELECT erstellt_am, label FROM snapshots WHERE id = ? AND besitzer = ?", (snapshot_id, besitzer)
    ).fetchone()
    if meta is None:
        raise ValueError(f"Snapshot mit ID {snapshot_id} existiert nicht.")

    erstellt_am, label = meta
    follower: dict[str, str] = {}
    following: dict[str, str] = {}
    for username, liste, seit_datum in conn.execute(
        "SELECT username, liste, seit_datum FROM eintraege WHERE snapshot_id = ?", (snapshot_id,)
    ):
        (follower if liste == "follower" else following)[username] = seit_datum

    return Snapshot(id=snapshot_id, erstellt_am=erstellt_am, label=label, follower=follower, following=following)


def snapshot_loeschen(conn: sqlite3.Connection, snapshot_id: int, besitzer: str = LOKAL) -> bool:
    gehoert_mir = conn.execute(
        "SELECT 1 FROM snapshots WHERE id = ? AND besitzer = ?", (snapshot_id, besitzer)
    ).fetchone()
    if not gehoert_mir:
        return False
    conn.execute("DELETE FROM eintraege WHERE snapshot_id = ?", (snapshot_id,))
    conn.execute("DELETE FROM workflow_entscheidungen WHERE snapshot_id = ?", (snapshot_id,))
    conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    conn.commit()
    return True


def letzten_snapshot_id(conn: sqlite3.Connection, besitzer: str = LOKAL) -> int | None:
    zeile = conn.execute(
        "SELECT id FROM snapshots WHERE besitzer = ? ORDER BY erstellt_am DESC, id DESC LIMIT 1", (besitzer,)
    ).fetchone()
    return zeile[0] if zeile else None


# ---------------------------------------------------- Dauerhafte Markierungen

def markierung_setzen(conn: sqlite3.Connection, besitzer: str, username: str, markierung: Entscheidung) -> None:
    conn.execute("""
        INSERT INTO account_markierungen (besitzer, username, markierung, gesetzt_am)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(besitzer, username) DO UPDATE SET markierung = excluded.markierung,
                                                      gesetzt_am = excluded.gesetzt_am
    """, (besitzer, username, Entscheidung(markierung).value, _jetzt()))
    conn.commit()


def markierung_loeschen(conn: sqlite3.Connection, besitzer: str, username: str) -> None:
    conn.execute("DELETE FROM account_markierungen WHERE besitzer = ? AND username = ?", (besitzer, username))
    conn.commit()


def markierungen_mehrere_setzen(conn: sqlite3.Connection, besitzer: str, usernames: Iterable[str],
                                markierung: Entscheidung | None) -> int:
    """Massenbearbeitung: setzt dieselbe Markierung für viele Accounts (None = Markierungen entfernen)."""
    namen = [u for u in usernames if u]
    jetzt = _jetzt()
    if markierung is None:
        conn.executemany("DELETE FROM account_markierungen WHERE besitzer = ? AND username = ?",
                         [(besitzer, u) for u in namen])
    else:
        conn.executemany("""
            INSERT INTO account_markierungen (besitzer, username, markierung, gesetzt_am)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(besitzer, username) DO UPDATE SET markierung = excluded.markierung,
                                                          gesetzt_am = excluded.gesetzt_am
        """, [(besitzer, u, Entscheidung(markierung).value, jetzt) for u in namen])
    conn.commit()
    return len(namen)


def markierungen_laden(conn: sqlite3.Connection, besitzer: str) -> dict[str, Entscheidung]:
    cur = conn.execute("SELECT username, markierung FROM account_markierungen WHERE besitzer = ?", (besitzer,))
    return {username: Entscheidung(wert) for username, wert in cur.fetchall()}


def markierungen_mit_datum(conn: sqlite3.Connection, besitzer: str) -> list[tuple[str, Entscheidung, str]]:
    cur = conn.execute(
        "SELECT username, markierung, gesetzt_am FROM account_markierungen WHERE besitzer = ? ORDER BY username",
        (besitzer,),
    )
    return [(u, Entscheidung(m), am) for u, m, am in cur.fetchall()]


# ------------------------------------------------------------ Personen-Listen

def liste_hinzufuegen(conn: sqlite3.Connection, besitzer: str, liste: PersonenListe,
                      usernames: Iterable[str]) -> int:
    """Fügt Nutzernamen einer Liste hinzu (Duplikate werden ignoriert). Gibt die Anzahl neuer Einträge zurück."""
    liste = PersonenListe(liste)
    vorher = conn.total_changes
    jetzt = _jetzt()
    conn.executemany(
        "INSERT OR IGNORE INTO personen_listen (besitzer, liste, username, hinzugefuegt_am) VALUES (?, ?, ?, ?)",
        [(besitzer, liste.value, u, jetzt) for u in usernames if u],
    )
    conn.commit()
    return conn.total_changes - vorher


def liste_entfernen(conn: sqlite3.Connection, besitzer: str, liste: PersonenListe, username: str) -> None:
    conn.execute(
        "DELETE FROM personen_listen WHERE besitzer = ? AND liste = ? AND username = ?",
        (besitzer, PersonenListe(liste).value, username),
    )
    conn.commit()


def liste_mehrere_entfernen(conn: sqlite3.Connection, besitzer: str, liste: PersonenListe,
                            usernames: Iterable[str]) -> int:
    """Massenbearbeitung: entfernt viele Nutzernamen auf einmal aus einer Liste."""
    vorher = conn.total_changes
    conn.executemany(
        "DELETE FROM personen_listen WHERE besitzer = ? AND liste = ? AND username = ?",
        [(besitzer, PersonenListe(liste).value, u) for u in usernames if u],
    )
    conn.commit()
    return conn.total_changes - vorher


def liste_laden(conn: sqlite3.Connection, besitzer: str, liste: PersonenListe) -> dict[str, str]:
    """Gibt {username: hinzugefuegt_am} zurück, alphabetisch sortiert."""
    cur = conn.execute(
        "SELECT username, hinzugefuegt_am FROM personen_listen WHERE besitzer = ? AND liste = ? ORDER BY username",
        (besitzer, PersonenListe(liste).value),
    )
    return dict(cur.fetchall())


# ------------------------------------------------------- Kommentare und Likes

def kommentare_speichern(conn: sqlite3.Connection, besitzer: str, kommentare) -> int:
    """Speichert Kommentare; schon vorhandene (gleiche ID) werden übersprungen. Gibt Anzahl neuer zurück."""
    vorher, jetzt = conn.total_changes, _jetzt()
    conn.executemany(
        "INSERT OR IGNORE INTO kommentare VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(besitzer, k.id, k.text, k.medien_owner, k.zeitstempel, k.datum, k.link, k.quelle, jetzt) for k in kommentare])
    conn.commit()
    return conn.total_changes - vorher


def kommentare_laden(conn: sqlite3.Connection, besitzer: str):
    from core.instagram_export import Kommentar
    cur = conn.execute("SELECT id, text, medien_owner, zeitstempel, datum, link, quelle FROM kommentare "
                       "WHERE besitzer = ? ORDER BY zeitstempel DESC", (besitzer,))
    return [Kommentar(*zeile) for zeile in cur.fetchall()]


def likes_speichern(conn: sqlite3.Connection, besitzer: str, likes) -> int:
    vorher, jetzt = conn.total_changes, _jetzt()
    conn.executemany(
        "INSERT OR IGNORE INTO likes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(besitzer, l.id, l.owner, l.zeitstempel, l.datum, l.link, l.art, jetzt) for l in likes])
    conn.commit()
    return conn.total_changes - vorher


def likes_laden(conn: sqlite3.Connection, besitzer: str):
    from core.instagram_export import Like
    cur = conn.execute("SELECT id, owner, zeitstempel, datum, link, art FROM likes "
                       "WHERE besitzer = ? ORDER BY zeitstempel DESC", (besitzer,))
    return [Like(*zeile) for zeile in cur.fetchall()]


def aktivitaet_leeren(conn: sqlite3.Connection, besitzer: str, art: str) -> None:
    """Alle importierten Kommentare bzw. Likes (samt Entscheidungen) löschen."""
    tabelle = {"kommentar": "kommentare", "like": "likes"}[art]
    conn.execute(f"DELETE FROM {tabelle} WHERE besitzer = ?", (besitzer,))
    conn.execute("DELETE FROM aktivitaet_entscheidungen WHERE besitzer = ? AND art = ?", (besitzer, art))
    conn.commit()


def aktivitaet_entscheidung_setzen(conn: sqlite3.Connection, besitzer: str, art: str, id: str,
                                   entscheidung: str | None) -> None:
    """entscheidung: 'entfernen', 'behalten' oder None (= Entscheidung löschen)."""
    if entscheidung is None:
        conn.execute("DELETE FROM aktivitaet_entscheidungen WHERE besitzer = ? AND art = ? AND id = ?",
                     (besitzer, art, id))
    else:
        conn.execute("""
            INSERT INTO aktivitaet_entscheidungen VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(besitzer, art, id) DO UPDATE SET entscheidung = excluded.entscheidung,
                                                         gesetzt_am = excluded.gesetzt_am
        """, (besitzer, art, id, entscheidung, _jetzt()))
    conn.commit()


def aktivitaet_entscheidungen_laden(conn: sqlite3.Connection, besitzer: str, art: str) -> dict[str, str]:
    cur = conn.execute("SELECT id, entscheidung FROM aktivitaet_entscheidungen WHERE besitzer = ? AND art = ?",
                       (besitzer, art))
    return dict(cur.fetchall())


# ------------------------------------------------------------- Aufräumen

def besitzer_daten_loeschen(conn: sqlite3.Connection, besitzer: str) -> None:
    """Löscht ALLE Daten eines Besitzers – aller Plattformen (z. B. bei Kontolöschung)."""
    muster = (besitzer, besitzer + "#%")          # "konto:5" und "konto:5#tiktok" usw.
    conn.execute("DELETE FROM eintraege WHERE snapshot_id IN "
                 "(SELECT id FROM snapshots WHERE besitzer = ? OR besitzer LIKE ?)", muster)
    for tabelle in ("snapshots", "account_markierungen", "personen_listen", "kommentare", "likes",
                    "aktivitaet_entscheidungen"):
        conn.execute(f"DELETE FROM {tabelle} WHERE besitzer = ? OR besitzer LIKE ?", muster)
    conn.commit()


def anonyme_daten_aufraeumen(conn: sqlite3.Connection, max_alter_stunden: float) -> int:
    """Löscht Daten anonymer Web-Besucher, die älter als max_alter_stunden sind. Gibt Anzahl gelöschter Snapshots zurück."""
    grenze = (datetime.datetime.now() - datetime.timedelta(hours=max_alter_stunden)).isoformat(timespec="seconds")
    alte = [z[0] for z in conn.execute(
        "SELECT id FROM snapshots WHERE besitzer LIKE 'anon:%' AND erstellt_am < ?", (grenze,)
    )]
    for sid in alte:
        conn.execute("DELETE FROM eintraege WHERE snapshot_id = ?", (sid,))
        conn.execute("DELETE FROM snapshots WHERE id = ?", (sid,))
    conn.execute("DELETE FROM account_markierungen WHERE besitzer LIKE 'anon:%' AND gesetzt_am < ?", (grenze,))
    conn.execute("DELETE FROM personen_listen WHERE besitzer LIKE 'anon:%' AND hinzugefuegt_am < ?", (grenze,))
    conn.execute("DELETE FROM kommentare WHERE besitzer LIKE 'anon:%' AND importiert_am < ?", (grenze,))
    conn.execute("DELETE FROM likes WHERE besitzer LIKE 'anon:%' AND importiert_am < ?", (grenze,))
    conn.execute("DELETE FROM aktivitaet_entscheidungen WHERE besitzer LIKE 'anon:%' AND gesetzt_am < ?", (grenze,))
    conn.commit()
    return len(alte)
