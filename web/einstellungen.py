"""
Zentrale Einstellungen der Web-App.

┌──────────────────────────────────────────────────────────────────────┐
│  KONTO-FUNKTION AN/AUS: einfach ACCOUNTS_AKTIVIERT unten umstellen.   │
│                                                                      │
│  False  -> reine anonyme Nutzung. Keine Konten, keine dauerhaften     │
│            Markierungen, keine Blockiert-Listen, keine Kategorie-     │
│            Auswahl. Hochgeladene Daten werden nach                    │
│            ANONYM_AUFBEWAHRUNG_STUNDEN automatisch gelöscht.          │
│  True   -> Registrieren/Anmelden ist möglich. Angemeldete Nutzer      │
│            bekommen alle Funktionen (dauerhafte Markierungen,         │
│            Kategorie-Auswahl, Blockiert-Listen, manuelle Freunde).    │
│            Ohne Anmeldung funktioniert die Seite weiterhin anonym.    │
│                                                                      │
│  E-Mail-Bestätigung & SMTP: siehe Abschnitt "E-Mail bei Konten".      │
│                                                                      │
│  Alternativ ohne Code-Änderung per Umgebungsvariable überschreiben:   │
│      ACCOUNTS_AKTIVIERT=1   (oder 0)                                  │
└──────────────────────────────────────────────────────────────────────┘
"""

import os
import secrets
from pathlib import Path


def _bool(name: str, standard: bool) -> bool:
    wert = os.environ.get(name)
    if wert is None:
        return standard
    return wert.strip().lower() in ("1", "true", "ja", "yes", "on")


# ============================ HIER UMSCHALTEN ============================
ACCOUNTS_AKTIVIERT: bool = _bool("ACCOUNTS_AKTIVIERT", True)
# =========================================================================

# Dürfen sich neue Nutzer selbst registrieren? (Nur relevant, wenn Konten aktiv.)
# Auf False setzen, wenn z. B. nur du und ausgewählte Leute Konten haben sollen.
REGISTRIERUNG_OFFEN: bool = _bool("REGISTRIERUNG_OFFEN", True)

# ------------------------------------------------------------ E-Mail bei Konten
# E_MAIL_PFLICHT        -> bei der Registrierung muss eine E-Mail-Adresse angegeben werden.
# E_MAIL_BESTAETIGUNG   -> das Konto kann erst benutzt werden, wenn der Link in der
#                          Bestätigungs-Mail angeklickt wurde (Double-Opt-in).
#                          Setzt E_MAIL_PFLICHT voraus.
# NEWSLETTER_ABFRAGEN   -> zusätzliches, freiwilliges Häkchen "Neuigkeiten per E-Mail".
#                          Werbe-Mails NUR an Nutzer mit diesem Häkchen (§ 7 UWG)!
E_MAIL_PFLICHT: bool = _bool("E_MAIL_PFLICHT", True)
E_MAIL_BESTAETIGUNG: bool = _bool("E_MAIL_BESTAETIGUNG", True)
NEWSLETTER_ABFRAGEN: bool = _bool("NEWSLETTER_ABFRAGEN", False)
# So lange ist ein Bestätigungs-Link gültig. Unbestätigte Konten werden danach gelöscht.
BESTAETIGUNG_GUELTIG_STUNDEN: int = int(os.environ.get("BESTAETIGUNG_GUELTIG_STUNDEN", "48"))
# So lange ist ein "Passwort vergessen"-Link gültig.
PASSWORT_LINK_GUELTIG_MINUTEN: int = int(os.environ.get("PASSWORT_LINK_GUELTIG_MINUTEN", "60"))

# Öffentliche Adresse der Seite – wird für die Links in den E-Mails benutzt,
# z. B. "https://follower.example.de". Leer = Adresse aus der Anfrage (nur zum Testen!).
OEFFENTLICHE_URL: str = os.environ.get("OEFFENTLICHE_URL", "").rstrip("/")

# Postausgangs-Server (SMTP) für die E-Mails. Die Daten bekommst du von deinem
# Mail-Anbieter (Strato, IONOS, Hetzner, Brevo, Mailjet …).
# SMTP_HOST leer = TESTMODUS: Mails werden nicht verschickt, sondern im
# Server-Log ausgegeben (dort steht dann der Bestätigungs-Link).
SMTP_HOST: str = os.environ.get("SMTP_HOST", "")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_BENUTZER: str = os.environ.get("SMTP_BENUTZER", "")
SMTP_PASSWORT: str = os.environ.get("SMTP_PASSWORT", "")
SMTP_VERSCHLUESSELUNG: str = os.environ.get("SMTP_VERSCHLUESSELUNG", "starttls")   # starttls | ssl | keine
SMTP_ABSENDER: str = os.environ.get("SMTP_ABSENDER", "")          # z. B. "Follower-Auswertung <noreply@example.de>"

