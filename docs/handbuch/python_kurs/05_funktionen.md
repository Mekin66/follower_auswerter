# Lektion 5 – Funktionen vertieft: Closures, Dekoratoren, Parameter

**Lernziele:** Parameterarten sicher einsetzen, verstehen warum `create_app()` aus lauter
inneren Funktionen besteht (Closures), Dekoratoren wie `@app.route` selbst bauen können,
Funktionen als Parameter übergeben (Dependency Injection).

## 5.1 Parameterarten

```python
def registrieren(conn, benutzername, passwort, passwort2,
                 email=None, email_pflicht=False, freigeschaltet=True,
                 newsletter=False, nutzung=None, avv_version=None) -> int:
```

Aufruf mit **Schlüsselwörtern** macht ihn lesbar und unempfindlich gegen die Reihenfolge:

```python
konten.registrieren(conn, "anna", "pw123456", "pw123456", email="a@b.de", nutzung="privat")
```

Weitere Formen:

```python
def f(a, b=2, *args, c, d=4, **kwargs): ...
#     │  │     │      │  │     └ alle übrigen Schlüsselwort-Argumente als dict
#     │  │     │      └──┴ nach *args: NUR per Schlüsselwort (keyword-only)
#     │  │     └ alle übrigen Positionsargumente als Tupel
#     └──┴ normal

def nur_benannt(*, pfad, modus="r"): ...   # "*" allein erzwingt Schlüsselwörter
```

Im Projekt: `create_app(**ueberschreiben)` nimmt beliebige Einstellungen entgegen:

```python
create_app(BETRIEBSMODUS="klassisch", DATENBANK_PFAD=tmp_path / "web.sqlite3")
# ueberschreiben == {"BETRIEBSMODUS": "klassisch", "DATENBANK_PFAD": ...}
```

Und umgekehrt beim Aufruf entpacken: `funktion(**ein_dict)`, `funktion(*eine_liste)`.

## 5.2 Funktionen sind Objekte

```python
def laut(text): return text.upper()
f = laut                  # keine Klammern: die Funktion selbst
f("hallo")                # 'HALLO'
sorted(namen, key=len)    # len wird übergeben, sorted ruft sie auf
```

## 5.3 Closures – innere Funktionen mit Gedächtnis

```python
def zaehler_bauen():
    stand = [0]                    # Liste, damit wir sie innen verändern können
    def zaehlen():
        stand[0] += 1
        return stand[0]
    return zaehlen

z = zaehler_bauen()
z(), z(), z()                      # 1, 2, 3 – "stand" lebt in der Closure weiter
```

Genau so ist `web/app.py` gebaut:

```python
def create_app(**ueberschreiben) -> Flask:
    cfg = {...}
    lock = threading.RLock()
    ablaeufe = OrderedDict()
    letztes_aufraeumen = [0.0]         # Liste aus demselben Grund wie oben

    def db(): ...                      # sieht cfg, db_pfad
    def konto_id(): ...                # sieht cfg

    @app.route("/api/tresor", methods=["PUT"])
    def tresor_speichern():
        ...  cfg["TRESOR_MAX_KB"] ...  # sieht cfg
    return app
```

Warum nicht globale Variablen? Jede `create_app()`-App hat **ihre eigenen** `cfg`, `ablaeufe`,
`lock`. Tests erzeugen viele Apps mit verschiedenen Einstellungen, ohne dass sie sich stören.

**`nonlocal`:** Statt der Listen-Krücke `[0.0]` kann man schreiben:

```python
def zaehler_bauen():
    stand = 0
    def zaehlen():
        nonlocal stand             # "stand" aus der äußeren Funktion meinen
        stand += 1
        return stand
    return zaehlen
```

## 5.4 Dekoratoren

Ein Dekorator ist eine Funktion, die eine Funktion bekommt und eine (meist erweiterte)
Funktion zurückgibt. `@name` darüber ist nur Kurzschrift:

```python
@dekorator
def f(): ...
# ist dasselbe wie
def f(): ...
f = dekorator(f)
```

Selbst gebaut – misst die Laufzeit:

```python
import functools, time

def zeit_messen(funktion):
    @functools.wraps(funktion)              # Name/Docstring der Originalfunktion behalten
    def huelle(*args, **kwargs):
        start = time.perf_counter()
        ergebnis = funktion(*args, **kwargs)
        print(f"{funktion.__name__}: {time.perf_counter() - start:.3f} s")
        return ergebnis
    return huelle

@zeit_messen
def lade(pfad):
    from core.archive_reader import lade_export
    return lade_export(pfad)
```

### Dekoratoren mit Parametern

