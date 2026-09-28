# Mobile Variante (Kivy) – Setup unter Windows

## "Failed to build 'kivy' when installing build dependencies for kivy"

Diese Fehlermeldung bedeutet: pip findet für deine Python-Version kein
fertiges "Wheel" (vorkompiliertes Paket) und versucht stattdessen, Kivy
selbst aus dem Quellcode zu bauen – das braucht einen C-Compiler samt
diverser Bibliotheken, die auf den wenigsten Windows-Rechnern installiert
sind. Praktisch immer einer von zwei Gründen:

### Ursache 1: Python-Version zu neu (am wahrscheinlichsten)

Kivy veröffentlicht Wheels immer erst mit etwas Verzögerung für ganz neue
Python-Versionen. Prüfe deine Version:

```powershell
python --version
```

Falls das 3.14 oder neuer ist (dein bisheriges .venv nutzt 3.14!): leg dir
eine virtuelle Umgebung mit Python 3.12 oder 3.13 an (parallel zu deiner normalen Installation, ohne
dass sich das gegenseitig stört):

```powershell
# Python 3.12 z. B. von https://www.python.org/downloads/ installieren,
# dann im Projektordner:
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r mobile\requirements.txt
```

### Ursache 2: "kivy" statt "kivy[base]" installiert

Nur `pip install kivy` zieht manchmal nicht automatisch die nötigen
vorkompilierten Abhängigkeiten (SDL2 fürs Fenster, GLEW für Grafik). Immer:

```powershell
pip install "kivy[base]==2.3.1"
```

Das steht jetzt auch schon so in `mobile/requirements.txt` – einfach:

```powershell
pip install -r mobile\requirements.txt
```

### Falls es immer noch nicht klappt

Als letzten Ausweg gibt es fertige Wheels direkt von Kivy (unabhängig von
PyPI), die auch für sehr neue oder sehr alte Python-Versionen oft schon
verfügbar sind, bevor sie es auf PyPI sind:

```powershell
pip install kivy --pre --extra-index-url https://kivy.org/downloads/wheels
```

### Kurzer Realitätscheck

Für's reine Testen/Entwickeln am PC ist das relevant. Für den **Android-
Build** später (über Buildozer, siehe `packaging/README.md`) spielt deine
lokale Windows-Kivy-Installation keine Rolle – Buildozer läuft ohnehin nur
unter Linux/WSL und lädt sich seine eigene Toolchain.
