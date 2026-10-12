# Lektion 8 – Dateien, JSON, ZIP, CSV und reguläre Ausdrücke

**Lernziele:** Pfade mit `pathlib`, Text vs. Bytes und Kodierungen, JSON lesen/schreiben,
ZIP-Dateien ohne Entpacken lesen, Dateien im Speicher (`io`), CSV für Excel, Regex lesen und schreiben.

## 8.1 `pathlib`

```python
from pathlib import Path, PurePosixPath

Path.home() / ".instagram_auswerter" / "verlauf.sqlite3"     # "/" verbindet Pfade, betriebssystemunabhängig
pfad.parent.mkdir(parents=True, exist_ok=True)                # Ordner anlegen, falls nötig
pfad.exists(), pfad.read_text(), pfad.write_text("…")
Path(__file__).resolve().parent                               # Ordner der aktuellen Datei
PurePosixPath("connections/x/followers_1.json").name          # 'followers_1.json' (ZIP-Pfade nutzen immer "/")
```

## 8.2 Text und Bytes

Dateien und Netzwerk liefern **Bytes**. Zu Text wird es erst durch Dekodieren:

```python
roh: bytes = archiv.read("followers_1.json")
text = roh.decode("utf-8-sig")          # "-sig" entfernt ein BOM (Windows-Editoren setzen es an den Anfang)
text = roh.decode("utf-8", "ignore")    # kaputte Bytes überspringen statt Fehler
"Ä".encode("utf-8")                     # b'\xc3\x84'
```

Auch in der Gegenrichtung: Die CSV-Ausgabe beginnt mit `"﻿"` (BOM), damit Excel die Datei
als UTF-8 erkennt und Umlaute richtig zeigt (`web/app.py::freunde_export`).

## 8.3 JSON

```python
import json
daten = json.loads(text)                               # Text -> Python (dict/list/str/int/float/bool/None)
json.dumps(daten, ensure_ascii=False, indent=2)        # Python -> Text; Umlaute bleiben lesbar
```

Robustes Lesen ohne Absturz bei Müll (archive_reader.py):

```python
def _json_oder_none(roh: bytes):
    try:
        return json.loads(roh.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
```

**Typen prüfen**, weil Exporte sich ändern:

```python
sld = eintrag.get("string_list_data")
if isinstance(sld, list) and sld and isinstance(sld[0], dict):
    ...
if isinstance(data_dict.get("timestamp"), (int, float)):
    ...
```

## 8.4 ZIP lesen, ohne zu entpacken

```python
import zipfile
with zipfile.ZipFile("export.zip") as archiv:
    for name in archiv.namelist():
        if name.endswith("following.json"):
            daten = json.loads(archiv.read(name))
```

`ZipFile` nimmt auch **Dateiobjekte** – z. B. einen Flask-Upload (`datei.stream`) oder einen
Puffer im Speicher. `zipfile.is_zipfile(obj)` prüft die Signatur, liest dafür aber im Objekt –
danach `obj.seek(0)` nicht vergessen.

Wie ZIP intern aufgebaut ist (Inhaltsverzeichnis am Ende), zeigt `web/static/tresor/zip.js` –
dort wird es mangels Bibliothek im Browser von Hand gelesen.

## 8.5 Dateien im Arbeitsspeicher: `io`

```python
import io
puffer = io.BytesIO()
with zipfile.ZipFile(puffer, "w") as z:            # tests/conftest.py: Test-Export erzeugen
    z.writestr("connections/followers_and_following/following.json", json.dumps({...}))
roh = puffer.getvalue()                             # fertige ZIP als bytes

text_puffer = io.StringIO()                         # export.py: CSV erst in einen String schreiben
```

So braucht man für Tests und Downloads keine temporären Dateien.

## 8.6 CSV

```python
import csv, io
puffer = io.StringIO()
schreiber = csv.writer(puffer, delimiter=";")       # ";" – deutsches Excel erwartet Semikolon
schreiber.writerow(["username", "quelle"])
schreiber.writerows([["anna", "gegenseitig"], ["ben", "manuell"]])
puffer.getvalue()
```

`csv` kümmert sich um Anführungszeichen, wenn ein Wert selbst `;` oder Zeilenumbrüche enthält.

## 8.7 Reguläre Ausdrücke (`re`)

### Lesen lernen