`@app.route("/avv", methods=["GET", "POST"])` – hier ruft man zuerst `app.route(...)` auf;
**das Ergebnis** ist der eigentliche Dekorator. Vereinfacht macht Flask:

```python
class MiniFlask:
    def __init__(self):
        self.routen = {}
    def route(self, pfad, methods=("GET",)):
        def dekorator(funktion):
            for m in methods:
                self.routen[(m, pfad)] = funktion   # merken, welche Funktion zu welcher URL gehört
            return funktion                          # Funktion unverändert zurück
        return dekorator

app = MiniFlask()

@app.route("/")
def start():
    return "Hallo"

app.routen[("GET", "/")]()     # 'Hallo'
```

Weitere Dekoratoren im Projekt: `@app.before_request`, `@app.teardown_appcontext`,
`@app.context_processor`, `@app.errorhandler(413)`, `@dataclass`, `@property`, `@classmethod`,
`@pytest.fixture`, `@pytest.mark.parametrize`.

### Übung zum Mitdenken: `nur_mit_konto` als Dekorator

Im Projekt wird `nur_mit_konto()` als erste Zeile in Routen aufgerufen. Als Dekorator sähe es so aus:

```python
def konto_pflicht(route):
    @functools.wraps(route)
    def huelle(*args, **kwargs):
        if konto_id() is None:
            abort(404)
        return route(*args, **kwargs)
    return huelle

@app.route("/listen")
@konto_pflicht              # Reihenfolge: zuerst konto_pflicht, dann route registrieren
def listen(): ...
```

## 5.5 Dependency Injection: Abhängigkeiten als Parameter

```python
class KontoPruefer:
    def __init__(self, plattform=Plattform.INSTAGRAM, abrufen: Callable[[str], Antwort] = http_abrufen):
        self._abrufen = abrufen
```

Normal ruft der Prüfer das Internet ab (`http_abrufen`). Ein Test übergibt eine falsche
Funktion, die feste Antworten liefert – ohne Netz, schnell, reproduzierbar:

```python
def falsch_abrufen(url):                       # Antwort(code, url, text)
    if url.endswith("/instagram/"):
        return Antwort(200, url, "<title>instagram (@instagram)</title>")
    return Antwort(404, url, "")

pruefer = KontoPruefer(abrufen=falsch_abrufen)
```

Gleiches Prinzip: `mail.senden(cfg, ..., postausgang=liste)` – im Testmodus landen Mails in
der übergebenen Liste statt im Postfach.

## 5.6 `lambda`

Eine Mini-Funktion ohne Namen, nur ein Ausdruck:

```python
abbrechen=lambda: job.abbrechen                    # web/app.py: "frag später nach"
key=lambda k: (-k.punkte, k.datum)
```

Wird es länger als eine Zeile: richtige Funktion mit Namen schreiben.

## Übungen

1. Schreibe einen Dekorator `wiederholen(n)`, der eine Funktion bis zu `n`-mal aufruft, falls
   sie eine `OSError` wirft (nützlich für Mailversand).
2. Schreibe `def mache_filter(muster: str)`, die eine Funktion zurückgibt, welche prüft, ob ein
   Nutzername `muster` enthält. Teste mit `list(filter(mache_filter("an"), ["anna", "ben", "jan"]))`.
3. Erzeuge zwei Apps: `create_app(BETRIEBSMODUS="tresor", ...)` und `create_app(BETRIEBSMODUS="klassisch", ...)`
   und zeige mit `app.test_client().get("/")`, dass sie sich unterschiedlich verhalten.
4. Was gibt `MiniFlask` aus 5.4 zurück, wenn man `@app.route("/x", methods=["GET","POST"])` benutzt? Wie viele Einträge hat `app.routen`?

<details><summary>Lösungen</summary>

1. ```python
   def wiederholen(n):
       def dekorator(funktion):
           @functools.wraps(funktion)
           def huelle(*args, **kwargs):
               for versuch in range(1, n + 1):
                   try:
                       return funktion(*args, **kwargs)
                   except OSError:
                       if versuch == n:
                           raise
                       time.sleep(2 ** versuch)
           return huelle
       return dekorator
   ```
2. ```python
   def mache_filter(muster):
       return lambda name: muster in name
   ```
   → `['anna', 'jan']`
3. Siehe `tests/test_tresor.py::test_startseite_ist_browser_app_und_server_wertet_nichts_aus`:
   Tresor liefert `id="app"`, klassisch das Upload-Formular.
4. Die Funktion selbst; `app.routen` hat zwei Einträge (`("GET","/x")`, `("POST","/x")`).
</details>
