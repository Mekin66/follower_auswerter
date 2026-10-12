"""
Kleines neuronales Netz zur Einstufung von Kommentaren (harmlos / prüfen / kritisch).

Warum ein eigenes Netz statt einer Bibliothek (PyTorch, scikit-learn)?
- Die App läuft auch auf Android (Kivy) und als .exe – große Bibliotheken
  würden die App um hunderte MB aufblähen. Dieses Netz ist reines Python.
- Es ist klein genug, um es Zeile für Zeile zu verstehen (siehe
  docs/handbuch/python_kurs/13_neuronales_netz.md).

Aufbau
======

    Text ──► Merkmale ──► Eingabeschicht ──► versteckte Schicht ──► Ausgabe
             (Hashing)    16384 + Stil        24 Neuronen, tanh     3 Klassen, Softmax

1. **Merkmale** (`merkmale()`): Der Text wird Unicode-normalisiert (NFKC,
   casefold – funktioniert für jede Sprache und Schrift, nicht nur a–z/äöü).
   Daraus werden Wörter, Zeichen-N-Gramme (3–5 Zeichen, damit auch
   Wortteile, Tippfehler und Beugungen erkannt werden: „idiot“, „idioten“,
   „iiidiot“) und Emojis. Jedes Merkmal wird per *Feature-Hashing*
   (CRC32 der UTF-8-Bytes) auf einen von DIM Plätzen abgebildet – so braucht
   man kein Wörterbuch und kennt auch nie gesehene Wörter teilweise.
   Dazu kommen ein paar Stil-Merkmale (Länge, GROSSBUCHSTABEN, „!!“,
   Kontaktdaten, nur Emojis).
2. **Netz** (`KommentarNetz`): eine versteckte Schicht mit tanh, dann
   Softmax über drei Klassen. Die erste Schicht wird nur für die Merkmale
   berechnet, die im Text vorkommen (dünn besetzt) – deshalb schnell genug
   in reinem Python.
3. **Training** (`trainieren()`): Gradientenabstieg mit Rückpropagation auf
   den beschrifteten Beispielen in `core/daten/kommentar_beispiele.tsv`.
   Das fertige Netz liegt in `core/daten/kommentar_netz.json` und wird mit
   `python -m core.kommentar_netz trainieren` neu erzeugt.
4. **Anpassen** (`angepasst()`): Entscheidungen des Nutzers im
   Kommentar-Modus („Entfernen“/„Behalten“) werden als zusätzliche Beispiele
   nachtrainiert – das Netz lernt, was DIESER Nutzer heikel findet.
5. **Erklären** (`erklaeren()`): Für jedes Wort wird geprüft, wie sich das
   Ergebnis ändert, wenn man es weglässt („Occlusion“). Die Wörter mit dem
   größten Einfluss sind die Begründung.

Alle Dateien werden ausdrücklich als UTF-8 gelesen und geschrieben.
"""

import argparse
import datetime
import hashlib
import json
import math
import random
import re
import sys
import unicodedata
import zlib
from collections.abc import Iterable
from pathlib import Path

KLASSEN = ("harmlos", "prüfen", "kritisch")
DIM = 16384                                 # Plätze für gehashte Text-Merkmale (2^14: wenige Kollisionen)
STIL = ("laenge", "gross", "ausrufe", "kontakt", "nur_zeichen", "link")
VERSTECKT = 24
FORMAT = 1

DATEN_ORDNER = Path(__file__).resolve().parent / "daten"
BEISPIELE_PFAD = DATEN_ORDNER / "kommentar_beispiele.tsv"
NETZ_PFAD = DATEN_ORDNER / "kommentar_netz.json"

_WORT = re.compile(r"\w+", re.UNICODE)
_WIEDERHOLUNG = re.compile(r"(.)\1{2,}")                   # "duuuumm" -> "duumm"
_TELEFON = re.compile(r"\+?\d[\d /-]{7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+", re.UNICODE)
_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


# ====================================================================== Merkmale

def normalisieren(text: str) -> str:
    """Unicode-Normalform NFKC (z. B. 𝐈𝐝𝐢𝐨𝐭 -> Idiot, ﬁ -> fi) – funktioniert für jede Sprache."""
    return unicodedata.normalize("NFKC", text or "")


def ist_emoji(zeichen: str) -> bool:
    return unicodedata.category(zeichen) in ("So", "Sk") or 0x1F000 <= ord(zeichen) <= 0x1FAFF


