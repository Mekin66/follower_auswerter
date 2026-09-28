"""
Kompatibilität: Der Prüfer heißt seit Version 3 core/konto_pruefer.py
(kann Instagram UND TikTok). Alte Importe funktionieren weiter.
"""
from core.konto_pruefer import (AccountStatus, KontoPruefer, PruefErgebnis,  # noqa: F401
                                PruefungNichtMoeglich, pruefe_mehrere)
