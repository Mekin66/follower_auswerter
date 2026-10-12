# Handbuch – Follower-Auswertung

Dieses Handbuch erklärt das gesamte Projekt: Aufbau, Code, Datenbank, rechtliches Modell,
Veröffentlichung – und enthält einen Python-Kurs, der genau an diesem Code lehrt.

| Kapitel | Inhalt | Für wen |
|---|---|---|
| [1. Projektstruktur](01_projektstruktur.md) | Ordnerbaum, Rolle jeder Datei, Datenfluss, Konventionen, Startbefehle | Einstieg |
| [2. Der Code erklärt](02_code_erklaert.md) | Modul für Modul: Klassen, Funktionen, knifflige Stellen (Python + Browser-App) | Entwickeln |
| [3. Datenbank](03_datenbank.md) | Tabellen, ansehen, verwalten, sichern, erweitern (Migrationen) | Betrieb & Entwickeln |
| [4. Tresor-Modus und Recht](04_tresor_und_recht.md) | Server als Auftragsverarbeiter, AVV, Ende-zu-Ende-Verschlüsselung, Grenzen, Checkliste | Betreiber |
| [5. Launch](05_launch.md) | Ausbaustufen, Kostenvergleich, Render / Hetzner / lokal Schritt für Schritt, Backups | Betreiber |
| [Python-Kurs](python_kurs/README.md) | 12 Lektionen mit Übungen und Lösungen, für Leute mit Grundkenntnissen | Lernen |

## Das Wichtigste in fünf Sätzen

1. Die Logik liegt in `core/`; Desktop (`gui/`), Handy (`mobile/`) und Web (`web/`) sind Oberflächen darum.
2. Die Web-Version läuft standardmäßig im **Tresor-Modus**: Exporte werden im Browser gelesen und
   ausgewertet, der Server speichert nur einen verschlüsselten Block, den er nicht lesen kann.
3. Damit ist der Betreiber für die Listen **Auftragsverarbeiter** (Art. 28 DSGVO); jeder Nutzer
   stimmt bei der Registrierung dem AV-Vertrag zu und gibt an, ob er privat oder geschäftlich nutzt.
4. Alle Schalter stehen in `web/einstellungen.py` und lassen sich per Umgebungsvariable setzen.
5. `python -m pytest tests` prüft alles – auch, dass der Browser-Parser dasselbe liefert wie der Python-Parser.

Weitere Dokumente: [`../ARCHITEKTUR.md`](../ARCHITEKTUR.md) (Entwicklungsgeschichte),
[`../VEROEFFENTLICHEN.md`](../VEROEFFENTLICHEN.md) (Stores, DSGVO-Checkliste).
