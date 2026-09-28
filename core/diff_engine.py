"""
Vergleicht zwei Snapshots miteinander (Punkt a).

Beispiel: Du hast vor 20 Tagen einen Export geladen und heute wieder.
Mit vergleiche_snapshots() bekommst du heraus, wer in der Zwischenzeit
neu gefolgt bzw. entfolgt ist – für beide Listen (Follower & Following).
"""

from core.models import Snapshot, Aenderung, ListTyp


def _vergleiche_liste(alt: dict[str, str], neu: dict[str, str], liste: ListTyp) -> list[Aenderung]:
    aenderungen: list[Aenderung] = []

    neu_dazugekommen = set(neu) - set(alt)
    weggefallen = set(alt) - set(neu)

    for username in sorted(neu_dazugekommen):
        aenderungen.append(Aenderung(username=username, liste=liste, art="neu"))

    for username in sorted(weggefallen):
        aenderungen.append(Aenderung(username=username, liste=liste, art="entfernt"))

    return aenderungen


def vergleiche_snapshots(alt: Snapshot, neu: Snapshot) -> list[Aenderung]:
    """
    Vergleicht zwei Snapshots (alt -> neu) und gibt alle Änderungen zurück.

    "neu" bei einem Follower-Eintrag heißt: dieser Account folgt mir jetzt,
    hat es beim alten Snapshot aber noch nicht getan.
    "entfernt" heißt entsprechend: der Account folgt mir jetzt nicht mehr
    (bzw. ich folge ihm nicht mehr, bei der Following-Liste).
    """
    if alt.erstellt_am > neu.erstellt_am:
        alt, neu = neu, alt  # immer chronologisch vergleichen, egal in welcher Reihenfolge übergeben

    aenderungen = []
    aenderungen += _vergleiche_liste(alt.follower, neu.follower, ListTyp.FOLLOWER)
    aenderungen += _vergleiche_liste(alt.following, neu.following, ListTyp.FOLLOWING)
    return aenderungen


def moegliche_blockierungen(alt: Snapshot, neu: Snapshot) -> list[str]:
    """
    Accounts, die im älteren Snapshot mit mir gegenseitig verbunden waren
    (folgten mir UND ich folgte ihnen) und im neueren in BEIDEN Listen fehlen.

    Genau das passiert, wenn mich jemand blockiert (Instagram entfernt dann
    beide Verbindungen). Es kann aber auch heißen: Account deaktiviert/
    gelöscht, Nutzername geändert, oder beide Seiten haben entfolgt. Daher
    nur ein "Verdacht" – bestätigen muss man es selbst.
    """
    if alt.erstellt_am > neu.erstellt_am:
        alt, neu = neu, alt
    vorher_gegenseitig = set(alt.follower) & set(alt.following)
    return sorted(u for u in vorher_gegenseitig if u not in neu.follower and u not in neu.following)
