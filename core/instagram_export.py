"""
Allgemeiner Leser für den Instagram-Datenexport – JSON UND HTML.

Instagram verpackt jede Liste etwas anders und ändert das Format immer
wieder. Statt für jede Datei einen eigenen Parser zu schreiben, macht
dieses Modul aus jedem Eintrag (egal ob JSON oder HTML) zuerst einen
einheitlichen "Eintrag":

    Eintrag(titel="anna",
            felder={"comment": "Tolles Foto!", "media owner": "ben"},
            links=["https://www.instagram.com/p/ABC123/"],
            zeitstempel=1700000000, texte=[...])

Daraus werden dann Accounts (Follower/Following), Kommentare oder Likes.
Welche Art eine Datei enthält, verrät ihr Dateiname (`datei_art`).
"""

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import PurePosixPath

from core.parser import normalisiere_username

# ------------------------------------------------------------------ Datenklassen

@dataclass
class Eintrag:
    titel: str = ""
    felder: dict[str, str] = field(default_factory=dict)   # Beschriftung (klein) -> Wert
    links: list[str] = field(default_factory=list)
    zeitstempel: float | None = None
    datum_text: str = ""                                    # z. B. aus HTML: "Nov 14, 2023, 10:00 AM"
    texte: list[str] = field(default_factory=list)          # alle sichtbaren Texte (HTML)


@dataclass
class Kommentar:
    id: str
    text: str
    medien_owner: str        # wem der Beitrag gehört, unter dem kommentiert wurde
    zeitstempel: float | None
    datum: str               # "14.11.2023 10:00" oder "Unbekannt"
    link: str                # Link zum Beitrag, falls im Export vorhanden
    quelle: str              # "Beitrag" oder "Reel"


@dataclass
class Like:
    id: str
    owner: str               # wessen Beitrag/Kommentar geliked wurde
    zeitstempel: float | None
    datum: str
    link: str
    art: str                 # "Beitrag" oder "Kommentar"


# ------------------------------------------------------------------ Datei-Arten

def datei_art(pfad: str) -> str | None:
    """Ordnet eine Export-Datei anhand ihres Namens ein. None = für uns uninteressant."""
    name = PurePosixPath(pfad.lower()).name
    ordner = pfad.lower()
    if not name.endswith((".json", ".html")):
        return None
    stamm = re.sub(r"(_\d+)?\.(json|html)$", "", name)          # "followers_1.json" -> "followers"
    if stamm == "followers":
        return "follower"
    if stamm == "following":
        return "following"
    if re.fullmatch(r"blocked_(profiles|accounts|users)", stamm):
        return "blockiert"
    if stamm == "close_friends":
        return "enge_freunde"
    if stamm.startswith("liked_") or (("/likes/" in ordner or ordner.startswith("likes/")) and "like" in stamm):
        return "likes"
    if stamm in ("post_comments", "reels_comments", "comments", "comments_reels") or (
            ("/comments/" in ordner or ordner.startswith("comments/")) and "comment" in stamm):
        return "kommentare"
    return None


# ------------------------------------------------------------------ JSON -> Einträge

def _feld_uebernehmen(eintrag: Eintrag, label: str, daten: dict) -> None:
    label = label.strip().lower()
    if daten.get("value") not in (None, ""):
        eintrag.felder[label] = str(daten["value"])
    if daten.get("href"):
        eintrag.links.append(str(daten["href"]))
    if isinstance(daten.get("timestamp"), (int, float)) and daten["timestamp"] > 0:
        eintrag.zeitstempel = eintrag.zeitstempel or float(daten["timestamp"])


def _json_eintrag(obj: dict) -> Eintrag | None:
    """Erkennt die drei bekannten Eintrags-Formen von Instagram."""
    if not any(k in obj for k in ("string_list_data", "string_map_data", "label_values")):
        return None
    e = Eintrag(titel=str(obj.get("title") or ""))
    if isinstance(obj.get("timestamp"), (int, float)) and obj["timestamp"] > 0:
        e.zeitstempel = float(obj["timestamp"])
    for teil in obj.get("string_list_data") or []:                  # Form 1: Liste
        if isinstance(teil, dict):
            _feld_uebernehmen(e, "value", teil)
    for label, teil in (obj.get("string_map_data") or {}).items():  # Form 2: benannte Felder
        if isinstance(teil, dict):
            _feld_uebernehmen(e, label, teil)
    for teil in obj.get("label_values") or []:                      # Form 3 (neuere Exporte)
        if isinstance(teil, dict):
            _feld_uebernehmen(e, str(teil.get("label") or ""), teil)
            for unter in teil.get("dict") or []:                    # verschachtelte Felder
                if isinstance(unter, dict):
                    for unter2 in unter.get("dict") or [unter]:
                        if isinstance(unter2, dict) and unter2.get("label"):
                            _feld_uebernehmen(e, str(unter2["label"]), unter2)
    for medium in obj.get("media_list_data") or []:
        if isinstance(medium, dict) and str(medium.get("uri", "")).startswith("http"):
            e.links.append(medium["uri"])
    return e


