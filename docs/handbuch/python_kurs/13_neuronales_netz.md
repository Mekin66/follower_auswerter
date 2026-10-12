# Lektion 13 – Ein neuronales Netz von Grund auf

**Lernziele:** verstehen, wie aus Text Zahlen werden, was ein Neuron rechnet, wie ein Netz durch
Rückpropagation lernt, wie man ehrlich misst, ob es etwas taugt – und wie man erklärt, *warum*
es etwas entscheidet. Alles am Beispiel von `core/kommentar_netz.py` (reines Python, keine Bibliothek).

## 13.1 Warum ein Netz statt Wortlisten?

Die alte Bewertung zählte Treffer in Wortlisten. Probleme:
- „Idioten“, „iiidiot“, „𝐈𝐝𝐢𝐨𝐭“ oder „Ты идиот“ standen nicht auf der Liste.
- „Wahl“ war immer heikel – auch in „gute Wahl, das Kleid!“.
- Jede Verbesserung hieß: Liste von Hand ergänzen.

Ein Netz lernt aus **Beispielen**. Wer es verbessern will, ergänzt Beispiele, nicht Regeln.
Und es kann aus den Entscheidungen des Nutzers dazulernen.

## 13.2 Von Text zu Zahlen: Merkmale

Ein Netz rechnet mit Zahlen. Also wird jeder Kommentar in einen **Vektor** übersetzt.

### Schritt 1: Unicode normalisieren (Lektion 8)

```python
>>> from core.kommentar_netz import woerter
>>> woerter("𝐈𝐝𝐢𝐨𝐭!! Du bist sooooo DUMM 😂")
['idiot', 'du', 'bist', 'soo', 'dumm']
```

### Schritt 2: Merkmale sammeln

Für jedes Wort: das Wort selbst und seine **Zeichen-N-Gramme** (3 bis 5 Zeichen, mit Rand `<…>`):

```
"idiot" -> w:idiot, c:<id, c:idi, c:dio, c:iot, c:ot>, c:<idi, c:idio, … , c:<idio, c:idiot, c:diot>
```

Warum N-Gramme? „idioten“ teilt viele N-Gramme mit „idiot“ → das Netz erkennt die
Verwandtschaft, auch wenn „idioten“ nie im Training vorkam. Emojis werden als eigene Merkmale
gezählt (`e:😂`).

### Schritt 3: Feature-Hashing

Statt eines Wörterbuchs „Wort → Nummer“ wird jedes Merkmal per Hash auf einen von 16 384
Plätzen abgebildet:

```python
def _platz(merkmal: str) -> tuple[int, float]:
    h = zlib.crc32(merkmal.encode("utf-8"))           # stabil: gleiche Bytes -> gleiche Zahl
    return h % DIM, (1.0 if (h >> 16) & 1 else -1.0)  # Platz und Vorzeichen
```

- Vorteil: kein Wörterbuch, beliebige neue Wörter haben automatisch einen Platz.
- Nachteil: Zwei Merkmale können denselben Platz treffen (**Kollision**). Das zufällige
  Vorzeichen sorgt dafür, dass sich Kollisionen im Mittel aufheben. Mit 2 048 Plätzen gab es
  spürbar mehr Fehlalarme als mit 16 384.
- **Nicht** Pythons `hash()` nehmen: Der ist bei jedem Programmstart anders (Sicherheitsfeature),
  das gespeicherte Netz würde nicht mehr passen.

Zum Schluss wird der Vektor auf Länge 1 normiert (lange Texte bekommen nicht automatisch größere
Werte). Dazu kommen sechs **Stil-Merkmale** mit festen Plätzen: Länge, Anteil Großbuchstaben,
„!!“/„??“, Telefon/E-Mail, nur Emojis/Zeichen, Link.

Ergebnis: ein *dünn besetzter* Vektor – von 16 390 Werten sind vielleicht 80 nicht null. Er wird
als dict `{platz: wert}` gespeichert.

## 13.3 Das Neuron

Ein Neuron bildet eine gewichtete Summe und schickt sie durch eine Aktivierungsfunktion:

```
h = tanh(b + w₁·x₁ + w₂·x₂ + … )
```

`tanh` drückt jede Zahl in den Bereich −1…1 und ist **nicht linear** – erst dadurch kann ein Netz
mehr als „Summe von Punkten“ lernen (z. B. „du“ allein ist harmlos, „du“ + Schimpfwort nicht).

## 13.4 Das Netz: zwei Schichten

```
x (16 390, dünn) ──W1──► h (24, tanh) ──W2──► z (3) ──softmax──► p = [harmlos, prüfen, kritisch]
```

