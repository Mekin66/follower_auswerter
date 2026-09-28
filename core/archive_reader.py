"""
Liest die relevanten Daten direkt aus dem gezippten Instagram-Export,
ohne die ZIP-Datei vorher manuell entpacken zu müssen.

Instagram liefert die Listen typischerweise unter einem Pfad wie:

    connections/followers_and_following/followers_1.json
    connections/followers_and_following/following.json
    connections/followers_and_following/blocked_profiles.json
    connections/followers_and_following/close_friends.json

Bei vielen Followern teilt Instagram die Liste auf mehrere Dateien auf
(followers_1.json, followers_2.json, ...) – die werden zusammengeführt.
"""

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from core.instagram_export import (Kommentar, Like, datei_art, eintraege_aus_html, eintraege_aus_json,
                                   like_art_aus_pfad, quelle_aus_pfad, zu_accounts, zu_kommentaren, zu_likes)
from core.parser import extrahiere_daten
from core.plattform import Plattform
from core.tiktok_parser import TikTokDaten, extrahiere_tiktok_json, extrahiere_tiktok_txt
from core.txt_format import lese_txt

# Die Dateinamen-Regeln (followers_1.json, following.json, liked_posts.json, ...)
# stehen in core/instagram_export.py::datei_art. Wichtig war dort z. B., dass
# "following_hashtags.json" NICHT als Following-Liste gelesen wird.


class ExportFormatFehler(ValueError):
    """Die Datei ist kein (lesbarer) Export von Instagram oder TikTok."""


@dataclass
class ArchivInhalt:
    follower: dict[str, str] = field(default_factory=dict)
    following: dict[str, str] = field(default_factory=dict)
    blockiert: dict[str, str] = field(default_factory=dict)      # von MIR blockierte Profile
    enge_freunde: dict[str, str] = field(default_factory=dict)   # "Enge Freunde"-Liste
    kommentare: list[Kommentar] = field(default_factory=list)    # meine Kommentare
    likes: list[Like] = field(default_factory=list)              # meine Likes
    plattform: Plattform = Plattform.INSTAGRAM                    # automatisch erkannt

    def enthaelt(self) -> dict[str, int]:
        """Was steckt im Export? {"Follower/Following": 850, "Kommentare": 120, "Likes": 3400} – nur Vorhandenes."""
        ergebnis = {}
        if self.follower or self.following:
            ergebnis["Follower/Following"] = len(self.follower) + len(self.following)
        if self.kommentare:
            ergebnis["Kommentare"] = len(self.kommentare)
        if self.likes:
            ergebnis["Likes"] = len(self.likes)
        return ergebnis

    def hat_follower_daten(self) -> bool:
        return bool(self.follower or self.following)


def _datei_lesen(pfad: str, roh: bytes, inhalt: ArchivInhalt) -> bool:
    """Liest EINE Export-Datei (JSON oder HTML) in `inhalt`. True, wenn sie etwas Brauchbares war."""
    art = datei_art(pfad)
    if art is None:
        return False
    ist_html = pfad.lower().endswith(".html")
    if ist_html:
        eintraege = eintraege_aus_html(roh.decode("utf-8", "ignore"))
    else:
        daten = _json_oder_none(roh)
        if daten is None:
            return False
        eintraege = eintraege_aus_json(daten)

    if art in ("follower", "following", "blockiert", "enge_freunde"):
        accounts = zu_accounts(eintraege) if ist_html else extrahiere_daten(daten)
        getattr(inhalt, art).update(accounts)
    elif art == "kommentare":
        inhalt.kommentare.extend(zu_kommentaren(eintraege, quelle_aus_pfad(pfad)))
    elif art == "likes":
        inhalt.likes.extend(zu_likes(eintraege, like_art_aus_pfad(pfad)))
    return True


def _doppelte_entfernen(inhalt: ArchivInhalt) -> None:
    """JSON und HTML desselben Exports oder mehrfach geladene Dateien nicht doppelt zählen."""
    inhalt.kommentare = list({k.id: k for k in inhalt.kommentare}.values())
    inhalt.likes = list({l.id: l for l in inhalt.likes}.values())


def lade_archiv(zip_pfad) -> ArchivInhalt:
    """
    Öffnet ein Export-ZIP (Pfad oder Dateiobjekt) und erkennt AUTOMATISCH, was
    drin ist: Follower/Following, Blockierte, enge Freunde, Kommentare, Likes –
    in beliebiger Kombination, als JSON oder HTML. Kein Instagram-Inhalt
    gefunden -> TikTok-Export versuchen.
    """
    inhalt = ArchivInhalt()
    gefunden = False
    with zipfile.ZipFile(zip_pfad) as archiv:
        namen = archiv.namelist()
        # JSON zuerst: Enthält ein Export beide Formate, liefert JSON die genaueren Daten.
        for eintrag in sorted(namen, key=lambda n: n.lower().endswith(".html")):
            if datei_art(eintrag) is None:
                continue
            gefunden |= _datei_lesen(eintrag, archiv.read(eintrag), inhalt)
        if not gefunden:
            return _tiktok_aus_zip(archiv, namen)
    _doppelte_entfernen(inhalt)
    if not (inhalt.hat_follower_daten() or inhalt.kommentare or inhalt.likes):
        raise ExportFormatFehler("Im Export wurden weder Follower, Kommentare noch Likes gefunden. "
                                 "Beim Export bitte diese Bereiche auswählen (siehe Anleitung).")
    return inhalt