def woerter(text: str) -> list[str]:
    """Wörter in Kleinschreibung (casefold: auch ß -> ss, griechisch, kyrillisch …)."""
    return [_WIEDERHOLUNG.sub(r"\1\1", w) for w in _WORT.findall(normalisieren(text).casefold())]


def _platz(merkmal: str) -> tuple[int, float]:
    """Feature-Hashing: stabiler Hash der UTF-8-Bytes (nicht Pythons hash(), der ist pro Start zufällig)."""
    h = zlib.crc32(merkmal.encode("utf-8"))
    return h % DIM, (1.0 if (h >> 16) & 1 else -1.0)


def _text_merkmale(woerter_liste: list[str], emojis: list[str]) -> dict[int, float]:
    roh: dict[str, float] = {}
    for w in woerter_liste:
        roh["w:" + w] = roh.get("w:" + w, 0.0) + 1.0
        rand = f"<{w}>"
        for n in (3, 4, 5):
            for i in range(len(rand) - n + 1):
                g = "c:" + rand[i:i + n]
                roh[g] = roh.get(g, 0.0) + 0.5
    for e in emojis:
        roh["e:" + e] = roh.get("e:" + e, 0.0) + 1.0
    vektor: dict[int, float] = {}
    for merkmal, wert in roh.items():
        platz, vorzeichen = _platz(merkmal)
        vektor[platz] = vektor.get(platz, 0.0) + vorzeichen * wert
    norm = math.sqrt(sum(v * v for v in vektor.values())) or 1.0
    return {k: v / norm for k, v in vektor.items() if v}


def stil_merkmale(text: str) -> list[float]:
    text = normalisieren(text)
    buchstaben = [z for z in text if z.isalpha()]
    gross = sum(1 for z in buchstaben if z.isupper()) / len(buchstaben) if len(buchstaben) >= 8 else 0.0
    return [
        min(len(text) / 250, 1.6),                                  # laenge
        gross,                                                      # gross
        min(len(re.findall(r"[!?]{2,}", text)), 3) / 3,            # ausrufe
        1.0 if (_TELEFON.search(text) or _EMAIL.search(text)) else 0.0,   # kontakt
        1.0 if text.strip() and not buchstaben else 0.0,            # nur_zeichen (Emojis, Satzzeichen)
        1.0 if _LINK.search(text) else 0.0,                         # link
    ]


def merkmale(text: str, ohne_wort: str | None = None, ohne_stil: int | None = None) -> tuple[dict[int, float], list[float]]:
    """(dünner Text-Vektor {platz: wert}, Stil-Vektor). ohne_* wird nur für erklaeren() gebraucht."""
    w = [x for x in woerter(text) if x != ohne_wort]
    emojis = [z for z in normalisieren(text) if ist_emoji(z) and z != ohne_wort]
    stil = stil_merkmale(text)
    if ohne_stil is not None:
        stil[ohne_stil] = 0.0
    return _text_merkmale(w, emojis), stil


# ====================================================================== Netz

def _softmax(werte: list[float]) -> list[float]:
    m = max(werte)
    e = [math.exp(v - m) for v in werte]
    s = sum(e)
    return [v / s for v in e]


