# Lektion 10 – Web mit Flask (und Kommandozeile mit argparse)

**Lernziele:** Wie eine Anfrage durch Flask läuft, Routen, Formulare, Templates (Jinja2),
Sessions, JSON-APIs, Hooks vor/nach Requests, Testen mit dem Test-Client, CLI-Werkzeuge.

## 10.1 Der Weg einer Anfrage

```
Browser ──HTTP──► gunicorn ──► Flask: before_request ──► Route-Funktion ──► Antwort
                                      (CSRF, Sperren)       (Logik, DB)       (HTML/JSON/Redirect)
                               teardown_appcontext (DB schließen) ◄──────────┘
```

## 10.2 Kleinste App

```python
from flask import Flask, request, redirect, url_for, render_template, abort

app = Flask(__name__)

@app.route("/")
def start():
    return "Hallo"

@app.route("/hallo/<name>")                      # Teil der URL als Parameter
def hallo(name):
    return f"Hallo {name}"                       # Achtung: in echtem HTML nur über Templates ausgeben (XSS)!

@app.route("/ergebnis/<int:snapshot_id>")        # Konverter: nur Zahlen, kommt als int an
def ergebnis(snapshot_id): ...

if __name__ == "__main__":
    app.run(debug=False)
```

## 10.3 Formulare und Weiterleitungen

```python
@app.route("/avv", methods=["GET", "POST"])
def avv():
    if request.method == "POST":
        nutzung = request.form.get("nutzung", "")       # Formularfeld (immer Text, evtl. fehlend)
        ...
        flash("Danke – deine Zustimmung ist gespeichert.")
        return redirect(url_for("start"))              # Post/Redirect/Get: kein doppeltes Absenden bei F5
    return render_template("avv.html", konto=info)
```

- `request.form` (POST-Felder), `request.args` (`?tab=freunde`), `request.files` (Uploads),
  `request.get_json()` (JSON-Body), `request.headers`.
- `url_for("start")` baut die URL aus dem **Funktionsnamen** – ändert man die URL im Dekorator,
  stimmen alle Links trotzdem.
- `abort(404)` beendet sofort mit Fehlerseite.

## 10.4 Templates (Jinja2)

```html
{% extends "basis.html" %}                       {# Grundgerüst erben #}
{% block inhalt %}
  <h1>{{ konto.benutzername }}</h1>               {# Ausgabe – automatisch HTML-escaped! #}
  {% if tresor_info %}
    <p>{{ (tresor_info.groesse / 1024)|round(1) }} KB</p>     {# Filter mit | #}
  {% endif %}
  {% for wert, text in nutzung_texte.items() %}
    <label><input type="radio" name="nutzung" value="{{ wert }}"> {{ text }}</label>
  {% endfor %}
  <form method="post"><input type="hidden" name="_csrf" value="{{ csrf_token() }}"> … </form>
{% endblock %}
```

**Auto-Escaping:** `{{ name }}` macht aus `<script>` harmloses `&lt;script&gt;`. Darum nie
`|safe` auf Nutzereingaben anwenden.

`@app.context_processor` stellt Variablen in **allen** Templates bereit (`tresor_modus`,
`benutzername`, `cfg` …), damit man sie nicht jeder `render_template` mitgeben muss.

## 10.5 Sessions

```python
session["konto_id"] = kid          # im signierten Cookie gespeichert
session.get("konto_id")            # lesen
session.clear()                    # abmelden
session.permanent = True           # Lebensdauer: PERMANENT_SESSION_LIFETIME (30 Tage)
```

Flask-Sessions liegen **im Cookie** beim Nutzer – mit `SECRET_KEY` signiert (nicht
verschlüsselt!). Der Nutzer kann sie lesen, aber nicht fälschen. Deshalb kommen dort nur IDs
und Tokens hinein, keine Geheimnisse. Ändert sich der `SECRET_KEY`, sind alle abgemeldet.

Sicherheits-Einstellungen (in `create_app`):

```python
SESSION_COOKIE_HTTPONLY=True      # JavaScript kommt nicht an das Cookie
SESSION_COOKIE_SAMESITE="Lax"     # wird bei fremden POST-Anfragen nicht mitgeschickt
SESSION_COOKIE_SECURE=True        # nur über HTTPS
```

## 10.6 Hooks

```python
@app.before_request
def _vor_jedem_request():
    if tresor_modus and request.endpoint in KLASSISCHE_ENDPUNKTE:
        abort(404)
    ...

@app.teardown_appcontext
def _db_schliessen(_fehler):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
```

`g` ist ein Notizzettel, der genau **eine** Anfrage lang lebt – ideal für die DB-Verbindung.

## 10.7 JSON-API

