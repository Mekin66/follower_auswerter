"""
Benutzerkonten der Web-App (nur aktiv, wenn einstellungen.ACCOUNTS_AKTIVIERT).

Gespeichert werden: Benutzername, Passwort-Hash (nie das Passwort selbst),
E-Mail-Adresse, Bestätigungs-Zeitpunkt und – nur wenn angehakt – die
Einwilligung in Neuigkeiten per E-Mail. Kein Klarname.

Freischaltung (Double-Opt-in): Neue Konten haben freigeschaltet = 0, bis der
Link aus der Bestätigungs-Mail angeklickt wurde. Erst dann ist ein Login
möglich. Unbestätigte Konten werden nach BESTAETIGUNG_GUELTIG_STUNDEN gelöscht.
Alte Konten (vor Version 5, ohne E-Mail) bleiben freigeschaltet.
"""

import datetime
import hashlib
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from core import history_store

MIN_PASSWORT_LAENGE = 8
_NAME_MUSTER = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
_EMAIL_MUSTER = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class KontoFehler(ValueError):
    pass


class EmailVergeben(KontoFehler):
    """E-Mail gehört schon zu einem Konto. Die Web-App verrät das NICHT auf der Seite
    (sonst könnte jeder testen, wer die App nutzt), sondern schickt dem Inhaber eine Info-Mail."""
    def __init__(self, konto_id: int):
        super().__init__("E-Mail-Adresse bereits vergeben.")
        self.konto_id = konto_id


