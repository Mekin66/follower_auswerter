"""
Schätzt ein, ob ein eigener Kommentar heikel sein könnte.

Seit Version 5 entscheidet ein kleines neuronales Netz (core/kommentar_netz.py)
statt fester Wortlisten. Es wurde an beschrifteten Beispielen trainiert
(core/daten/kommentar_beispiele.tsv), erkennt dadurch auch Abwandlungen,
Tippfehler und andere Sprachen und lernt aus den Entscheidungen des Nutzers
im Kommentar-Modus dazu (siehe core/aktivitaet.py).

Es bleibt eine VORSORTIERUNG, kein Urteil: Die Entscheidung trifft immer der
Nutzer. Jede Bewertung nennt ihre Gründe – welche Wörter bzw. Merkmale die
Einstufung am stärksten beeinflusst haben.

Stufen = die wahrscheinlichste Klasse des Netzes:
    harmlos  -> Empfehlung "Behalten"
    prüfen   -> Empfehlung "Ansehen"
    kritisch -> Empfehlung "Löschen empfohlen"
Punkte (0–100) = 100 × (P(kritisch) + ½ P(prüfen)) – zum Sortieren, heikelste zuerst.
"""

import re
from dataclasses import dataclass, field

from core.kommentar_netz import KLASSEN, KommentarNetz, normalisieren, standard_netz

HARMLOS, PRUEFEN, KRITISCH = KLASSEN
EMPFEHLUNG = {HARMLOS: "Behalten", PRUEFEN: "Ansehen", KRITISCH: "Löschen empfohlen"}

STIL_TEXTE = {
    "#laenge": "sehr langer Text",
    "#gross": "überwiegend GROSSBUCHSTABEN",
    "#ausrufe": "mehrere !!/??",
    "#kontakt": "enthält Telefonnummer/E-Mail",
    "#nur_zeichen": "nur Emojis/Zeichen",
    "#link": "enthält einen Link",
}
MIN_ANTEIL = 0.15          # Merkmale mit weniger Einfluss werden nicht als Grund genannt


@dataclass
class Bewertung:
    stufe: str
    punkte: int
    gruende: list[str] = field(default_factory=list)
    treffer: list[str] = field(default_factory=list)              # Wörter im Originaltext (zum Hervorheben)
    wahrscheinlichkeiten: dict[str, float] = field(default_factory=dict)
    erklaert: bool = True                                        # False = Gründe noch nicht berechnet

    @property
    def empfehlung(self) -> str:
        return EMPFEHLUNG[self.stufe]


def _original_schreibweise(text: str, wort: str) -> str:
    """Das Wort so, wie es im Kommentar steht (für die gelbe Markierung), z. B. 'idiot' -> 'Idiot'."""
    for kandidat in re.findall(r"\w+", normalisieren(text)):
        if kandidat.casefold() == wort or re.sub(r"(.)\1{2,}", r"\1\1", kandidat.casefold()) == wort:
            return kandidat
    return wort


def bewerte(text: str, netz: KommentarNetz | None = None, erklaeren: bool = True) -> Bewertung:
    """erklaeren=False: nur Stufe und Punkte (schnell, zum Sortieren/Zählen vieler Kommentare)."""
    netz = netz or standard_netz()
    text = (text or "").strip()
    if not text:
        return Bewertung(HARMLOS, 0, ["leer"], [], {HARMLOS: 1.0, PRUEFEN: 0.0, KRITISCH: 0.0})
    p = netz.wahrscheinlichkeiten(text)
    stufe = max(p, key=p.get)
    punkte = round(100 * netz.risiko(p))
    gruende = [f"Netz: {p[KRITISCH]:.0%} kritisch, {p[PRUEFEN]:.0%} prüfen, {p[HARMLOS]:.0%} harmlos"]
    treffer: list[str] = []
    if erklaeren and stufe != HARMLOS:
        for merkmal, anteil in netz.erklaeren(text):
            if anteil < MIN_ANTEIL or len(gruende) > 3:
                break
            if merkmal.startswith("#"):
                gruende.append(f"{STIL_TEXTE.get(merkmal, merkmal)} ({anteil:.0%})")
            else:
                wort = _original_schreibweise(text, merkmal)
                treffer.append(wort)
                gruende.append(f"„{wort}“ ({anteil:.0%})")
    return Bewertung(stufe, punkte, gruende, treffer, p, erklaert=erklaeren)