```python
def _vorwaerts(self, eingaben):
    h = list(self.b1)
    for i, x in eingaben:                  # nur die ~80 vorhandenen Merkmale!
        zeile = self.w1[i]
        for j in range(self.versteckt):
            h[j] += zeile[j] * x
    h = [math.tanh(v) for v in h]
    z = list(self.b2)
    for j, hj in enumerate(h):
        for k in range(3):
            z[k] += hj * self.w2[j][k]
    return h, _softmax(z)
```

**Softmax** macht aus drei beliebigen Zahlen Wahrscheinlichkeiten, die sich zu 1 addieren:

```python
def _softmax(werte):
    m = max(werte)                         # Trick gegen Überlauf bei exp()
    e = [math.exp(v - m) for v in werte]
    return [v / sum(e) for v in e]
```

Weil nur die vorhandenen Merkmale angefasst werden, kostet ein Kommentar ca. 0,2 ms – schnell
genug in reinem Python, auch auf dem Handy.

## 13.5 Lernen: Verlust und Rückpropagation

**Verlust (Kreuzentropie):** Wie überrascht ist das Netz von der richtigen Antwort?
`-log(p[richtige_klasse])` – bei 99 % richtig ≈ 0,01, bei 1 % ≈ 4,6.

**Gradientenabstieg:** Jedes Gewicht ein kleines Stück in die Richtung schieben, in der der
Verlust sinkt. Die Richtung liefert die **Ableitung**, berechnet von hinten nach vorne
(„Rückpropagation“, Kettenregel):

```python
d_z = [p[k] - soll[k] for k in range(3)]                        # Softmax + Kreuzentropie: so einfach
d_h = [sum(w2[j][k] * d_z[k] for k in range(3)) * (1 - h[j]**2)  # tanh'(x) = 1 - tanh(x)²
       for j in range(versteckt)]
w2[j][k] -= lernrate * d_z[k] * h[j]                            # Ausgabeschicht
w1[i][j] -= lernrate * d_h[j] * x_i                             # nur für vorhandene Merkmale i
```

Das ist der Kern von `_schritt()`. Dazu kommen drei bewährte Kniffe:

| Kniff | Warum | im Code |
|---|---|---|
| **Klassengewichte** | Gibt es weniger „prüfen“-Beispiele, zählen diese stärker | `gewichte` in `trainieren()` |
| **Label Smoothing** | Ziel ist 90 % statt 100 % → weniger übersicher, bessere Verallgemeinerung | `soll` in `_schritt()` |
| **L2-Regularisierung** | zieht Gewichte leicht Richtung 0 → kein Auswendiglernen einzelner Wörter | `l2 * zeile[j]` |
| **sinkende Lernrate** | erst große, dann feine Schritte | `lernrate / (1 + epoche * 0.05)` |

Eine **Epoche** = einmal alle Beispiele (gemischt) durchgehen. 40 Epochen × 400 Beispiele ≈ 5 Sekunden.

## 13.6 Ehrlich messen: Kreuzvalidierung

Nach dem Training erkennt das Netz alle Trainingsbeispiele richtig (100 %) – das sagt wenig.
Die Frage ist: Wie gut ist es bei Kommentaren, die es **nie gesehen** hat?

```python
def kreuzvalidierung(beispiele, teile=5):
    for t in range(teile):
        test = gemischt[t::teile]                       # jedes 5. Beispiel zurückhalten
        training = [b for i, b in enumerate(gemischt) if i % teile != t]
        netz = KommentarNetz(); netz.trainieren(training)
        # … auf "test" prüfen und zählen
```

Aktuell ca. **72 %** bei drei Klassen (Raten wäre 33 %). Ausprobierte Einstellungen (größeres
Netz, mehr/weniger Regularisierung) änderten wenig – der Engpass sind die **Daten**: gut 400
Beispiele sind wenig. Mehr und vielfältigere Beispiele sind der wirksamste Hebel.
Die Verwechslungsliste zeigt, wo es hakt (`kritisch->harmlos: 30` = übersehene Beleidigungen).

## 13.7 Erklären: Welches Wort war schuld?

Ein Netz ist erst einmal eine „Black Box“. Einfaches, ehrliches Verfahren (**Occlusion**):
jedes Wort einmal weglassen und schauen, wie stark das Risiko sinkt.

```python
basis = log_chance(risiko(text))
for wort in woerter(text):
    einfluss[wort] = basis - log_chance(risiko(text ohne wort))
```

Gemessen wird in **Log-Chancen** `log(r / (1 − r))`: Zwischen 99 % und 99,9 % liegen im
Prozentmaß kaum Unterschiede, in Log-Chancen aber deutliche. Die positiven Einflüsse werden zu
Anteilen normiert, z. B. „Idiot“ mit 61 %. In der App werden nur Einflüsse ab 15 % als Grund genannt
(`MIN_ANTEIL` in `kommentar_bewertung.py`), damit Füllwörter wie „ein“ nicht als Grund erscheinen.