def init_konten(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS konten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            benutzername TEXT NOT NULL UNIQUE COLLATE NOCASE,
            passwort_hash TEXT NOT NULL,
            erstellt_am TEXT NOT NULL
        )
    """)
    spalten = {z[1] for z in conn.execute("PRAGMA table_info(konten)")}
    if "letzter_login" not in spalten:                      # Migration für ältere Datenbanken
        conn.execute("ALTER TABLE konten ADD COLUMN letzter_login TEXT")
        conn.execute("UPDATE konten SET letzter_login = erstellt_am WHERE letzter_login IS NULL")
    # Version 5: E-Mail + Freischaltung. DEFAULT 1 -> bestehende Konten bleiben nutzbar.
    for spalte, typ in (("email", "TEXT"), ("email_bestaetigt_am", "TEXT"), ("email_neu", "TEXT"),
                        ("newsletter_am", "TEXT"), ("freigeschaltet", "INTEGER NOT NULL DEFAULT 1")):
        if spalte not in spalten:
            conn.execute(f"ALTER TABLE konten ADD COLUMN {spalte} {typ}")
    # Jede Adresse nur einmal (Groß-/Kleinschreibung egal); NULL (keine Adresse) darf mehrfach vorkommen
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_konten_email ON konten(email COLLATE NOCASE) "
                 "WHERE email IS NOT NULL")
    conn.commit()


def email_normalisieren(email: str | None) -> str:
    """Leerzeichen weg, alles klein. Wirft KontoFehler bei offensichtlich falschen Adressen."""
    email = (email or "").strip().lower()
    if len(email) > 254 or not _EMAIL_MUSTER.match(email):
        raise KontoFehler("Bitte eine gültige E-Mail-Adresse eingeben.")
    return email


def _jetzt() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def login_merken(conn: sqlite3.Connection, konto_id: int) -> None:
    conn.execute("UPDATE konten SET letzter_login = ? WHERE id = ?", (_jetzt(), konto_id))
    conn.commit()


def inaktive_konten_loeschen(conn: sqlite3.Connection, tage: int) -> int:
    """Löscht Konten (mit allen Daten), die sich seit `tage` Tagen nicht angemeldet haben. 0 = aus."""
    if tage <= 0:
        return 0
    grenze = (datetime.datetime.now() - datetime.timedelta(days=tage)).isoformat(timespec="seconds")
    alte = [z[0] for z in conn.execute(
        "SELECT id FROM konten WHERE COALESCE(letzter_login, erstellt_am) < ?", (grenze,))]
    for konto_id in alte:
        konto_loeschen(conn, konto_id)
    return len(alte)


def besitzer_id(konto_id: int) -> str:
    return f"konto:{konto_id}"


def _passwort_pruefen_regeln(passwort: str, passwort2: str, wort: str = "Das Passwort") -> None:
    if len(passwort or "") < MIN_PASSWORT_LAENGE:
        raise KontoFehler(f"{wort} muss mindestens {MIN_PASSWORT_LAENGE} Zeichen lang sein.")
    if passwort != passwort2:
        raise KontoFehler("Die beiden Passwörter stimmen nicht überein.")


def registrieren(conn: sqlite3.Connection, benutzername: str, passwort: str, passwort2: str,
                 email: str | None = None, email_pflicht: bool = False, freigeschaltet: bool = True,
                 newsletter: bool = False) -> int:
    """
    Legt ein Konto an und gibt die ID zurück.
    freigeschaltet=False -> Login erst nach Klick auf den Bestätigungs-Link.
    Wirft KontoFehler (Eingabe falsch) bzw. EmailVergeben (Adresse existiert schon).
    """
    benutzername = (benutzername or "").strip()
    if not _NAME_MUSTER.match(benutzername):
        raise KontoFehler("Benutzername: 3–30 Zeichen, nur Buchstaben, Ziffern, Punkt, Unterstrich, Bindestrich.")
    if conn.execute("SELECT 1 FROM konten WHERE benutzername = ?", (benutzername,)).fetchone():
        raise KontoFehler("Dieser Benutzername ist bereits vergeben.")
    email = email_normalisieren(email) if (email or "").strip() or email_pflicht else None
    _passwort_pruefen_regeln(passwort, passwort2)
    if email:
        vorhanden = konto_per_email(conn, email)
        if vorhanden:
            raise EmailVergeben(vorhanden[0])
    jetzt = _jetzt()
    try:
        cur = conn.execute(
            "INSERT INTO konten (benutzername, passwort_hash, erstellt_am, email, freigeschaltet, newsletter_am) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (benutzername, generate_password_hash(passwort), jetzt, email, int(freigeschaltet),
             jetzt if newsletter else None),
        )
    except sqlite3.IntegrityError:                     # gleichzeitige Registrierung mit gleichem Namen
        raise KontoFehler("Dieser Benutzername ist bereits vergeben.") from None
    conn.commit()
    return cur.lastrowid


def anmelden(conn: sqlite3.Connection, name_oder_email: str, passwort: str) -> int | None:
    """Login mit Benutzername ODER E-Mail. Gibt die Konto-ID zurück (auch wenn noch nicht freigeschaltet)."""
    eingabe = (name_oder_email or "").strip()
    spalte = "email" if "@" in eingabe else "benutzername"
    zeile = conn.execute(
        f"SELECT id, passwort_hash FROM konten WHERE {spalte} = ? COLLATE NOCASE", (eingabe,)
    ).fetchone()
    if zeile and check_password_hash(zeile[1], passwort or ""):
        return zeile[0]
    return None


def ist_freigeschaltet(conn: sqlite3.Connection, konto_id: int) -> bool:
    zeile = conn.execute("SELECT freigeschaltet FROM konten WHERE id = ?", (konto_id,)).fetchone()
    return bool(zeile and zeile[0])


def konto_info(conn: sqlite3.Connection, konto_id: int) -> dict | None:
    """Alle Konto-Angaben als dict (für die Konto-Seite und den Daten-Export)."""
    zeile = conn.execute(
        "SELECT id, benutzername, erstellt_am, letzter_login, email, email_bestaetigt_am, email_neu, "
        "newsletter_am, freigeschaltet FROM konten WHERE id = ?", (konto_id,)).fetchone()
    if not zeile:
        return None
    namen = ("id", "benutzername", "erstellt_am", "letzter_login", "email", "email_bestaetigt_am", "email_neu",
             "newsletter_am", "freigeschaltet")
    return dict(zip(namen, zeile))


def konto_per_email(conn: sqlite3.Connection, email: str) -> tuple[int, str] | None:
    return conn.execute("SELECT id, benutzername FROM konten WHERE email = ? COLLATE NOCASE",
                        ((email or "").strip(),)).fetchone()


def konto_per_name_oder_email(conn: sqlite3.Connection, eingabe: str) -> tuple[int, str, str | None] | None:
    eingabe = (eingabe or "").strip()
    spalte = "email" if "@" in eingabe else "benutzername"
    return conn.execute(f"SELECT id, benutzername, email FROM konten WHERE {spalte} = ? COLLATE NOCASE",
                        (eingabe,)).fetchone()


def email_bestaetigen(conn: sqlite3.Connection, konto_id: int, email: str) -> str:
    """
    Wird aufgerufen, wenn der Link aus der Mail angeklickt wurde.
    Rückgabe: "freigeschaltet" (Konto jetzt aktiv), "geaendert" (neue Adresse übernommen),
              "schon" (war schon bestätigt) oder "ungueltig".
    """
    info = konto_info(conn, konto_id)
    if not info:
        return "ungueltig"
    if info["email_neu"] and info["email_neu"] == email:
        if konto_per_email(conn, email):
            conn.execute("UPDATE konten SET email_neu = NULL WHERE id = ?", (konto_id,))
            conn.commit()
            return "ungueltig"                        # inzwischen von jemand anderem bestätigt
        conn.execute("UPDATE konten SET email = ?, email_neu = NULL, email_bestaetigt_am = ?, freigeschaltet = 1 "
                     "WHERE id = ?", (email, _jetzt(), konto_id))
        conn.commit()
        return "geaendert"
    if info["email"] != email:
        return "ungueltig"
    if info["freigeschaltet"] and info["email_bestaetigt_am"]:
        return "schon"
    conn.execute("UPDATE konten SET freigeschaltet = 1, email_bestaetigt_am = COALESCE(email_bestaetigt_am, ?) "
                 "WHERE id = ?", (_jetzt(), konto_id))
    conn.commit()
    return "freigeschaltet"


def email_aendern_anfordern(conn: sqlite3.Connection, konto_id: int, neue_email: str, passwort: str) -> str:
    """Merkt die neue Adresse vor (email_neu). Übernommen wird sie erst nach Klick auf den Link."""
    if not passwort_pruefen(conn, konto_id, passwort):
        raise KontoFehler("Das Passwort ist falsch.")
    neue_email = email_normalisieren(neue_email)
    info = konto_info(conn, konto_id)
    if info["email"] == neue_email:
        raise KontoFehler("Das ist bereits deine E-Mail-Adresse.")
    vorhanden = konto_per_email(conn, neue_email)
    if vorhanden:
        raise EmailVergeben(vorhanden[0])
    conn.execute("UPDATE konten SET email_neu = ? WHERE id = ?", (neue_email, konto_id))
    conn.commit()
    return neue_email


def newsletter_setzen(conn: sqlite3.Connection, konto_id: int, ja: bool) -> None:
    """Einwilligung in Neuigkeiten per E-Mail erteilen (mit Zeitpunkt) bzw. widerrufen."""
    conn.execute("UPDATE konten SET newsletter_am = ? WHERE id = ?", (_jetzt() if ja else None, konto_id))
    conn.commit()


def passwort_fingerabdruck(conn: sqlite3.Connection, konto_id: int) -> str:
    """
    Kurzer Fingerabdruck des aktuellen Passwort-Hashes. Er steckt im "Passwort vergessen"-Link.
    Nach dem Ändern des Passworts passt er nicht mehr -> der Link funktioniert nur EINMAL.
    """
    zeile = conn.execute("SELECT passwort_hash FROM konten WHERE id = ?", (konto_id,)).fetchone()
    return hashlib.sha256(zeile[0].encode()).hexdigest()[:16] if zeile else ""


def passwort_setzen(conn: sqlite3.Connection, konto_id: int, neu: str, neu2: str) -> None:
    """Neues Passwort ohne das alte (nur über den geprüften Link aus der Mail erreichbar)."""
    _passwort_pruefen_regeln(neu, neu2, "Das neue Passwort")
    conn.execute("UPDATE konten SET passwort_hash = ? WHERE id = ?", (generate_password_hash(neu), konto_id))
    conn.commit()


def unbestaetigte_konten_loeschen(conn: sqlite3.Connection, stunden: int) -> int:
    """Löscht Konten, deren E-Mail nicht innerhalb von `stunden` bestätigt wurde."""
    if stunden <= 0:
        return 0
    grenze = (datetime.datetime.now() - datetime.timedelta(hours=stunden)).isoformat(timespec="seconds")
    alte = [z[0] for z in conn.execute(
        "SELECT id FROM konten WHERE freigeschaltet = 0 AND erstellt_am < ?", (grenze,))]
    for konto_id in alte:
        konto_loeschen(conn, konto_id)
    return len(alte)


def email_liste(conn: sqlite3.Connection, nur_newsletter: bool = False) -> list[tuple[str, str, str | None]]:
    """[(benutzername, email, newsletter_am)] aller bestätigten Adressen – für den Betreiber."""
    sql = ("SELECT benutzername, email, newsletter_am FROM konten "
           "WHERE email IS NOT NULL AND email_bestaetigt_am IS NOT NULL")
    if nur_newsletter:
        sql += " AND newsletter_am IS NOT NULL"
    return conn.execute(sql + " ORDER BY erstellt_am").fetchall()


def konto_laden(conn: sqlite3.Connection, konto_id: int) -> tuple[int, str, str] | None:
    return conn.execute(
        "SELECT id, benutzername, erstellt_am FROM konten WHERE id = ?", (konto_id,)
    ).fetchone()


def passwort_pruefen(conn: sqlite3.Connection, konto_id: int, passwort: str) -> bool:
    zeile = conn.execute("SELECT passwort_hash FROM konten WHERE id = ?", (konto_id,)).fetchone()
    return bool(zeile and check_password_hash(zeile[0], passwort or ""))


def passwort_aendern(conn: sqlite3.Connection, konto_id: int, alt: str, neu: str, neu2: str) -> None:
    if not passwort_pruefen(conn, konto_id, alt):
        raise KontoFehler("Das aktuelle Passwort ist falsch.")
    passwort_setzen(conn, konto_id, neu, neu2)


def konto_loeschen(conn: sqlite3.Connection, konto_id: int) -> None:
    """Löscht das Konto und ALLE zugehörigen Daten (Recht auf Löschung, DSGVO Art. 17)."""
    history_store.besitzer_daten_loeschen(conn, besitzer_id(konto_id))
    conn.execute("DELETE FROM konten WHERE id = ?", (konto_id,))
    conn.commit()


def anonyme_daten_uebernehmen(conn: sqlite3.Connection, anon_besitzer: str, konto_id: int) -> int:
    """Nach Login/Registrierung: Auswertungen der anonymen Sitzung ins Konto übernehmen."""
    anon_basis = anon_besitzer.split("#", 1)[0]
    ziel = besitzer_id(konto_id)
    # "anon:x" -> "konto:5" und "anon:x#tiktok" -> "konto:5#tiktok"
    muster = (ziel, anon_basis, anon_basis, anon_basis + "#%")
    cur = conn.execute(
        "UPDATE snapshots SET besitzer = ? || substr(besitzer, length(?) + 1) WHERE besitzer = ? OR besitzer LIKE ?",
        muster)
    anzahl = cur.rowcount
    for tabelle in ("kommentare", "likes", "aktivitaet_entscheidungen"):   # importierte Kommentare/Likes mitnehmen
        conn.execute(f"UPDATE OR IGNORE {tabelle} SET besitzer = ? || substr(besitzer, length(?) + 1) "
                     "WHERE besitzer = ? OR besitzer LIKE ?", muster)
    conn.commit()
    return anzahl
