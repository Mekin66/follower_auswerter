#!/usr/bin/env bash
# Baut die Android-App. Nur unter Linux oder Windows-WSL lauffähig.
#   bash packaging/build_android.sh          -> Debug-APK zum Testen (bin/*.apk)
#   bash packaging/build_android.sh release  -> signierbares App Bundle für Google Play (bin/*.aab)
set -euo pipefail
cd "$(dirname "$0")/../mobile"

# core/ liegt eine Ebene höher; Buildozer packt aber nur mobile/ ein.
rm -rf core
cp -r ../core ./core
find core -name "__pycache__" -type d -prune -exec rm -rf {} +

MODUS="${1:-debug}"
buildozer -v android "$MODUS"
echo "Fertig. Ergebnis liegt in mobile/bin/"
