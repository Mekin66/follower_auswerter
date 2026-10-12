# 5. Launch – günstig online gehen

> Preise: Stand Oktober 2026, ohne Gewähr. Hetzner hat 2026 zweimal die Preise erhöht – vor
> der Bestellung auf der Anbieterseite prüfen.

## 5.1 Erst entscheiden: welche Ausbaustufe?

Der Tresor-Modus macht einen sehr billigen Start möglich, weil der Server im einfachsten
Fall **gar nichts speichert**.

| Stufe | Einstellung | Was der Server tut | Speicher nötig? | Mail nötig? | Rechtlicher Aufwand |
|---|---|---|---|---|---|
| **1 – Nur Browser** | `BETRIEBSMODUS=tresor`, `ACCOUNTS_AKTIVIERT=0` | liefert nur die Webseite aus | nein | nein | Impressum + kurze Datenschutzerklärung |
| **2 – Mit Tresor** | `BETRIEBSMODUS=tresor`, `ACCOUNTS_AKTIVIERT=1` | Konten + verschlüsselte Tresore | ja (Volume) | ja (SMTP) | + AVV, Backups, Löschfristen |
| (klassisch) | `BETRIEBSMODUS=klassisch` | wertet selbst aus, Klartext | ja | bei Konten | voll verantwortlich – **nicht öffentlich betreiben** |

**Empfehlung:** Mit Stufe 1 starten, Resonanz abwarten, dann Stufe 2 freischalten. Der Wechsel
ist nur eine Umgebungsvariable.

## 5.2 Optionen im Vergleich

| Option | Kosten/Monat (ca.) | Stufe 1 | Stufe 2 | Serverwissen | Bemerkung |
|---|---|---|---|---|---|
| **Lokal / Heimnetz** | 0 € | ✔ | ✔ | gering | nur für dich, `python web/app.py` |
| **Render Free** | 0 € | ✔ | ✘ | keins | schläft nach Inaktivität (erster Aufruf ~1 min), kein dauerhafter Speicher |
| **Render Starter + Disk** | ca. 7 $ + 0,25 $/GB | ✔ | ✔ | keins | `render.yaml` liegt bei; US-Firma, Server Frankfurt |
| **Hetzner Cloud CX23** (2 vCPU, 4 GB, 40 GB) | ca. 5,49 € (+ Backups +20 %) | ✔ | ✔ | mittel | deutsche Firma, Rechenzentrum DE/FI, AVV per Klick |
| **Kleiner VPS anderer Anbieter** (netcup, IONOS, Strato …) | ca. 1–5 € | ✔ | ✔ | mittel | auf Standort EU und AVV achten |
| **Domain** (.de) | ca. 0,50–1,50 € | optional | empfohlen | – | Render liefert sonst `*.onrender.com` |
| **E-Mail-Versand** | 0 € (Brevo/Mailjet Free-Kontingent oder Postfach des Domain-Anbieters) | – | nötig | gering | SMTP-Daten in `.env` |

**Realistische Gesamtkosten:**
- Stufe 1: **0 €** (Render Free) bis ca. **1 €** mit eigener Domain.
- Stufe 2: ca. **7–9 €** (Hetzner CX23 + Backups + Domain) oder ca. **8–9 $** (Render Starter + 1 GB).

Rechenbedarf: Der Server rechnet im Tresor-Modus praktisch nichts. Ein Tresor ist
komprimiert und verschlüsselt meist 10–500 KB. Selbst 1 000 Nutzer passen in 1 GB.

## 5.3 Weg A: Render (ohne Serverkenntnisse)

1. Projekt auf GitHub (privates Repo reicht).
2. render.com → **New → Blueprint** → Repo wählen. `render.yaml` legt Docker-Build, Region
   Frankfurt, Disk und zufälligen `SECRET_KEY` an.
3. Im Dashboard eintragen: `BETREIBER_NAME`, `BETREIBER_ADRESSE`, `BETREIBER_EMAIL`,
   `AUFSICHTSBEHOERDE`, `OEFFENTLICHE_URL`.
4. **Stufe 1 auf dem Free-Plan:** in `render.yaml` `plan: free` setzen und den Block `disk:`
   entfernen (Free hat keine Disk). `ACCOUNTS_AKTIVIERT` bleibt `0`.
   Achtung: Ohne Disk wird der `SECRET_KEY` aus der Umgebungsvariablen genutzt – `generateValue: true`
   erledigt das.
