# 4. Tresor-Modus und rechtliche Einordnung

> **Keine Rechtsberatung.** Dieses Kapitel erklärt, wie das Projekt technisch gebaut ist und
> welche rechtlichen Überlegungen dahinterstehen. Vor einem öffentlichen Start die Texte
> (`datenschutz.html`, `avv.html`, `impressum.html`) von einer Fachperson prüfen lassen.

## 4.1 Was geändert wurde – kurz

| Vorher (Modus `klassisch`) | Jetzt (Modus `tresor`, Standard) |
|---|---|
| Export wird **hochgeladen**, der Server liest ihn aus | Export wird **im Browser** gelesen, nichts wird hochgeladen |
| Server speichert Nutzernamen im Klartext (`snapshots`, `eintraege` …) | Server speichert pro Konto **einen verschlüsselten Block** (`tresore`) |
| Server wertet aus (Vergleich, Entfolgen-Modus, Auto-Prüfung) | Browser wertet aus (`web/static/tresor/*.js`) |
| Betreiber = **Verantwortlicher** für die Listen | Betreiber = **Auftragsverarbeiter** (Art. 28 DSGVO), Nutzer = Verantwortlicher |
| Kein Vertrag mit dem Nutzer über die Listen | **AV-Vertrag** (`/avv`) wird bei der Registrierung angenommen |
| – | Abfrage **privat / geschäftlich** bei der Registrierung |

Umschalten: `BETRIEBSMODUS=tresor` oder `klassisch` (Umgebungsvariable oder `web/einstellungen.py`).

## 4.2 Die Rollen

```
 ┌──────────────── Nutzer (Verantwortlicher) ───────────────┐
 │ Browser: liest Export, wertet aus, verschlüsselt          │
 │ kennt das Tresor-Passwort                                  │
 └───────────────┬──────────────────────────────────────────┘
                 │  nur "FA1.<salt>.<iv>.<geheimtext>"  (HTTPS)
 ┌───────────────▼──────────────── Betreiber (Auftragsverarbeiter) ┐
 │ Flask-Server: speichert den Block, liefert ihn wieder aus        │
 │ kann ihn NICHT entschlüsseln, wertet nichts aus                  │
 └───────────────┬──────────────────────────────────────────────────┘
                 │
 ┌───────────────▼──── Hoster (Unterauftragsverarbeiter) ┐
 │ z. B. Hetzner: Rechenzentrum, Festplatte, Backups      │
 └────────────────────────────────────────────────────────┘
```

**Wichtig – was der Betreiber trotzdem selbst verantwortet:** Für die *Konto*-Daten
(Benutzername, E-Mail, Passwort-Hash, Login-Zeiten, AVV-Zustimmung, IP-Adressen in
Server-Logs) bist du weiterhin **Verantwortlicher**. Dafür gilt die normale
Datenschutzerklärung. Nur der Tresor-*Inhalt* läuft über den AVV.

## 4.3 Was die Vorlage aus der Aufgabe richtig sagt – und was präzisiert wurde

1. **AV-Vertrag:** umgesetzt (`web/templates/avv.html`, Pflicht-Häkchen bei der
   Registrierung). Art. 28 Abs. 9 DSGVO erlaubt den Abschluss in elektronischer Form.
   Gespeichert werden Fassung (`AVV_VERSION`) und Zeitpunkt – das ist dein Nachweis.
   Ändert sich der Text, Fassung hochzählen → alle müssen neu zustimmen; bis dahin
   kann der Tresor nur noch gelesen/gelöscht, aber nicht gespeichert werden.
2. **„Blind“ für den Inhalt:** umgesetzt als echte Ende-zu-Ende-Verschlüsselung, nicht nur
   „datenbankseitig isoliert“. Das ist die stärkere Variante.
3. **„Keine globalen Skripte über die Tabellen“:** Der Server *kann* gar nichts auswerten.
   Zusätzlich sind im Tresor-Modus alle Routen abgeschaltet, die Listen lesen würden
   (`KLASSISCHE_ENDPUNKTE` in `web/app.py`), und die Instagram-Prüfung ist aus.
4. **„Der Nutzer haftet, Sie sind geschützt“ – Präzisierung:**
   - Nutzt eine Privatperson die App rein privat, gilt für **sie** die Haushaltsausnahme
     (Art. 2 Abs. 2 lit. c DSGVO).
   - Für **dich** als Anbieter gilt die DSGVO trotzdem: Erwägungsgrund 18 sagt ausdrücklich,
     dass sie für Verantwortliche oder Auftragsverarbeiter gilt, die die *Mittel* für solche
     privaten Tätigkeiten bereitstellen. Die Verschlüsselung senkt dein Risiko stark, macht es
     aber nicht zu null.
   - Ein AV-Vertrag „verschiebt“ keine Haftung vollständig: Nach Art. 82 DSGVO haftet auch
     der Auftragsverarbeiter, wenn er seine eigenen Pflichten verletzt (z. B. schlechte
     Sicherheit). Deshalb sind die technischen Maßnahmen (§ 6 des AVV) der eigentliche Schutz.