```python
@app.route("/api/tresor", methods=["PUT"])
def tresor_speichern():
    anfrage = request.get_json(silent=True) or {}         # silent: bei kaputtem JSON None statt Fehler
    ...
    return _api_json({"version": version})

def _api_fehler(text, status, **extra):
    antwort = app.response_class(json.dumps({"fehler": text, **extra}, ensure_ascii=False),
                                 status=status, mimetype="application/json")
    antwort.headers["Cache-Control"] = "no-store"
    return antwort
```

(Flask kann auch einfach `return {"version": 1}` – ein dict wird automatisch JSON. Das Projekt
baut die Antwort selbst, um Header wie `Cache-Control` zu setzen.)

HTTP-Statuscodes im Projekt: 200 ok, 302 Weiterleitung, 400 falsche Anfrage, 401 nicht
angemeldet, 403 nicht erlaubt (AVV fehlt), 404 nicht gefunden, 409 Konflikt, 413 zu groß, 429 zu viele Versuche.

Gegenstück im Browser (`speicher.js`):

```js
const antwort = await fetch("/api/tresor", { method: "PUT", headers: { "Content-Type": "application/json",
                            "X-CSRF-Token": csrf() }, body: JSON.stringify({ inhalt, basis_version }) });
```

## 10.8 Testen mit dem Test-Client

```python
def test_api_nur_mit_anmeldung(tmp_path):
    app = create_app(BETRIEBSMODUS="tresor", DATENBANK_PFAD=tmp_path / "web.sqlite3", SECRET_KEY="x")
    c = app.test_client()                 # simulierter Browser mit Cookies
    r = c.get("/api/tresor")
    assert r.status_code == 401
    r = c.post("/avv", data={"_csrf": token, "avv": "1"})
    r = c.open("/api/tresor", method="PUT", json={...}, headers={"X-CSRF-Token": token})
    r.json                                # Antwort als dict
    r.get_data(as_text=True)              # HTML als Text
```

## 10.9 Produktion

`app.run()` ist nur zum Entwickeln. Auf dem Server:

```bash
gunicorn --workers 1 --threads 8 --bind 0.0.0.0:8000 web.app:app
#                                                      └ Modul web.app, Variable app
```

`debug=True` öffentlich = jeder kann Python-Code auf deinem Server ausführen. Niemals.

## 10.10 Kommandozeilen-Werkzeug mit `argparse`

```python
import argparse

parser = argparse.ArgumentParser(description="Verwaltung der Follower-Auswertung (Web)")
unter = parser.add_subparsers(dest="befehl", required=True)
unter.add_parser("tresore", help="Größe der Tresore").set_defaults(f=befehl_tresore)
p = unter.add_parser("loeschen", help="Konto löschen")
p.add_argument("name")                                     # Pflicht-Argument
p.set_defaults(f=befehl_loeschen)
p = unter.add_parser("emails")
p.add_argument("--newsletter", action="store_true")        # Schalter
p.add_argument("--csv")                                    # optional mit Wert
p.set_defaults(f=befehl_emails)

args = parser.parse_args()
args.f(args)                                               # passende Funktion aufrufen
```

`--help` erzeugt argparse automatisch.

## Übungen

1. Füge eine Route `/api/status` hinzu, die `{"modus": "tresor", "konten": true}` liefert. Teste sie.
2. Schreibe einen Test, der prüft, dass `/api/tresor` ohne `X-CSRF-Token` mit 400 antwortet.
3. Füge `python -m web.verwaltung statistik` hinzu: Anzahl Konten, davon privat/geschäftlich, Anzahl Tresore.
4. Warum leitet `/avv` nach dem POST weiter, statt direkt eine Seite zu rendern?

<details><summary>Lösungen</summary>

1. In `create_app`:
   ```python
   @app.route("/api/status")
   def api_status():
       return _api_json({"modus": cfg["BETRIEBSMODUS"], "konten": cfg["ACCOUNTS_AKTIVIERT"]})
   ```
   Test: `assert app.test_client().get("/api/status").json["modus"] == "tresor"`
2. Siehe `tests/test_tresor.py::test_api_nur_mit_anmeldung_und_csrf` (letzte Zeile).
3. ```python
   def befehl_statistik(_args):
       conn = _verbindung()
       for nutzung, n in conn.execute("SELECT COALESCE(nutzung,'-'), COUNT(*) FROM konten GROUP BY nutzung"):
           print(f"{nutzung:<14} {n}")
       print("Tresore:", tresor.statistik(conn)[0])
   ```
   + `unter.add_parser("statistik").set_defaults(f=befehl_statistik)`
4. Post/Redirect/Get: Ein Neuladen der Seite schickt das Formular nicht noch einmal ab.
</details>
