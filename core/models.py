"""
Zentrale Datenmodelle des Projekts.

Warum eigene Klassen statt einfacher dicts?
- Bessere Lesbarkeit (self.username statt eintrag["username"])
- Der Editor/die IDE kann Tippfehler bei Feldnamen erkennen
- Einfacher zu erweitern, wenn später mehr Felder dazukommen
"""

from dataclasses import dataclass
from enum import Enum


class ListTyp(str, Enum):
    """Welche Instagram-Liste ein Eintrag betrifft."""
    FOLLOWER = "follower"      # Leute, die mir folgen
    FOLLOWING = "following"    # Leute, denen ich folge


@dataclass
class Account:
    """Ein einzelner Instagram-Account, wie er in einem Export vorkommt."""
    username: str
    seit_datum: str  # bereits als "DD.MM.YYYY" formatiert, siehe parser.py


@dataclass
class Snapshot:
    """
    Eine 'Momentaufnahme' des Archivs zu einem bestimmten Zeitpunkt.
    Über mehrere Snapshots hinweg lässt sich vergleichen, wer neu gefolgt
    oder entfolgt ist.
    """
    id: int | None          # None, solange der Snapshot noch nicht gespeichert ist
    erstellt_am: str        # ISO-Zeitstempel, z. B. "2026-08-22T10:15:00"
    label: str              # frei wählbarer Name, z. B. "Export August"
    follower: dict[str, str]    # username -> seit_datum
    following: dict[str, str]   # username -> seit_datum


@dataclass
class Aenderung:
    """Eine einzelne Veränderung zwischen zwei Snapshots (für den Diff)."""
    username: str
    liste: ListTyp
    art: str  # "neu" (dazugekommen) oder "entfernt" (weggefallen)


class Entscheidung(str, Enum):
    """
    Markierung eines Accounts, der mir nicht zurückfolgt (Entfolgen-Modus).

    Seit Version 2 werden diese Markierungen DAUERHAFT pro Account
    gespeichert (nicht mehr pro Snapshot). Beim nächsten Export kann man
    dadurch pro Kategorie auswählen, ob diese Accounts erneut abgefragt/
    geprüft werden sollen oder nicht.

    BEHALTEN     -> "Ist okay, dass er mir nicht folgt" – bleibt.
    ENTFERNT     -> Ich entfolge dem Account.
    DEAKTIVIERT  -> Der Account scheint deaktiviert/gelöscht zu sein.
    """
    BEHALTEN = "behalten"
    ENTFERNT = "entfernt"
    DEAKTIVIERT = "deaktiviert"


ENTSCHEIDUNG_TEXTE: dict[Entscheidung, str] = {
    Entscheidung.BEHALTEN: "Behalten (ok, dass sie mir nicht folgen)",
    Entscheidung.DEAKTIVIERT: "Scheint deaktiviert",
    Entscheidung.ENTFERNT: "Entfolgen / entfolgt",
}


class PersonenListe(str, Enum):
    """
    Frei pflegbare Personen-Listen (unabhängig von einem Snapshot).

    FREUNDE            -> manuell als Freund markiert (zusätzlich zu den
                          automatisch erkannten gegenseitigen Follows)
    BLOCKIERT_VON_MIR  -> Leute, die ich blockiert habe
    BLOCKIERT_MICH     -> Leute, die mich blockiert haben
    """
    FREUNDE = "freunde"
    BLOCKIERT_VON_MIR = "blockiert_von_mir"
    BLOCKIERT_MICH = "blockiert_mich"


LISTEN_TEXTE: dict[PersonenListe, str] = {
    PersonenListe.FREUNDE: "Freunde (manuell)",
    PersonenListe.BLOCKIERT_VON_MIR: "Von mir blockiert",
    PersonenListe.BLOCKIERT_MICH: "Hat mich blockiert",
}