def eintraege_aus_json(daten) -> list[Eintrag]:
    ergebnis: list[Eintrag] = []

    def durchlaufen(obj):
        if isinstance(obj, dict):
            eintrag = _json_eintrag(obj)
            if eintrag is not None:
                ergebnis.append(eintrag)
                return
            for wert in obj.values():
                durchlaufen(wert)
        elif isinstance(obj, list):
            for wert in obj:
                durchlaufen(wert)

    durchlaufen(daten)
    return ergebnis


# ------------------------------------------------------------------ HTML -> Einträge

class _ExportHTML(HTMLParser):
    """
    Instagram-HTML-Exporte bestehen aus vielen gleich aufgebauten Blöcken
    (<div class="... uiBoxWhite ..."> bzw. "_a6-g"). Jeder Block = ein Eintrag.
    Tabellenzeilen (<td>Beschriftung</td><td>Wert</td>) werden zu Feldern.
    """

    BLOCK_KLASSEN = ("uibox", "_a6-g", "pam")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.eintraege: list[Eintrag] = []
        self._tiefe_block: int | None = None
        self._tiefe = 0
        self._aktuell: Eintrag | None = None
        self._zellen: list[str] | None = None
        self._zelle: list[str] | None = None
        self._titel_modus = False
        self._alle_links: list[tuple[str, str]] = []   # Rückfall ohne Blöcke: (href, Text)
        self._link: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            self._tiefe += 1
            klasse = (attrs.get("class") or "").lower()
            if self._tiefe_block is None and any(k in klasse for k in self.BLOCK_KLASSEN):
                self._tiefe_block = self._tiefe
                self._aktuell = Eintrag()
        elif tag == "tr":
            self._zellen = []
        elif tag == "td" and self._zellen is not None:
            self._zelle = []
        elif tag in ("h2", "h3") and self._aktuell is not None:
            self._titel_modus = True
        elif tag == "a" and attrs.get("href"):
            self._link, self._link_text = attrs["href"], []
            if self._aktuell is not None:
                self._aktuell.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "div":
            if self._tiefe_block is not None and self._tiefe == self._tiefe_block:
                if self._aktuell and (self._aktuell.texte or self._aktuell.links):
                    self.eintraege.append(self._aktuell)
                self._aktuell, self._tiefe_block = None, None
            self._tiefe -= 1
        elif tag == "td" and self._zelle is not None and self._zellen is not None:
            self._zellen.append(" ".join(self._zelle).strip())
            self._zelle = None
        elif tag == "tr" and self._zellen is not None:
            if self._aktuell is not None and len(self._zellen) >= 2 and self._zellen[0]:
                self._aktuell.felder[self._zellen[0].strip().lower()] = self._zellen[1]
            self._zellen = None
        elif tag in ("h2", "h3"):
            self._titel_modus = False
        elif tag == "a" and self._link is not None:
            self._alle_links.append((self._link, " ".join(self._link_text).strip()))
            self._link = None

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._zelle is not None:
            self._zelle.append(text)
        if self._link is not None:
            self._link_text.append(text)
        if self._aktuell is not None:
            self._aktuell.texte.append(text)
            if self._titel_modus and not self._aktuell.titel:
                self._aktuell.titel = text


def eintraege_aus_html(text: str) -> list[Eintrag]:
    p = _ExportHTML()
    p.feed(text)
    if p.eintraege:
        for e in p.eintraege:
            e.datum_text = next((t for t in reversed(e.texte) if datum_aus_text(t)), "")
        return p.eintraege
    # Rückfall: keine erkennbaren Blöcke -> jeder Profil-Link ist ein Eintrag
    return [Eintrag(titel=t, links=[h], texte=[t]) for h, t in p._alle_links if "instagram.com" in h]


# ------------------------------------------------------------------ Datum

_MONATE = {"jan": 1, "feb": 2, "mar": 3, "mär": 3, "mrz": 3, "apr": 4, "may": 5, "mai": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "dez": 12}
_DATUM_EN = re.compile(r"([A-Za-zä]{3})[a-z]*\.? (\d{1,2}), (\d{4})(?:,? (\d{1,2}):(\d{2}) ?([ap]m)?)?", re.I)
_DATUM_DE = re.compile(r"(\d{1,2})\. ?([A-Za-zä]{3})[a-zä]*\.? (\d{4})(?:,? (\d{1,2}):(\d{2}))?", re.I)
_DATUM_NUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:,? (\d{1,2}):(\d{2}))?")


