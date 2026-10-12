# Lektion 4 – Objektorientierung im Projekt

**Lernziele:** Wann eine Klasse sinnvoll ist, Vererbung (von Python-Klassen erben),
`@classmethod` als „zweiter Konstruktor“, Komposition statt Vererbung, magische Methoden.

## 4.1 Wann eine Klasse?

Eine Klasse lohnt sich, wenn **Daten und das, was man damit tut, zusammengehören und sich über
die Zeit ändern** (Zustand). Der Entfolgen-Durchgang ist so ein Fall: Es gibt Kandidaten,
bisherige Entscheidungen und einen Verlauf für „Zurück“.

Reine Umrechnungen ohne Zustand sind dagegen **Funktionen** (`normalisiere_username`,
`vergleiche_snapshots`). Das Projekt mischt beides bewusst.

## 4.2 Eine Klasse lesen: `RemovalSession`

```python
@dataclass
class RemovalSession:
    kandidaten: list[str]
    seit_daten: dict[str, str]
    entscheidungen: dict[str, Entscheidung] = field(default_factory=dict)
    verlauf: list[str] = field(default_factory=list)

    def aktueller_kandidat(self) -> str | None:
        for kandidat in self.kandidaten:
            if kandidat not in self.entscheidungen:
                return kandidat
        return None

    def entscheide(self, entscheidung: Entscheidung) -> str | None:
        kandidat = self.aktueller_kandidat()
        if kandidat is None:
            return None
        self.entscheidungen[kandidat] = Entscheidung(entscheidung)
        self.verlauf.append(kandidat)
        return kandidat

    def zurueck(self) -> str | None:
        if not self.verlauf:
            return None
        letzter = self.verlauf.pop()
        self.entscheidungen.pop(letzter, None)
        return letzter
```

Beachte das Design: Der „aktuelle Kandidat“ wird **nicht gespeichert**, sondern jedes Mal
**berechnet** (erster ohne Entscheidung). Dadurch kann er nie „verrutschen“ – ein häufiger
Fehler bei Index-Zählern (`self.index += 1`), wenn man zurückspringt.

## 4.3 Komposition: `EntfolgenAblauf` *hat* eine `RemovalSession`

```python
class EntfolgenAblauf:
    def __init__(self, besitzer, snapshot, markierungen, freunde_manuell=None, erneut_pruefen=None):
        ...
        self.session = RemovalSession(kandidaten=kandidaten, seit_daten=snapshot.following)

    def entscheide(self, conn, entscheidung):
        kandidat = self.session.entscheide(entscheidung)          # Logik weiterreichen
        if kandidat is not None:
            history_store.markierung_setzen(conn, self.besitzer, kandidat, Entscheidung(entscheidung))
        return kandidat
```

`RemovalSession` kennt keine Datenbank, `EntfolgenAblauf` ergänzt das Speichern. So lässt sich
die reine Logik einfach testen, und die Speicherung lässt sich austauschen. Merksatz:
**„hat ein“ → Komposition, „ist ein“ → Vererbung.** Ein Ablauf *ist* keine Session, er *hat* eine.

## 4.4 Vererbung: von Python-Klassen erben

### Eigene Ausnahmen

```python
class KontoFehler(ValueError):
    pass

class EmailVergeben(KontoFehler):
    def __init__(self, konto_id: int):
        super().__init__("E-Mail-Adresse bereits vergeben.")   # Konstruktor der Elternklasse
        self.konto_id = konto_id
```

`except KontoFehler` fängt auch `EmailVergeben` (Unterklasse). `web/app.py` fängt
`EmailVergeben` zuerst und behandelt es besonders, danach allgemein `KontoFehler`.

### HTMLParser erweitern

```python
from html.parser import HTMLParser

class _ExportHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.eintraege = []

    def handle_starttag(self, tag, attrs):   # wird vom HTMLParser aufgerufen
        ...
    def handle_endtag(self, tag):
        ...
```

Das ist das **Template-Method-Muster**: Die Elternklasse steuert den Ablauf (`feed()` liest
das HTML), die Unterklasse überschreibt die „Haken“-Methoden. Ausprobieren:

