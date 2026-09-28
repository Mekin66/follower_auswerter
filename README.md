# Follower-Auswertung (Version 4)

Wertet den offiziellen Datenexport von **Instagram und TikTok** aus – oder selbst erstellte Listen: Wer folgt dir nicht zurück,
wer ist neu dazugekommen oder weg, wer sind deine Freunde – ohne Login bei Instagram.

Drei Oberflächen, eine gemeinsame Logik (`core/`):

| Start | Befehl |
|---|---|
| Desktop (Windows/Mac/Linux) | `python main.py` |
| Web | `pip install -r web/requirements.txt` → `python web/app.py` → http://localhost:5000 |
| Mobile (Test am PC) | `pip install -r mobile/requirements.txt` → `python mobile/main.py` |

> **Python-Version:** Desktop und Web laufen mit Python 3.10–3.14. Für die
> Mobile-Version **Python 3.12 oder 3.13** verwenden – Kivy 2.3.1 hat (Stand
> September 2026) keine Pakete für Python 3.14, die Installation schlägt dort fehl.

## Neu in Version 4

- **Kommentar-Modus:** eigene Instagram-Kommentare Schritt für Schritt durchgehen (wie der Entfolgen-Modus).
  Eine Regel-Bewertung (Wortlisten, Länge, Großbuchstaben, „!!“, Kontaktdaten – keine KI) sortiert vor:
  **kritisch → Löschen empfohlen**, **prüfen**, **harmlos** (Emojis, kurze Kommentare). Jede Einstufung nennt ihre Gründe.
  Link zum Beitrag bzw. Profil, Datum, Liste „Zum Löschen“ als TXT, Link zur Instagram-Aktivitätsseite.
- **Like-Modus:** Likes nach Account gruppiert („wem gebe ich am meisten Likes“), alle oder nur die eines Accounts durchgehen.
- **Automatische Erkennung des Export-Inhalts:** ZIP mit Followern, Kommentaren, Likes oder beliebiger Kombination;
  einzelne Dateien gehen auch. **HTML-Exporte** von Instagram werden jetzt gelesen (JSON bleibt empfohlen).
- **E-Mail bei Konten (Web):** E-Mail-Pflicht, **Bestätigungs-Link (Double-Opt-in)**, Login mit Name oder E-Mail,
  **Passwort vergessen**, E-Mail ändern, freiwillige Newsletter-Einwilligung, Verwaltungs-Befehle
  (`python -m web.verwaltung …`). SMTP-Einstellungen in `web/einstellungen.py` bzw. `.env`.
- **Logo** für alle Oberflächen (Fenster-Icon, Favicon, App-Icon, .exe-Icon).
- **Desktop:** Follower-Liste scrollt jetzt mit dem Mausrad (vorher fing die umgebende Scroll-Fläche das Mausrad ab),
  neues zweispaltiges Layout mit Suchfeld.

## Neu in Version 3

- **Zuverlässigere Prüfung „Scheint deaktiviert“:** Vor jeder Prüfung testet das Programm mit einem
  sicher existierenden und einem sicher nicht existierenden Account, ob die Plattform gerade eine
  verlässliche Unterscheidung zulässt. Bei Sperre/Login-Pflicht bricht es mit klarer Meldung ab.
  Treffer sind nur noch **Vorschläge**, die man per Häkchen bestätigt.
  (Vorher wurden aktive Accounts fälschlich als deaktiviert erkannt, weil Instagram die Fehlermeldung
  in den Sprachdaten jeder Seite mitliefert.)
- **TikTok:** Export (ZIP, JSON oder TXT) wird automatisch erkannt; Daten beider Plattformen bleiben
  getrennt; Umschalter Instagram/TikTok in allen Oberflächen.
- **TXT-Listen und Listen-Editor:** Follower/Following selbst eintippen oder als Textdatei laden und speichern.
- **Anleitungen für Laien** in Web, Desktop und App (gleiche Texte aus `core/anleitungen.py`).

## Neu in Version 2

- **Markierungen bleiben dauerhaft.** Wer einmal als „Behalten“, „Scheint deaktiviert“
  oder „Entfolgen“ markiert ist, wird beim nächsten Export nicht wieder abgefragt oder geprüft.
  Vor dem Start wählst du pro Gruppe, ob sie **erneut abgefragt** werden soll.
- **Eigene Listen:** „Von mir blockiert“, „Hat mich blockiert“, „Freunde (manuell)“.
  Blockierte Profile und „Enge Freunde“ werden aus dem ZIP-Export automatisch übernommen.
  Der Verlaufs-Vergleich zeigt einen **Blockier-Verdacht** (vorher gegenseitig gefolgt,
  jetzt beide Verbindungen weg).
- **Massenauswahl in „Meine Listen“:** mehrere Einträge per Häkchen (Web, App) bzw.
  Strg/Umschalt-Klick (Desktop) auswählen, „Alle“, Filterfeld, dann gesammelt entfernen,
  verschieben/kopieren in eine andere Liste oder Markierungen ändern/zurücksetzen.
- **Freunde-Liste:** alle gegenseitigen Follows + manuell eingetragene Freunde,
  Export als CSV (Excel) oder Text.
- **Web-Version mit Konten** – per Schalter `ACCOUNTS_AKTIVIERT` in `web/einstellungen.py`.
  Ohne Konten gibt es dort bewusst keine dauerhaften Markierungen und keine Blockiert-Listen.
- Fehler behoben: Web-Upload lieferte immer Fehler 500; Mobile-App lud ihr Layout doppelt;
  „Zurück“ im Wizard konnte den falschen Account zurücksetzen; `following_hashtags.json`
  wurde als Account-Liste mitgelesen; neuere Exporte ohne `value`-Feld wurden nicht erkannt;
  Android-App hatte keine Internet-Berechtigung; im Web sahen alle Besucher denselben Verlauf.

Veröffentlichen: siehe [docs/VEROEFFENTLICHEN.md](docs/VEROEFFENTLICHEN.md).
Aufbau des Codes: siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).
Tests: `pip install pytest` → `python -m pytest tests`.
