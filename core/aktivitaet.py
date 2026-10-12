"""
Kommentar- und Like-Modus: eigene Kommentare/Likes Schritt für Schritt durchgehen.

Funktioniert wie der Entfolgen-Modus: ein Eintrag nach dem anderen,
Entscheidung "Entfernen" oder "Behalten", "Zurück" macht die letzte
Entscheidung rückgängig, alles wird sofort gespeichert. Bereits entschiedene
Einträge werden beim nächsten Mal übersprungen (außer man wählt "erneut").

Das Programm löscht NICHTS selbst auf Instagram – es zeigt dir, was du
löschen willst, mit Datum und Link, damit du es schnell findest.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from core import history_store
from core.instagram_export import Kommentar, Like
from core.kommentar_bewertung import HARMLOS, KRITISCH, PRUEFEN, Bewertung, bewerte
from core.kommentar_netz import KommentarNetz, standard_netz

KOMMENTAR, LIKE = "kommentar", "like"
ENTFERNEN, BEHALTEN = "entfernen", "behalten"

# Instagram-Seiten, auf denen man eigene Kommentare/Likes gesammelt sieht und
# (auch mehrere auf einmal) löschen kann. In der App: Profil -> Menü ->
# "Deine Aktivität" -> "Interaktionen" -> "Kommentare" bzw. "Likes".
AKTIVITAET_URL = {
    KOMMENTAR: "https://www.instagram.com/your_activity/interactions/comments/",
    LIKE: "https://www.instagram.com/your_activity/interactions/likes/",
}

FILTER_RISKANT, FILTER_KRITISCH, FILTER_ALLE = "riskant", "kritisch", "alle"

# Ab so vielen eigenen Entscheidungen lernt das Netz die Vorlieben des Nutzers dazu
MIN_EIGENE_ENTSCHEIDUNGEN = 5


def persoenliches_netz(kommentare: list[Kommentar], vorher: dict[str, str]) -> KommentarNetz:
    """
    Das Standard-Netz, nachtrainiert mit den bisherigen Entscheidungen des Nutzers:
    "Entfernen" zählt als kritisch, "Behalten" als harmlos. Unter
    MIN_EIGENE_ENTSCHEIDUNGEN bleibt es beim Standard-Netz.
    """
    texte = {k.id: k.text for k in kommentare}
    eigene = [(texte[i], KRITISCH if e == ENTFERNEN else HARMLOS) for i, e in vorher.items() if i in texte]
    if len(eigene) < MIN_EIGENE_ENTSCHEIDUNGEN:
        return standard_netz()
    return standard_netz().angepasst(eigene)


def kommentar_statistik(kommentare: list[Kommentar]) -> dict[str, int]:
    zaehler = Counter(bewerte(k.text, erklaeren=False).stufe for k in kommentare)
    return {KRITISCH: zaehler[KRITISCH], PRUEFEN: zaehler[PRUEFEN], HARMLOS: zaehler[HARMLOS]}


def like_statistik(likes: list[Like]) -> list[tuple[str, int, str]]:
    """[(account, anzahl, letzter Like)] – wem du am häufigsten Likes gibst, absteigend."""
    anzahl = Counter(l.owner or "(unbekannt)" for l in likes)
    letzter: dict[str, tuple[float, str]] = {}
    for l in likes:
        name = l.owner or "(unbekannt)"
        if l.zeitstempel and l.zeitstempel > letzter.get(name, (0, ""))[0]:
            letzter[name] = (l.zeitstempel, l.datum)
    return [(name, n, letzter.get(name, (0, "Unbekannt"))[1]) for name, n in anzahl.most_common()]


def such_link(eintrag) -> str:
    """Bester Link, um einen Kommentar/Like auf Instagram wiederzufinden."""
    if eintrag.link:
        return eintrag.link                                # direkter Link zum Beitrag (falls im Export)
    owner = getattr(eintrag, "medien_owner", None) or getattr(eintrag, "owner", "")
    return f"https://www.instagram.com/{owner}/" if owner else ""


@dataclass
class AktivitaetAblauf:
    besitzer: str
    art: str                                   # KOMMENTAR oder LIKE
    eintraege: dict[str, object]               # id -> Kommentar/Like
    reihenfolge: list[str]                     # abzufragende IDs in Reihenfolge
    vorher: dict[str, str]                     # gespeicherte Entscheidungen vor dem Start (für "Zurück")
    uebersprungen: int = 0                     # schon entschieden bzw. vom Filter ausgeblendet
    entscheidungen: dict[str, str] = field(default_factory=dict)
    verlauf: list[str] = field(default_factory=list)
    _bewertungen: dict[str, Bewertung] = field(default_factory=dict)
    _netz: KommentarNetz | None = None

    # ------------------------------------------------ Erzeugen
    @classmethod
    def fuer_kommentare(cls, besitzer: str, kommentare: list[Kommentar], vorher: dict[str, str],
                        filter: str = FILTER_RISKANT, erneut: bool = False) -> "AktivitaetAblauf":
        """filter: 'kritisch' (nur kritische), 'riskant' (kritisch + prüfen) oder 'alle'. Heikelste zuerst."""
        netz = persoenliches_netz(kommentare, vorher)
        bewertungen = {k.id: bewerte(k.text, netz, erklaeren=False) for k in kommentare}
        erlaubt = {FILTER_KRITISCH: {KRITISCH}, FILTER_RISKANT: {KRITISCH, PRUEFEN}}.get(filter, {KRITISCH, PRUEFEN, HARMLOS})
        auswahl = [k for k in kommentare if bewertungen[k.id].stufe in erlaubt and (erneut or k.id not in vorher)]
        auswahl.sort(key=lambda k: (-bewertungen[k.id].punkte, -(k.zeitstempel or 0)))
        ablauf = cls(besitzer, KOMMENTAR, {k.id: k for k in kommentare}, [k.id for k in auswahl], dict(vorher),
                     uebersprungen=len(kommentare) - len(auswahl))
        ablauf._bewertungen = bewertungen
        ablauf._netz = netz
        return ablauf

    @classmethod
    def fuer_likes(cls, besitzer: str, likes: list[Like], vorher: dict[str, str],
                   account: str | None = None, erneut: bool = False) -> "AktivitaetAblauf":
        """account: nur Likes bei diesem Account (z. B. einem Ex). Neueste zuerst."""
        auswahl = [l for l in likes if (not account or l.owner == account) and (erneut or l.id not in vorher)]
        auswahl.sort(key=lambda l: -(l.zeitstempel or 0))
        return cls(besitzer, LIKE, {l.id: l for l in likes}, [l.id for l in auswahl], dict(vorher),
                   uebersprungen=len(likes) - len(auswahl))

    # ------------------------------------------------ Abfragen
    def aktueller(self):
        for id in self.reihenfolge:
            if id not in self.entscheidungen:
                return self.eintraege[id]
        return None

    def bewertung(self, eintrag) -> Bewertung | None:
        """Bewertung MIT Begründung – erst beim Anzeigen berechnet (spart Zeit bei vielen Kommentaren)."""
        if self.art != KOMMENTAR or eintrag is None:
            return None
        b = self._bewertungen.get(eintrag.id)
        if b is not None and not b.erklaert:
            b = self._bewertungen[eintrag.id] = bewerte(eintrag.text, self._netz)
        return b

    def fortschritt(self) -> tuple[int, int]:
        return len(self.entscheidungen), len(self.reihenfolge)

    def ist_fertig(self) -> bool:
        return self.aktueller() is None

    def kann_zurueck(self) -> bool:
        return bool(self.verlauf)

    def zusammenfassung(self) -> dict[str, list]:
        ergebnis = {ENTFERNEN: [], BEHALTEN: []}
        for id in self.reihenfolge:
            if id in self.entscheidungen:
                ergebnis[self.entscheidungen[id]].append(self.eintraege[id])
        return ergebnis

    # ------------------------------------------------ Schreiben
    def entscheide(self, conn: sqlite3.Connection, entscheidung: str):
        eintrag = self.aktueller()
        if eintrag is None or entscheidung not in (ENTFERNEN, BEHALTEN):
            return None
        self.entscheidungen[eintrag.id] = entscheidung
        self.verlauf.append(eintrag.id)
        history_store.aktivitaet_entscheidung_setzen(conn, self.besitzer, self.art, eintrag.id, entscheidung)
        return eintrag

    def zurueck(self, conn: sqlite3.Connection):
        if not self.verlauf:
            return None
        id = self.verlauf.pop()
        self.entscheidungen.pop(id, None)
        history_store.aktivitaet_entscheidung_setzen(conn, self.besitzer, self.art, id, self.vorher.get(id))
        return self.eintraege[id]


def alle_zum_entfernen(conn: sqlite3.Connection, besitzer: str, art: str) -> list:
    """Alles, was (in irgendeinem Durchgang) als 'Entfernen' markiert wurde – für Export und Liste."""
    entscheidungen = history_store.aktivitaet_entscheidungen_laden(conn, besitzer, art)
    eintraege = history_store.kommentare_laden(conn, besitzer) if art == KOMMENTAR else history_store.likes_laden(conn, besitzer)
    return [e for e in eintraege if entscheidungen.get(e.id) == ENTFERNEN]
