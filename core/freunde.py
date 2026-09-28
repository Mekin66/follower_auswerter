"""
Freunde-Liste.

"Freunde" sind hier:
1. automatisch: alle, die mir folgen UND denen ich folge (gegenseitig)
2. manuell: Accounts, die ich selbst in die Freunde-Liste eingetragen habe
   (z. B. Freunde, die kaum auf Instagram aktiv sind oder mir nicht folgen)
"""

from collections.abc import Iterable
from dataclasses import dataclass

QUELLE_GEGENSEITIG = "gegenseitig"
QUELLE_MANUELL = "manuell"
QUELLE_BEIDES = "gegenseitig + manuell"


@dataclass
class Freund:
    username: str
    quelle: str
    folgt_mir_seit: str
    ich_folge_seit: str


def freunde_ermitteln(follower: dict[str, str], following: dict[str, str],
                      manuell: Iterable[str] = ()) -> list[Freund]:
    manuell = set(manuell)
    gegenseitig = set(follower) & set(following)
    ergebnis: list[Freund] = []
    for user in sorted(gegenseitig | manuell):
        if user in gegenseitig and user in manuell:
            quelle = QUELLE_BEIDES
        elif user in gegenseitig:
            quelle = QUELLE_GEGENSEITIG
        else:
            quelle = QUELLE_MANUELL
        ergebnis.append(Freund(
            username=user,
            quelle=quelle,
            folgt_mir_seit=follower.get(user, "–"),
            ich_folge_seit=following.get(user, "–"),
        ))
    return ergebnis
