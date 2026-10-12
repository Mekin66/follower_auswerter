"""Tests für das neuronale Netz der Kommentar-Bewertung (core/kommentar_netz.py)."""

import json

import pytest

from core import kommentar_netz as kn
from core.aktivitaet import BEHALTEN, ENTFERNEN, AktivitaetAblauf, persoenliches_netz
from core.instagram_export import Kommentar
from core.kommentar_bewertung import HARMLOS, KRITISCH, PRUEFEN, bewerte


def test_mitgeliefertes_netz_passt_zu_den_trainingsdaten():
    """Wer die Beispiele ändert, muss neu trainieren: python -m core.kommentar_netz trainieren"""
    info = kn.standard_netz().info
    assert info["daten"] == kn.daten_fingerabdruck(), "Netz veraltet – bitte neu trainieren"
    assert info["trefferquote_training"] >= 0.95


def test_dateien_sind_utf8():
    roh = kn.BEISPIELE_PFAD.read_bytes()
    roh.decode("utf-8")                                        # wirft bei falscher Kodierung
    assert "😍".encode("utf-8") in roh and "ü".encode("utf-8") in roh
    json.loads(kn.NETZ_PFAD.read_text(encoding="utf-8"))


def test_unicode_merkmale():
    assert kn.woerter("𝐈𝐝𝐢𝐨𝐭!!") == ["idiot"]                  # NFKC: Mathe-Fettschrift -> normale Buchstaben
    assert kn.woerter("GROẞ Straße") == ["gross", "strasse"]   # casefold
    assert kn.woerter("idiooooot") == ["idioot"]               # Buchstaben-Wiederholungen gekürzt
    assert kn.woerter("Ты идиот") == ["ты", "идиот"]           # kyrillisch
    assert kn.ist_emoji("😍") and not kn.ist_emoji("a")
    stil = dict(zip(kn.STIL, kn.stil_merkmale("😍🔥")))
    assert stil["nur_zeichen"] == 1.0
    assert dict(zip(kn.STIL, kn.stil_merkmale("Ruf an: 0176 1234567")))["kontakt"] == 1.0


def test_hashing_ist_stabil():
    """Pythons hash() ist pro Programmstart zufällig – das Netz muss crc32 nutzen."""
    assert kn._platz("w:idiot") == kn._platz("w:idiot")
    assert 0 <= kn._platz("w:idiot")[0] < kn.DIM


@pytest.mark.parametrize("text, stufe", [
    ("😍🔥", HARMLOS),
    ("Wunderschönes Foto!", HARMLOS),
    ("Du bist so ein Idiot!!!", KRITISCH),
    ("𝐈𝐝𝐢𝐨𝐭", KRITISCH),
    ("Die Migration ist ein politisches Thema", PRUEFEN),
    ("Ruf mich an: 0176 12345678", KRITISCH),
])
def test_einstufung(text, stufe):
    assert bewerte(text).stufe == stufe


def test_begruendung_nennt_das_entscheidende_wort():
    b = bewerte("Was für ein dummer Trottel")
    assert b.stufe == KRITISCH and "Trottel" in b.treffer
    assert b.gruende[0].startswith("Netz:") and any("Trottel" in g for g in b.gruende)
    assert sum(b.wahrscheinlichkeiten.values()) == pytest.approx(1.0)
    schnell = bewerte("Was für ein dummer Trottel", erklaeren=False)
    assert not schnell.erklaert and schnell.stufe == KRITISCH and schnell.treffer == []


def test_training_lernt_und_ist_reproduzierbar():
    daten = [("du bist toll", HARMLOS), ("schönes bild", HARMLOS), ("du blödmann", KRITISCH),
             ("blöde kuh", KRITISCH), ("die regierung", PRUEFEN), ("wahl und politik", PRUEFEN)] * 3
    a, b = kn.KommentarNetz(), kn.KommentarNetz()
    verlauf = a.trainieren(daten, epochen=15)
    b.trainieren(daten, epochen=15)
    assert verlauf[-1] < verlauf[0]
    assert a.wahrscheinlichkeiten("blödmann") == b.wahrscheinlichkeiten("blödmann")
    p = a.wahrscheinlichkeiten("so ein blödmann")
    assert max(p, key=p.get) == KRITISCH


def test_speichern_und_laden(tmp_path):
    netz = kn.KommentarNetz()
    netz.trainieren([("hallo", HARMLOS), ("idiot", KRITISCH), ("politik", PRUEFEN)], epochen=5)
    netz.info = {"notiz": "Grüße 😍"}
    netz.speichern(tmp_path / "netz.json")
    geladen = kn.KommentarNetz.laden(tmp_path / "netz.json")
    assert geladen.info["notiz"] == "Grüße 😍"
    assert geladen.wahrscheinlichkeiten("idiot")[KRITISCH] == pytest.approx(netz.wahrscheinlichkeiten("idiot")[KRITISCH], abs=1e-3)
    kaputt = json.loads((tmp_path / "netz.json").read_text(encoding="utf-8"))
    kaputt["dim"] = 7
    with pytest.raises(ValueError):
        kn.KommentarNetz.aus_dict(kaputt)


def test_beispieldatei_format_wird_geprueft(tmp_path):
    datei = tmp_path / "b.tsv"
    datei.write_text("# Kommentar\nharmlos\tHallo 👋\npruefen\tWahl\n", encoding="utf-8")
    assert kn.beispiele_laden(datei) == [("Hallo 👋", HARMLOS), ("Wahl", PRUEFEN)]
    datei.write_text("schlimm\tText\n", encoding="utf-8")
    with pytest.raises(ValueError):
        kn.beispiele_laden(datei)


def _kommentar(i, text):
    return Kommentar(id=str(i), text=text, medien_owner="x", zeitstempel=1700000000 + i, datum="-", link="", quelle="Beitrag")


def test_netz_lernt_aus_entscheidungen_des_nutzers():
    """Ein Nutzer, der Fußball-Lästereien löschen will, bekommt solche Kommentare danach höher eingestuft."""
    eigene = [_kommentar(i, t) for i, t in enumerate([
        "Bayern verliert eh wieder", "Dortmund ist so peinlich", "Schalke steigt ab haha",
        "Bayern-Fans sind alle gleich", "Dortmund kann nix", "Schalke ist ein Witz"])]
    neu = _kommentar(99, "Bayern ist so peinlich, Schalke auch")
    vorher = {k.id: ENTFERNEN for k in eigene}
    standard = kn.KommentarNetz.risiko(kn.standard_netz().wahrscheinlichkeiten(neu.text))
    netz = persoenliches_netz(eigene + [neu], vorher)
    assert netz is not kn.standard_netz() and netz.info["angepasst_mit"] == len(eigene)
    assert netz.risiko(netz.wahrscheinlichkeiten(neu.text)) > standard + 0.1
    # Unter der Mindestzahl bleibt es beim Standard-Netz
    assert persoenliches_netz(eigene, {"0": BEHALTEN}) is kn.standard_netz()
    # Der Durchgang nutzt das angepasste Netz für die Reihenfolge
    ablauf = AktivitaetAblauf.fuer_kommentare("lokal", eigene + [neu], vorher, filter="alle")
    assert ablauf.reihenfolge == ["99"]
    assert ablauf.bewertung(neu).erklaert
