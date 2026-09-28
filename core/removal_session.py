"""
Logik für den Entfolgen-Modus.

Ablauf: Man geht Schritt für Schritt durch alle Accounts, denen man folgt,
die einem aber nicht zurückfolgen, und trifft pro Account eine
Entscheidung (behalten / entfernen / scheint deaktiviert).

NEU in Version 2:
- Entscheidungen werden dauerhaft pro Account gespeichert (nicht mehr pro
  Snapshot). Beim nächsten Export werden bereits markierte Accounts daher
  NICHT automatisch wieder abgefragt oder geprüft.
- Vor dem Start wählt man pro Kategorie (Behalten / Deaktiviert /
  Entfolgt / Freunde) aus, ob diese Accounts erneut abgefragt werden sollen.
- "Zurück" merkt sich die Reihenfolge der manuellen Entscheidungen und
  stellt beim Rückgängigmachen die vorherige Markierung wieder her.

Dieses Modul enthält keinerlei GUI-Code.
"""

import sqlite3
from dataclasses import dataclass, field

from core import history_store
from core.konto_pruefer import AccountStatus, PruefErgebnis
from core.models import Entscheidung, Snapshot

KATEGORIE_FREUNDE = "freunde"

# Reihenfolge + Anzeigetexte der Kategorien für die Auswahl vor dem Start
KATEGORIEN: list[tuple[str, str]] = [
    (Entscheidung.BEHALTEN.value, "„Behalten“ (ok, dass sie mir nicht folgen)"),
    (Entscheidung.DEAKTIVIERT.value, "„Scheint deaktiviert“"),
    (Entscheidung.ENTFERNT.value, "„Entfolgen“ markiert, aber ich folge noch"),
    (KATEGORIE_FREUNDE, "In meiner Freunde-Liste"),
]


def ermittle_kandidaten(follower_daten: dict[str, str], following_daten: dict[str, str]) -> list[str]:
    """Alle Accounts, denen ich folge, die mir aber nicht zurückfolgen (alphabetisch)."""
    return sorted(user for user in following_daten if user not in follower_daten)


@dataclass
class RemovalSession:
    """Reiner Ablauf-Zustand (welcher Kandidat ist dran, was wurde entschieden)."""
    kandidaten: list[str]
    seit_daten: dict[str, str]
    entscheidungen: dict[str, Entscheidung] = field(default_factory=dict)
    verlauf: list[str] = field(default_factory=list)  # Reihenfolge MANUELLER Entscheidungen

    def aktueller_kandidat(self) -> str | None:
        for kandidat in self.kandidaten:
            if kandidat not in self.entscheidungen:
                return kandidat
        return None

    def aktuelles_seit_datum(self) -> str:
        kandidat = self.aktueller_kandidat()
        return "" if kandidat is None else self.seit_daten.get(kandidat, "Unbekannt")

    def entscheide(self, entscheidung: Entscheidung) -> str | None:
        """Speichert die Entscheidung für den aktuellen Kandidaten. Gibt dessen Namen zurück."""
        kandidat = self.aktueller_kandidat()
        if kandidat is None:
            return None
        self.entscheidungen[kandidat] = Entscheidung(entscheidung)
        self.verlauf.append(kandidat)
        return kandidat

    def automatisch_markieren(self, username: str, entscheidung: Entscheidung) -> None:
        """Markierung durch die automatische Prüfung – taucht NICHT im Zurück-Verlauf auf."""
        if username in self.kandidaten:
            self.entscheidungen[username] = Entscheidung(entscheidung)

    def zurueck(self) -> str | None:
        """Macht die letzte manuelle Entscheidung rückgängig. Gibt den betroffenen Namen zurück."""
        if not self.verlauf:
            return None
        letzter = self.verlauf.pop()
        self.entscheidungen.pop(letzter, None)
        return letzter

    def kann_zurueck(self) -> bool:
        return bool(self.verlauf)

    def ist_fertig(self) -> bool:
        return self.aktueller_kandidat() is None

    def fortschritt(self) -> tuple[int, int]:
        """(bereits entschieden, gesamt)"""
        return (len(self.entscheidungen), len(self.kandidaten))

    def zusammenfassung(self) -> dict[Entscheidung, list[str]]:
        ergebnis: dict[Entscheidung, list[str]] = {e: [] for e in Entscheidung}
        for username, entscheidung in self.entscheidungen.items():
            ergebnis[entscheidung].append(username)
        for liste in ergebnis.values():
            liste.sort()
        return ergebnis


@dataclass
class KategorieUebersicht:
    """Wie viele der aktuellen Nicht-Zurückfolger sind schon in welcher Kategorie?"""
    alle: list[str]
    neu: list[str]                       # noch nie markiert
    gruppen: dict[str, list[str]]        # Kategorie-Schlüssel -> Nutzernamen

    def anzahl(self, kategorie: str) -> int:
        return len(self.gruppen.get(kategorie, []))


def kategorien_ermitteln(snapshot: Snapshot, markierungen: dict[str, Entscheidung],
                         freunde_manuell: set[str] | None = None) -> KategorieUebersicht:
    freunde_manuell = freunde_manuell or set()
    alle = ermittle_kandidaten(snapshot.follower, snapshot.following)
    gruppen: dict[str, list[str]] = {schluessel: [] for schluessel, _ in KATEGORIEN}
    neu: list[str] = []
    for user in alle:
        if user in freunde_manuell:
            gruppen[KATEGORIE_FREUNDE].append(user)   # Freunde haben Vorrang
        elif user in markierungen:
            gruppen[markierungen[user].value].append(user)
        else:
            neu.append(user)
    return KategorieUebersicht(alle=alle, neu=neu, gruppen=gruppen)


