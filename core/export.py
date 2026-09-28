"""
Text-/CSV-Exporte, die von allen drei Oberflächen gleich genutzt werden.
"""

import csv
import io

from core.freunde import Freund
from core.models import Entscheidung, ENTSCHEIDUNG_TEXTE


def entfolgen_bericht(zusammenfassung: dict[Entscheidung, list[str]], noch_zu_entfolgen: list[str] = ()) -> str:
    zeilen: list[str] = []
    for entscheidung in (Entscheidung.ENTFERNT, Entscheidung.BEHALTEN, Entscheidung.DEAKTIVIERT):
        namen = zusammenfassung.get(entscheidung, [])
        zeilen.append(f"{ENTSCHEIDUNG_TEXTE[entscheidung]} ({len(namen)}):")
        zeilen.extend(f"  - {name}" for name in namen)
        zeilen.append("")
    if noch_zu_entfolgen:
        zeilen.append(f"Früher als 'Entfolgen' markiert, aber du folgst noch ({len(noch_zu_entfolgen)}):")
        zeilen.extend(f"  - {name}" for name in noch_zu_entfolgen)
        zeilen.append("")
    return "\n".join(zeilen)


def namensliste_text(titel: str, namen) -> str:
    namen = list(namen)
    return "\n".join([f"{titel} ({len(namen)}):"] + [f"  - {n}" for n in namen]) + "\n"


def freunde_csv(freunde: list[Freund]) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["username", "quelle", "folgt_mir_seit", "ich_folge_seit", "profil"])
    for f in freunde:
        schreiber.writerow([f.username, f.quelle, f.folgt_mir_seit, f.ich_folge_seit,
                            f"https://www.instagram.com/{f.username}/"])
    return puffer.getvalue()


def aktivitaet_bericht(art: str, eintraege) -> str:
    """Liste der Kommentare/Likes zum Entfernen – mit Datum und Link zum schnellen Wiederfinden."""
    from core.aktivitaet import AKTIVITAET_URL, KOMMENTAR, such_link
    titel = "Kommentare zum Löschen" if art == KOMMENTAR else "Likes zum Entfernen"
    zeilen = [f"{titel} ({len(eintraege)})",
              f"Alle gesammelt auf Instagram: {AKTIVITAET_URL[art]}",
              "(App: Profil > Menü > Deine Aktivität > Interaktionen)", ""]
    for e in sorted(eintraege, key=lambda x: -(x.zeitstempel or 0)):
        if art == KOMMENTAR:
            zeilen.append(f"- {e.datum} · bei @{e.medien_owner or '?'} · {such_link(e)}")
            zeilen.append(f"    „{e.text}“")
        else:
            zeilen.append(f"- {e.datum} · {e.art} von @{e.owner or '?'} · {such_link(e)}")
    return "\n".join(zeilen) + "\n"