5. **Privat oder geschäftlich?** Statt das vorab festzulegen, fragt die App es bei der
   Registrierung ab (`konten.nutzung`). Das ist wichtig, weil nur Privatleute die
   Haushaltsausnahme haben. Geschäftliche Nutzer brauchen selbst eine Rechtsgrundlage
   (meist Art. 6 Abs. 1 lit. f) und müssen ggf. informieren – das steht in § 11 des AVV.
   Übersicht für dich: `python -m web.verwaltung avv`.

## 4.4 Technischer Ablauf

### Speichern

1. Browser liest Export (`parser.js`, ZIP über `zip.js`) → `{follower, following, …}`.
2. `auswertung.js` legt einen Snapshot im Tresor-Objekt an.
3. `speicher.js` → `krypto.verschluesseln()`:
   JSON → gzip → AES-256-GCM (Schlüssel aus PBKDF2-SHA-256, 600 000 Runden, zufälliges Salt,
   zufälliger IV bei *jedem* Speichern).
4. `PUT /api/tresor` mit `{inhalt: "FA1.…", basis_version: 3}` und Header `X-CSRF-Token`.
5. Server (`web/tresor.py`): Format prüfen (Klartext wird abgelehnt), Version vergleichen,
   speichern, neue Version zurückgeben.

### Laden

1. `GET /api/tresor` → verschlüsselter Block.
2. Nutzer gibt Tresor-Passwort ein → Schlüssel ableiten → entschlüsseln.
   Falsches Passwort oder manipulierter Block → GCM-Prüfung schlägt fehl → klare Meldung.

### Konflikte (zwei Tabs, zwei Geräte)

Jede Speicherung schickt mit, auf welcher Version sie beruht. Passt sie nicht
(jemand anders hat inzwischen gespeichert), antwortet der Server mit **409** und die App
fragt: „Anderen Stand laden“ oder „Meinen Stand behalten“. So geht nichts unbemerkt verloren.

### Warum ein eigenes Tresor-Passwort?

Das Login-Passwort kennt der Server (er prüft es). Würde man den Schlüssel daraus ableiten,
könnte der Server ihn theoretisch auch berechnen. Das Tresor-Passwort verlässt den Browser
nie. Nachteil: Vergessen = Daten weg. Deshalb gibt es die verschlüsselte **Sicherungsdatei**
und den **Klartext-Export** unter „Tresor“.

### Warum keine fremden Bibliotheken (JSZip, CryptoJS …)?

- WebCrypto, `CompressionStream` und `DecompressionStream` sind in allen aktuellen Browsern eingebaut.
- Jedes fremde Skript könnte das Passwort mitlesen. Die strenge **Content-Security-Policy**
  (`TRESOR_CSP` in `web/app.py`) erlaubt nur Skripte vom eigenen Server.
- Kein CDN = keine IP-Übermittlung an Dritte, kein Cookie-Banner nötig.

## 4.5 Grenzen, die du kennen solltest

- **Der Server liefert den Code aus.** Ein Betreiber mit bösen Absichten könnte manipuliertes
  JavaScript ausliefern. Das ist bei *jeder* Web-App mit E2E-Verschlüsselung so (auch bei
  großen Anbietern). Gegenmittel: Quellcode offenlegen, Änderungen nachvollziehbar halten.
- **Metadaten** sieht der Server: Größe des Tresors, Zeitpunkt der Speicherung, IP-Adresse.
  Diese stehen in der Datenschutzerklärung.
- **Kommentar-/Like-Modus** gibt es im Tresor-Modus (noch) nicht – nur Follower-Funktionen.
  Desktop- und Mobile-App können ihn weiterhin (lokal). Erweiterung: siehe
  [Python-Kurs, Lektion 12](python_kurs/12_projekt_erweitern.md).
- **ZIP64** (Exporte > 4 GB) liest der Browser-Leser nicht. Bei Instagram nur
  „Follower und gefolgte Personen“ exportieren.

## 4.6 Checkliste vor dem Start

- [ ] `BETREIBER_NAME`, `BETREIBER_ADRESSE`, `BETREIBER_EMAIL`, `HOSTER_NAME`, `HOSTER_SITZ`, `AUFSICHTSBEHOERDE` gesetzt
- [ ] AV-Vertrag mit dem **Hoster** abgeschlossen (Hetzner: im Kundenportal „Auftragsverarbeitung“)
- [ ] `BACKUP_LOESCHFRIST_TAGE` passt zur tatsächlichen Backup-Rotation
- [ ] Nur HTTPS (`COOKIES_NUR_HTTPS=1`, Caddy/Render liefern TLS automatisch)
- [ ] `avv.html`, `datenschutz.html`, `impressum.html` rechtlich prüfen lassen
- [ ] Verzeichnis der Verarbeitungstätigkeiten (Art. 30 Abs. 2 – auch als Auftragsverarbeiter) angelegt
- [ ] Ablauf für Datenpannen (Meldung an Nutzer binnen 48 h laut AVV § 8) festgelegt