```python
from html.parser import HTMLParser

class LinkSammler(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href"))

p = LinkSammler()
p.feed('<p><a href="https://instagram.com/anna">anna</a></p>')
print(p.links)    # ['https://instagram.com/anna']
```

## 4.5 `@classmethod` als benannter Konstruktor

```python
@dataclass
class AktivitaetAblauf:
    ...
    @classmethod
    def fuer_kommentare(cls, besitzer, kommentare, vorher, filter=FILTER_RISKANT, erneut=False):
        bewertungen = {k.id: bewerte(k.text) for k in kommentare}
        auswahl = [...]
        ablauf = cls(besitzer, KOMMENTAR, {k.id: k for k in kommentare}, [k.id for k in auswahl], dict(vorher))
        ablauf._bewertungen = bewertungen
        return ablauf

    @classmethod
    def fuer_likes(cls, besitzer, likes, vorher, account=None, erneut=False):
        ...
```

Aufruf: `AktivitaetAblauf.fuer_kommentare(...)`. `cls` ist die Klasse selbst. Vorteil: zwei
verständlich benannte Wege, ein Objekt zu bauen, statt eines `__init__` mit vielen
Wenn-Dann-Parametern.

`@staticmethod` (ohne `self`/`cls`) gibt es auch – im Projekt nicht genutzt, weil man solche
Funktionen in Python meist einfach auf Modulebene schreibt.

## 4.6 Magische Methoden („Dunder“)

| Methode | wird aufgerufen bei | im Projekt |
|---|---|---|
| `__init__` | Objekt erzeugen | überall |
| `__repr__` | Anzeige in Konsole/Debugger | von `@dataclass` erzeugt |
| `__eq__` | `a == b` | von `@dataclass` erzeugt |
| `__enter__`/`__exit__` | `with obj:` | `sqlite3.Connection`, `zipfile.ZipFile`, `smtplib.SMTP` (Lektion 7) |
| `__iter__`/`__next__` | `for x in obj` | Generatoren erledigen das automatisch (Lektion 6) |

## 4.7 Klassen in JavaScript – zum Vergleich

Die Browser-App hat dieselbe Klasse in JS (`web/static/tresor/auswertung.js`):

```js
export class EntfolgenAblauf {
  constructor(bereich, snapshot, erneut) { ... }
  aktueller() { return this.kandidaten.find((n) => !(n in this.entscheidungen)) ?? null; }
  entscheide(wert) { ... }
}
```

`constructor` ≙ `__init__`, `this` ≙ `self` (aber ohne es als Parameter zu schreiben).

## Übungen

1. Schreibe eine Klasse `Zaehler` mit `erhoehe()`, `zurueck()` (letzte Erhöhung rückgängig) und
   `wert` als Property. Speichere dafür einen Verlauf – nicht nur eine Zahl.
2. Schreibe `class TresorZuGross(TresorFehler)` mit Attribut `max_kb` und benutze sie in
   `web/tresor.py::pruefen`. Was musst du in `web/app.py` *nicht* ändern und warum?
3. Erweitere `LinkSammler` so, dass er nur Instagram-Profile sammelt (nutze `normalisiere_username`).
4. Warum wäre `class EntfolgenAblauf(RemovalSession)` (Vererbung) hier ungünstiger?

<details><summary>Lösungen</summary>

1. ```python
   class Zaehler:
       def __init__(self):
           self._schritte: list[int] = []
       def erhoehe(self, um: int = 1):
           self._schritte.append(um)
       def zurueck(self):
           if self._schritte:
               self._schritte.pop()
       @property
       def wert(self) -> int:
           return sum(self._schritte)
   ```
2. Da `TresorZuGross` von `TresorFehler` erbt, fängt `except tresor.TresorFehler` in `app.py`
   sie automatisch – nichts zu ändern.
3. In `handle_starttag`: `name = normalisiere_username(href)` nur übernehmen, wenn
   `"instagram.com/" in href` und der Pfad nicht mit `p/`, `reel/` … beginnt.
4. Dann hätte der Ablauf *alle* Methoden der Session (auch `entscheide` ohne DB) – man könnte
   versehentlich die Variante ohne Speichern aufrufen. Komposition zeigt nur, was gewollt ist.
</details>