def lade_aus_zip(zip_pfad) -> tuple[dict[str, str], dict[str, str]]:
    """Kompatibilitäts-Funktion: gibt nur (follower, following) zurück."""
    inhalt = lade_archiv(zip_pfad)
    return inhalt.follower, inhalt.following


def _json_oder_none(roh: bytes):
    try:
        return json.loads(roh.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _tiktok_aus_zip(archiv: zipfile.ZipFile, namen: list[str]) -> ArchivInhalt:
    """TikTok-Export: eine user_data*.json oder mehrere TXT-Dateien."""
    daten = TikTokDaten()
    for eintrag in namen:
        klein = eintrag.lower()
        if klein.endswith(".json"):
            json_daten = _json_oder_none(archiv.read(eintrag))
            if json_daten is not None:
                extrahiere_tiktok_json(json_daten, daten)
        elif klein.endswith(".txt"):
            extrahiere_tiktok_txt(PurePosixPath(klein).name, archiv.read(eintrag).decode("utf-8-sig", "ignore"), daten)
    if daten.leer():
        raise ExportFormatFehler(
            "In dieser ZIP-Datei wurden keine Follower-Listen gefunden. Erwartet wird der "
            "Datenexport von Instagram oder TikTok (siehe Anleitung)."
        )
    return ArchivInhalt(follower=daten.follower, following=daten.following, blockiert=daten.blockiert,
                        plattform=Plattform.TIKTOK)


def lade_export(quelle, dateiname: str = "") -> ArchivInhalt:
    """
    Lädt einen kompletten Export, egal ob Instagram oder TikTok, ZIP oder
    TikTok-JSON. `quelle` = Pfad oder Dateiobjekt, `dateiname` hilft bei Uploads.
    """
    if zipfile.is_zipfile(quelle):
        if hasattr(quelle, "seek"):
            quelle.seek(0)                    # is_zipfile hat im Dateiobjekt gelesen -> zurückspulen
        return lade_archiv(quelle)
    if hasattr(quelle, "seek"):
        quelle.seek(0)
    if hasattr(quelle, "read"):
        roh = quelle.read()
    else:
        with open(quelle, "rb") as datei:
            roh = datei.read()
        dateiname = dateiname or str(quelle)
    # Einzelne Instagram-Datei (JSON oder HTML), z. B. post_comments_1.json oder liked_posts.html?
    einzeln = ArchivInhalt()
    if datei_art(dateiname) and _datei_lesen(PurePosixPath(dateiname.replace("\\", "/")).name, roh, einzeln):
        if einzeln.hat_follower_daten() or einzeln.kommentare or einzeln.likes:
            _doppelte_entfernen(einzeln)
            return einzeln
    json_daten = _json_oder_none(roh)
    if json_daten is not None:
        daten = extrahiere_tiktok_json(json_daten)
        if not daten.leer():
            return ArchivInhalt(follower=daten.follower, following=daten.following, blockiert=daten.blockiert,
                                plattform=Plattform.TIKTOK)
        raise ExportFormatFehler(
            "Diese JSON-Datei enthält nur EINE Liste. Einzelne Instagram-Dateien bitte in die Felder "
            "„Follower“ bzw. „Following“ laden – oder gleich die ganze ZIP-Datei."
        )
    raise ExportFormatFehler("Unbekanntes Dateiformat. Erwartet: ZIP-Datei des Exports oder eine einzelne "
                             "JSON-/HTML-Datei daraus.")


def lade_liste(roh: bytes, dateiname: str = "") -> dict[str, str]:
    """
    Eine einzelne Liste (Follower ODER Following): Instagram-JSON, TikTok-JSON
    oder eine selbst erstellte TXT-Datei.
    """
    text = roh.decode("utf-8-sig", errors="ignore")
    if dateiname.lower().endswith(".txt"):
        return lese_txt(text)
    if dateiname.lower().endswith((".html", ".htm")) or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return zu_accounts(eintraege_aus_html(text))          # Follower-/Following-Liste im HTML-Format
    json_daten = _json_oder_none(roh)
    if json_daten is None:
        return lese_txt(text)                 # keine gültige JSON -> als Textliste versuchen
    ergebnis = extrahiere_daten(json_daten)
    if not ergebnis:                          # evtl. TikTok-JSON mit nur einer Liste
        tiktok = extrahiere_tiktok_json(json_daten)
        for teil in (tiktok.follower, tiktok.following):
            ergebnis.update(teil)
    return ergebnis
