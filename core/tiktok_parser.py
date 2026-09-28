"""
Liest den TikTok-Datenexport ("Deine Daten herunterladen").

TikTok liefert entweder EINE große JSON-Datei (user_data.json bzw.
user_data_tiktok.json) oder mehrere TXT-Dateien. Die genaue Struktur hat
sich über die Jahre geändert (z. B. "Activity" -> "Your Activity",
"Follower List" -> "Follower"). Deshalb sucht dieser Parser nicht nach
festen Pfaden, sondern läuft durch die ganze Datei und nimmt jede Liste,
deren Einträge einen Nutzernamen haben. Ob es Follower, Following oder
Blockierte sind, verrät der Name der Liste (bzw. der TXT-Datei):

    {"Activity": {"Follower List": {"FansList": [{"Date": "...", "UserName": "anna"}]},
                  "Following List": {"Following": [{"Date": "...", "UserName": "ben"}]}}}
"""

from dataclasses import dataclass, field

from core.parser import normalisiere_username
from core.txt_format import datum_lesen, lese_txt

_NAMENS_SCHLUESSEL = ("UserName", "Username", "username", "userName", "uniqueId", "unique_id")


@dataclass
class TikTokDaten:
    follower: dict[str, str] = field(default_factory=dict)
    following: dict[str, str] = field(default_factory=dict)
    blockiert: dict[str, str] = field(default_factory=dict)

    def leer(self) -> bool:
        return not (self.follower or self.following or self.blockiert)


def liste_einordnen(bezeichnung: str) -> str | None:
    """'Following List' -> 'following', 'FansList' -> 'follower', 'Block List' -> 'blockiert'."""
    b = bezeichnung.lower()
    if "block" in b:
        return "blockiert"
    if "following" in b:          # zuerst prüfen: "following" enthält "follow", aber nicht "follower"
        return "following"
    if "fan" in b or "follower" in b:
        return "follower"
    return None


def _name_aus(eintrag: dict) -> str:
    for schluessel in _NAMENS_SCHLUESSEL:
        if eintrag.get(schluessel):
            return normalisiere_username(str(eintrag[schluessel]))
    return ""


def extrahiere_tiktok_json(daten, ergebnis: TikTokDaten | None = None) -> TikTokDaten:
    ergebnis = ergebnis or TikTokDaten()

    def durchlaufen(obj, pfad: list[str]):
        if isinstance(obj, dict):
            for schluessel, wert in obj.items():
                durchlaufen(wert, pfad + [str(schluessel)])
        elif isinstance(obj, list) and obj and all(isinstance(e, dict) for e in obj):
            if any(_name_aus(e) for e in obj[:5]):                 # Liste mit Nutzernamen gefunden
                art = liste_einordnen(" / ".join(pfad))
                if art:
                    ziel = getattr(ergebnis, art)
                    for eintrag in obj:
                        name = _name_aus(eintrag)
                        if name:
                            ziel[name] = datum_lesen(eintrag.get("Date") or eintrag.get("date"))
            else:
                for eintrag in obj:
                    durchlaufen(eintrag, pfad)

    durchlaufen(daten, [])
    return ergebnis


def extrahiere_tiktok_txt(dateiname: str, text: str, ergebnis: TikTokDaten | None = None) -> TikTokDaten:
    ergebnis = ergebnis or TikTokDaten()
    art = liste_einordnen(dateiname)
    if art:
        getattr(ergebnis, art).update(lese_txt(text))
    return ergebnis