def datum_aus_text(text: str) -> datetime.datetime | None:
    """Liest Datumsangaben aus HTML-Exporten, z. B. 'Nov 14, 2023, 10:00 AM' oder '14. Nov. 2023, 10:00'."""
    text = text.strip()
    try:
        if m := _DATUM_EN.search(text):
            mon = _MONATE.get(m.group(1).lower()[:3])
            if mon:
                std, minute = int(m.group(4) or 0), int(m.group(5) or 0)
                if m.group(6):
                    std = std % 12 + (12 if m.group(6).lower() == "pm" else 0)
                return datetime.datetime(int(m.group(3)), mon, int(m.group(2)), std, minute)
        if m := _DATUM_DE.search(text):
            mon = _MONATE.get(m.group(2).lower()[:3])
            if mon:
                return datetime.datetime(int(m.group(3)), mon, int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0))
        if m := _DATUM_NUM.search(text):
            return datetime.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), int(m.group(4) or 0), int(m.group(5) or 0))
    except ValueError:
        return None
    return None


def _zeit(e: Eintrag) -> tuple[float | None, str, str]:
    """(zeitstempel, "TT.MM.JJJJ", "TT.MM.JJJJ HH:MM")"""
    if e.zeitstempel:
        try:
            d = datetime.datetime.fromtimestamp(e.zeitstempel)
            return e.zeitstempel, d.strftime("%d.%m.%Y"), d.strftime("%d.%m.%Y %H:%M")
        except (OverflowError, OSError, ValueError):
            pass
    d = datum_aus_text(e.datum_text) if e.datum_text else None
    if d:
        return d.timestamp(), d.strftime("%d.%m.%Y"), d.strftime("%d.%m.%Y %H:%M")
    return None, "Unbekannt", "Unbekannt"


# ------------------------------------------------------------------ Einträge -> Ergebnisse

def _feld(e: Eintrag, *stichworte: str) -> str:
    for label, wert in e.felder.items():
        if any(s in label for s in stichworte):
            return wert
    return ""


def _profil_aus_links(e: Eintrag) -> str:
    for link in e.links:
        if re.search(r"instagram\.com/(?:_u/)?[A-Za-z0-9._]+/?$", link):
            return normalisiere_username(link)
    return ""


def _beitrag_link(e: Eintrag) -> str:
    return next((l for l in e.links if re.search(r"instagram\.com/(p|reel|reels|tv)/", l)), "")


def zu_accounts(eintraege: list[Eintrag]) -> dict[str, str]:
    """Follower-/Following-Listen (vor allem aus HTML)."""
    ergebnis: dict[str, str] = {}
    for e in eintraege:
        name = normalisiere_username(e.titel or e.felder.get("value", "") or _profil_aus_links(e)
                                     or (e.texte[0] if e.texte else ""))
        if name:
            ergebnis[name] = _zeit(e)[1]
    return ergebnis


def _kurz_id(*teile) -> str:
    return hashlib.sha1("|".join(str(t) for t in teile).encode("utf-8")).hexdigest()[:16]


def zu_kommentaren(eintraege: list[Eintrag], quelle: str = "Beitrag") -> list[Kommentar]:
    ergebnis = []
    for e in eintraege:
        text = _feld(e, "comment", "kommentar") or e.felder.get("value", "")
        if not text and e.texte:                     # HTML ohne Tabelle: längster Text ist der Kommentar
            kandidaten = [t for t in e.texte if not datum_aus_text(t) and t != e.titel]
            text = max(kandidaten, key=len, default="")
        if not text:
            continue
        owner = normalisiere_username(_feld(e, "owner", "inhaber", "besitzer", "eigentümer") or e.titel)
        zeit, _, datum = _zeit(e)
        ergebnis.append(Kommentar(id=_kurz_id(zeit, owner, text), text=text, medien_owner=owner,
                                  zeitstempel=zeit, datum=datum, link=_beitrag_link(e), quelle=quelle))
    return ergebnis


def zu_likes(eintraege: list[Eintrag], art: str = "Beitrag") -> list[Like]:
    ergebnis = []
    for e in eintraege:
        owner = normalisiere_username(e.titel or _feld(e, "owner", "inhaber", "user", "nutzer") or _profil_aus_links(e))
        link = _beitrag_link(e) or next((l for l in e.links if "instagram.com" in l), "")
        if not owner and not link:
            continue
        zeit, _, datum = _zeit(e)
        ergebnis.append(Like(id=_kurz_id(zeit, owner, link, art), owner=owner, zeitstempel=zeit,
                             datum=datum, link=link, art=art))
    return ergebnis


def quelle_aus_pfad(pfad: str) -> str:
    return "Reel" if "reel" in pfad.lower() else "Beitrag"


def like_art_aus_pfad(pfad: str) -> str:
    return "Kommentar" if "comment" in PurePosixPath(pfad.lower()).name else "Beitrag"
