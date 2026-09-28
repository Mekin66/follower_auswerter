import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

# Web-App soll in Tests nie in web/daten schreiben
os.environ.setdefault("DATEN_ORDNER", tempfile.mkdtemp(prefix="ia_test_"))
os.environ.setdefault("SECRET_KEY", "test")


def eintrag(name, ts=1700000000, format="title"):
    if format == "title":
        return {"title": name, "string_list_data": [{"timestamp": ts}]}
    if format == "value":
        return {"title": "", "string_list_data": [{"value": name, "href": f"https://www.instagram.com/{name}", "timestamp": ts}]}
    return {"title": "", "string_list_data": [{"href": f"https://www.instagram.com/_u/{name}", "timestamp": ts}]}


def export_zip(follower, following, blockiert=(), enge=(), extra=None) -> bytes:
    puffer = io.BytesIO()
    basis = "connections/followers_and_following/"
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr(basis + "followers_1.json", json.dumps([eintrag(n, format="value") for n in follower]))
        z.writestr(basis + "following.json", json.dumps({"relationships_following": [eintrag(n) for n in following]}))
        z.writestr(basis + "following_hashtags.json", json.dumps({"relationships_following_hashtags": [eintrag("hashtag_fake")]}))
        if blockiert:
            z.writestr(basis + "blocked_profiles.json", json.dumps({"relationships_blocked_users": [eintrag(n, format="href") for n in blockiert]}))
        if enge:
            z.writestr(basis + "close_friends.json", json.dumps({"relationships_close_friends": [eintrag(n, format="value") for n in enge]}))
        for pfad, inhalt in (extra or {}).items():
            z.writestr(pfad, inhalt)
    return puffer.getvalue()


@pytest.fixture
def conn(tmp_path):
    from core import history_store
    c = history_store.init_db(tmp_path / "t.sqlite3")
    yield c
    c.close()
