# Lektion 7 – Fehlerbehandlung und Kontextmanager

**Lernziele:** eigene Ausnahmen sinnvoll entwerfen, Fehler gezielt (nicht pauschal) fangen,
`raise … from` verstehen, `with` und eigene Kontextmanager schreiben.

## 7.1 Grundform

```python
try:
    inhalt = lade_export(datei)
except ExportFormatFehler as e:          # erwarteter Fehler: verständliche Meldung
    flash(str(e))
except Exception as e:                   # unerwartet: allgemeiner Hinweis, Programm läuft weiter
    flash(f"Die Datei konnte nicht gelesen werden ({e}).")
else:
    ...                                  # nur wenn KEIN Fehler kam
finally:
    ...                                  # IMMER (z. B. aufräumen)
```

Regel: **So eng wie möglich fangen.** `except Exception` nur an der äußersten Stelle (Route,
Hintergrund-Thread), wo ein Absturz schlimmer wäre als eine allgemeine Meldung. Im Projekt
stehen solche Stellen mit `# noqa: BLE001` und Begründung.

`finally` im Projekt (`web/app.py`, Hintergrundprüfung):

```python
try:
    for erg in pruefe_mehrere(...): ...
except PruefungNichtMoeglich as e:
    job.fehler = str(e)
finally:
    job.fertig = True          # sonst wartet die Webseite ewig
```

## 7.2 Eigene Ausnahmen entwerfen

```python
class TresorFehler(ValueError):                    # Basisklasse für alles rund um den Tresor
    pass

class VersionsKonflikt(TresorFehler):              # Spezialfall mit Zusatzinfo
    def __init__(self, aktuelle_version: int):
        super().__init__("Der Tresor wurde inzwischen an anderer Stelle geändert.")
        self.aktuelle_version = aktuelle_version
```

Benutzung in `web/app.py` – **speziell vor allgemein**:

```python
try:
    version = tresor.speichern(...)
except tresor.VersionsKonflikt as e:
    return _api_fehler(str(e), 409, grund="konflikt", version=e.aktuelle_version)
except tresor.TresorFehler as e:
    return _api_fehler(str(e), 400, grund="format")
```

Vorteile eigener Klassen: Der Aufrufer kann gezielt reagieren (409 vs. 400), Zusatzdaten
mitgeben (`aktuelle_version`), und die Meldung ist für Menschen geschrieben.

Von welcher eingebauten Klasse erben?
`ValueError` – falscher Wert (Formatfehler, Konto-Eingaben); `RuntimeError` – „geht gerade
nicht“ (`PruefungNichtMoeglich`, `MailFehler`); `LookupError`/`KeyError` – etwas nicht gefunden.

## 7.3 `raise … from`

```python
except (OSError, smtplib.SMTPException) as e:
    log.error("Mailversand an %s fehlgeschlagen: %s", an, e)
    raise MailFehler(str(e)) from e              # mail.py
```

Die neue Ausnahme ist für den Aufrufer verständlich (`MailFehler`), die Ursache bleibt im
Traceback erhalten („The above exception was the direct cause of …“). Mit `from None`
unterdrückt man die Ursache bewusst (z. B. `konten.py`, wenn ein `IntegrityError` nur
„Name vergeben“ bedeutet).

## 7.4 Fehler als Rückgabewert oder Ausnahme?

| Rückgabe `None` | Ausnahme |
|---|---|
| „nicht gefunden“ ist normal (`konto_info()` → `None`) | etwas ist schiefgelaufen und der Aufrufer muss reagieren |
| `anmelden()` → `None` bei falschem Passwort | `snapshot_laden()` → `ValueError`, wird in der Route zu 404 |

## 7.5 Kontextmanager: `with`

`with` garantiert Aufräumen – auch bei Fehlern:

```python
with zipfile.ZipFile(zip_pfad) as archiv:          # Datei wird sicher geschlossen
    namen = archiv.namelist()

with urllib.request.urlopen(anfrage, timeout=timeout) as a:   # Verbindung wird geschlossen
    text = a.read()

with lock:                                          # Lock wird sicher freigegeben (Lektion 11)
    ablaeufe[schluessel] = ablauf

with server:                                        # smtplib: QUIT wird gesendet
    server.send_message(nachricht)
```

Achtung bei `sqlite3`: `with conn:` **schließt nicht** die Verbindung, sondern macht eine
Transaktion (commit bei Erfolg, rollback bei Fehler). Schließen muss man selbst (`conn.close()`)
oder `contextlib.closing(conn)` nutzen.

### Eigener Kontextmanager

```python
from contextlib import contextmanager
import sqlite3

@contextmanager
def verbindung(pfad):
    conn = sqlite3.connect(pfad)
    try:
        yield conn            # hier läuft der Block im "with"
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

with verbindung("web/daten/web.sqlite3") as conn:
    conn.execute("UPDATE konten SET nutzung = 'privat' WHERE nutzung IS NULL")
```

Flask macht für die Web-App etwas Ähnliches: `db()` öffnet pro Request eine Verbindung,
`@app.teardown_appcontext` schließt sie danach – egal ob die Route erfolgreich war.

## 7.6 Logging statt print

```python
import logging
log = logging.getLogger(__name__)
log.warning("TESTMODUS – Mail an %s nicht verschickt", an)    # %s: wird nur formatiert, wenn ausgegeben
log.error("Mailversand an %s fehlgeschlagen: %s", an, e)
log.exception("Unerwarteter Fehler")                           # inkl. Traceback, nur in except-Blöcken
```

gunicorn leitet die Logs nach `docker compose logs app`.

## Übungen

1. Schreibe `class ZuVieleVersuche(RuntimeError)` mit Attribut `sekunden` (Wartezeit) und eine
   Funktion, die sie bei mehr als 10 Versuchen wirft.
2. Was ist falsch?
   ```python
   try:
       konto = konten.registrieren(...)
   except konten.KontoFehler:
       flash("Fehler")
   except konten.EmailVergeben:
       ...
   ```
3. Schreibe einen Kontextmanager `zeitmessung(name)`, der beim Verlassen die Dauer ausgibt.
4. Warum steht im Hintergrund-Thread `except Exception`, in `lese_txt` aber nicht?

<details><summary>Lösungen</summary>

1. ```python
   class ZuVieleVersuche(RuntimeError):
       def __init__(self, sekunden: int):
           super().__init__(f"Zu viele Versuche. Bitte {sekunden} s warten.")
           self.sekunden = sekunden
   ```
2. `EmailVergeben` ist eine Unterklasse von `KontoFehler` – der erste `except` fängt sie schon,
   der zweite wird nie erreicht. Spezielle Ausnahmen zuerst.
3. ```python
   @contextmanager
   def zeitmessung(name):
       start = time.perf_counter()
       try:
           yield
       finally:
           print(f"{name}: {time.perf_counter() - start:.3f} s")
   ```
4. Ein unbehandelter Fehler im Thread würde still verschwinden und `job.fertig` nie gesetzt –
   die Seite würde ewig laden. `lese_txt` dagegen soll Fehler an den Aufrufer weitergeben.
</details>
