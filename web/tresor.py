"""
Tresor: verschlüsselter Speicher pro Konto (nur BETRIEBSMODUS "tresor").

Der Server ist hier reiner Cloud-Speicher – vergleichbar mit einer Datei in
Google Drive. Der Browser verschlüsselt alle Listen (Follower, Following,
Markierungen, Freunde, Blockierte) mit einem Tresor-Passwort, das NIE an den
Server geschickt wird (AES-256-GCM, Schlüssel per PBKDF2 aus dem Passwort,
siehe web/static/tresor/krypto.js). Beim Server kommt nur ein Textblock an:

    FA1.<salt>.<iv>.<geheimtext>        (jeweils Base64url)

Diesen Block speichert der Server unverändert und liefert ihn beim nächsten
Besuch wieder aus. Er kann ihn nicht entschlüsseln, durchsucht ihn nicht und
wertet nichts aus. Damit er nicht versehentlich doch Klartext annimmt (z. B.
durch einen Fehler im Browser-Code), prüft `pruefen()` das Format und lehnt
alles ab, was nicht wie ein verschlüsselter Block aussieht.

Gleichzeitiges Bearbeiten in zwei Browser-Tabs: Jeder Tresor hat eine
Versionsnummer. Wer speichert, schickt mit, auf welcher Version seine
Änderungen beruhen. Passt das nicht mehr, gibt es einen Konflikt (HTTP 409)
statt stillem Überschreiben ("optimistic locking").
"""

import datetime
import re
import sqlite3

FORMAT_PRAEFIX = "FA1."
# Präfix + drei Base64url-Teile, getrennt durch Punkte
_FORMAT = re.compile(r"^FA1\.[A-Za-z0-9_-]{16,64}\.[A-Za-z0-9_-]{12,32}\.[A-Za-z0-9_-]{16,}$")


class TresorFehler(ValueError):
    pass


class VersionsKonflikt(TresorFehler):
    """Der Tresor wurde inzwischen anderswo gespeichert (z. B. in einem zweiten Tab)."""
    def __init__(self, aktuelle_version: int):
        super().__init__("Der Tresor wurde inzwischen an anderer Stelle geändert.")
        self.aktuelle_version = aktuelle_version


def init_tresor(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tresore (
            konto_id INTEGER PRIMARY KEY,
            inhalt TEXT NOT NULL,
            version INTEGER NOT NULL,
            groesse INTEGER NOT NULL,
            aktualisiert_am TEXT NOT NULL
        )
    """)
    conn.commit()


def _jetzt() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def pruefen(inhalt: object, max_kb: int) -> str:
    """Nimmt nur verschlüsselte Blöcke im erwarteten Format an. Gibt den Block zurück."""
    if not isinstance(inhalt, str) or not inhalt.startswith(FORMAT_PRAEFIX):
        raise TresorFehler("Unbekanntes Format – es werden nur verschlüsselte Tresore gespeichert.")
    if len(inhalt) > max_kb * 1024:
        raise TresorFehler(f"Der Tresor ist zu groß (max. {max_kb // 1024} MB). Bitte alte Auswertungen löschen.")
    if not _FORMAT.match(inhalt):
        raise TresorFehler("Unbekanntes Format – es werden nur verschlüsselte Tresore gespeichert.")
    return inhalt


def laden(conn: sqlite3.Connection, konto_id: int) -> dict | None:
    zeile = conn.execute("SELECT inhalt, version, groesse, aktualisiert_am FROM tresore WHERE konto_id = ?",
                         (konto_id,)).fetchone()
    if zeile is None:
        return None
    return {"inhalt": zeile[0], "version": zeile[1], "groesse": zeile[2], "aktualisiert_am": zeile[3]}


def info(conn: sqlite3.Connection, konto_id: int) -> dict | None:
    """Wie laden(), aber ohne den Inhalt (für Konto-Seite und Verwaltung)."""
    zeile = conn.execute("SELECT version, groesse, aktualisiert_am FROM tresore WHERE konto_id = ?",
                         (konto_id,)).fetchone()
    return None if zeile is None else {"version": zeile[0], "groesse": zeile[1], "aktualisiert_am": zeile[2]}


def speichern(conn: sqlite3.Connection, konto_id: int, inhalt: str, basis_version: int | None,
              max_kb: int) -> int:
    """
    Speichert den Block und gibt die neue Versionsnummer zurück.
    basis_version = Version, die der Browser zuletzt geladen hat (None/0 = neuer Tresor).
    """
    pruefen(inhalt, max_kb)
    vorhanden = info(conn, konto_id)
    aktuell = vorhanden["version"] if vorhanden else 0
    if (basis_version or 0) != aktuell:
        raise VersionsKonflikt(aktuell)
    neu = aktuell + 1
    if vorhanden:
        # "AND version = ?" schützt auch gegen zwei gleichzeitige Anfragen im selben Moment
        cur = conn.execute("UPDATE tresore SET inhalt = ?, version = ?, groesse = ?, aktualisiert_am = ? "
                           "WHERE konto_id = ? AND version = ?",
                           (inhalt, neu, len(inhalt), _jetzt(), konto_id, aktuell))
        if cur.rowcount != 1:
            raise VersionsKonflikt(info(conn, konto_id)["version"])
    else:
        try:
            conn.execute("INSERT INTO tresore (konto_id, inhalt, version, groesse, aktualisiert_am) "
                         "VALUES (?, ?, ?, ?, ?)", (konto_id, inhalt, neu, len(inhalt), _jetzt()))
        except sqlite3.IntegrityError:
            raise VersionsKonflikt(info(conn, konto_id)["version"]) from None
    conn.commit()
    return neu


def loeschen(conn: sqlite3.Connection, konto_id: int) -> bool:
    cur = conn.execute("DELETE FROM tresore WHERE konto_id = ?", (konto_id,))
    conn.commit()
    return cur.rowcount > 0


def statistik(conn: sqlite3.Connection) -> tuple[int, int]:
    """(Anzahl Tresore, Gesamtgröße in Bytes) – für den Betreiber, ohne Inhalte."""
    anzahl, summe = conn.execute("SELECT COUNT(*), COALESCE(SUM(groesse), 0) FROM tresore").fetchone()
    return anzahl, summe
