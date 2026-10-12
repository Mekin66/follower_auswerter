# Lektion 11 – Threads, Locks und Sicherheit

**Lernziele:** Hintergrundarbeit mit Threads, Race Conditions mit Locks verhindern, warum
gunicorn mit genau einem Worker läuft; Passwörter richtig speichern, Zufall für Sicherheit,
CSRF, signierte Tokens, Grundbegriffe der Verschlüsselung im Tresor.

## 11.1 Threads

```python
import threading

def im_hintergrund():
    for erg in pruefe_mehrere(offene, ...):
        ...

threading.Thread(target=im_hintergrund, daemon=True).start()
return redirect(url_for("entfolgen", snapshot_id=snapshot_id))     # Antwort sofort, Prüfung läuft weiter
```

`daemon=True`: Der Thread hält das Programm beim Beenden nicht auf.

**Wichtig:** Im Thread gibt es keinen Request mehr – `session`, `request`, `g` funktionieren dort
nicht. Deshalb wird vorher gemerkt, was gebraucht wird:

```python
plattform_des_jobs = plattform()   # im Thread gibt es keine Session mehr -> vorher merken
```

Python-Threads laufen wegen des GIL nicht echt parallel auf mehreren Kernen, aber für Warten
auf Netzwerk (wie hier) sind sie ideal.

## 11.2 Race Conditions und Locks

Greifen zwei Threads gleichzeitig auf dieselben Daten zu, kann es krachen:

```python
# Thread A und B gleichzeitig:
if schluessel not in pruefjobs:      # beide sehen "nicht vorhanden"
    pruefjobs[schluessel] = job      # beide starten eine Prüfung
```

Ein Lock lässt immer nur einen hinein:

```python
lock = threading.RLock()
with lock:
    if schluessel in pruefjobs and not pruefjobs[schluessel].fertig:
        return redirect(...)
    pruefjobs[schluessel] = PruefJob(gesamt=len(offene))
```

`RLock` (re-entrant) darf derselbe Thread mehrfach betreten – praktisch, wenn eine
geschützte Funktion eine andere geschützte aufruft.

## 11.3 Warum genau 1 gunicorn-Worker?

Worker sind getrennte **Prozesse** mit getrenntem Arbeitsspeicher. Die laufenden
Entfolgen-Abläufe (`ablaeufe`) liegen im Speicher eines Prozesses. Mit zwei Workern landet die
nächste Anfrage womöglich im anderen Prozess, der den Ablauf nicht kennt. Darum
`--workers 1 --threads 8`. Im **Tresor-Modus** ist der Server zustandslos (alles steckt in der DB
bzw. im Browser) – dort wären mehrere Worker kein Problem.

## 11.4 Passwörter speichern

Niemals im Klartext, niemals mit schnellen Hashes wie `sha256` allein:

```python
from werkzeug.security import generate_password_hash, check_password_hash
h = generate_password_hash("geheim123")     # 'scrypt:32768:8:1$<salt>$<hash>'
check_password_hash(h, "geheim123")          # True
```

Der Hash enthält Verfahren, Parameter und ein zufälliges **Salt** – gleiche Passwörter ergeben
verschiedene Hashes, und scrypt ist absichtlich langsam (bremst Durchprobieren).

## 11.5 Zufall für Sicherheit: `secrets`, nicht `random`

```python
import secrets
secrets.token_urlsafe(24)       # CSRF-Token, anonyme IDs
secrets.token_hex(32)           # SECRET_KEY
secrets.compare_digest(a, b)    # Vergleich in konstanter Zeit
```

`random` ist vorhersagbar (für Spiele/Simulationen gedacht). `compare_digest` verhindert
Timing-Angriffe: Ein normales `==` bricht beim ersten falschen Zeichen ab, und aus der
Antwortzeit könnte man das Token Zeichen für Zeichen erraten.

## 11.6 CSRF

Eine fremde Seite könnte ein Formular bauen, das an *deine* App postet – der Browser schickt
das Login-Cookie mit. Schutz: ein Zufallstoken in jedem Formular, das die fremde Seite nicht
kennen kann (Lektion 10, `_vor_jedem_request`). Zusätzlich `SameSite=Lax` beim Cookie.

## 11.7 Signierte Tokens (E-Mail-Links)

```python
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

s = URLSafeTimedSerializer("SECRET_KEY")
token = s.dumps({"id": 5, "email": "a@b.de"}, salt="email")        # in den Link
daten = s.loads(token, salt="email", max_age=48 * 3600)             # beim Klick; wirft bei Fälschung/Ablauf
```

