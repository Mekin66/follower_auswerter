"""
Parsen der rohen Instagram-JSON-Dateien.
"""

import datetime
import re

# Profil-Links von Instagram (instagram.com/name, instagram.com/_u/name) und TikTok (tiktok.com/@name)
_HREF_MUSTER = re.compile(r"(?:instagram\.com/(?:_u/)?|tiktok\.com/@)([A-Za-z0-9._]+)/?", re.IGNORECASE)


def normalisiere_username(text: str) -> str:
    """
    Macht aus einer Nutzereingabe einen sauberen Instagram-Nutzernamen.

    Akzeptiert z. B. "@Anna.M", " anna.m ", "https://www.instagram.com/anna.m/",
    "https://www.tiktok.com/@anna.m" und liefert jeweils "anna.m". Instagram-Nutzernamen sind nicht
    case-sensitiv, deshalb wird alles kleingeschrieben.
    """
    text = (text or "").strip()
    treffer = _HREF_MUSTER.search(text)
    if treffer:
        text = treffer.group(1)
    text = text.lstrip("@").strip().strip("/")
    # Nur erlaubte Zeichen behalten (Buchstaben, Ziffern, Punkt, Unterstrich)
    text = re.sub(r"[^A-Za-z0-9._]", "", text)
    return text.lower()


def usernames_aus_text(text: str) -> list[str]:
    """Zerlegt einen Freitext (Komma, Leerzeichen, Zeilenumbruch) in normalisierte Nutzernamen."""
    teile = re.split(r"[\s,;]+", text or "")
    ergebnis: list[str] = []
    for teil in teile:
        name = normalisiere_username(teil)
        if name and name not in ergebnis:
            ergebnis.append(name)
    return ergebnis


def extrahiere_daten(daten: dict | list) -> dict[str, str]:
    """
    Durchsucht die JSON-Daten flexibel nach Nutzernamen und Timestamps.

    Instagram nutzt je nach Export-Version unterschiedliche Strukturen:
    - Manchmal ist der Username direkt im Feld "title"
    - Manchmal steckt er in string_list_data[0]["value"]
    - In neueren Exporten fehlt "value" teilweise – dann steckt der Name
      nur noch im Link string_list_data[0]["href"]
    - Der Zeitstempel steckt (wenn vorhanden) in string_list_data[0]["timestamp"]

    Gibt ein Dictionary zurück: {"nutzername": "DD.MM.YYYY"}
    """
    nutzer_daten: dict[str, str] = {}

    def verarbeite_eintrag(eintrag: dict) -> None:
        username = ""
        timestamp = 0

        if eintrag.get("title"):
            username = str(eintrag["title"])

        sld = eintrag.get("string_list_data")
        if isinstance(sld, list) and sld and isinstance(sld[0], dict):
            data_dict = sld[0]
            if not username and data_dict.get("value"):
                username = str(data_dict["value"])
            if not username and data_dict.get("href"):
                username = normalisiere_username(str(data_dict["href"]))
            if isinstance(data_dict.get("timestamp"), (int, float)):
                timestamp = data_dict["timestamp"]

        username = normalisiere_username(username)
        if not username:
            return

        if timestamp > 0:
            try:
                datum = datetime.datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y')
            except (OverflowError, OSError, ValueError):
                datum = "Datumsfehler"
        else:
            datum = "Unbekannt"

        nutzer_daten[username] = datum

    # Instagram verschachtelt die Daten unterschiedlich (Liste oder Dictionary)
    if isinstance(daten, dict):
        for value in daten.values():
            if isinstance(value, list):
                for eintrag in value:
                    if isinstance(eintrag, dict):
                        verarbeite_eintrag(eintrag)
    elif isinstance(daten, list):
        for eintrag in daten:
            if isinstance(eintrag, dict):
                verarbeite_eintrag(eintrag)

    return nutzer_daten