class EntfolgenAblauf:
    """
    Verbindet den Ablauf (RemovalSession) mit der dauerhaften Speicherung.
    Alle schreibenden Methoden bekommen die DB-Verbindung übergeben, damit
    ein Ablauf-Objekt auch über mehrere Web-Requests (jeweils eigene
    Verbindung) hinweg leben kann.
    """

    def __init__(self, besitzer: str, snapshot: Snapshot, markierungen: dict[str, Entscheidung],
                 freunde_manuell: set[str] | None = None, erneut_pruefen: set[str] | None = None):
        """
        erneut_pruefen: Kategorie-Schlüssel (siehe KATEGORIEN), deren Accounts
        erneut abgefragt werden sollen. None = alle Accounts abfragen
        (keine dauerhaften Markierungen berücksichtigen, z. B. anonyme Web-Nutzung).
        """
        self.besitzer = besitzer
        self.snapshot_id = snapshot.id
        self.uebersicht = kategorien_ermitteln(snapshot, markierungen if erneut_pruefen is not None else {},
                                               freunde_manuell if erneut_pruefen is not None else set())
        self.erneut_pruefen = set(erneut_pruefen) if erneut_pruefen is not None else None
        self._markierungen_vorher = dict(markierungen)

        if self.erneut_pruefen is None:
            kandidaten = list(self.uebersicht.alle)
            self.uebersprungen: dict[str, list[str]] = {}
        else:
            kandidaten = list(self.uebersicht.neu)
            self.uebersprungen = {}
            for schluessel, namen in self.uebersicht.gruppen.items():
                if schluessel in self.erneut_pruefen:
                    kandidaten += namen
                elif namen:
                    self.uebersprungen[schluessel] = list(namen)
            kandidaten.sort()

        self.session = RemovalSession(kandidaten=kandidaten, seit_daten=snapshot.following)
        self.automatisch_geprueft = False        # für die Oberflächen: wurde die Vorprüfung schon angeboten?
        self.automatisch_erkannt: list[str] = [] # vom Nutzer BESTÄTIGTE Vorschläge
        self.vorschlaege: dict[str, str] = {}    # Name -> Grund; noch nicht bestätigt
        self.vorschlaege_offen = False           # True = Oberfläche soll die Vorschläge zur Bestätigung zeigen
        self.pruef_meldung = ""                  # z. B. Abbruchgrund der automatischen Prüfung

    # ---- Abfragen
    def offene(self) -> list[str]:
        return [u for u in self.session.kandidaten if u not in self.session.entscheidungen]

    def aktueller_kandidat(self) -> str | None:
        return self.session.aktueller_kandidat()

    def seit(self, username: str | None = None) -> str:
        username = username or self.aktueller_kandidat()
        return self.session.seit_daten.get(username, "Unbekannt") if username else ""

    def bisherige_markierung(self, username: str) -> Entscheidung | None:
        return self._markierungen_vorher.get(username)

    def fortschritt(self) -> tuple[int, int]:
        return self.session.fortschritt()

    def ist_fertig(self) -> bool:
        return self.session.ist_fertig()

    def kann_zurueck(self) -> bool:
        return self.session.kann_zurueck()

    def zusammenfassung(self) -> dict[Entscheidung, list[str]]:
        return self.session.zusammenfassung()

    def noch_zu_entfolgen(self) -> list[str]:
        """Accounts, die früher als 'Entfolgen' markiert wurden, denen man laut Export aber noch folgt."""
        return self.uebersprungen.get(Entscheidung.ENTFERNT.value, [])

    # ---- Schreiben
    def entscheide(self, conn: sqlite3.Connection, entscheidung: Entscheidung) -> str | None:
        kandidat = self.session.entscheide(entscheidung)
        if kandidat is not None:
            history_store.markierung_setzen(conn, self.besitzer, kandidat, Entscheidung(entscheidung))
        return kandidat

    def zurueck(self, conn: sqlite3.Connection) -> str | None:
        username = self.session.zurueck()
        if username is None:
            return None
        vorher = self._markierungen_vorher.get(username)
        if vorher is None:
            history_store.markierung_loeschen(conn, self.besitzer, username)
        else:
            history_store.markierung_setzen(conn, self.besitzer, username, vorher)
        return username

    def auto_ergebnis_uebernehmen(self, conn: sqlite3.Connection | None, ergebnis: PruefErgebnis) -> bool:
        """
        Merkt sich ein Ergebnis der automatischen Prüfung als VORSCHLAG.
        Es wird nichts gespeichert – erst vorschlaege_bestaetigen() markiert.
        (`conn` bleibt als Parameter, damit alte Aufrufe weiter funktionieren.)
        """
        if ergebnis.status != AccountStatus.NICHT_ERREICHBAR:
            return False
        if ergebnis.username in self.session.entscheidungen or ergebnis.username not in self.session.kandidaten:
            return False
        self.vorschlaege[ergebnis.username] = getattr(ergebnis, "grund", "") or "nicht erreichbar"
        self.vorschlaege_offen = True
        return True

    def vorschlaege_bestaetigen(self, conn: sqlite3.Connection, namen) -> int:
        """Markiert die ausgewählten Vorschläge als 'Scheint deaktiviert'. Nicht gewählte kommen in die normale Abfrage."""
        anzahl = 0
        for name in namen:
            if name in self.vorschlaege and name not in self.session.entscheidungen:
                self.session.automatisch_markieren(name, Entscheidung.DEAKTIVIERT)
                history_store.markierung_setzen(conn, self.besitzer, name, Entscheidung.DEAKTIVIERT)
                self.automatisch_erkannt.append(name)
                anzahl += 1
        self.vorschlaege = {}
        self.vorschlaege_offen = False
        return anzahl
