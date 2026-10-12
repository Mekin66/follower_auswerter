# Lektion 2 – Moderne Syntax, die das Projekt ständig nutzt

**Lernziele:** f-Strings sicher einsetzen, Comprehensions statt Schleifen schreiben,
Mengenoperationen für Vergleiche nutzen, `sorted` mit `key`, Walross-Operator, Entpacken.

## 2.1 f-Strings

```python
anzahl, name = 3, "anna"
f"{anzahl} Account(s) von {name} entfernt."      # Variablen einsetzen
f"{groesse / 1024:>9.1f} KB"                      # Format: rechtsbündig, 9 breit, 1 Nachkommastelle
f"{kid:>4}  {name:<20}"                           # web/verwaltung.py: Tabellen-Ausgabe
f"{datetime.datetime.now():%d.%m.%Y %H:%M}"       # Datum formatieren (web/app.py)
f"{name!r}"                                       # repr() -> 'anna' mit Anführungszeichen (gut zum Debuggen)
```

**Nicht** für SQL! Werte gehören dort als Parameter `?` hinein (Lektion 9).

## 2.2 Comprehensions

Eine Schleife, die eine neue Liste/Menge/dict baut, schreibt man kürzer als Comprehension:

```python
# Liste: alle, denen ich folge, die mir nicht folgen (removal_session.py)
sorted(user for user in following_daten if user not in follower_daten)

# dict: Einstellungen einsammeln (web/app.py)
cfg = {name: getattr(einstellungen, name) for name in dir(einstellungen) if name.isupper()}

# set: Spaltennamen einer Tabelle (history_store.py)
{zeile[1] for zeile in conn.execute("PRAGMA table_info(konten)")}

# dict "umdrehen" und dabei Duplikate entfernen (archive_reader.py)
inhalt.kommentare = list({k.id: k for k in inhalt.kommentare}.values())
```

Das letzte Beispiel ist ein Klassiker: Ein dict hat jeden Schlüssel nur einmal – also bleibt
pro `id` nur ein Kommentar übrig, die Reihenfolge bleibt erhalten.

**Generator-Ausdruck** = Comprehension mit runden Klammern; erzeugt keine Liste im Speicher:

```python
sum(1 for z in buchstaben if z.isupper())          # kommentar_netz.py
any(_TIKTOK_NAME.match(z) for z in zeilen)         # bricht beim ersten Treffer ab
```

## 2.3 Mengen (set) – das Herz der Auswertung

```python
follower  = {"anna", "ben", "carl"}
following = {"anna", "dora"}

following - follower      # {'dora'}            folgen mir nicht zurück
follower - following      # {'ben', 'carl'}     ich folge nicht zurück
follower & following      # {'anna'}            gegenseitig ("Freunde")
follower | following      # alle zusammen
```

`set(dict)` nimmt die Schlüssel. Deshalb funktioniert in `diff_engine.py`:

```python
neu_dazugekommen = set(neu) - set(alt)          # neu, alt sind dict[str, str]
```

`in` ist bei Mengen und dicts *sehr* schnell (Hash-Tabelle), bei Listen langsam
(muss alle durchsuchen). Bei 10 000 Followern merkt man den Unterschied deutlich.

## 2.4 Sortieren mit `key`

```python
sorted(namen)                                              # alphabetisch
sorted(namen, key=len)                                     # nach Länge
auswahl.sort(key=lambda k: -(k.zeitstempel or 0))          # neueste zuerst (aktivitaet.py)
auswahl.sort(key=lambda k: (-bewertungen[k.id].punkte, -(k.zeitstempel or 0)))   # erst Punkte, dann Zeit
sorted(namen, key=lambda n: n.lower().endswith(".html"))   # JSON vor HTML (False < True)
```

Ein **Tupel** als Schlüssel sortiert nach dem ersten Element, bei Gleichstand nach dem zweiten usw.
`k.zeitstempel or 0` ersetzt `None` durch 0 – `None` lässt sich nicht mit Zahlen vergleichen.

