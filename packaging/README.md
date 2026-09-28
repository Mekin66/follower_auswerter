# Packaging & Vertrieb – Übersicht

Drei Varianten, die alle dieselbe Logik aus `core/` nutzen:

| Variante | Ordner | Zielplattform | Aufwand |
|---|---|---|---|
| Desktop (Tkinter) | `gui/` + `main.py` | Windows/Mac/Linux als .exe/Programm | gering |
| Web-App (Flask) | `web/` | Browser, Basis für PWA in den Stores | mittel |
| Mobile (Kivy) | `mobile/` | Android (und mit Einschränkungen iOS) | hoch |

## 1. Desktop -> .exe (Windows)

```bash
pip install pyinstaller
pyinstaller packaging/build_exe.spec
```

Ergebnis: `dist/FollowerAuswertung.exe` – eine einzelne Datei, die du
weitergeben kannst. Kein Python muss beim Nutzer installiert sein.
Auf Mac/Linux erzeugt derselbe Befehl ein natives Programm für das
jeweilige Betriebssystem (aber: für eine Mac-App musst du auf einem Mac
bauen, für eine Windows-exe auf Windows – PyInstaller baut nicht plattformübergreifend).

**Das ist NICHT der Weg in den Apple/Google Store** – Windows-exe-Dateien
werden von keinem der beiden Stores akzeptiert. Für die Stores siehe unten.

## 2. Web-App -> Google Play & Apple App Store

Tkinter- und Kivy-Apps kann man nicht "einfach so" in die Stores bringen.
Der pragmatischste Weg ist daher oft: **Web-App bauen, dann als PWA in
eine Store-fähige Hülle packen.**

Schritte:

1. `web/app.py` lokal testen: `pip install -r web/requirements.txt`, dann
   `python web/app.py` und `http://localhost:5000` öffnen.
2. Die Web-App auf einen Server bringen (z. B. Render, Railway, Fly.io,
   PythonAnywhere, eigener Server) – erst dann ist sie über das Internet
   erreichbar, was für Schritt 3 nötig ist.
3. Mit **[Capacitor](https://capacitorjs.com/)** (oder Bubblewrap für
   Android) die gehostete Web-App in eine echte Android/iOS-App
   verpacken. Das erzeugt ein Android-Projekt (Android Studio) bzw.
   Xcode-Projekt, das du regulär im jeweiligen Store einreichen kannst.
4. Store-Voraussetzungen, unabhängig vom technischen Weg:
   - Google Play: Google-Play-Console-Konto (einmalig ca. 25 USD), App
     durchläuft eine automatisierte + teils manuelle Prüfung.
   - Apple App Store: Apple-Developer-Programm (99 USD **pro Jahr**),
     Review durch Apple (kann Tage dauern, Apple ist bei einfachen
     Utility-Apps mit Web-Ansicht öfters kritisch – ggf. Nutzen klar
     kommunizieren, warum es eine App und keine reine Webseite ist).

## 3. Mobile (Kivy) -> Android/iOS nativ

`mobile/` enthält eine native Kivy-Version. Vorteil: läuft direkt auf dem
Gerät (kein Server nötig), Nachteil: deutlich mehr Setup-Aufwand.

**Android** (mit [Buildozer](https://buildozer.readthedocs.io/), nur unter
Linux/WSL lauffähig). Das Skript kopiert vorher `core/` in den `mobile/`-Ordner
(Buildozer packt nur diesen Ordner ein – das fehlte in Version 1):

```bash
pip install buildozer
bash packaging/build_android.sh          # .apk zum Testen
bash packaging/build_android.sh release  # .aab für Google Play (muss signiert werden)
```

**iOS**: deutlich aufwändiger – Kivy braucht dafür `kivy-ios`, einen Mac
mit Xcode, und ein Apple-Developer-Konto. Realistisch nur sinnvoll, wenn
du wirklich eine native App willst und bereit bist, dich in Xcode
einzuarbeiten. Für die meisten Fälle ist Weg 2 (Web-App + Capacitor) für
iOS der deutlich geringere Aufwand.

## Empfehlung

- Nur für dich/Freunde: **Desktop-exe** reicht völlig.
- Soll es "offiziell" in beide Stores: **Web-App + Capacitor**, weil du
  dann nur eine Codebasis (die Web-App) pflegen musst statt einer eigenen
  nativen App pro Plattform.
- Natives Kivy nur, wenn du gezielt Dinge brauchst, die eine Web-App nicht
  kann (z. B. tiefe Systemintegration).

## Veröffentlichen

Schritt-für-Schritt (Hosting, Impressum/Datenschutz, Google Play, Konto-Schalter):
siehe `docs/VEROEFFENTLICHEN.md`. Fertige Dateien dafür: `Dockerfile`, `render.yaml`,
`packaging/server/` (eigener Server mit automatischem HTTPS).
