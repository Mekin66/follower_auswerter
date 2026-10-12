# Lektion 3 – Typen, Datenklassen, Enums

**Lernziele:** Type Hints lesen und schreiben, Daten mit `@dataclass` modellieren, die Falle mit
veränderlichen Standardwerten kennen, `Enum` sinnvoll einsetzen, `@property` verstehen.

## 3.1 Type Hints

```python
def snapshot_laden(conn: sqlite3.Connection, snapshot_id: int, besitzer: str = LOKAL) -> Snapshot:
def konto_info(conn: sqlite3.Connection, konto_id: int) -> dict | None:
def lese_txt(text: str) -> dict[str, str]:
def pruefe_mehrere(usernames: Iterable[str], ...) -> Iterator[PruefErgebnis]:
```

- `dict | None` = „dict oder None“ (seit Python 3.10; früher `Optional[dict]`).
- `dict[str, str]`, `list[tuple[int, str, str]]` beschreiben auch den Inhalt.
- `Iterable[str]` (aus `collections.abc`) = „irgendwas, über das man iterieren kann“ – Liste,
  Menge, Generator. Das ist großzügiger als `list[str]` und daher für Parameter oft besser.
- `Callable[[str], Antwort]` = Funktion, die einen `str` nimmt und eine `Antwort` liefert.

**Python prüft Hints zur Laufzeit nicht.** Sie helfen dem Editor (Autovervollständigung,
Warnungen) und dem Leser. Prüfen kann man sie mit `mypy` (`pip install mypy`, `mypy core`).

## 3.2 `@dataclass`

```python
from dataclasses import dataclass, field

@dataclass
class Snapshot:
    id: int | None
    erstellt_am: str
    label: str
    follower: dict[str, str]
    following: dict[str, str]
```

Der Dekorator erzeugt automatisch `__init__`, `__repr__` und `__eq__`:

```python
>>> s = Snapshot(None, "2026-10-12T10:00:00", "Test", {"anna": "–"}, {})
>>> s
Snapshot(id=None, erstellt_am='2026-10-12T10:00:00', label='Test', follower={'anna': '–'}, following={})
>>> s == Snapshot(None, "2026-10-12T10:00:00", "Test", {"anna": "–"}, {})
True
```

### Die Falle: veränderliche Standardwerte

```python
@dataclass
class ArchivInhalt:
    follower: dict[str, str] = field(default_factory=dict)   # richtig
    # follower: dict[str, str] = {}                           # Fehler! (dataclass verbietet es sogar)
```

Ein Standardwert wird **einmal** erzeugt. Ein `{}` als Standard würde von *allen* Objekten
geteilt – trägt man bei einem etwas ein, steht es bei allen. `default_factory=dict` ruft für
jedes neue Objekt `dict()` auf. Dieselbe Falle gibt es bei Funktionen:

```python
def schlecht(namen=[]):      # die Liste lebt über alle Aufrufe weiter!
    namen.append("x"); return namen
schlecht(); schlecht()       # ['x', 'x']

def gut(namen=None):
    namen = namen or []      # so macht es z. B. extrahiere_tiktok_json mit "ergebnis"
```

### Methoden in Dataclasses

Dataclasses sind normale Klassen – Methoden dürfen rein:

```python
@dataclass
class ArchivInhalt:
    ...
    def hat_follower_daten(self) -> bool:
        return bool(self.follower or self.following)
```

`RemovalSession` (removal_session.py) und `AktivitaetAblauf` (aktivitaet.py) sind ganze
Ablauf-Logiken als Dataclass.

## 3.3 Enum

```python
from enum import Enum

class Entscheidung(str, Enum):
    BEHALTEN = "behalten"
    ENTFERNT = "entfernt"
    DEAKTIVIERT = "deaktiviert"
```

```python
>>> Entscheidung("behalten")            # aus Text (z. B. Formular, DB)
<Entscheidung.BEHALTEN: 'behalten'>
>>> Entscheidung("quatsch")
ValueError: 'quatsch' is not a valid Entscheidung
>>> Entscheidung.BEHALTEN.value
'behalten'
>>> Entscheidung.BEHALTEN == "behalten"  # dank (str, Enum)
True
>>> [e.value for e in Entscheidung]      # über alle iterieren
['behalten', 'entfernt', 'deaktiviert']
```

Der `ValueError` bei unbekannten Werten ist ein eingebauter Schutz: `web/app.py` nutzt ihn,
um manipulierte Formulareingaben abzufangen:

```python
try:
    entscheidung = Entscheidung(request.form.get("entscheidung", ""))
except ValueError:
    abort(400)
```

Muster „Standard bei unbekanntem Wert“ (plattform.py):

```python
def plattform_aus_text(text: str | None) -> Plattform:
    try:
        return Plattform(text)
    except ValueError:
        return Plattform.INSTAGRAM
```

Zu Enums gehören oft Anzeigetexte als dict: `ENTSCHEIDUNG_TEXTE[Entscheidung.BEHALTEN]`.

## 3.4 `@property`

```python
@dataclass
class Bewertung:
    stufe: str
    punkte: int
    ...
    @property
    def empfehlung(self) -> str:
        return EMPFEHLUNG[self.stufe]
```

`bewertung.empfehlung` – ohne Klammern – sieht aus wie ein Attribut, wird aber jedes Mal
berechnet. Gut für Werte, die sich aus anderen ergeben (keine doppelte Speicherung, nie veraltet).

## 3.5 Wann dataclass, wann dict?

| dict | dataclass |
|---|---|
| Schlüssel sind *Daten* (Nutzernamen → Datum) | Schlüssel sind *feste Felder* (id, label, …) |
| beliebig viele Einträge | fester Aufbau |
| JSON 1:1 | Tippfehler (`s.lable`) fallen sofort auf |

Darum: `follower` ist ein dict, `Snapshot` eine dataclass.

## Übungen

1. Schreibe eine Dataclass `Tresorinfo(version: int, groesse: int, aktualisiert_am: str)` mit einer
   Property `groesse_kb`.
2. Was passiert hier und warum?
   ```python
   @dataclass
   class Liste:
       namen: list = field(default_factory=list)
   a, b = Liste(), Liste(); a.namen.append("x"); print(b.namen)
   ```
3. Schreibe ein Enum `Nutzung(str, Enum)` mit `PRIVAT` und `GESCHAEFTLICH` und eine Funktion,
   die bei unbekanntem Text `None` liefert.
4. Lass `mypy core/models.py` laufen. Baue absichtlich einen Typfehler ein (`label: int` und
   übergib einen String) – meldet mypy ihn? Läuft der Code trotzdem?

<details><summary>Lösungen</summary>

1. ```python
   @dataclass
   class Tresorinfo:
       version: int
       groesse: int
       aktualisiert_am: str

       @property
       def groesse_kb(self) -> float:
           return round(self.groesse / 1024, 1)
   ```
2. `[]` – jedes Objekt hat dank `default_factory` seine eigene Liste.
3. ```python
   class Nutzung(str, Enum):
       PRIVAT = "privat"
       GESCHAEFTLICH = "geschaeftlich"

   def nutzung_aus(text: str) -> Nutzung | None:
       try:
           return Nutzung(text)
       except ValueError:
           return None
   ```
   (Im Projekt ist es bewusst einfacher gelöst: `NUTZUNG_TEXTE` als dict in `konten.py`.)
4. mypy meldet den Fehler; Python führt den Code trotzdem aus – Hints sind nur Hinweise.
</details>
