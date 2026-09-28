"""
Schätzt ein, ob ein eigener Kommentar heikel sein könnte.

WICHTIG: Das ist eine einfache, nachvollziehbare Regel-Bewertung (Wortlisten,
Länge, Schreibstil) – keine KI und kein Urteil. Sie sortiert nur vor, damit
man die wahrscheinlich heiklen Kommentare zuerst sieht. Die Entscheidung
trifft immer der Nutzer. Jede Bewertung nennt ihre Gründe.

Stufen:
    harmlos  (0–19 Punkte)  -> Empfehlung "Behalten"
    prüfen   (20–44 Punkte) -> Empfehlung "Ansehen"
    kritisch (ab 45 Punkten)-> Empfehlung "Löschen empfohlen"

Eigene Wörter ergänzen: einfach in WORTLISTEN eintragen. Ein * am Ende
bedeutet "Wortanfang" (palästin* trifft auch "Palästinenser").
"""

import re
from dataclasses import dataclass, field

HARMLOS, PRUEFEN, KRITISCH = "harmlos", "prüfen", "kritisch"
EMPFEHLUNG = {HARMLOS: "Behalten", PRUEFEN: "Ansehen", KRITISCH: "Löschen empfohlen"}

# Kategorie -> (Punkte, Wörter)
WORTLISTEN: dict[str, tuple[int, list[str]]] = {
    "Beleidigung / Schimpfwort": (45, [
        "idiot*", "dumm*", "blöd*", "depp*", "trottel*", "arsch*", "wichser*", "hure*", "hurensohn*", "schlampe*",
        "fotze*", "spast*", "missgeburt*", "lappen", "penner*", "bastard*", "vollidiot*", "schwachsinn*",
        "fuck*", "shit*", "bitch*", "asshole*", "stupid*", "retard*", "dumbass*", "loser*", "hässlich*"]),
    "Gewalt / Drohung": (50, [
        "töten", "tötet", "umbringen", "abstechen", "erschießen", "erschiessen", "verreck*", "abknallen",
        "kill", "killen", "aufhängen", "vergasen", "zusammenschlagen"]),
    "Diskriminierung": (50, [
        "schwuchtel*", "kanake*", "zigeuner*", "neger*", "behindert", "untermensch*", "judenschwein*"]),
    "Politik / Religion / Gesellschaft": (30, [
        "afd", "cdu", "csu", "spd", "fdp", "grünen", "linke", "bsw", "nazi*", "faschist*", "kommunist*",
        "trump*", "putin*", "selenskyj", "ukrain*", "russland", "russen", "israel*", "palästin*", "gaza", "hamas",
        "islam*", "muslim*", "moslem*", "jude", "juden", "migrant*", "migration*", "flüchtling*", "ausländer*", "abschieb*",
        "gender*", "woke", "impf*", "corona*", "querdenk*", "regierung*", "politik*", "wahl", "wählen",
        "merz", "scholz", "habeck", "weidel", "abtreibung*", "religion*"]),
    "Sexuelle Inhalte": (30, ["sex*", "nackt*", "porno*", "nudes", "titten", "schwanz*", "blowjob*", "onlyfans"]),
    "Drogen / Alkohol": (20, ["kiffen", "gekifft", "koks*", "drogen*", "besoffen*", "weed", "joint*", "ecstasy"]),
}

_TELEFON = re.compile(r"(\+?\d[\d /-]{7,}\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_BUCHSTABE = re.compile(r"[A-Za-zÄÖÜäöüß]")


def _muster(woerter: list[str]) -> re.Pattern:
    teile = []
    for w in woerter:
        if w.endswith("*"):
            teile.append(re.escape(w[:-1]) + r"[a-zäöüß]*")       # Wortanfang
        else:
            teile.append(re.escape(w))                            # ganzes Wort
    return re.compile(r"(?<![a-zäöüß])(" + "|".join(teile) + r")(?![a-zäöüß])", re.IGNORECASE)


_KATEGORIE_MUSTER = {name: (punkte, _muster(woerter)) for name, (punkte, woerter) in WORTLISTEN.items()}


@dataclass
class Bewertung:
    stufe: str
    punkte: int
    gruende: list[str] = field(default_factory=list)
    treffer: list[str] = field(default_factory=list)   # gefundene Wörter (zum Hervorheben)

    @property
    def empfehlung(self) -> str:
        return EMPFEHLUNG[self.stufe]


def bewerte(text: str) -> Bewertung:
    text = (text or "").strip()
    buchstaben = _BUCHSTABE.findall(text)
    woerter = re.findall(r"[\wÄÖÜäöüß]+", text)

    if not buchstaben:
        return Bewertung(HARMLOS, 0, ["nur Emojis/Zeichen"])

    punkte, gruende, treffer = 0, [], []
    for name, (wert, muster) in _KATEGORIE_MUSTER.items():
        gefunden = sorted({m.group(1).lower() for m in muster.finditer(text)})
        if gefunden:
            punkte += wert
            gruende.append(f"{name}: {', '.join(gefunden[:4])}")
            treffer += gefunden

    laenge = len(text)
    if laenge >= 300:
        punkte += 35
        gruende.append(f"sehr lang ({laenge} Zeichen)")
    elif laenge >= 150:
        punkte += 25
        gruende.append(f"lang ({laenge} Zeichen)")
    elif laenge >= 80:
        punkte += 12
        gruende.append(f"mittellang ({laenge} Zeichen)")

    gross = sum(1 for b in buchstaben if b.isupper())
    if len(buchstaben) >= 8 and gross / len(buchstaben) > 0.6:
        punkte += 15
        gruende.append("überwiegend GROSSBUCHSTABEN")
    if re.search(r"[!?]{2,}", text):
        punkte += 10
        gruende.append("mehrere !!/??")
    if re.search(r"\b(du bist|ihr seid|you are|you're|halt die fresse|halts maul)\b", text, re.IGNORECASE):
        punkte += 10
        gruende.append("direkte Ansprache/Urteil über Personen")
    if _TELEFON.search(text) or _EMAIL.search(text):
        punkte += 20
        gruende.append("enthält Telefonnummer/E-Mail")

    if punkte == 0 and len(woerter) <= 3:
        gruende.append("sehr kurz")
    punkte = min(punkte, 100)
    stufe = KRITISCH if punkte >= 45 else PRUEFEN if punkte >= 20 else HARMLOS
    return Bewertung(stufe, punkte, gruende or ["keine Auffälligkeiten"], treffer)
