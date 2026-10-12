"""
Startet die JavaScript-Tests der Tresor-App (tests/js/) mit Node.js und prüft dabei,
dass der Browser-Parser einen Export GENAU SO liest wie der Python-Parser.
Ohne installiertes Node.js wird der Test übersprungen.
"""

import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from conftest import PROJEKT, export_zip
from core.archive_reader import lade_export

NODE = shutil.which("node")


def _node_version() -> int:
    return int(subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")[0])


@pytest.mark.skipif(NODE is None or _node_version() < 20, reason="Node.js >= 20 nicht installiert")
@pytest.mark.parametrize("art", ["instagram", "tiktok"])
def test_js_logik_und_gleiches_ergebnis_wie_python(tmp_path, art):
    if art == "instagram":
        roh = export_zip(["anna", "ben"], ["anna", "carl"], blockiert=["troll"], enge=["anna"])
    else:
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("TikTok/user_data_tiktok.json", json.dumps({"Activity": {
                "Follower List": {"FansList": [{"Date": "2024-01-05 18:22:10", "UserName": "Anna"}]},
                "Following List": {"Following": [{"Date": "2024-02-01 10:00:00", "UserName": "ben"}]}}}))
        roh = puffer.getvalue()
    pfad = tmp_path / "export.zip"
    pfad.write_bytes(roh)
    py = lade_export(io.BytesIO(roh), "export.zip")
    erwartet = {"plattform": py.plattform.value, "follower": py.follower, "following": py.following,
                "blockiert": py.blockiert, "enge_freunde": py.enge_freunde}
    umgebung = {**os.environ, "FA_TEST_ZIP": str(pfad), "FA_TEST_ERWARTET": json.dumps(erwartet)}
    lauf = subprocess.run([NODE, "--test", str(Path("tests") / "js" / "tresor.test.mjs")], cwd=PROJEKT, env=umgebung,
                          capture_output=True, text=True, timeout=120)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
