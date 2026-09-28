# Veröffentlichen – wie und wo

Kurzfassung: **Zuerst die Web-Version öffentlich machen** (ohne Konten), danach
optional die **Android-App** in Google Play. iOS erst später.

| Weg | Wofür | Aufwand | laufende Kosten |
|---|---|---|---|
| Web-App auf Render (Frankfurt) | schnellster Start, kein Serverwissen nötig | gering | bezahlter Plan für dauerhaften Speicher |
| Web-App auf eigenem VPS (z. B. Hetzner, Deutschland) | günstig, volle Kontrolle, DSGVO-freundlich | mittel | kleiner VPS + Domain |
| Android-App (Kivy) in Google Play | Nutzer, die eine „echte“ App wollen; läuft komplett offline auf dem Handy | hoch | einmalig 25 USD Entwicklerkonto |
| Desktop-.exe | nur für dich/Freunde | gering | keine |

---

## 1. Vorher erledigen (gilt für jeden Weg)

1. **Name ohne „Instagram“/„TikTok“.** Meta und TikTok erlauben ihre Marken nicht im Namen oder
   Logo fremder Apps; Stores lehnen solche Apps ab. Das Projekt heißt deshalb nach
   außen „Follower-Auswertung“. Beschreibend („für Instagram-Datenexporte“) ist ok.
2. **Impressum + Datenschutzerklärung** (Pflicht in Deutschland bei öffentlichem Angebot).
   Vorlagen liegen in `web/templates/impressum.html` und `datenschutz.html`; die Angaben
   kommen aus den Umgebungsvariablen `BETREIBER_NAME`, `BETREIBER_ADRESSE`,
   `BETREIBER_EMAIL`, `HOSTER_NAME`. Die Datenschutz-Vorlage ist ein Startpunkt, keine
   Rechtsberatung – im Zweifel prüfen lassen (z. B. über einen Generator wie e-recht24).
3. **Auftragsverarbeitungsvertrag (AVV)** mit dem Hoster abschließen (bei Hetzner/Render
   im Kundenkonto per Klick).
4. **Automatische Prüfung aus:** `AUTO_CHECK_AKTIVIERT=0`. Auf einem Server laufen alle
   Prüfungen über dieselbe IP – Instagram sperrt die schnell, und automatisiertes Abrufen
   widerspricht Instagrams Nutzungsbedingungen. In der Desktop-/Android-App (läuft beim
   Nutzer selbst) bleibt sie verfügbar.
5. **Konten erst einmal aus:** `ACCOUNTS_AKTIVIERT=0`. Siehe Abschnitt 4.

---

## 2. Web-App veröffentlichen

### Variante A: Render (am einfachsten)

1. Projekt auf GitHub hochladen (privates Repo reicht). `.venv`, `.idea`, `web/daten`
   nicht mit hochladen (siehe `.gitignore`).
2. Auf render.com anmelden → **New → Blueprint** → Repo wählen. `render.yaml` im
   Projekt legt alles an: Docker-Build, Region Frankfurt, 1 GB Speicher für die
   Datenbank, zufälliger `SECRET_KEY`.
3. Im Dashboard `BETREIBER_NAME`, `BETREIBER_ADRESSE`, `BETREIBER_EMAIL` eintragen.
4. Optional eigene Domain verbinden (Render → Settings → Custom Domain). HTTPS kommt automatisch.

### Variante B: Eigener Server (Hetzner o. Ä.)

1. Kleinsten VPS mit Ubuntu mieten, Docker installieren, Domain per A-Record auf die
   Server-IP zeigen lassen.
2. Projekt auf den Server kopieren, dann:
   ```bash
   cp packaging/server/.env.beispiel packaging/server/.env   # ausfüllen!
   # in packaging/server/Caddyfile die eigene Domain eintragen
   docker compose -f packaging/server/docker-compose.yml up -d --build
   ```
   Caddy besorgt das HTTPS-Zertifikat automatisch.
3. Backup: Das Docker-Volume `daten` enthält die komplette Datenbank (`web.sqlite3`).

### Wichtig für jeden Server

- Gunicorn **immer mit genau 1 Worker** starten (`--workers 1 --threads 8`, so im
  Dockerfile). Laufende Entfolgen-Abläufe liegen im Arbeitsspeicher; mit mehreren
  Workern würden Nutzer zwischen Prozessen springen.
- Niemals `debug=True` oder `flask run --debug` öffentlich laufen lassen.

---

## 3. Android-App in Google Play

Die Kivy-App läuft komplett auf dem Handy (keine Server, keine Konten nötig) und hat
alle Funktionen inkl. Listen und Kategorie-Auswahl.