```bash
python -m core.kommentar_netz testen "Was für ein dummer Trottel"
harmlos     2.1%
prüfen      2.0%
kritisch   95.9%
  'trottel': 66% des Risikos
  'dummer': 19% des Risikos
  'ein': 9% des Risikos
```

## 13.8 Aus Entscheidungen lernen

```python
def angepasst(self, eigene, basis=None, epochen=8):
    kopie = KommentarNetz.aus_dict(self.als_dict())                 # Original bleibt unverändert
    stichprobe = random.Random(len(eigene)).sample(basis, min(len(basis), 80))
    kopie.trainieren(stichprobe + list(eigene) * 3, epochen=epochen, lernrate=0.05)
    return kopie
```

- „Entfernen“ → Beispiel „kritisch“, „Behalten“ → „harmlos“.
- **Dreifach gewichtet**, damit die eigenen Entscheidungen zählen.
- **Mit Stichprobe der Grunddaten gemischt**, sonst „vergisst“ das Netz alles andere
  (*katastrophales Vergessen*).
- Kleine Lernrate, wenige Epochen: feinjustieren statt neu lernen (*Fine-Tuning*).

## 13.9 Speichern in UTF-8

```python
def speichern(self, pfad):
    pfad.write_text(json.dumps(self.als_dict(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
```

- `encoding="utf-8"` ausdrücklich – unter Windows wäre der Standard sonst cp1252.
- `ensure_ascii=False` schreibt „Grüße 😍“ lesbar statt `ü`.
- Nur benutzte Zeilen der ersten Schicht werden gespeichert (Hash-Plätze, die nie vorkamen, sind 0).
- Gewichte auf 4 Nachkommastellen gerundet → ca. 1,2 MB.

## 13.10 Grenzen – ehrlich gesagt

- Ironie, Insider, Zusammenhang (wer schreibt wem?) erkennt das Netz nicht.
- Es spiegelt die Beispiele wider: Was dort fehlt oder einseitig ist, macht es falsch.
- Es ist eine **Vorsortierung**. Die Entscheidung trifft immer der Nutzer.
- Große Sprachmodelle wären genauer, bräuchten aber Internet oder hunderte MB – das
  widerspricht dem Ziel „läuft lokal, nichts verlässt das Gerät“.

## Übungen

1. Probiere `python -m core.kommentar_netz testen "…"` mit eigenen Sätzen. Finde einen, den das Netz
   falsch einstuft, ergänze ihn (und zwei Varianten) in `kommentar_beispiele.tsv`, trainiere neu.
   Wie ändert sich die Trefferquote der Kreuzvalidierung?
2. Ändere `VERSTECKT` auf 8 und 64 und miss jeweils die Kreuzvalidierung. Was beobachtest du?
3. Entferne in `_text_merkmale` die Zeichen-N-Gramme (nur ganze Wörter). Wie gut erkennt das Netz
   danach „Idioten“ oder „iiidiot“?
4. Schreibe einen Test: Ein Netz, das nur mit `[("toll", harmlos), ("doof", kritisch)] * 10` trainiert
   wurde, stuft „toll toll“ als harmlos ein.
5. Für Fortgeschrittene: Ersetze `tanh` durch ReLU (`max(0, x)`, Ableitung 0 oder 1). Was musst du
   in `_vorwaerts` und `_schritt` ändern?

<details><summary>Lösungen / Hinweise</summary>

1. Typisch steigt die Quote nur wenig – einzelne Beispiele helfen vor allem bei *ähnlichen* Sätzen.
   Wichtig: danach `python -m pytest tests` (der Fingerabdruck-Test prüft, dass neu trainiert wurde).
2. Bei dieser Datenmenge kaum Unterschied (ca. 71–73 %); 64 Neuronen trainieren langsamer.
3. Ohne N-Gramme kennt das Netz nur exakt gesehene Wörter – „Idioten“ fällt dann oft auf „harmlos“.
4. ```python
   def test_mini_netz():
       n = kn.KommentarNetz()
       n.trainieren([("toll", "harmlos"), ("doof", "kritisch")] * 10, epochen=20)
       p = n.wahrscheinlichkeiten("toll toll")
       assert max(p, key=p.get) == "harmlos"
   ```
5. In `_vorwaerts`: `h = [max(0.0, v) for v in h]`; in `_schritt` statt `(1 - h[j] * h[j])` den Faktor
   `(1.0 if h[j] > 0 else 0.0)`. Achtung: Mit der Null-Initialisierung von W1 starten alle Neuronen bei 0 –
   bei ReLU lernt dann nichts („tote Neuronen“). Lösung: W1 klein zufällig initialisieren oder b1 leicht positiv.
</details>
