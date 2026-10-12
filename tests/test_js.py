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
from core import kommentar_netz
from core.archive_reader import lade_export
from test_core import _gemischtes_zip

NETZ_TEXTE = ["😍🔥", "Du bist so ein Idiot!!!", "𝐈𝐝𝐢𝐨𝐭", "Die Migration ist ein politisches Thema", "x" * 320,
              "Was für ein dummer Trottel", "Ruf mich an: 0176 12345678", "GROẞE Straße!!", "Ты идиот",
              "Çok güzel olmuş 😍", "idiooooot", "", "Schöne Grüße an alle 👋 www.beispiel.de"]

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
    netz = kommentar_netz.standard_netz()
    netz_erwartet = [{"text": t, "p": netz.wahrscheinlichkeiten(t),
                      "top": (netz.erklaeren(t) or [[None]])[0][0] if t else None} for t in NETZ_TEXTE]
    akt_pfad = tmp_path / "aktivitaet.zip"
    akt_pfad.write_bytes(_gemischtes_zip())
    akt = lade_export(io.BytesIO(_gemischtes_zip()))
    akt_erwartet = {"kommentare": [vars(k) for k in akt.kommentare], "likes": [vars(l) for l in akt.likes],
                    "follower": akt.follower}
    umgebung = {**os.environ, "FA_TEST_ZIP": str(pfad), "FA_TEST_ERWARTET": json.dumps(erwartet),
                "FA_TEST_NETZ": json.dumps(netz_erwartet), "FA_TEST_AKT_ZIP": str(akt_pfad),
                "FA_TEST_AKT_ERWARTET": json.dumps(akt_erwartet)}
    lauf = subprocess.run([NODE, "--test", str(Path("tests") / "js" / "tresor.test.mjs")], cwd=PROJEKT, env=umgebung,
                          capture_output=True, text=True, timeout=120)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
