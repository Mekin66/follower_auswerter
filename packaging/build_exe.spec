# PyInstaller-Konfiguration für die Desktop-Variante (Tkinter).
#
# Erzeugt eine einzelne .exe-Datei (Windows) bzw. ein ausführbares Programm
# (Mac/Linux), die main.py + core/ + gui/ enthält.
#
# Nutzung (im Projekt-Hauptordner, also eine Ebene über packaging/):
#
#   pip install pyinstaller
#   pyinstaller packaging/build_exe.spec
#
# Das fertige Programm liegt danach in dist/FollowerAuswertung(.exe)

# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=[],
    datas=[('../gui/logo.png', 'gui'),      # Logo im Fenster/Kopf
           ('../core/daten', 'core/daten')],   # Kommentar-Netz (Gewichte + Trainingsbeispiele)
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['kivy', 'flask', 'werkzeug', 'jinja2'],  # gehören nicht zur Desktop-Version
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FollowerAuswertung',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # kein Konsolenfenster, reines GUI-Programm
    onefile=True,
    icon='../assets/logo.ico',   # Programmsymbol (Explorer, Taskleiste)
)
