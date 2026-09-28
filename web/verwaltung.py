"""
Verwaltung für den Betreiber – auf dem Server in der Konsole ausführen.

    python -m web.verwaltung konten                 # alle Konten anzeigen
    python -m web.verwaltung emails                 # bestätigte E-Mail-Adressen
    python -m web.verwaltung emails --newsletter    # nur mit Einwilligung für Neuigkeiten
    python -m web.verwaltung emails --csv adressen.csv
    python -m web.verwaltung loeschen BENUTZERNAME  # Konto samt Daten löschen
    python -m web.verwaltung mailtest DEINE@ADRESSE # prüft die SMTP-Einstellungen

Mit Docker:  docker compose exec web python -m web.verwaltung konten

WICHTIG (DSGVO/UWG): Werbung oder Newsletter nur an Adressen aus
"emails --newsletter" schicken. Die übrigen Adressen dürfen nur für das Konto
selbst (Bestätigung, Passwort, wichtige Hinweise zum Dienst) benutzt werden.
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web import einstellungen, konten, mail  # noqa: E402


def _verbindung() -> sqlite3.Connection:
    conn = sqlite3.connect(einstellungen.DATENBANK_PFAD)
    konten.init_konten(conn)
    return conn


def befehl_konten(_args) -> None:
    conn = _verbindung()
    zeilen = conn.execute("SELECT id, benutzername, email, freigeschaltet, erstellt_am, letzter_login, newsletter_am "
                          "FROM konten ORDER BY id").fetchall()
    print(f"{'ID':>4}  {'Benutzername':<20} {'E-Mail':<32} {'aktiv':<5} {'erstellt':<10} {'letzter Login':<10} NL")
    for kid, name, email, aktiv, erstellt, login, nl in zeilen:
        print(f"{kid:>4}  {name:<20} {email or '-':<32} {'ja' if aktiv else 'nein':<5} {erstellt[:10]:<10} "
              f"{(login or '')[:10]:<10} {'ja' if nl else ''}")
    print(f"\n{len(zeilen)} Konto/Konten")


def befehl_emails(args) -> None:
    liste = konten.email_liste(_verbindung(), nur_newsletter=args.newsletter)
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            schreiber = csv.writer(f, delimiter=";")
            schreiber.writerow(["benutzername", "email", "newsletter_einwilligung_am"])
            schreiber.writerows(liste)
        print(f"{len(liste)} Adressen gespeichert in {args.csv}")
    else:
        for name, email, nl in liste:
            print(f"{email:<40} {name:<20} {('Newsletter seit ' + nl[:10]) if nl else ''}")
        print(f"\n{len(liste)} Adresse(n)")


def befehl_loeschen(args) -> None:
    conn = _verbindung()
    treffer = konten.konto_per_name_oder_email(conn, args.name)
    if not treffer:
        sys.exit("Konto nicht gefunden.")
    if input(f"Konto '{treffer[1]}' und ALLE Daten löschen? (ja/nein) ").strip().lower() != "ja":
        sys.exit("Abgebrochen.")
    konten.konto_loeschen(conn, treffer[0])
    print("Gelöscht.")


def befehl_mailtest(args) -> None:
    cfg = {n: getattr(einstellungen, n) for n in dir(einstellungen) if n.isupper()}
    if mail.ist_testmodus(cfg):
        print("Hinweis: SMTP_HOST ist leer -> Testmodus, die Mail wird nur hier ausgegeben.")
    mail.senden(cfg, args.adresse, "Test der Follower-Auswertung", "Wenn du das liest, funktioniert der Mailversand.")
    print("Gesendet.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verwaltung der Follower-Auswertung (Web)")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("konten", help="alle Konten anzeigen").set_defaults(f=befehl_konten)
    p = unter.add_parser("emails", help="bestätigte E-Mail-Adressen")
    p.add_argument("--newsletter", action="store_true", help="nur mit Einwilligung für Neuigkeiten")
    p.add_argument("--csv", help="als CSV-Datei speichern")
    p.set_defaults(f=befehl_emails)
    p = unter.add_parser("loeschen", help="Konto samt Daten löschen")
    p.add_argument("name", help="Benutzername oder E-Mail")
    p.set_defaults(f=befehl_loeschen)
    p = unter.add_parser("mailtest", help="Test-Mail schicken")
    p.add_argument("adresse")
    p.set_defaults(f=befehl_mailtest)
    args = parser.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