5. **Stufe 2:** `plan: starter`, Disk behalten, `ACCOUNTS_AKTIVIERT=1`, SMTP-Variablen setzen.
6. Eigene Domain: Settings → Custom Domain. HTTPS kommt automatisch.

## 5.4 Weg B: Eigener Server bei Hetzner (am günstigsten mit Speicher)

```bash
# 1. Server anlegen: Hetzner Cloud Console → CX23, Ubuntu 24.04, Standort Nürnberg/Falkenstein,
#    SSH-Schlüssel hinterlegen, "Backups" aktivieren (+20 %).
# 2. Domain: A-Record (und AAAA für IPv6) auf die Server-IP.
ssh root@DEINE_IP

# 3. Grundschutz
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 ufw unattended-upgrades
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable

# 4. Projekt holen
git clone https://github.com/DEIN_NAME/follower_auswerter.git && cd follower_auswerter
cp packaging/server/.env.beispiel packaging/server/.env
nano packaging/server/.env              # SECRET_KEY (z. B. `openssl rand -hex 32`), Betreiberdaten, SMTP …
nano packaging/server/Caddyfile         # deine-domain.de eintragen

# 5. Starten (Caddy holt das HTTPS-Zertifikat automatisch)
docker compose -f packaging/server/docker-compose.yml up -d --build
docker compose -f packaging/server/docker-compose.yml logs -f app
```

**Update einspielen:**

```bash
cd follower_auswerter && git pull
docker compose -f packaging/server/docker-compose.yml up -d --build
```

**Tägliches Backup** (`crontab -e` auf dem Server):

```cron
15 3 * * * docker compose -f /root/follower_auswerter/packaging/server/docker-compose.yml exec -T app python -c "import sqlite3,datetime;s=sqlite3.connect('/data/web.sqlite3');d=sqlite3.connect(f'/data/backup-{datetime.date.today()}.sqlite3');s.backup(d)"
30 3 * * * docker compose -f /root/follower_auswerter/packaging/server/docker-compose.yml exec -T app find /data -name 'backup-*.sqlite3' -mtime +30 -delete
```

Die `30` muss zu `BACKUP_LOESCHFRIST_TAGE` passen. Für Sicherungen außerhalb des Servers
zusätzlich Hetzner-Backups oder eine Storage Box nutzen.

## 5.5 Weg C: Lokal / zum Ausprobieren

```bash
pip install -r web/requirements.txt
COOKIES_NUR_HTTPS=0 python web/app.py                         # Stufe 1
COOKIES_NUR_HTTPS=0 ACCOUNTS_AKTIVIERT=1 python web/app.py    # Stufe 2, Bestätigungs-Links stehen im Terminal
```

Im Heimnetz für andere Geräte erreichbar machen: in `web/app.py` unten `host="0.0.0.0"` –
**nie** so ins Internet stellen (kein HTTPS).

## 5.6 Checkliste vor dem Livegang

- [ ] `SECRET_KEY` lang und zufällig, nicht im Git
- [ ] `COOKIES_NUR_HTTPS=1`, Seite nur über HTTPS erreichbar
- [ ] `BETRIEBSMODUS=tresor`
- [ ] Impressum, Datenschutz, AVV mit echten Angaben – geprüft (Kapitel 4.6)
- [ ] AVV mit dem Hoster abgeschlossen
- [ ] Bei Stufe 2: SMTP getestet (`python -m web.verwaltung mailtest DU@…`), Backups laufen
- [ ] `python -m pytest tests` grün
- [ ] Einmal komplett durchgeklickt: Export laden → Ergebnis → Entfolgen → Tresor sperren/entsperren
- [ ] Name/Logo ohne „Instagram“/„TikTok“ (Markenrecht, siehe `docs/VEROEFFENTLICHEN.md`)

## 5.7 Später: App-Stores

Die Web-App lässt sich als **PWA** bzw. per Capacitor/Bubblewrap in die Stores bringen; die
Kivy-App (`mobile/`) läuft komplett offline. Details: `docs/VEROEFFENTLICHEN.md` und
`packaging/README.md`. Google Play: einmalig 25 $; Apple: 99 $/Jahr.