class KommentarNetz:
    """Ein Netz mit einer versteckten Schicht. Gewichte als einfache Python-Listen."""

    def __init__(self, versteckt: int = VERSTECKT, seed: int = 7):
        zufall = random.Random(seed)
        eingang = DIM + len(STIL)
        self.versteckt = versteckt
        # Erste Schicht startet bei 0: Hash-Plätze, die nie vorkommen, bleiben 0 (kleine Datei).
        # Die Symmetrie bricht die zufällig gestartete zweite Schicht.
        self.w1 = [[0.0] * versteckt for _ in range(eingang)]
        self.b1 = [0.0] * versteckt
        grenze = math.sqrt(6 / (versteckt + len(KLASSEN)))
        self.w2 = [[zufall.uniform(-grenze, grenze) for _ in KLASSEN] for _ in range(versteckt)]
        self.b2 = [0.0] * len(KLASSEN)
        self.info: dict = {}

    # ---------------------------------------------------------------- Vorwärts
    def _eingaben(self, text_vektor: dict[int, float], stil: list[float]) -> list[tuple[int, float]]:
        return list(text_vektor.items()) + [(DIM + i, v) for i, v in enumerate(stil) if v]

    def _vorwaerts(self, eingaben: list[tuple[int, float]]) -> tuple[list[float], list[float]]:
        h = list(self.b1)
        for i, x in eingaben:
            zeile = self.w1[i]
            for j in range(self.versteckt):
                h[j] += zeile[j] * x
        h = [math.tanh(v) for v in h]
        z = list(self.b2)
        for j, hj in enumerate(h):
            zeile = self.w2[j]
            for k in range(len(KLASSEN)):
                z[k] += hj * zeile[k]
        return h, _softmax(z)

    def wahrscheinlichkeiten(self, text: str, **ohne) -> dict[str, float]:
        _, p = self._vorwaerts(self._eingaben(*merkmale(text, **ohne)))
        return dict(zip(KLASSEN, p))

    @staticmethod
    def risiko(p: dict[str, float]) -> float:
        """Eine Zahl 0–1: kritisch zählt voll, prüfen halb."""
        return p["kritisch"] + 0.5 * p["prüfen"]

    @staticmethod
    def _log_chance(r: float) -> float:
        r = min(max(r, 1e-6), 1 - 1e-6)
        return math.log(r / (1 - r))

    # ---------------------------------------------------------------- Erklären
    def erklaeren(self, text: str, max_woerter: int = 40) -> list[tuple[str, float]]:
        """
        Welche Wörter/Emojis/Stilmerkmale haben das Risiko erhöht? Liefert [(merkmal, anteil)],
        anteil = Anteil am gesamten erhöhenden Einfluss (0–1), größter zuerst.

        Verfahren ("Occlusion"): jedes Merkmal einmal weglassen und neu rechnen. Verglichen wird
        in Log-Chancen (log(r / (1 - r))), weil bei 99 % vs. 99,9 % sonst kaum ein Unterschied sichtbar wäre.
        """
        basis = self._log_chance(self.risiko(self.wahrscheinlichkeiten(text)))
        kandidaten: list[str] = []
        for w in woerter(text) + [z for z in normalisieren(text) if ist_emoji(z)]:
            if w not in kandidaten:
                kandidaten.append(w)
        einfluss = [(w, basis - self._log_chance(self.risiko(self.wahrscheinlichkeiten(text, ohne_wort=w))))
                    for w in kandidaten[:max_woerter]]
        stil = stil_merkmale(text)
        for i, name in enumerate(STIL):
            if stil[i] >= 0.3:
                einfluss.append((f"#{name}", basis - self._log_chance(
                    self.risiko(self.wahrscheinlichkeiten(text, ohne_stil=i)))))
        positiv = [(m, d) for m, d in einfluss if d > 0]
        summe = sum(d for _, d in positiv) or 1.0
        return sorted(((m, d / summe) for m, d in positiv), key=lambda e: -e[1])

    # ---------------------------------------------------------------- Training
    def _schritt(self, eingaben, ziel: int, lernrate: float, gewicht: float, l2: float,
                 glaettung: float = 0.1) -> float:
        h, p = self._vorwaerts(eingaben)
        # "Label Smoothing": Ziel ist nicht 100 %, sondern 90 % für die richtige Klasse – das Netz
        # wird dadurch weniger übersicher und verallgemeinert besser auf unbekannte Kommentare.
        soll = [glaettung / len(KLASSEN) + (1 - glaettung if k == ziel else 0.0) for k in range(len(KLASSEN))]
        verlust = -sum(s * math.log(max(pk, 1e-12)) for s, pk in zip(soll, p)) * gewicht
        # Ausgabeschicht: Ableitung von Softmax + Kreuzentropie = p - soll
        d_z = [(p[k] - soll[k]) * gewicht for k in range(len(KLASSEN))]
        d_h = [sum(self.w2[j][k] * d_z[k] for k in range(len(KLASSEN))) * (1 - h[j] * h[j])
               for j in range(self.versteckt)]
        for j in range(self.versteckt):
            zeile = self.w2[j]
            for k in range(len(KLASSEN)):
                zeile[k] -= lernrate * (d_z[k] * h[j] + l2 * zeile[k])
        for k in range(len(KLASSEN)):
            self.b2[k] -= lernrate * d_z[k]
        for i, x in eingaben:                         # nur die vorhandenen Merkmale (dünn besetzt)
            zeile = self.w1[i]
            for j in range(self.versteckt):
                zeile[j] -= lernrate * (d_h[j] * x + l2 * zeile[j])
        for j in range(self.versteckt):
            self.b1[j] -= lernrate * d_h[j]
        return verlust

    def trainieren(self, beispiele: Iterable[tuple[str, str]], epochen: int = 40, lernrate: float = 0.15,
                   l2: float = 5e-4, seed: int = 7, ausgabe=None) -> list[float]:
        """beispiele: [(text, klasse)]. Gibt den mittleren Verlust je Epoche zurück."""
        daten = [(self._eingaben(*merkmale(t)), KLASSEN.index(k)) for t, k in beispiele]
        if not daten:
            return []
        anzahl = [sum(1 for _, z in daten if z == k) for k in range(len(KLASSEN))]
        gewichte = [len(daten) / (len(KLASSEN) * a) if a else 0.0 for a in anzahl]   # seltene Klassen stärker
        zufall = random.Random(seed)
        verlauf = []
        for epoche in range(epochen):
            zufall.shuffle(daten)
            rate = lernrate / (1 + epoche * 0.05)
            summe = sum(self._schritt(e, z, rate, gewichte[z], l2) for e, z in daten)
            verlauf.append(summe / len(daten))
            if ausgabe:
                ausgabe(f"Epoche {epoche + 1:>3}: Verlust {verlauf[-1]:.4f}")
        return verlauf

    def angepasst(self, eigene: list[tuple[str, str]], basis: list[tuple[str, str]] | None = None,
                  epochen: int = 8) -> "KommentarNetz":
        """
        Kopie des Netzes, nachtrainiert mit den Entscheidungen des Nutzers (dreifach gewichtet)
        plus einer Stichprobe der Grund-Beispiele, damit das Netz nicht alles andere vergisst.
        """
        kopie = KommentarNetz.aus_dict(self.als_dict())
        basis = basis if basis is not None else beispiele_laden()
        stichprobe = random.Random(len(eigene)).sample(basis, min(len(basis), 80))
        kopie.trainieren(stichprobe + list(eigene) * 3, epochen=epochen, lernrate=0.05)
        kopie.info = {**self.info, "angepasst_mit": len(eigene)}
        return kopie

    # ---------------------------------------------------------------- Speichern (UTF-8, JSON)
    def als_dict(self) -> dict:
        runden = lambda zeile: [round(v, 4) for v in zeile]          # noqa: E731
        return {"format": FORMAT, "klassen": list(KLASSEN), "dim": DIM, "stil": list(STIL),
                "versteckt": self.versteckt, "info": self.info,
                "w1": {str(i): runden(z) for i, z in enumerate(self.w1) if any(z)},   # nur benutzte Zeilen
                "b1": runden(self.b1), "w2": [runden(z) for z in self.w2], "b2": runden(self.b2)}

    @classmethod
    def aus_dict(cls, d: dict) -> "KommentarNetz":
        if d.get("format") != FORMAT or d.get("dim") != DIM or tuple(d.get("stil", ())) != STIL:
            raise ValueError("Die Netz-Datei passt nicht zu dieser Programmversion – bitte neu trainieren.")
        netz = cls(versteckt=d["versteckt"])
        for i, zeile in d["w1"].items():
            netz.w1[int(i)] = list(zeile)
        netz.b1, netz.w2, netz.b2 = list(d["b1"]), [list(z) for z in d["w2"]], list(d["b2"])
        netz.info = d.get("info", {})
        return netz

    def speichern(self, pfad: Path = NETZ_PFAD) -> None:
        pfad.write_text(json.dumps(self.als_dict(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def laden(cls, pfad: Path = NETZ_PFAD) -> "KommentarNetz":
        return cls.aus_dict(json.loads(pfad.read_text(encoding="utf-8")))


# ====================================================================== Beispiele

def beispiele_laden(pfad: Path = BEISPIELE_PFAD) -> list[tuple[str, str]]:
    """
    Liest die Trainingsbeispiele (UTF-8, Tabulator-getrennt):  klasse<TAB>text
    Zeilen mit # sind Kommentare. Klassen: harmlos, prüfen (oder pruefen), kritisch.
    """
    ergebnis = []
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not zeile.strip() or zeile.startswith("#"):
            continue
        klasse, _, text = zeile.partition("\t")
        klasse = klasse.strip().replace("pruefen", "prüfen")
        if klasse not in KLASSEN or not text.strip():
            raise ValueError(f"{pfad.name}, Zeile {nr}: erwartet 'klasse<TAB>text', Klasse aus {KLASSEN}")
        ergebnis.append((text.replace("\\n", "\n"), klasse))
    return ergebnis


def daten_fingerabdruck(pfad: Path = BEISPIELE_PFAD) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()[:16]


def _vorhersage(netz: KommentarNetz, text: str) -> str:
    p = netz.wahrscheinlichkeiten(text)
    return max(p, key=p.get)


def kreuzvalidierung(beispiele: list[tuple[str, str]], teile: int = 5, seed: int = 7) -> dict:
    """
    Ehrliche Trefferquote: Die Beispiele werden in `teile` Gruppen geteilt; jede Gruppe wird
    einmal mit einem Netz geprüft, das sie beim Training NICHT gesehen hat.
    Ergebnis: {"trefferquote": 0.84, "verwechslungen": {"kritisch->harmlos": 3, ...}}
    """
    gemischt = list(beispiele)
    random.Random(seed).shuffle(gemischt)
    richtig, verwechslungen = 0, {}
    for t in range(teile):
        test = gemischt[t::teile]
        training = [b for i, b in enumerate(gemischt) if i % teile != t]
        netz = KommentarNetz()
        netz.trainieren(training)
        for text, soll in test:
            ist = _vorhersage(netz, text)
            if ist == soll:
                richtig += 1
            else:
                schluessel = f"{soll}->{ist}"
                verwechslungen[schluessel] = verwechslungen.get(schluessel, 0) + 1
    return {"trefferquote": round(richtig / len(gemischt), 3),
            "verwechslungen": dict(sorted(verwechslungen.items(), key=lambda x: -x[1]))}


def neu_trainieren(ausgabe=print, pruefen: bool = False) -> KommentarNetz:
    beispiele = beispiele_laden()
    netz = KommentarNetz()
    verlauf = netz.trainieren(beispiele, ausgabe=ausgabe)
    richtig = sum(1 for t, k in beispiele if _vorhersage(netz, t) == k)
    netz.info = {"trainiert_am": datetime.date.today().isoformat(), "beispiele": len(beispiele),
                 "daten": daten_fingerabdruck(), "verlust": round(verlauf[-1], 4),
                 "trefferquote_training": round(richtig / len(beispiele), 3)}
    if pruefen:
        ausgabe("Kreuzvalidierung (5 Durchgänge) …")
        cv = kreuzvalidierung(beispiele)
        netz.info["trefferquote_ungesehen"] = cv["trefferquote"]
        ausgabe(f"Trefferquote auf ungesehenen Beispielen: {cv['trefferquote']:.1%}  Verwechslungen: {cv['verwechslungen']}")
    return netz


_STANDARD: KommentarNetz | None = None


def standard_netz() -> KommentarNetz:
    """Das mitgelieferte, vortrainierte Netz (einmal geladen, dann im Speicher)."""
    global _STANDARD
    if _STANDARD is None:
        _STANDARD = KommentarNetz.laden()
    return _STANDARD


# ====================================================================== Kommandozeile

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Kommentar-Netz trainieren und testen")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("trainieren", help=f"aus {BEISPIELE_PFAD.name} neu trainieren und speichern")
    p.add_argument("--ohne-pruefung", action="store_true", help="Kreuzvalidierung überspringen (schneller)")
    p = unter.add_parser("testen", help="einen Text einstufen")
    p.add_argument("text")
    args = parser.parse_args(argv)
    if args.befehl == "trainieren":
        netz = neu_trainieren(ausgabe=lambda t: print(t) if not t.startswith("Epoche") else None,
                              pruefen=not args.ohne_pruefung)
        netz.speichern()
        print(f"Gespeichert: {NETZ_PFAD} – {netz.info}")
    else:
        netz = standard_netz()
        for klasse, wert in netz.wahrscheinlichkeiten(args.text).items():
            print(f"{klasse:<9} {wert:6.1%}")
        for merkmal, anteil in netz.erklaeren(args.text)[:5]:
            print(f"  {merkmal!r}: {anteil:.0%} des Risikos")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")       # Windows-Konsole: Umlaute/Emojis korrekt ausgeben
    main()
