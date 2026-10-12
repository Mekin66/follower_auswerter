# Lektion 1 – Projekt, Module und Umgebung

**Lernziele:** virtuelle Umgebung anlegen, Abhängigkeiten installieren, verstehen, wie Python
Module findet, und warum `if __name__ == "__main__":` überall steht.

## 1.1 Virtuelle Umgebung

Jedes Projekt bekommt seine eigene Python-Umgebung, damit sich Paketversionen verschiedener
Projekte nicht in die Quere kommen.

```bash
cd follower_auswerter
python -m venv .venv                 # Umgebung anlegen (Ordner .venv, steht in .gitignore)
source .venv/bin/activate            # Linux/Mac
.venv\Scripts\activate               # Windows
pip install -r web/requirements.txt pytest
pip freeze                           # zeigt, was installiert ist
```

`requirements.txt` listet die Abhängigkeiten. `Flask>=3.0` heißt „mindestens 3.0“. Für
Server-Deployments pinnt man oft exakt (`Flask==3.1.2`), damit ein Update nicht überraschend
etwas kaputt macht.

## 1.2 Module und Pakete

- Ein **Modul** ist eine `.py`-Datei (`core/parser.py`).
- Ein **Paket** ist ein Ordner mit Modulen, meist mit `__init__.py` (`core/`, `gui/`, `web/`).

```python
from core.parser import normalisiere_username        # eine Funktion holen
from core import history_store                        # ganzes Modul holen
history_store.snapshot_speichern(...)                 # Zugriff mit Modulnamen davor
from core.models import Entscheidung, Snapshot        # mehrere Namen
from web import einstellungen as standard_einstellungen   # umbenennen
```

Faustregel im Projekt: Funktionen, die man oft nutzt, direkt importieren; Module mit vielen
Funktionen (`history_store`, `konten`) als Ganzes, damit beim Lesen klar ist, woher etwas kommt.

### Wo sucht Python?

In der Liste `sys.path`: zuerst der Ordner des gestarteten Skripts, dann die installierten
Pakete. Startest du `python web/app.py`, ist `web/` der Startordner – `core` liegt aber eine
Ebene höher. Deshalb steht oben in `web/app.py`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`__file__` ist der Pfad der aktuellen Datei; `.parent.parent` geht zwei Ordner hoch zum
Projektordner. Und weil `app.py` sowohl als Skript als auch als Paket (`web.app` für gunicorn)
geladen wird, gibt es diesen Trick:

```python
try:
    from web import einstellungen, konten, mail, tresor   # als Paket "web.app"
except ImportError:
    import einstellungen, konten, mail, tresor            # als Skript "python web/app.py"
```

## 1.3 `if __name__ == "__main__":`

Jedes Modul hat die Variable `__name__`. Wird die Datei direkt gestartet, ist sie
`"__main__"`, beim Import ist sie der Modulname (`"web.app"`).

```python
# web/app.py, ganz unten
app = create_app()                 # läuft IMMER (auch bei Import durch gunicorn)

if __name__ == "__main__":         # läuft NUR bei "python web/app.py"
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
```

## 1.4 `python -m`

`python -m web.verwaltung konten` startet ein Modul *als Teil seines Pakets* – Python setzt den
aktuellen Ordner in `sys.path`, und relative Paket-Imports funktionieren. Genauso
`python -m pytest`, `python -m venv`.

## 1.5 Umgebungsvariablen

Einstellungen, die je Server anders sind (Passwörter, Pfade), gehören nicht in den Code:

```python
import os
SMTP_HOST = os.environ.get("SMTP_HOST", "")                  # Standard "" falls nicht gesetzt
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))  # immer Text -> umwandeln!
```

Setzen: `SMTP_HOST=smtp.example.de python web/app.py` (Linux/Mac) oder per `.env`-Datei
in Docker (`env_file:`).

## 1.6 Code-Stil

- Einrückung 4 Leerzeichen, Zeilen bis ca. 120 Zeichen (im Projekt üblich).
- `snake_case` für Funktionen/Variablen, `PascalCase` für Klassen, `GROSS` für Konstanten.
- Ein führender Unterstrich (`_jetzt()`, `_FORMAT`) heißt „intern, nicht von außen benutzen“.
- Docstrings (`"""…"""`) direkt unter `def`/`class` erklären *warum*, nicht nur *was*.

## Übungen

1. Lege eine virtuelle Umgebung an, installiere die Abhängigkeiten und führe `python -m pytest tests -q` aus.
2. Öffne eine Python-Konsole im Projektordner und gib `sys.path` aus. Was steht an erster Stelle?
3. Schreibe `core/hallo.py` mit einer Funktion `gruss(name)` und einem `__main__`-Block, der
   `gruss("Welt")` ausgibt. Importiere die Funktion danach in der Konsole – wird der Gruß dabei ausgegeben?
4. Starte die Web-App mit `BETRIEBSMODUS=klassisch` und `COOKIES_NUR_HTTPS=0`. Was ändert sich auf der Startseite?

<details><summary>Lösungen</summary>

2. `''` bzw. der aktuelle Ordner – deshalb klappt `import core…` aus dem Projektordner.
3. ```python
   def gruss(name: str) -> str:
       return f"Hallo {name}!"

   if __name__ == "__main__":
       print(gruss("Welt"))
   ```
   Beim Import wird **nichts** ausgegeben – der `__main__`-Block läuft nicht.
4. Statt der Browser-App erscheint das Upload-Formular (`index.html`); die Navigation zeigt
   „Listen-Editor“, „Kommentare“, „Likes“.
</details>
