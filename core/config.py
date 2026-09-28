"""
Konfiguration der trackbaren Datenkategorien (Vorbereitung für Punkt d).

Instagram-Archive enthalten weit mehr als nur Follower/Following, z. B.:
- "connections/followers_and_following/" -> Follower, Following, enge Freunde, ...
- "personal_information/"                -> personenbezogene Daten
- "your_activity_across_meta/"           -> Aktivitäten (Likes, Kommentare, ...)

Damit später weitere Kategorien dazukommen können, ohne den Code an zehn
Stellen anfassen zu müssen, gibt es hier eine zentrale Liste. Aktuell sind
nur FOLLOWER und FOLLOWING aktiv (das ist, was main.py bereits kann), aber
das Grundgerüst ist so gebaut, dass neue Kategorien einfach ergänzt werden
können: einfach einen neuen DatenKategorie-Eintrag + passenden Parser
hinzufügen.
"""

from dataclasses import dataclass


@dataclass
class DatenKategorie:
    id: str            # interner Schlüssel, z. B. "follower"
    anzeige_name: str  # Name für die UI, z. B. "Follower"
    aktiv: bool = True  # ob diese Kategorie aktuell unterstützt/angezeigt wird


# Zentrale Liste aller (geplanten) Kategorien.
# aktiv=False bedeutet: schon vorgesehen, aber noch nicht implementiert.
VERFUEGBARE_KATEGORIEN: list[DatenKategorie] = [
    DatenKategorie(id="follower", anzeige_name="Follower (folgen mir)", aktiv=True),
    DatenKategorie(id="following", anzeige_name="Following (ich folge)", aktiv=True),
    DatenKategorie(id="personenbezogen", anzeige_name="Personenbezogene Informationen", aktiv=False),
    DatenKategorie(id="aktivitaet", anzeige_name="Meine Aktivitäten auf Instagram", aktiv=False),
]


def aktive_kategorien() -> list[DatenKategorie]:
    """Gibt nur die aktuell unterstützten Kategorien zurück."""
    return [k for k in VERFUEGBARE_KATEGORIEN if k.aktiv]
