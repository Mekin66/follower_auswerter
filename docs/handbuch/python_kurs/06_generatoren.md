# Lektion 6 – Iteratoren und Generatoren

**Lernziele:** verstehen, was bei `for` passiert, Generatorfunktionen mit `yield` schreiben,
große Datenmengen „lazy“ verarbeiten, Fortschritt melden und abbrechen.

## 6.1 Was `for` wirklich tut

```python
namen = ["anna", "ben"]
it = iter(namen)       # Iterator holen
next(it)               # 'anna'
next(it)               # 'ben'
next(it)               # StopIteration -> for-Schleife endet
```

Alles, was `iter()` versteht, ist **iterierbar**: Listen, Strings, dicts (Schlüssel), Mengen,
Dateien (Zeilen), `sqlite3`-Cursor (Zeilen), `zip()`, `enumerate()` …

## 6.2 Generatorfunktionen

Eine Funktion mit `yield` liefert ihre Werte **nacheinander**, statt alle auf einmal zu
berechnen. Sie pausiert bei jedem `yield` und macht beim nächsten `next()` dort weiter.

```python
def countdown(n):
    while n > 0:
        yield n
        n -= 1

for zahl in countdown(3):
    print(zahl)          # 3 2 1
```

## 6.3 Das Projektbeispiel: `pruefe_mehrere`

```python
def pruefe_mehrere(usernames, verzoegerung_sekunden=3.0, abbrechen=None, plattform=Plattform.INSTAGRAM,
                   pruefer=None) -> Iterator[PruefErgebnis]:
    pruefer = pruefer or KontoPruefer(plattform)
    pruefer.kalibrieren()
    unklar_in_folge = 0
    for i, username in enumerate(usernames):
        if abbrechen is not None and abbrechen():
            return                                  # Generator beenden
        if i > 0 and verzoegerung_sekunden:
            time.sleep(verzoegerung_sekunden)
        ergebnis = pruefer.pruefe(username)
        yield ergebnis                              # ← Ergebnis SOFORT an den Aufrufer
        unklar_in_folge = unklar_in_folge + 1 if ergebnis.status == AccountStatus.UNSICHER else 0
        if unklar_in_folge >= MAX_UNKLAR_IN_FOLGE:
            raise PruefungNichtMoeglich(...)
```

Warum Generator? 300 Accounts × 3 Sekunden = 15 Minuten. Mit `return liste` sähe der Nutzer
15 Minuten lang nichts. Mit `yield` kann der Aufrufer nach jedem Account den Fortschritt
aktualisieren:

```python
# web/app.py, im Hintergrund-Thread
for erg in pruefe_mehrere(offene, cfg["AUTO_CHECK_PAUSE_SEKUNDEN"], abbrechen=lambda: job.abbrechen):
    with lock:
        job.erledigt += 1
        job.letzter = f"{erg.username} ({erg.status.value})"
```

Und **Abbrechen** ist trivial: Der Aufrufer setzt `job.abbrechen = True`, die Lambda liefert
beim nächsten Durchlauf `True`, der Generator endet.

Wichtig: Der Code *im* Generator läuft erst, wenn jemand iteriert. `pruefe_mehrere(...)`
allein tut noch nichts – nicht einmal kalibrieren.

## 6.4 Generator-Ausdrücke und Lazy Evaluation

```python
summe = sum(len(n) for n in namen)                   # keine Zwischenliste
erster_html = next((n for n in namen if n.endswith(".html")), None)   # stoppt beim ersten Treffer
```

`next(generator, standard)` ist das Muster „erstes passendes Element oder Standard“ – im Projekt in
`instagram_export.py`:

```python
e.datum_text = next((t for t in reversed(e.texte) if datum_aus_text(t)), "")
```

## 6.5 Rekursives Durchlaufen

Verschachtelte JSON-Daten unbekannter Tiefe (TikTok-Export) durchläuft man rekursiv. Als
Generator geschrieben, wird das besonders elegant – `yield from` reicht die Werte eines
inneren Generators durch:

```python
def alle_listen(obj, pfad=()):
    """Liefert (pfad, liste) für jede Liste von dicts irgendwo in obj."""
    if isinstance(obj, dict):
        for schluessel, wert in obj.items():
            yield from alle_listen(wert, pfad + (schluessel,))
    elif isinstance(obj, list) and obj and all(isinstance(e, dict) for e in obj):
        yield pfad, obj

daten = {"Activity": {"Following List": {"Following": [{"UserName": "ben"}]}}}
list(alle_listen(daten))
# [(('Activity', 'Following List', 'Following'), [{'UserName': 'ben'}])]
```

`core/tiktok_parser.py` macht dasselbe mit einer inneren Funktion `durchlaufen()`, die direkt
ins Ergebnis schreibt. Beide Wege sind üblich.

## 6.6 `itertools` – Werkzeugkasten

```python
import itertools
list(itertools.islice(gen, 5))              # nur die ersten 5
itertools.chain(follower, following)        # mehrere Iterierbare hintereinander
for a, b in itertools.pairwise(snapshots):  # (s1,s2), (s2,s3), …  – z. B. Verlauf über alle Exporte
    ...
itertools.groupby(sorted(likes, key=k), key=k)   # gruppieren (vorher sortieren!)
```

`collections.Counter` passt ebenfalls hierher:

```python
from collections import Counter
Counter(like.owner for like in likes).most_common(10)   # wem gebe ich die meisten Likes?
```

## Übungen

1. Schreibe einen Generator `in_stuecken(liste, n)`, der eine Liste in Stücke der Länge `n` teilt.
   (Nützlich, um viele Datenbank-Zeilen portionsweise zu schreiben.)
2. Baue mit `itertools.pairwise` eine Funktion, die für eine Liste von Snapshots (nach Datum
   sortiert) für jedes Paar die Anzahl neuer Follower liefert.
3. Schreibe `pruefe_mehrere` „nach“ als Mini-Version ohne Netz: Generator `langsam(namen)`, der
   jeden Namen mit 0,5 s Pause liefert, und eine Schleife, die nach 3 Namen abbricht. Wie lange dauert es?
4. Warum wird bei `g = pruefe_mehrere(["a"])` noch keine Anfrage an Instagram geschickt?

<details><summary>Lösungen</summary>

1. ```python
   def in_stuecken(liste, n):
       for i in range(0, len(liste), n):
           yield liste[i:i + n]
   ```
2. ```python
   from itertools import pairwise
   def neue_follower_je_schritt(snapshots):
       for alt, neu in pairwise(snapshots):
           yield neu.label, len(set(neu.follower) - set(alt.follower))
   ```
3. ```python
   def langsam(namen):
       for i, n in enumerate(namen):
           if i: time.sleep(0.5)
           yield n
   for i, n in enumerate(langsam(["a","b","c","d","e"])):
       if i == 2: break
   ```
   ca. 1 Sekunde – die restlichen Namen werden nie berechnet.
4. Generatorfunktionen starten erst beim ersten `next()` (bzw. in der `for`-Schleife).
</details>