Der Inhalt ist lesbar (Base64), aber nicht fälschbar. `salt` trennt Zwecke: Ein
E-Mail-Token taugt nicht als Passwort-Token. Der Passwort-Link enthält zusätzlich einen
Fingerabdruck des aktuellen Hashes – nach dem Ändern passt er nicht mehr (einmalig nutzbar).

## 11.8 Verschlüsselung im Tresor – die Begriffe

Die Verschlüsselung passiert in JavaScript (`krypto.js`), die Konzepte sind aber dieselben
wie in Python. Mit Python lässt sich der Schlüssel-Teil nachvollziehen:

```python
import hashlib, os
salt = os.urandom(16)
schluessel = hashlib.pbkdf2_hmac("sha256", b"mein-tresor-pw", salt, 600_000, dklen=32)   # 32 Byte = 256 Bit
```

| Begriff | Bedeutung | im Projekt |
|---|---|---|
| **KDF** (PBKDF2) | macht aus einem Passwort einen Schlüssel; absichtlich langsam | 600 000 Runden SHA-256 |
| **Salt** | Zufall, damit gleiche Passwörter verschiedene Schlüssel ergeben | 16 Byte, steht offen im Block |
| **AES-256** | symmetrische Verschlüsselung (gleicher Schlüssel zum Ver- und Entschlüsseln) | |
| **GCM** | Betriebsart mit eingebauter Echtheitsprüfung (erkennt Manipulation/falschen Schlüssel) | |
| **IV/Nonce** | Zufall pro Verschlüsselung; darf sich **nie** mit demselben Schlüssel wiederholen | 12 Byte, neu bei jedem Speichern |
| **Ende-zu-Ende** | nur die Endpunkte (Browser) haben den Schlüssel, der Server nicht | Tresor-Passwort verlässt den Browser nie |

Zum Ausprobieren in Python (Paket `cryptography`, nicht im Projekt nötig):

```python
# pip install cryptography
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
aes = AESGCM(schluessel)
iv = os.urandom(12)
geheim = aes.encrypt(iv, b'{"follower": ["anna"]}', b"FA1")
aes.decrypt(iv, geheim, b"FA1")      # b'{"follower": ["anna"]}'
aes.decrypt(iv, geheim, b"FA2")      # InvalidTag – falsche Zusatzdaten
```

Damit könntest du sogar einen Tresor-Block in Python öffnen (Format: `FA1.salt.iv.geheimtext`,
Base64url, Inhalt gzip-komprimiertes JSON) – siehe Abschlussprojekt in Lektion 12.

## 11.9 Weitere Schutzmaßnahmen im Projekt

- **Content-Security-Policy** (`TRESOR_CSP`): Browser führt nur Skripte vom eigenen Server aus.
- **Login-Sperre** nach 10 Fehlversuchen in 15 Minuten pro IP (`_zu_viele_fehlversuche`).
- **Keine Benutzer-Aufzählung:** Bei „E-Mail schon vergeben“ zeigt die Seite dasselbe wie bei
  Erfolg und schickt dem Inhaber eine Info-Mail.
- **Session-Fixation:** Nach dem Login `session.clear()` und neu befüllen.
- **Offene Weiterleitungen** verhindert: `ziel.startswith("/") and not ziel.startswith("//")`.
- **Upload-Größe** begrenzt (`MAX_CONTENT_LENGTH`), Tresor-Größe begrenzt (`TRESOR_MAX_KB`).

## Übungen

1. Starte 10 Threads, die je 10 000-mal `zaehler += 1` machen (globale Variable). Ist das Ergebnis
   immer 100 000? Baue einen Lock ein.
2. Erzeuge zwei Hashes desselben Passworts mit `generate_password_hash`. Sind sie gleich? Warum
   funktioniert `check_password_hash` trotzdem?
3. Erzeuge ein `itsdangerous`-Token, ändere ein Zeichen und versuche `loads`. Welche Ausnahme kommt?
4. Leite mit `hashlib.pbkdf2_hmac` zweimal einen Schlüssel aus demselben Passwort ab – einmal mit
   gleichem, einmal mit anderem Salt. Miss die Zeit für 600 000 Runden.

<details><summary>Lösungen</summary>

1. Oft ja (das GIL schützt einfache Operationen häufig), aber garantiert ist es **nicht** –
   `+=` besteht aus Lesen, Rechnen, Schreiben. Mit `with lock: zaehler += 1` ist es sicher.
2. Verschieden (anderes Salt). Das Salt steht im Hash; `check_password_hash` liest es heraus und rechnet nach.
3. `BadSignature`.
4. Gleiches Salt → gleicher Schlüssel, anderes Salt → anderer. Dauer typischerweise 0,2–0,8 s –
   genau diese Bremse macht Passwort-Raten teuer.
</details>