1. Build (nur Linux oder Windows-WSL):
   ```bash
   pip install buildozer
   bash packaging/build_android.sh          # Test-APK aufs eigene Handy
   bash packaging/build_android.sh release  # .aab für Google Play
   ```
   Vorher in `mobile/buildozer.spec` `package.domain` auf etwas Eigenes setzen
   (z. B. `de.deinname`) – das ist später nicht mehr änderbar.
2. Google-Play-Console-Konto anlegen (einmalig 25 USD).
3. **Neue private Entwicklerkonten** müssen vor der Veröffentlichung einen
   **geschlossenen Test mit mindestens 12 Testern über 14 Tage** durchführen.
4. Im Store-Eintrag: Datenschutz-URL (die Web-Datenschutzseite oder eine eigene Seite),
   Formular „Datensicherheit“ ausfüllen (App sammelt keine Daten, alles bleibt lokal),
   Screenshots, Beschreibung ohne „Instagram“ im Titel.

## 4. iOS / App Store

Kivy auf iOS braucht einen Mac mit Xcode und ein Apple-Developer-Konto (99 USD/Jahr).
Eine reine „Webseite in App-Hülle“ lehnt Apple häufig ab (Richtlinie 4.2 „Minimum
Functionality“). Empfehlung: iOS-Nutzer vorerst die Web-Version nutzen lassen – sie
funktioniert im Safari-Browser und kann über „Zum Home-Bildschirm“ wie eine App abgelegt werden.

---

## 5. Die Konto-Funktion ein- und ausschalten

In `web/einstellungen.py`:

```python
ACCOUNTS_AKTIVIERT: bool = _bool("ACCOUNTS_AKTIVIERT", False)   # <- False/True
```

oder ohne Code-Änderung per Umgebungsvariable `ACCOUNTS_AKTIVIERT=1` bzw. `0`.

| | Konten AUS | Konten AN, nicht angemeldet | Konten AN, angemeldet |
|---|---|---|---|
| Auswertung, Freunde-Liste (gegenseitig), Verlauf, Vergleich, Entfolgen-Modus | ✓ | ✓ | ✓ |
| Daten nach 24 h automatisch gelöscht | ✓ | ✓ | – (bleiben, bis man sie löscht) |
| Markierungen dauerhaft + Auswahl „welche Gruppe erneut abfragen“ | – | – | ✓ |
| Listen: von mir blockiert / hat mich blockiert / Freunde manuell | – | – | ✓ |
| Blockierte Profile + enge Freunde aus dem Export übernehmen | – | – | ✓ |
| Konto löschen, alle Daten als JSON herunterladen | – | – | ✓ |

Weitere Schalter: `REGISTRIERUNG_OFFEN` (Konten an, aber keine neuen Registrierungen –
z. B. nur für dich), `ANONYM_AUFBEWAHRUNG_STUNDEN`, `MAX_UPLOAD_MB`.

Bevor du Konten öffentlich anschaltest: Datenschutzerklärung ergänzen (Konten werden in
der Vorlage schon automatisch erwähnt), regelmäßige Backups der Datenbank einrichten.
Passwörter werden gehasht gespeichert, es gibt Schutz gegen gefälschte Formulare (CSRF)
und eine Sperre nach 10 falschen Login-Versuchen in 15 Minuten.

### E-Mail-Bestätigung und Mailversand (ab Version 4)

Bei aktiven Konten muss man bei der Registrierung eine E-Mail-Adresse angeben und den
Link in der Bestätigungs-Mail anklicken (Double-Opt-in). Erst dann ist das Konto aktiv.
Unbestätigte Konten werden nach 48 Stunden gelöscht. Es gibt „Passwort vergessen“.