| Muster | bedeutet |
|---|---|
| `.` | ein beliebiges Zeichen |
| `\d`, `\s`, `\w` | Ziffer, Leerraum, Wortzeichen |
| `[A-Za-z0-9._]` | eines dieser Zeichen; `[^…]` = keines davon |
| `*`, `+`, `?`, `{3,30}` | 0+, 1+, 0–1, 3 bis 30 Mal |
| `^`, `$` | Anfang, Ende |
| `( … )` | Gruppe (zum Herausholen) |
| `(?: … )` | Gruppe ohne Herausholen |
| `(?<![a-z])` | „davor steht kein Buchstabe“ (Lookbehind) |

### Projektbeispiele

```python
# parser.py: Nutzername aus Profil-Link
_HREF_MUSTER = re.compile(r"(?:instagram\.com/(?:_u/)?|tiktok\.com/@)([A-Za-z0-9._]+)/?", re.IGNORECASE)
treffer = _HREF_MUSTER.search("https://www.instagram.com/_u/anna.m/")
treffer.group(1)    # 'anna.m'

# konten.py: erlaubte Benutzernamen
_NAME_MUSTER = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
bool(_NAME_MUSTER.match("anna_m"))   # True

# instagram_export.py: "followers_1.json" -> "followers"
re.sub(r"(_\d+)?\.(json|html)$", "", "followers_1.json")

# web/tresor.py: nur verschlüsselte Blöcke
_FORMAT = re.compile(r"^FA1\.[A-Za-z0-9_-]{16,64}\.[A-Za-z0-9_-]{12,32}\.[A-Za-z0-9_-]{16,}$")
```

`re.compile` einmal auf Modulebene spart Arbeit bei jedem Aufruf und gibt dem Muster einen Namen.
`r"…"` (Raw-String) verhindert, dass Python `\d` selbst umdeutet.

Funktionen: `match` (am Anfang), `fullmatch` (ganzer Text), `search` (irgendwo), `findall`
(alle als Liste), `finditer` (alle als Match-Objekte), `sub` (ersetzen), `split` (zerlegen).

### Wörter mit Wortgrenzen (kommentar_bewertung.py)

```python
def _muster(woerter):
    teile = [re.escape(w[:-1]) + r"[a-zäöüß]*" if w.endswith("*") else re.escape(w) for w in woerter]
    return re.compile(r"(?<![a-zäöüß])(" + "|".join(teile) + r")(?![a-zäöüß])", re.IGNORECASE)
```

`re.escape` macht Sonderzeichen in Nutzereingaben harmlos. Die Lookarounds verhindern, dass
„Klasse“ das Wort „ass“ trifft.

## 8.8 HTML parsen

Für HTML nie Regex für die Struktur verwenden, sondern einen Parser (`html.parser.HTMLParser`,
Lektion 4). Regex ist nur ok, um aus einzelnen Attributwerten etwas herauszuholen.

## Übungen

1. Schreibe `def zeilen_zaehlen(pfad: Path) -> int`, die eine Textdatei mit BOM korrekt liest.
2. Erzeuge im Speicher eine ZIP mit `followers_1.json` und lies sie mit `core.archive_reader.lade_export`
   wieder ein (Tipp: `tests/conftest.py::export_zip`).
3. Schreibe eine Regex, die Datumsangaben `TT.MM.JJJJ` findet und die drei Teile als Gruppen liefert.
4. Exportiere die Freunde-Liste als CSV mit den Spalten `name;seit` in einen String.

<details><summary>Lösungen</summary>

1. `return len(pfad.read_text(encoding="utf-8-sig").splitlines())`
2. ```python
   import io, sys; sys.path.insert(0, "tests")
   from conftest import export_zip
   from core.archive_reader import lade_export
   inhalt = lade_export(io.BytesIO(export_zip(["anna"], ["ben"])), "x.zip")
   inhalt.follower, inhalt.following
   ```
3. `re.findall(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", "am 14.11.2023 und 01.02.2024")`
   → `[('14', '11', '2023'), ('01', '02', '2024')]`
4. ```python
   puffer = io.StringIO()
   w = csv.writer(puffer, delimiter=";")
   w.writerow(["name", "seit"])
   w.writerows((f.username, f.folgt_mir_seit) for f in freunde_ermitteln(follower, following))
   puffer.getvalue()
   ```
</details>
