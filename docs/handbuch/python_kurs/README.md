# Python-Kurs am eigenen Projekt

Für alle, die **Python-Grundlagen** kennen (Variablen, `if`, Schleifen, Listen, dicts,
Funktionen) und jetzt verstehen wollen, wie ein echtes, mehrteiliges Programm gebaut ist.
Jede Lektion erklärt ein Thema **an Code aus diesem Projekt**, enthält kleine Beispiele zum
Ausprobieren und endet mit Übungen samt Lösungen (zum Aufklappen).

## Aufbau

| # | Lektion | Thema | Beispiele aus dem Projekt |
|---|---|---|---|
| 1 | [Projekt, Module, Umgebung](01_projekt_und_module.md) | venv, pip, Pakete, Imports, `__name__` | `main.py`, `web/app.py`, `core/` |
| 2 | [Moderne Syntax](02_moderne_syntax.md) | f-Strings, Comprehensions, Mengen, Walross, `sorted(key=)` | `diff_engine.py`, `txt_format.py` |
| 3 | [Typen und Datenklassen](03_typen_und_dataclasses.md) | Type Hints, `@dataclass`, `Enum`, `@property` | `models.py`, `archive_reader.py` |
| 4 | [Objektorientierung](04_oop.md) | Klassen, Vererbung, `@classmethod`, Komposition | `removal_session.py`, `instagram_export.py` |
| 5 | [Funktionen vertieft](05_funktionen.md) | Closures, Dekoratoren, `*args/**kwargs`, Dependency Injection | `create_app()`, `@app.route` |
| 6 | [Iteratoren und Generatoren](06_generatoren.md) | `yield`, Lazy Evaluation, `itertools` | `konto_pruefer.pruefe_mehrere` |
| 7 | [Fehler und Kontextmanager](07_fehler_und_with.md) | eigene Exceptions, `raise … from`, `with`, `contextlib` | `ExportFormatFehler`, `VersionsKonflikt` |
| 8 | [Dateien, JSON, ZIP, Regex](08_dateien_und_formate.md) | `pathlib`, `json`, `zipfile`, `io`, `csv`, `re` | `archive_reader.py`, `parser.py` |
| 9 | [SQLite](09_sqlite.md) | Verbindungen, Parameter, Transaktionen, Migrationen | `history_store.py`, `tresor.py` |
| 10 | [Web mit Flask](10_flask.md) | Routen, Templates, Sessions, JSON-API, CLI mit `argparse` | `web/app.py`, `verwaltung.py` |
| 11 | [Threads und Sicherheit](11_threads_und_sicherheit.md) | `threading`, Locks, Passwort-Hashes, CSRF, Kryptografie | `app.py`, `konten.py`, `krypto.js` |
| 12 | [Testen und erweitern](12_projekt_erweitern.md) | `pytest`, Fixtures, Mocking; Abschlussprojekte | `tests/` |

## So arbeitest du damit

1. Projekt einrichten (Lektion 1), dann `python -m pytest tests` – alles sollte grün sein.
2. Lektionen der Reihe nach; Beispiele in einer Python-Konsole (`python` oder `ipython`) mittippen.
3. Zu jeder Lektion die genannte Projektdatei öffnen und die Stellen suchen.
4. Übungen erst selbst lösen, dann aufklappen.
5. Zum Schluss ein Abschlussprojekt aus Lektion 12 umsetzen – mit Test.

Tipp: In der Konsole Projektmodule importieren funktioniert aus dem Projektordner:

```python
>>> from core.parser import normalisiere_username
>>> normalisiere_username("https://www.instagram.com/_u/Anna.M/")
'anna.m'
```
