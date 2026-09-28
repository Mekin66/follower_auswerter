"""
Prüft, ob Accounts (Instagram oder TikTok) noch existieren.

WARUM DIE ERSTE VERSION UNZUVERLÄSSIG WAR
- Sie suchte auf der Profilseite nach Sätzen wie "Sorry, this page isn't
  available". Instagram liefert solche Texte aber inzwischen in den
  Sprachdateien JEDER Seite mit -> aktive Accounts wurden als "deaktiviert"
  erkannt (falsch-positiv).
- Bei Login-Sperren oder Rate-Limits sieht jede Seite gleich aus. Die alte
  Version hat trotzdem hunderte Accounts weiter "geprüft".

WIE ES JETZT FUNKTIONIERT
1. Kalibrierung: Vor jeder Prüfung werden zwei Accounts geprüft, deren
   Ergebnis feststeht – einer, der sicher existiert (@instagram bzw.
   @tiktok), und ein zufälliger Fantasiename, der sicher NICHT existiert.
   Daraus lernt der Prüfer, wie "gibt es" und "gibt es nicht" GERADE
   aussehen (Statuscode + Seitentitel). Unterscheiden sich die beiden
   nicht, bricht die Prüfung sofort mit einer klaren Meldung ab, statt
   Unsinn zu liefern.
2. Ein Account gilt nur dann als "nicht erreichbar", wenn seine Antwort
   dem Fantasienamen gleicht UND nichts auf ein echtes Profil hinweist.
3. Kommen mehrmals hintereinander nur unklare Antworten (typisch für eine
   Sperre), bricht die Prüfung ab.
4. Die Ergebnisse sind nur VORSCHLÄGE – die Oberflächen lassen sie vor dem
   Übernehmen bestätigen.

Es werden nur öffentliche Seiten ohne Login abgerufen.
"""

import html as html_modul
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import Enum

from core.plattform import PLATTFORM_TEXTE, Plattform, plattform_aus_text, profil_url


class AccountStatus(str, Enum):
    AKTIV = "aktiv"
    NICHT_ERREICHBAR = "nicht_erreichbar"   # gelöscht, deaktiviert oder umbenannt
    UNSICHER = "unsicher"                    # keine verlässliche Aussage möglich


@dataclass
class PruefErgebnis:
    username: str
    status: AccountStatus
    grund: str = ""


class PruefungNichtMoeglich(RuntimeError):
    """Die Plattform lässt gerade keine verlässliche Prüfung zu (Sperre, Login-Pflicht, geändertes Layout)."""


@dataclass
class Antwort:
    code: int            # HTTP-Statuscode, 0 = keine Verbindung
    url: str             # endgültige Adresse (nach Weiterleitungen)
    text: str            # Seiteninhalt (klein geschrieben)


_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
_BEKANNT = {Plattform.INSTAGRAM: "instagram", Plattform.TIKTOK: "tiktok"}
_TITEL = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
MAX_UNKLAR_IN_FOLGE = 5


def http_abrufen(url: str, timeout: float = 10.0) -> Antwort:
    """Standard-Abruf. In Tests wird diese Funktion durch eine Attrappe ersetzt."""
    anfrage = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as a:
            return Antwort(a.status, a.geturl(), a.read(2_000_000).decode("utf-8", "ignore").lower())
    except urllib.error.HTTPError as fehler:
        try:
            text = fehler.read(500_000).decode("utf-8", "ignore").lower()
        except Exception:  # noqa: BLE001
            text = ""
        return Antwort(fehler.code, url, text)
    except Exception:  # noqa: BLE001 – Timeout, DNS, keine Verbindung
        return Antwort(0, url, "")


@dataclass
class _Merkmale:
    code: int
    titel: str           # Seitentitel, Nutzername herausgenommen
    profil: bool         # enthält die Seite eindeutige Profildaten zu genau diesem Namen?
    sperre: bool         # Login-Wand, Challenge oder Rate-Limit?