## 2.5 Walross-Operator `:=`

Zuweisen *und* prüfen in einem Ausdruck (seit Python 3.8):

```python
# txt_format.py
if treffer := _TIKTOK_DATUM.match(zeile):
    letztes_datum = datum_lesen(treffer.group(1))

# web/app.py
if (fehler := _tresor_zugang()) is not None:
    return fehler
```

Ohne Walross bräuchte man jeweils eine Zeile mehr. Sparsam einsetzen – nur, wo es lesbarer wird.

## 2.6 Entpacken

```python
erstellt_am, label = meta                          # Tupel auf zwei Variablen
for username, liste, seit_datum in conn.execute(...):   # jede Zeile direkt entpacken
kid, name, email = treffer
anzahl, summe = conn.execute("SELECT COUNT(*), SUM(groesse) FROM tresore").fetchone()
art, _, ziel_name = aktion.partition(":")          # "_" = Wert wird nicht gebraucht
daten = {"konto": info, **extra}                   # dicts zusammenführen
```

## 2.7 Kleine, nützliche Eingebaute

```python
"verschieben:freunde".partition(":")     # ('verschieben', ':', 'freunde')
text.strip().lower()                     # Leerzeichen weg, klein
" ".join(["a", "b"])                     # 'a b'
dict.setdefault(name, "Unbekannt")       # nur setzen, wenn noch nicht vorhanden (txt_format.py)
dict.get("x", standard)                  # lesen mit Standardwert
enumerate(liste)                         # (index, element)
zip(namen, werte)                        # paarweise, z. B. dict(zip(namen, zeile)) in konten.py
min(..., default=0) / max(kandidaten, key=len, default="")
```

## 2.8 Bedingte Ausdrücke und Wahrheitswerte

```python
quelle = QUELLE_BEIDES if user in gegenseitig and user in manuell else QUELLE_GEGENSEITIG
ziel = request.form.get("zurueck", "") or url_for("start")    # leerer String ist "falsy"
```

„Falsy“ sind: `None`, `False`, `0`, `""`, `[]`, `{}`, `set()`. Alles andere ist „truthy“.

## Übungen

1. Gegeben `alt = {"a": "1", "b": "2"}`, `neu = {"b": "2", "c": "3"}`. Berechne mit Mengen, wer neu ist und wer weg ist.
2. Schreibe als dict-Comprehension: aus `["Anna", "ben", "anna"]` ein dict `{name_klein: anzahl}`.
3. Sortiere `[("anna", 3), ("ben", 10), ("carl", 3)]` absteigend nach Zahl, bei Gleichstand alphabetisch.
4. Was liefert `"@Anna.M".lstrip("@").lower()` und warum reicht das nicht als `normalisiere_username`?
5. Schreibe mit Walross: lies Zeilen aus einer Liste, bis eine leere kommt, und gib die Anzahl zurück.

<details><summary>Lösungen</summary>

1. `set(neu) - set(alt)` → `{'c'}`; `set(alt) - set(neu)` → `{'a'}`.
2. ```python
   namen = ["Anna", "ben", "anna"]
   {n: [x.lower() for x in namen].count(n) for n in {x.lower() for x in namen}}
   # besser lesbar: from collections import Counter; Counter(x.lower() for x in namen)
   ```
3. `sorted(daten, key=lambda t: (-t[1], t[0]))` → `[('ben', 10), ('anna', 3), ('carl', 3)]`
4. `'anna.m'` – aber Profil-Links (`https://instagram.com/anna.m/`), Leerzeichen und unerlaubte
   Zeichen würden nicht behandelt. Genau das macht die Regex in `parser.py`.
5. ```python
   def zaehlen(zeilen):
       it, n = iter(zeilen), 0
       while (z := next(it, "")) != "":
           n += 1
       return n
   ```
</details>
