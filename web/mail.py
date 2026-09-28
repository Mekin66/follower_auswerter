"""
E-Mails verschicken (Bestätigungs-Link, Passwort vergessen).

Nutzt nur die Python-Standardbibliothek (smtplib + email). Ist kein
SMTP-Server eingetragen (SMTP_HOST leer), läuft der TESTMODUS: Die Mail wird
nicht verschickt, sondern ins Server-Log geschrieben und im "Postausgang"
gespeichert (für automatische Tests).
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

log = logging.getLogger("follower_auswertung.mail")


class MailFehler(RuntimeError):
    pass


def ist_testmodus(cfg: dict) -> bool:
    return not cfg.get("SMTP_HOST")


def senden(cfg: dict, an: str, betreff: str, text: str, postausgang: list | None = None) -> None:
    """Schickt eine reine Text-Mail. Wirft MailFehler, wenn der Versand scheitert."""
    absender = cfg.get("SMTP_ABSENDER") or cfg.get("BETREIBER_EMAIL") or "noreply@localhost"
    name, adresse = parseaddr(absender)
    nachricht = EmailMessage()
    nachricht["From"] = formataddr((name or "Follower-Auswertung", adresse))
    nachricht["To"] = an
    nachricht["Subject"] = betreff
    nachricht["Date"] = formatdate(localtime=True)
    nachricht["Message-ID"] = make_msgid(domain=adresse.split("@")[-1] or None)
    nachricht.set_content(text)

    if ist_testmodus(cfg):
        log.warning("TESTMODUS (kein SMTP_HOST) – Mail an %s nicht verschickt:\n%s\n%s", an, betreff, text)
        print(f"\n===== E-Mail (Testmodus) an {an} =====\n{betreff}\n\n{text}\n=====\n", flush=True)
        if postausgang is not None:
            postausgang.append({"an": an, "betreff": betreff, "text": text})
            del postausgang[:-50]                       # nur die letzten 50 behalten
        return

    art = (cfg.get("SMTP_VERSCHLUESSELUNG") or "starttls").lower()
    kontext = ssl.create_default_context()
    try:
        if art == "ssl":
            server = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=20, context=kontext)
        else:
            server = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=20)
        with server:
            if art == "starttls":
                server.starttls(context=kontext)
            if cfg.get("SMTP_BENUTZER"):
                server.login(cfg["SMTP_BENUTZER"], cfg.get("SMTP_PASSWORT", ""))
            server.send_message(nachricht)
    except (OSError, smtplib.SMTPException) as e:
        log.error("Mailversand an %s fehlgeschlagen: %s", an, e)
        raise MailFehler(str(e)) from e


# ------------------------------------------------------------ Texte
def text_bestaetigung(benutzername: str, link: str, stunden: int) -> tuple[str, str]:
    return ("Bitte bestätige deine E-Mail-Adresse", f"""Hallo {benutzername},

bitte bestätige deine E-Mail-Adresse für die Follower-Auswertung. Klicke dazu auf diesen Link:

{link}

Der Link ist {stunden} Stunden gültig. Danach wird das unbestätigte Konto automatisch gelöscht.

Du hast dich nicht registriert? Dann ignoriere diese E-Mail einfach – ohne Bestätigung passiert nichts.
""")


def text_schon_registriert(link_anmelden: str, link_passwort: str) -> tuple[str, str]:
    return ("Du hast bereits ein Konto", f"""Hallo,

jemand (vermutlich du) wollte mit dieser E-Mail-Adresse ein neues Konto erstellen.
Es gibt aber schon ein Konto mit dieser Adresse.

Anmelden: {link_anmelden}
Passwort vergessen? {link_passwort}

Warst du das nicht? Dann ignoriere diese E-Mail einfach.
""")


def text_passwort(benutzername: str, link: str, minuten: int) -> tuple[str, str]:
    return ("Neues Passwort festlegen", f"""Hallo {benutzername},

über diesen Link kannst du ein neues Passwort festlegen:

{link}

Der Link ist {minuten} Minuten gültig und funktioniert nur einmal.

Du hast das nicht angefordert? Dann ignoriere diese E-Mail – dein Passwort bleibt unverändert.
""")


def text_neue_adresse(benutzername: str, link: str, stunden: int) -> tuple[str, str]:
    return ("Neue E-Mail-Adresse bestätigen", f"""Hallo {benutzername},

bitte bestätige deine neue E-Mail-Adresse mit diesem Link:

{link}

Der Link ist {stunden} Stunden gültig. Bis dahin bleibt deine bisherige Adresse aktiv.
""")