class KontoPruefer:
    def __init__(self, plattform: Plattform | str = Plattform.INSTAGRAM,
                 abrufen: Callable[[str], Antwort] = http_abrufen):
        self.plattform = plattform_aus_text(plattform)
        self._abrufen = abrufen
        self._nicht_vorhanden: _Merkmale | None = None   # "so sieht ein fehlender Account aus"
        self._bekannt: _Merkmale | None = None           # "so sieht ein existierender Account aus"

    # ---------------------------------------------------------------- Merkmale
    def _merkmale(self, username: str, a: Antwort) -> _Merkmale:
        u = username.lower()
        titel = html_modul.unescape(_TITEL.search(a.text).group(1)) if _TITEL.search(a.text) else ""
        titel_roh = " ".join(titel.split())
        titel = titel_roh.replace(f"@{u}", "@{name}")     # nur die Handle-Schreibweise ersetzen
        # "profil" nur, wenn der Name UND typische Profildaten vorkommen – der
        # bloße Name reicht nicht, weil manche Fehlerseiten die Adresse zitieren.
        if self.plattform == Plattform.TIKTOK:
            profil = f'"uniqueid":"{u}"' in a.text and "followercount" in a.text
            sperre = a.code in (403, 429) or "/login" in a.url
        else:
            profil = (f"(@{u})" in titel_roh or f"(&#064;{u})" in a.text
                      or (f'"username":"{u}"' in a.text
                          and ("follower_count" in a.text or "edge_followed_by" in a.text)))
            sperre = (a.code in (401, 403, 429) or "/accounts/login" in a.url or "/challenge" in a.url
                      or '"require_login":true' in a.text)
        return _Merkmale(a.code, titel, profil, sperre)

    def _abruf(self, username: str) -> _Merkmale:
        return self._merkmale(username, self._abrufen(profil_url(self.plattform, urllib.parse.quote(username))))

    # ---------------------------------------------------------------- Kalibrierung
    def kalibrieren(self) -> None:
        """Wirft PruefungNichtMoeglich, wenn gerade keine verlässliche Unterscheidung möglich ist."""
        name = PLATTFORM_TEXTE[self.plattform]
        bekannt = self._abruf(_BEKANNT[self.plattform])
        fantasie = "zz" + secrets.token_hex(10)               # z. B. zz9f3a... – existiert praktisch sicher nicht
        fehlt = self._abruf(fantasie)
        if bekannt.code == 0 or fehlt.code == 0:
            raise PruefungNichtMoeglich(f"Keine Internetverbindung zu {name}.")
        if bekannt.sperre or fehlt.sperre:
            raise PruefungNichtMoeglich(
                f"{name} verlangt gerade eine Anmeldung oder bremst Anfragen (Sperre). "
                "Bitte später erneut versuchen oder die Accounts manuell prüfen.")
        unterscheidbar = (not fehlt.profil) and (
            bekannt.profil or bekannt.code != fehlt.code or bekannt.titel != fehlt.titel)
        if not unterscheidbar:
            raise PruefungNichtMoeglich(
                f"{name} zeigt für existierende und nicht existierende Accounts gerade dieselbe "
                "Seite. Eine automatische Prüfung wäre unzuverlässig – bitte manuell prüfen.")
        self._bekannt = bekannt
        self._nicht_vorhanden = fehlt

    # ---------------------------------------------------------------- Einzelprüfung
    def pruefe(self, username: str) -> PruefErgebnis:
        if self._nicht_vorhanden is None:
            self.kalibrieren()
        m = self._abruf(username)
        fehlt, bekannt = self._nicht_vorhanden, self._bekannt
        if m.code == 0:
            return PruefErgebnis(username, AccountStatus.UNSICHER, "keine Verbindung")
        if m.sperre:
            return PruefErgebnis(username, AccountStatus.UNSICHER, "Plattform bremst / Login verlangt")
        if m.profil:
            return PruefErgebnis(username, AccountStatus.AKTIV, "Profil gefunden")
        if m.code == 404 and fehlt.code == 404:
            return PruefErgebnis(username, AccountStatus.NICHT_ERREICHBAR, "Seite existiert nicht (404)")
        gleicht_fehlendem = m.code == fehlt.code and m.titel == fehlt.titel
        gleicht_bekanntem = m.code == bekannt.code and m.titel == bekannt.titel and bekannt.titel != fehlt.titel
        if gleicht_fehlendem and not gleicht_bekanntem:
            return PruefErgebnis(username, AccountStatus.NICHT_ERREICHBAR,
                                 "Seite sieht aus wie bei einem nicht existierenden Account")
        if gleicht_bekanntem:
            return PruefErgebnis(username, AccountStatus.AKTIV, "Seite sieht aus wie ein aktives Profil")
        return PruefErgebnis(username, AccountStatus.UNSICHER, "Seite nicht eindeutig")


def pruefe_mehrere(usernames: Iterable[str], verzoegerung_sekunden: float = 3.0,
                   abbrechen: Callable[[], bool] | None = None,
                   plattform: Plattform | str = Plattform.INSTAGRAM,
                   pruefer: KontoPruefer | None = None) -> Iterator[PruefErgebnis]:
    """
    Prüft Accounts nacheinander (mit Pause) und liefert jedes Ergebnis sofort.
    Wirft PruefungNichtMoeglich: wenn die Kalibrierung scheitert oder
    MAX_UNKLAR_IN_FOLGE Antworten hintereinander unklar sind (Sperre).
    """
    pruefer = pruefer or KontoPruefer(plattform)
    pruefer.kalibrieren()
    unklar_in_folge = 0
    for i, username in enumerate(usernames):
        if abbrechen is not None and abbrechen():
            return
        if i > 0 and verzoegerung_sekunden:
            time.sleep(verzoegerung_sekunden)
        ergebnis = pruefer.pruefe(username)
        yield ergebnis
        unklar_in_folge = unklar_in_folge + 1 if ergebnis.status == AccountStatus.UNSICHER else 0
        if unklar_in_folge >= MAX_UNKLAR_IN_FOLGE:
            raise PruefungNichtMoeglich(
                f"{MAX_UNKLAR_IN_FOLGE} Antworten hintereinander waren unklar – vermutlich bremst die Plattform "
                "gerade. Bisherige Ergebnisse bleiben erhalten; bitte später fortsetzen.")