# Automatische "Scheint deaktiviert"-Prüfung über instagram.com.
# Auf einem öffentlichen Server laufen ALLE Prüfungen über dieselbe Server-IP,
# Instagram sperrt die dann sehr schnell. Für öffentliche Server eher False.
AUTO_CHECK_AKTIVIERT: bool = _bool("AUTO_CHECK_AKTIVIERT", True)
AUTO_CHECK_MAX_ACCOUNTS: int = int(os.environ.get("AUTO_CHECK_MAX_ACCOUNTS", "300"))
AUTO_CHECK_PAUSE_SEKUNDEN: float = float(os.environ.get("AUTO_CHECK_PAUSE_SEKUNDEN", "3"))

# Wie lange Daten anonymer Besucher gespeichert bleiben
ANONYM_AUFBEWAHRUNG_STUNDEN: float = float(os.environ.get("ANONYM_AUFBEWAHRUNG_STUNDEN", "24"))

# Maximale Upload-Größe. Tipp: Bei Instagram nur "Follower und gefolgte
# Personen" exportieren, dann ist das ZIP meist nur wenige hundert KB groß.
MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "200"))

# Speicherort der Datenbank (auf Servern auf ein dauerhaftes Volume legen!)
DATEN_ORDNER = Path(os.environ.get("DATEN_ORDNER", Path(__file__).resolve().parent / "daten"))
DATENBANK_PFAD = Path(os.environ.get("DATENBANK_PFAD", DATEN_ORDNER / "web.sqlite3"))

# Nur auf True setzen, wenn die Seite ausschließlich über HTTPS erreichbar ist
COOKIES_NUR_HTTPS: bool = _bool("COOKIES_NUR_HTTPS", True)

# Cookie-Banner (siehe docs/VEROEFFENTLICHEN.md, Abschnitt DSGVO):
#   "aus"          -> kein Banner. Richtig, solange NUR das technisch notwendige
#                     Sitzungs-Cookie benutzt wird (so ist die App gebaut).
#   "hinweis"      -> kleiner Info-Hinweis "nur notwendige Cookies" mit OK-Knopf.
#   "einwilligung" -> echter Einwilligungs-Banner (Alle akzeptieren / Nur notwendige).
#                     Nötig, sobald du Statistik, Werbung, Videos o. Ä. einbindest.
#                     Diese Dienste gehören in templates/optionale_dienste.html und
#                     werden NUR nach Einwilligung geladen.
COOKIE_BANNER: str = os.environ.get("COOKIE_BANNER", "aus").strip().lower()

# Konten, in die sich so lange niemand eingeloggt hat, werden samt Daten gelöscht
# (Grundsatz der Speicherbegrenzung, Art. 5 DSGVO). 0 = nie automatisch löschen.
KONTO_LOESCHEN_NACH_TAGEN: int = int(os.environ.get("KONTO_LOESCHEN_NACH_TAGEN", "365"))

# Angaben für Impressum/Datenschutz (in Deutschland Pflicht bei öffentlichem Angebot)
BETREIBER_NAME: str = os.environ.get("BETREIBER_NAME", "")
BETREIBER_ADRESSE: str = os.environ.get("BETREIBER_ADRESSE", "")
BETREIBER_EMAIL: str = os.environ.get("BETREIBER_EMAIL", "")
HOSTER_NAME: str = os.environ.get("HOSTER_NAME", "")
HOSTER_SITZ: str = os.environ.get("HOSTER_SITZ", "")                    # z. B. "Deutschland" oder "USA, Server in Frankfurt"
AUFSICHTSBEHOERDE: str = os.environ.get("AUFSICHTSBEHOERDE", "")        # Datenschutzbehörde deines Bundeslandes


def secret_key() -> str:
    """
    Geheimer Schlüssel für signierte Cookies. Auf dem Server per
    Umgebungsvariable SECRET_KEY setzen; sonst wird einmalig einer erzeugt
    und im Datenordner gespeichert (damit Logins einen Neustart überleben).
    """
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    datei = DATEN_ORDNER / ".secret_key"
    DATEN_ORDNER.mkdir(parents=True, exist_ok=True)
    if datei.exists():
        return datei.read_text().strip()
    schluessel = secrets.token_hex(32)
    datei.write_text(schluessel)
    return schluessel
