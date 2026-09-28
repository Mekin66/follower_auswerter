"""
Unterstützte Plattformen (Instagram, TikTok).

Die Daten beider Plattformen werden strikt getrennt gespeichert, damit
z. B. "anna" auf TikTok nicht mit "anna" auf Instagram vermischt wird.
Technisch passiert das über den "Bereich": der Besitzer bekommt für TikTok
einfach den Zusatz "#tiktok" (lokal -> lokal#tiktok, konto:5 -> konto:5#tiktok).
Instagram behält den bisherigen Besitzer – alte Daten bleiben dadurch gültig.
"""

from enum import Enum


class Plattform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


PLATTFORM_TEXTE: dict[Plattform, str] = {
    Plattform.INSTAGRAM: "Instagram",
    Plattform.TIKTOK: "TikTok",
}

TRENNER = "#"


def plattform_aus_text(text: str | None) -> Plattform:
    """Unbekannte/leere Werte werden zu Instagram (Standard)."""
    try:
        return Plattform(text)
    except ValueError:
        return Plattform.INSTAGRAM


def bereich(besitzer: str, plattform: Plattform | str) -> str:
    """Besitzer-Schlüssel, unter dem die Daten dieser Plattform gespeichert werden."""
    plattform = plattform_aus_text(plattform)
    basis = besitzer.split(TRENNER, 1)[0]
    return basis if plattform == Plattform.INSTAGRAM else f"{basis}{TRENNER}{plattform.value}"


def profil_url(plattform: Plattform | str, username: str) -> str:
    if plattform_aus_text(plattform) == Plattform.TIKTOK:
        return f"https://www.tiktok.com/@{username}"
    return f"https://www.instagram.com/{username}/"
