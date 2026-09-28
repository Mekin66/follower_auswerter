[app]
title = Follower-Auswertung
package.name = followerauswertung
# WICHTIG vor der Store-Veröffentlichung: eigene, eindeutige Domain eintragen
# (z. B. de.deinname). Kann nach der ersten Veröffentlichung nicht mehr geändert werden.
package.domain = org.example
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,json
source.exclude_dirs = __pycache__,bin,.buildozer
version = 4.0.0

# App-Symbol und Startbild (Logo)
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/icon.png
android.presplash_color = #1C1E21

# core/ wird von packaging/build_android.sh vor dem Build hierher kopiert.
# androidstorage4kivy = System-Dateidialog (nötig ab Android 11 für den Download-Ordner)
requirements = python3,kivy==2.3.1,androidstorage4kivy

orientation = portrait
fullscreen = 0

# INTERNET fehlte in Version 1 -> die automatische Prüfung lieferte auf dem
# Handy immer "unsicher". Dateizugriff läuft jetzt über den Systemdialog.
android.permissions = INTERNET,READ_EXTERNAL_STORAGE
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
# Google Play verlangt ein App Bundle (.aab):  buildozer android release
android.release_artifact = aab

[buildozer]
log_level = 2
warn_on_root = 1