| Einstellung | Bedeutung |
|---|---|
| `E_MAIL_PFLICHT=1` | E-Mail-Adresse ist Pflicht |
| `E_MAIL_BESTAETIGUNG=1` | Konto erst nach Klick auf den Link aktiv |
| `NEWSLETTER_ABFRAGEN=0` | freiwilliges Häkchen „Neuigkeiten per E-Mail“ |
| `OEFFENTLICHE_URL` | z. B. `https://follower.example.de` – für die Links in den Mails |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_VERSCHLUESSELUNG`, `SMTP_BENUTZER`, `SMTP_PASSWORT`, `SMTP_ABSENDER` | Postausgangsserver deines Mail-Anbieters |

Ohne `SMTP_HOST` läuft der **Testmodus**: Mails werden nicht verschickt, sondern im
Server-Log ausgegeben. Typische Werte: Strato `smtp.strato.de`, Port 465, `ssl`;
IONOS `smtp.ionos.de`, 587, `starttls`. Test: `python -m web.verwaltung mailtest du@example.de`.

Adressen abrufen: `python -m web.verwaltung emails` (alle bestätigten) bzw.
`emails --newsletter --csv liste.csv` (nur mit Einwilligung). **Werbung nur an die
Newsletter-Liste** – für alle anderen ist die Adresse nur für das Konto da (§ 7 UWG).
Mit dem Mail-Anbieter einen Vertrag zur Auftragsverarbeitung (AVV) abschließen.


---

## 6. DSGVO-Checkliste und Cookie-Banner

Die Software ist datensparsam gebaut. DSGVO-konform wird der **Betrieb** aber erst durch die
Punkte unten – die kann kein Code für dich erledigen. (Keine Rechtsberatung; bei einem
kostenpflichtigen Angebot die Texte von einem Anwalt oder einem Generator prüfen lassen.)

**Was der Code schon erledigt**

- Nur Nutzernamen + Datum werden aus Exporten gelesen, sonst nichts.
- Ohne Konto: Löschung nach 24 h. Mit Konto: Löschung inaktiver Konten nach
  `KONTO_LOESCHEN_NACH_TAGEN` (Standard 365), Konto löschen und Datenexport per Knopf.
- Keine E-Mail-Adressen, Passwörter nur als Hash, keine externen Skripte/Schriften/Videos,
  keine Tracking-Cookies, keine Zugriffsprotokolle durch die App selbst.
- Nutzer sehen nur ihre eigenen Daten (getrennt nach Besitzer).
- Datenschutzerklärung-Vorlage passt sich automatisch an die Schalter an.

**Was du erledigen musst**

1. `BETREIBER_NAME`, `BETREIBER_ADRESSE`, `BETREIBER_EMAIL` (ladungsfähige Anschrift!),
   `HOSTER_NAME`, `HOSTER_SITZ`, `AUFSICHTSBEHOERDE` setzen.
2. Mit dem Hoster einen **Auftragsverarbeitungsvertrag** (AVV, Art. 28) abschließen.
   Einfachster Weg: Hoster mit Sitz in der EU (z. B. Hetzner). Bei US-Anbietern (z. B. Render)
   zusätzlich prüfen, ob sie unter dem EU-US Data Privacy Framework zertifiziert sind, und das
   in Abschnitt 5 der Datenschutzerklärung eintragen.
3. **Verzeichnis der Verarbeitungstätigkeiten** (Art. 30) anlegen – eine Tabelle: welche Daten,
   Zweck, Rechtsgrundlage, Löschfrist, technische Schutzmaßnahmen. Die Angaben stehen in der
   Datenschutzerklärung.
4. HTTPS erzwingen (`COOKIES_NUR_HTTPS=1`), regelmäßige Backups, Updates.
5. Automatische Prüfung auf dem Server aus lassen (`AUTO_CHECK_AKTIVIERT=0`).
6. Wenn du Geld verlangst: zusätzlich AGB, Widerrufsbelehrung, Zahlungsanbieter in der
   Datenschutzerklärung.

**Cookie-Banner – brauchst du einen?**

Solange die Seite nur das eingebaute Sitzungs-Cookie nutzt: **nein**. Technisch notwendige
Cookies sind nach § 25 Abs. 2 Nr. 2 TDDDG ohne Einwilligung erlaubt; es reicht der Abschnitt
„Cookies“ in der Datenschutzerklärung. Ein Banner ohne Grund stört nur.

Einschalten über `COOKIE_BANNER` (Umgebungsvariable oder `web/einstellungen.py`):

| Wert | Wirkung | Wann |
|---|---|---|
| `aus` | kein Banner (Standard) | nur notwendiges Cookie – heutiger Stand |
| `hinweis` | Info-Leiste „nur notwendige Cookies“ mit „Verstanden“ | freiwillige Transparenz |
| `einwilligung` | Banner mit „Nur notwendige“ / „Alle akzeptieren“ (gleich groß), Link „Cookie-Einstellungen“ im Fuß zum Widerrufen | sobald du Statistik, Werbung, eingebettete Videos o. Ä. nutzt |

Optionale Dienste trägst du in `web/templates/optionale_dienste.html` ein. Sie werden nur
geladen, wenn der Besucher „Alle akzeptieren“ gewählt hat. Jeden Dienst zusätzlich in der
Datenschutzerklärung (Abschnitt 4) mit Anbieter, Zweck und Speicherdauer nennen.
