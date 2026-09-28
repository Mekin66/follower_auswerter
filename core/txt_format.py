"""
Eigene Listen als einfache Textdatei (.txt).

Format zum Selbst-Erstellen (eine Zeile pro Account):

    # Kommentarzeilen beginnen mit #
    anna
    @ben.m
    carl;14.11.2023            <- optional mit Datum (TT.MM.JJJJ oder JJJJ-MM-TT)
    https://www.instagram.com/dora/

Mehrere Namen in einer Zeile, getrennt durch Komma oder Leerzeichen, gehen
auch. Zusätzlich wird das TXT-Format des TikTok-Datenexports erkannt:

    Date: 2024-01-05 18:22:10
    Username: anna
"""

import datetime
import re

from core.parser import normalisiere_username, usernames_aus_text

_TIKTOK_NAME = re.compile(r"^\s*user\s*name\s*:\s*(\S+)", re.IGNORECASE)
_TIKTOK_DATUM = re.compile(r"^\s*date\s*:\s*(.+)$", re.IGNORECASE)


def datum_lesen(text: str | None) -> str:
    """'14.11.2023', '2023-11-14' oder '2023-11-14 18:22:10' -> '14.11.2023'. Sonst 'Unbekannt'."""
    text = (text or "").strip()
    for muster in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(text[:19], muster).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return "Unbekannt"


def lese_txt(text: str) -> dict[str, str]:
    """Liest eine Textliste und gibt {nutzername: datum} zurück."""
    text = (text or "").lstrip("﻿")          # Byte-Order-Mark von Windows-Editoren entfernen
    zeilen = text.splitlines()

    # TikTok-TXT-Export erkennen ("Username: ...")
    if any(_TIKTOK_NAME.match(z) for z in zeilen):
        ergebnis: dict[str, str] = {}
        letztes_datum = "Unbekannt"
        for zeile in zeilen:
            if treffer := _TIKTOK_DATUM.match(zeile):
                letztes_datum = datum_lesen(treffer.group(1))
            elif treffer := _TIKTOK_NAME.match(zeile):
                name = normalisiere_username(treffer.group(1))
                if name:
                    ergebnis[name] = letztes_datum
                letztes_datum = "Unbekannt"
        return ergebnis

    ergebnis = {}
    for zeile in zeilen:
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        if ";" in zeile or "\t" in zeile:                     # name;datum  oder  name<TAB>datum
            teile = re.split(r"[;\t]", zeile, maxsplit=1)       # ["carl", "14.11.2023"]
            name = normalisiere_username(teile[0])
            if name:
                ergebnis[name] = datum_lesen(teile[1] if len(teile) > 1 else "")
        else:
            for name in usernames_aus_text(zeile):            # "anna, ben carl"
                ergebnis.setdefault(name, "Unbekannt")
    return ergebnis


def schreibe_txt(daten: dict[str, str], titel: str) -> str:
    """Erzeugt eine TXT-Liste im eigenen Format (mit Datum, wenn bekannt)."""
    zeilen = [f"# {titel} – {len(daten)} Accounts",
              "# Eine Zeile pro Account. Optional mit Datum: name;TT.MM.JJJJ",
              ""]
    for name in sorted(daten):
        datum = daten[name]
        zeilen.append(f"{name};{datum}" if datum and datum not in ("Unbekannt", "Datumsfehler") else name)
    return "\n".join(zeilen) + "\n"
