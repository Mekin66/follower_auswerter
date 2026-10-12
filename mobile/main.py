"""
Mobile-Variante mit Kivy (Android; auf dem PC zum Testen lauffähig).

Nutzt dieselben core/-Module wie Desktop- und Web-Version.

Screens:
- "haupt":     Daten laden + auswerten
- "entfolgen": Entfolgen-Modus mit Kategorie-Auswahl und automatischer Prüfung
- "freunde":   Freunde-Liste (gegenseitig + manuell)
- "listen":    Meine Listen (Freunde, von mir blockiert, hat mich blockiert, Markierungen)
- "editor":    Listen selbst eintippen / TXT laden
- "aktivitaet": Kommentar- bzw. Like-Modus (eigene Kommentare/Likes durchgehen)
- "hilfe":     Anleitungen

Behobene Fehler gegenüber Version 1:
- Die .kv-Datei wurde doppelt geladen (Kivy lädt "instagramauswerter.kv"
  automatisch UND build() hat sie nochmal geladen) -> jeder Screen lag
  zweimal übereinander, Knöpfe reagierten nicht zuverlässig.
- Auf Android lag die Datenbank im Home-Ordner statt im App-Speicher.
- Auf Android 11+ darf die App den Download-Ordner nicht mehr einfach
  lesen -> Dateiauswahl jetzt über den System-Dateidialog (SAF).
- Lange Listen werden per RecycleView gezeichnet (vorher: ein Label pro
  Account -> bei tausenden Followern sehr langsam).

Lokal testen:
    pip install -r mobile/requirements.txt
    python mobile/main.py

Android-Build: siehe packaging/README.md bzw. packaging/build_android.sh
"""

import json
import re
import sys
import threading
from pathlib import Path

_HIER = Path(__file__).resolve().parent
# Im Android-Build liegt core/ direkt neben main.py (wird vorher hineinkopiert),
# beim Testen am PC eine Ebene höher.
sys.path.insert(0, str(_HIER))
sys.path.insert(0, str(_HIER.parent))

from kivy.app import App
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.utils import platform

from core import history_store
from core.aktivitaet import (AKTIVITAET_URL, BEHALTEN, ENTFERNEN, FILTER_ALLE, FILTER_KRITISCH, FILTER_RISKANT,
                             KOMMENTAR, LIKE, AktivitaetAblauf, alle_zum_entfernen, kommentar_statistik,
                             like_statistik, such_link)
from core.export import aktivitaet_bericht
from core.kommentar_bewertung import HARMLOS, KRITISCH, PRUEFEN
from core.anleitungen import ANLEITUNGEN, anleitung
from core.archive_reader import ExportFormatFehler, lade_export, lade_liste
from core.freunde import QUELLE_MANUELL, freunde_ermitteln
from core.konto_pruefer import PruefungNichtMoeglich, pruefe_mehrere
from core.models import ENTSCHEIDUNG_TEXTE, LISTEN_TEXTE, Entscheidung, PersonenListe
from core.parser import usernames_aus_text
from core.plattform import PLATTFORM_TEXTE, Plattform, bereich, profil_url
from core.txt_format import lese_txt, schreibe_txt
from core.removal_session import KATEGORIEN, EntfolgenAblauf, kategorien_ermitteln

BESITZER = history_store.LOKAL
TEXT_DUNKEL = (0.106, 0.118, 0.129, 1)
TEXT_SCHWACH = (0.396, 0.404, 0.420, 1)
ROT = (0.863, 0.149, 0.149, 1)
GRUEN = (0.086, 0.639, 0.290, 1)
BLAU = (0.094, 0.467, 0.788, 1)
ORANGE = (0.851, 0.467, 0.024, 1)
STUFEN_FARBE = {KRITISCH: ROT, PRUEFEN: ORANGE, HARMLOS: GRUEN}


def label(text: str, farbe=TEXT_DUNKEL, fett=False, hoehe: float = 28, groesse="15sp") -> Label:
    """Label mit Zeilenumbruch, das mit seinem Text mitwächst."""
    lbl = Label(text=text, color=farbe, bold=fett, size_hint_y=None, height=dp(hoehe), font_size=groesse,
                halign="left", valign="middle")
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    lbl.bind(texture_size=lambda inst, ts: setattr(inst, "height", max(dp(hoehe), ts[1] + dp(6))))
    return lbl


class ZeileMitKnopf(RecycleDataViewBehavior, BoxLayout):
    """
    Listenzeile für RecycleView: optionales Häkchen links (Massenauswahl),
    Text, optionaler Knopf rechts. Der Auswahl-Zustand steht in den DATEN
    (nicht im Widget), weil RecycleView Zeilen-Widgets beim Scrollen wiederverwendet.
    """
    text = StringProperty("")
    farbe = ListProperty(list(TEXT_DUNKEL))
    knopf_text = StringProperty("")
    aktion = ObjectProperty(None, allownone=True)
    ausgewaehlt = BooleanProperty(False)
    umschalten = ObjectProperty(None, allownone=True)


# ============================================================ Haupt
class HauptScreen(Screen):
    status_text = StringProperty("Bitte Daten laden.")
    plattform_name = StringProperty("Instagram")

    def on_pre_enter(self, *_):
        self.plattform_waehlen(App.get_running_app().plattform.value, nur_anzeigen=True)

    def plattform_waehlen(self, wert: str, nur_anzeigen: bool = False):
        """Umschalten Instagram/TikTok: zeigt die letzte Auswertung dieser Plattform."""
        app = App.get_running_app()
        if not nur_anzeigen or app.letzter_snapshot_id is None:
            app.plattform = Plattform(wert)
            app.follower_daten, app.following_daten = {}, {}
            app.letzter_snapshot_id = history_store.letzten_snapshot_id(app.db, app.besitzer)
        self.plattform_name = PLATTFORM_TEXTE[app.plattform]
        if app.letzter_snapshot_id is not None:
            snap = history_store.snapshot_laden(app.db, app.letzter_snapshot_id, app.besitzer)
            self.status_text = f"Letzte {self.plattform_name}-Auswertung: {snap.label}"
            self._listen_fuellen(snap.follower, snap.following)
        else:
            self.status_text = f"Noch keine {self.plattform_name}-Auswertung. Neu hier? Tippe auf „Anleitung“."
            self._listen_fuellen({}, {})

    # ---- Dateiauswahl
    def datei_dialog_oeffnen(self, ziel: str, fertig=None):
        """
        ziel: 'follower', 'following', 'zip' oder 'txt'.
        fertig: optionale Funktion (ziel, pfad), die statt _datei_laden aufgerufen wird (z. B. vom Editor).
        """
        self._fertig = fertig or self._datei_laden
        if platform == "android":
            try:
                self._android_auswahl(ziel)
                return
            except Exception as e:  # noqa: BLE001 – Fallback auf einfachen Dialog
                self.status_text = f"System-Dateiauswahl nicht verfügbar ({e}), nutze einfache Auswahl."
        self._kivy_auswahl(ziel)

    def _android_auswahl(self, ziel: str):
        # Storage Access Framework über androidstorage4kivy (siehe buildozer.spec)
        from androidstorage4kivy import Chooser, SharedStorage  # type: ignore

        def gewaehlt(uri_liste):
            if not uri_liste:
                return
            privat = SharedStorage().copy_from_shared(uri_liste[0])  # Kopie im App-Cache
            Clock.schedule_once(lambda _dt: self._fertig(ziel, privat))

        self._chooser = Chooser(gewaehlt)
        self._chooser.choose_content("*/*")          # ZIP, JSON oder TXT

    def _kivy_auswahl(self, ziel: str):
        start = Path.home() / "Downloads"
        inhalt = BoxLayout(orientation="vertical", spacing=dp(6))
        filter_je_ziel = {"zip": ["*.zip", "*.json"], "txt": ["*.txt"]}
        chooser = FileChooserListView(filters=filter_je_ziel.get(ziel, ["*.json", "*.txt"]),
                                      path=str(start if start.exists() else Path.home()))
        inhalt.add_widget(chooser)
        knopf = Factory.PrimaerKnopf(text="Auswählen", size_hint_y=None, height=dp(46))
        inhalt.add_widget(knopf)
        popup = Popup(title="Datei auswählen", content=inhalt, size_hint=(0.95, 0.95))

        def uebernehmen(*_):
            if chooser.selection:
                popup.dismiss()
                self._fertig(ziel, chooser.selection[0])

        knopf.bind(on_release=uebernehmen)
        chooser.bind(on_submit=lambda *_: uebernehmen())
        popup.open()

    def _datei_laden(self, ziel: str, pfad: str):
        app = App.get_running_app()
        try:
            if ziel == "zip":
                inhalt = lade_export(pfad)
                if inhalt.plattform != app.plattform:
                    self.plattform_waehlen(inhalt.plattform.value)
                app.follower_daten, app.following_daten = inhalt.follower, inhalt.following
                app.blockiert_aus_zip, app.enge_freunde_aus_zip = inhalt.blockiert, inhalt.enge_freunde
                # Kommentare/Likes werden sofort gespeichert (doppelte werden ignoriert)
                neu_k = history_store.kommentare_speichern(app.db, app.besitzer, inhalt.kommentare)
                neu_l = history_store.likes_speichern(app.db, app.besitzer, inhalt.likes)
                erkannt = ", ".join(f"{n} {name}" for name, n in inhalt.enthaelt().items())
                teile = [f"{PLATTFORM_TEXTE[inhalt.plattform]}-Export erkannt: {erkannt}."]
                if inhalt.hat_follower_daten():
                    teile.append("Jetzt „Auswerten“ tippen.")
                if inhalt.kommentare or inhalt.likes:
                    teile.append(f"Neu gespeichert: {neu_k} Kommentare, {neu_l} Likes – unten bei 3. öffnen.")
                self.status_text = " ".join(teile)
            else:
                with open(pfad, "rb") as f:
                    daten = lade_liste(f.read(), pfad)
                if ziel == "follower":
                    app.follower_daten = daten
                    self.status_text = f"Follower geladen ({len(daten)})."
                else:
                    app.following_daten = daten
                    self.status_text = f"Following geladen ({len(daten)})."
        except ExportFormatFehler as e:
            self.status_text = str(e)
        except Exception as e:  # noqa: BLE001
            self.status_text = f"Fehler beim Laden: {e}"

    # ---- Auswerten
    def auswerten(self):
        app = App.get_running_app()
        if not app.follower_daten and not app.following_daten:
            self.status_text = "Bitte zuerst die Export-Datei laden (oder Listen im Editor eintippen)."
            return
        app.letzter_snapshot_id = history_store.snapshot_speichern(app.db, app.follower_daten, app.following_daten,
                                                                   label=getattr(app, "naechstes_label", None),
                                                                   besitzer=app.besitzer)
        app.naechstes_label = None
        neu_b = history_store.liste_hinzufuegen(app.db, app.besitzer, PersonenListe.BLOCKIERT_VON_MIR, app.blockiert_aus_zip)
        neu_f = history_store.liste_hinzufuegen(app.db, app.besitzer, PersonenListe.FREUNDE, app.enge_freunde_aus_zip)
        app.blockiert_aus_zip, app.enge_freunde_aus_zip = {}, {}
        self._listen_fuellen(app.follower_daten, app.following_daten)
        zusatz = f" +{neu_b} blockiert, +{neu_f} enge Freunde übernommen." if (neu_b or neu_f) else ""
        self.status_text = f"Ausgewertet und gespeichert.{zusatz}"
        app.follower_daten, app.following_daten = {}, {}   # verhindert doppeltes Speichern

    def _listen_fuellen(self, follower: dict, following: dict):
        self.ids.following_liste.data = [
            {"text": f"{u}  ·  seit {d}", "color": ROT if u not in follower else TEXT_DUNKEL}
            for u, d in sorted(following.items())]
        self.ids.follower_liste.data = [
            {"text": f"{u}  ·  seit {d}", "color": ROT if u not in following else TEXT_DUNKEL}
            for u, d in sorted(follower.items())]
        self.ids.lbl_following.text = f"Ich folge ({len(following)})"
        self.ids.lbl_follower.text = f"Folgen mir ({len(follower)})"

    def aktivitaet_oeffnen(self, art: str):
        app = App.get_running_app()
        app.aktivitaet_art = art
        self.manager.current = "aktivitaet"

    def oeffnen(self, screen: str):
        if App.get_running_app().letzter_snapshot_id is None and screen not in ("listen", "editor", "hilfe"):
            self.status_text = "Bitte zuerst Daten laden und auswerten."
            return
        self.manager.current = screen


class UnterScreen(Screen):
    def zurueck_zum_hauptscreen(self):
        self.manager.current = "haupt"

    def _inhalt(self) -> BoxLayout:
        box = self.ids.inhalt
        box.clear_widgets()
        return box


# ============================================================ Entfolgen
class EntfolgenScreen(UnterScreen):
    def on_pre_enter(self, *_):
        app = App.get_running_app()
        self.snapshot = history_store.snapshot_laden(app.db, app.letzter_snapshot_id, app.besitzer)
        self.markierungen = history_store.markierungen_laden(app.db, app.besitzer)
        self.freunde = set(history_store.liste_laden(app.db, app.besitzer, PersonenListe.FREUNDE))
        self.ablauf: EntfolgenAblauf | None = None
        self._abbrechen = False
        uebersicht = kategorien_ermitteln(self.snapshot, self.markierungen, self.freunde)
        if not uebersicht.alle:
            self._inhalt().add_widget(label("Niemand folgt dir aktuell nicht zurück.", fett=True))
        elif any(uebersicht.anzahl(k) for k, _ in KATEGORIEN):
            self._auswahl_anzeigen(uebersicht)
        else:
            self._starten(set())

    def on_leave(self, *_):
        self._abbrechen = True

    def _auswahl_anzeigen(self, uebersicht):
        box = self._inhalt()
        box.add_widget(label("Welche Gruppen erneut abfragen?", fett=True, groesse="17sp"))
        box.add_widget(label(f"{len(uebersicht.alle)} folgen dir nicht zurück, {len(uebersicht.neu)} davon neu "
                             "(werden immer abgefragt). Angehakte Gruppen werden erneut abgefragt.",
                             TEXT_SCHWACH, groesse="13sp"))
        self._checkboxen = {}
        for schluessel, text in KATEGORIEN:
            anzahl = uebersicht.anzahl(schluessel)
            zeile = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            cb = Factory.CheckBox(size_hint_x=None, width=dp(40), color=BLAU, disabled=not anzahl)
            self._checkboxen[schluessel] = cb
            zeile.add_widget(cb)
            zeile.add_widget(label(text, TEXT_DUNKEL if anzahl else TEXT_SCHWACH, groesse="14sp"))
            zeile.add_widget(Label(text=str(anzahl), color=TEXT_DUNKEL, bold=True, size_hint_x=None, width=dp(40)))
            box.add_widget(zeile)
        box.add_widget(Factory.PrimaerKnopf(text="Weiter", size_hint_y=None, height=dp(48),
                                            on_release=lambda *_: self._starten(
                                                {k for k, cb in self._checkboxen.items() if cb.active})))

    def _starten(self, erneut: set):
        self.ablauf = EntfolgenAblauf(App.get_running_app().besitzer, self.snapshot, self.markierungen, self.freunde, erneut)
        if not self.ablauf.session.kandidaten:
            self._zusammenfassung_anzeigen(nichts_offen=True)
        else:
            self._angebot_anzeigen()

    def _angebot_anzeigen(self):
        box = self._inhalt()
        offen = len(self.ablauf.offene())
        box.add_widget(label("Automatische Vorprüfung", fett=True, groesse="17sp"))
        box.add_widget(label(f"{offen} Accounts sind offen. Ich kann prüfen, ob welche deaktiviert/gelöscht wirken "
                             f"(ca. {max(1, round(offen * 4 / 60))} Min., nicht 100 % zuverlässig).",
                             TEXT_SCHWACH, groesse="13sp"))
        zeile = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        zeile.add_widget(Factory.PrimaerKnopf(text="Automatisch prüfen", on_release=lambda *_: self._pruefen()))
        zeile.add_widget(Factory.DezentKnopf(text="Überspringen", on_release=lambda *_: self._wizard()))
        box.add_widget(zeile)

    def _pruefen(self):
        box = self._inhalt()
        offene = self.ablauf.offene()
        box.add_widget(label("Prüfe Accounts …", fett=True, groesse="17sp"))
        status = label("Starte …", TEXT_SCHWACH, groesse="13sp")
        box.add_widget(status)
        box.add_widget(Factory.DezentKnopf(text="Abbrechen", size_hint_y=None, height=dp(44),
                                           on_release=lambda *_: setattr(self, "_abbrechen", True)))
        self._abbrechen = False
        db = App.get_running_app().db
        zaehler = {"n": 0}

        def ergebnis_verarbeiten(erg):   # läuft im Hauptthread (Clock)
            zaehler["n"] += 1
            self.ablauf.auto_ergebnis_uebernehmen(db, erg)
            status.text = (f"{zaehler['n']} von {len(offene)} geprüft · "
                           f"{len(self.ablauf.vorschlaege)} Vorschläge\nzuletzt: {erg.username}")

        plattform = App.get_running_app().plattform

        def hintergrund():
            meldung = ""
            try:
                for erg in pruefe_mehrere(offene, 3.0, abbrechen=lambda: self._abbrechen, plattform=plattform):
                    Clock.schedule_once(lambda _dt, e=erg: ergebnis_verarbeiten(e))
            except PruefungNichtMoeglich as e:
                meldung = str(e)
            except Exception as e:  # noqa: BLE001
                meldung = f"Unerwarteter Fehler: {e}"
            Clock.schedule_once(lambda _dt: self._nach_pruefung(meldung) if self.manager.current == "entfolgen"
                                else None, 0.2)

        threading.Thread(target=hintergrund, daemon=True).start()

    def _nach_pruefung(self, meldung: str):
        if meldung:
            inhalt = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(6))
            text = Label(text=meldung, color=(1, 1, 1, 1), font_size="15sp", halign="left", valign="top")
            text.bind(size=lambda inst, groesse: setattr(inst, "text_size", groesse))
            inhalt.add_widget(text)
            fenster = Popup(title="Automatische Prüfung gestoppt", size_hint=(0.9, 0.45), content=inhalt)
            inhalt.add_widget(Factory.PrimaerKnopf(text="OK", size_hint_y=None, height=dp(44),
                                                   on_release=lambda *_: fenster.dismiss()))
            fenster.open()
        if self.ablauf.vorschlaege_offen:
            self._vorschlaege_anzeigen()
        else:
            self._wizard()

    def _vorschlaege_anzeigen(self):
        """Treffer der Prüfung bestätigen: nur Angehakte werden als 'Scheint deaktiviert' übernommen."""
        box = self._inhalt()
        box.add_widget(label(f"{len(self.ablauf.vorschlaege)} Account(s) scheinen nicht mehr zu existieren",
                             fett=True, groesse="17sp"))
        box.add_widget(label("Kurz prüfen (Profil öffnen). Nur angehakte werden übernommen, der Rest wird normal abgefragt.",
                             TEXT_SCHWACH, groesse="13sp"))
        haken = {}
        for name, grund in self.ablauf.vorschlaege.items():
            zeile = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            cb = Factory.CheckBox(active=True, size_hint_x=None, width=dp(40), color=BLAU)
            haken[name] = cb
            zeile.add_widget(cb)
            zeile.add_widget(label(f"{name} – {grund}", groesse="13sp"))
            zeile.add_widget(Factory.DezentKnopf(text="Profil", size_hint_x=None, width=dp(72),
                                                 on_release=lambda *_, n=name: self._profil(n)))
            box.add_widget(zeile)

        def uebernehmen(*_):
            self.ablauf.vorschlaege_bestaetigen(App.get_running_app().db, [n for n, cb in haken.items() if cb.active])
            self._wizard()

        box.add_widget(Factory.PrimaerKnopf(text="Angehakte übernehmen", size_hint_y=None, height=dp(48),
                                            on_release=uebernehmen))

    def _wizard(self):
        if self.ablauf.ist_fertig():
            self._zusammenfassung_anzeigen()
            return
        db = App.get_running_app().db
        box = self._inhalt()
        kandidat = self.ablauf.aktueller_kandidat()
        entschieden, gesamt = self.ablauf.fortschritt()
        box.add_widget(label(f"{entschieden} von {gesamt} bearbeitet", TEXT_SCHWACH, groesse="13sp"))
        box.add_widget(Factory.ProgressBar(max=max(gesamt, 1), value=entschieden, size_hint_y=None, height=dp(12)))
        box.add_widget(Label(text=kandidat, font_size="24sp", bold=True, color=TEXT_DUNKEL,
                             size_hint_y=None, height=dp(56)))
        box.add_widget(label(f"Du folgst seit {self.ablauf.seit(kandidat)}", TEXT_SCHWACH, groesse="13sp"))
        bisher = self.ablauf.bisherige_markierung(kandidat)
        if bisher:
            box.add_widget(label(f"bisher: {ENTSCHEIDUNG_TEXTE[bisher]}", BLAU, groesse="13sp"))

        def entscheiden(e):
            self.ablauf.entscheide(db, e)
            self._wizard()

        zeile = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        zeile.add_widget(Factory.ErfolgKnopf(text="Behalten", on_release=lambda *_: entscheiden(Entscheidung.BEHALTEN)))
        zeile.add_widget(Factory.GefahrKnopf(text="Entfolgen", on_release=lambda *_: entscheiden(Entscheidung.ENTFERNT)))
        zeile.add_widget(Factory.WarnungKnopf(text="Deaktiviert?",
                                              on_release=lambda *_: entscheiden(Entscheidung.DEAKTIVIERT)))
        box.add_widget(zeile)
        zeile2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        zeile2.add_widget(Factory.DezentKnopf(text="< Zurück", disabled=not self.ablauf.kann_zurueck(),
                                              on_release=lambda *_: self._zurueck()))
        zeile2.add_widget(Factory.DezentKnopf(text="Profil öffnen", on_release=lambda *_: self._profil(kandidat)))
        box.add_widget(zeile2)

    @staticmethod
    def _profil(username: str):
        import webbrowser
        webbrowser.open(profil_url(App.get_running_app().plattform, username))

    def _zurueck(self):
        if self.ablauf.zurueck(App.get_running_app().db):
            self._wizard()

    def _zusammenfassung_anzeigen(self, nichts_offen=False):
        box = self._inhalt()
        box.add_widget(label("Nichts offen – alles bereits markiert." if nichts_offen else "Fertig! Zusammenfassung",
                             fett=True, groesse="17sp"))
        zusammenfassung = self.ablauf.zusammenfassung()
        for e in (Entscheidung.ENTFERNT, Entscheidung.BEHALTEN, Entscheidung.DEAKTIVIERT):
            namen = zusammenfassung[e]
            if namen:
                box.add_widget(label(f"{ENTSCHEIDUNG_TEXTE[e]} ({len(namen)}):", fett=True))
                box.add_widget(label(", ".join(namen), TEXT_SCHWACH, groesse="13sp"))
        if self.ablauf.noch_zu_entfolgen():
            box.add_widget(label("Früher als 'Entfolgen' markiert, aber du folgst noch:", ROT, fett=True))
            box.add_widget(label(", ".join(self.ablauf.noch_zu_entfolgen()), TEXT_SCHWACH, groesse="13sp"))
        if self.ablauf.kann_zurueck():
            box.add_widget(Factory.DezentKnopf(text="< Letzte Entscheidung korrigieren", size_hint_y=None,
                                               height=dp(44), on_release=lambda *_: self._zurueck()))


# ============================================================ Freunde
class FreundeScreen(UnterScreen):
    info = StringProperty("")

    def on_pre_enter(self, *_):
        self._laden()

    def _laden(self):
        app = App.get_running_app()
        snap = history_store.snapshot_laden(app.db, app.letzter_snapshot_id, app.besitzer)
        manuell = history_store.liste_laden(app.db, app.besitzer, PersonenListe.FREUNDE)
        freunde = freunde_ermitteln(snap.follower, snap.following, manuell)
        self.info = f"{len(freunde)} Freunde (gegenseitig + manuell) · Basis: {snap.label}"
        self.ids.liste.data = [
            {"text": f"{f.username}  ·  {f.quelle}", "farbe": list(BLAU if QUELLE_MANUELL in f.quelle else TEXT_DUNKEL),
             "knopf_text": "Entfernen" if f.quelle == QUELLE_MANUELL else "",
             "aktion": (lambda u=f.username: self._entfernen(u)) if f.quelle == QUELLE_MANUELL else None}
            for f in freunde]

    def hinzufuegen(self):
        namen = usernames_aus_text(self.ids.eingabe.text)
        if namen:
            history_store.liste_hinzufuegen(App.get_running_app().db, App.get_running_app().besitzer, PersonenListe.FREUNDE, namen)
            self.ids.eingabe.text = ""
            self._laden()

    def _entfernen(self, username: str):
        history_store.liste_entfernen(App.get_running_app().db, App.get_running_app().besitzer, PersonenListe.FREUNDE, username)
        self._laden()


# ============================================================ Listen
class ListenScreen(UnterScreen):
    aktiv = StringProperty(PersonenListe.BLOCKIERT_VON_MIR.value)
    info = StringProperty("")
    anzahl_ausgewaehlt = StringProperty("0")

    def on_pre_enter(self, *_):
        self._auswahl: set[str] = set()
        self._laden()

    def tab(self, name: str):
        self.aktiv = name
        self._auswahl = set()
        self._laden()

    def _namen(self) -> list[str]:
        db = App.get_running_app().db
        if self.aktiv == "markierungen":
            return [u for u, _, _ in history_store.markierungen_mit_datum(db, App.get_running_app().besitzer)]
        return list(history_store.liste_laden(db, App.get_running_app().besitzer, PersonenListe(self.aktiv)))

    def _laden(self):
        db = App.get_running_app().db
        self._auswahl &= set(self._namen())   # verschwundene Namen aus der Auswahl werfen
        self.anzahl_ausgewaehlt = str(len(self._auswahl))

        def zeile(u: str, text: str, knopf: str, aktion):
            return {"text": text, "farbe": list(TEXT_DUNKEL), "knopf_text": knopf, "aktion": aktion,
                    "ausgewaehlt": u in self._auswahl, "umschalten": (lambda u=u: self._umschalten(u))}

        if self.aktiv == "markierungen":
            eintraege = history_store.markierungen_mit_datum(db, App.get_running_app().besitzer)
            self.info = f"{len(eintraege)} markierte Accounts – „Zurücksetzen“ = wird wieder abgefragt"
            self.ids.liste.data = [zeile(u, f"{u}  ·  {m.value}", "Zurücksetzen",
                                         lambda u=u: self._markierung_loeschen(u)) for u, m, _ in eintraege]
            self.ids.eingabe_zeile.opacity, self.ids.eingabe_zeile.disabled = 0, True
            self.ids.btn_sammel.text = "Auswahl zurücksetzen"
            return
        self.ids.eingabe_zeile.opacity, self.ids.eingabe_zeile.disabled = 1, False
        self.ids.btn_sammel.text = "Auswahl entfernen"
        liste = PersonenListe(self.aktiv)
        eintraege = history_store.liste_laden(db, App.get_running_app().besitzer, liste)
        self.info = f"{LISTEN_TEXTE[liste]}: {len(eintraege)}"
        self.ids.liste.data = [zeile(u, f"{u}  ·  {am[:10]}", "Entfernen", lambda u=u: self._entfernen(u))
                               for u, am in eintraege.items()]

    # ---- Massenauswahl
    def _umschalten(self, username: str):
        self._auswahl ^= {username}          # ^= : hinzufügen, falls fehlt, sonst entfernen
        self._laden()

    def alle_auswaehlen(self, alle: bool):
        self._auswahl = set(self._namen()) if alle else set()
        self._laden()

    def sammelaktion(self):
        if not self._auswahl:
            return
        db = App.get_running_app().db
        if self.aktiv == "markierungen":
            history_store.markierungen_mehrere_setzen(db, App.get_running_app().besitzer, self._auswahl, None)
        else:
            history_store.liste_mehrere_entfernen(db, App.get_running_app().besitzer, PersonenListe(self.aktiv), self._auswahl)
        self._auswahl = set()
        self._laden()

    # ---- Einzelaktionen
    def hinzufuegen(self):
        if self.aktiv == "markierungen":
            return
        namen = usernames_aus_text(self.ids.eingabe.text)
        if namen:
            history_store.liste_hinzufuegen(App.get_running_app().db, App.get_running_app().besitzer, PersonenListe(self.aktiv), namen)
            self.ids.eingabe.text = ""
            self._laden()

    def _entfernen(self, username: str):
        history_store.liste_entfernen(App.get_running_app().db, App.get_running_app().besitzer, PersonenListe(self.aktiv), username)
        self._laden()

    def _markierung_loeschen(self, username: str):
        history_store.markierung_loeschen(App.get_running_app().db, App.get_running_app().besitzer, username)
        self._laden()


# ============================================================ Editor
class EditorScreen(UnterScreen):
    """Listen selbst eintippen oder TXT-Dateien laden; danach auswerten."""
    aktiv = StringProperty("follower")
    info = StringProperty("")

    def on_pre_enter(self, *_):
        app = App.get_running_app()
        if not self.ids.feld_follower.text and not self.ids.feld_following.text and app.letzter_snapshot_id:
            self.info = "Tipp: „Übernehmen“ lädt deine letzte Auswertung zum Weiterbearbeiten."
        self._zaehlen()

    def tab(self, name: str):
        self.aktiv = name
        self._zaehlen()

    def _zaehlen(self, *_):
        f = len(lese_txt(self.ids.feld_follower.text))
        g = len(lese_txt(self.ids.feld_following.text))
        self.info = f"Follower: {f} Namen · Following: {g} Namen · ein Name pro Zeile"

    def letzte_uebernehmen(self):
        app = App.get_running_app()
        if app.letzter_snapshot_id is None:
            self.info = "Noch keine Auswertung vorhanden."
            return
        snap = history_store.snapshot_laden(app.db, app.letzter_snapshot_id, app.besitzer)
        self.ids.feld_follower.text = schreibe_txt(snap.follower, "Follower")
        self.ids.feld_following.text = schreibe_txt(snap.following, "Following")
        self._zaehlen()

    def txt_laden(self):
        """Nutzt denselben Dateidialog wie der Haupt-Screen und hängt den Text an das aktive Feld an."""
        haupt = self.manager.get_screen("haupt")
        feld = self.ids.feld_follower if self.aktiv == "follower" else self.ids.feld_following

        def einfuegen(_ziel, pfad):
            with open(pfad, "r", encoding="utf-8-sig", errors="ignore") as f:
                feld.text = (feld.text.rstrip() + "\n" if feld.text.strip() else "") + f.read()
            self._zaehlen()

        haupt.datei_dialog_oeffnen("txt", fertig=einfuegen)

    def txt_speichern(self):
        app = App.get_running_app()
        ordner = Path(app.user_data_dir)
        for name, feld in (("follower", self.ids.feld_follower), ("following", self.ids.feld_following)):
            (ordner / f"{app.plattform.value}_{name}.txt").write_text(
                schreibe_txt(lese_txt(feld.text), name.capitalize()), encoding="utf-8")
        self.info = f"Gespeichert in: {ordner}"

    def auswerten(self):
        app = App.get_running_app()
        app.follower_daten = lese_txt(self.ids.feld_follower.text)
        app.following_daten = lese_txt(self.ids.feld_following.text)
        if not app.follower_daten and not app.following_daten:
            self.info = "Bitte mindestens eine Liste ausfüllen."
            return
        app.naechstes_label = "Eigene Liste"
        haupt = self.manager.get_screen("haupt")
        self.manager.current = "haupt"
        haupt.auswerten()


# ============================================================ Kommentare & Likes
class AktivitaetScreen(UnterScreen):
    """
    Kommentar- bzw. Like-Modus – funktioniert wie der Entfolgen-Modus:
    Übersicht -> Durchgang (Löschen/Behalten/Zurück) -> Liste mit Links.
    Welche Art gerade dran ist, steht in app.aktivitaet_art.
    """

    def on_pre_enter(self, *_):
        self.art = App.get_running_app().aktivitaet_art
        self.ablauf: AktivitaetAblauf | None = None
        self.uebersicht()

    # ---- Hilfsfunktionen
    def _eintraege(self):
        app = App.get_running_app()
        if self.art == KOMMENTAR:
            return history_store.kommentare_laden(app.db, app.besitzer)
        return history_store.likes_laden(app.db, app.besitzer)

    def _vorher(self):
        app = App.get_running_app()
        return history_store.aktivitaet_entscheidungen_laden(app.db, app.besitzer, self.art)

    @staticmethod
    def _oeffnen(url: str):
        import webbrowser
        if url:
            webbrowser.open(url)

    # ---- 1. Übersicht
    def uebersicht(self):
        box = self._inhalt()
        eintraege = self._eintraege()
        titel = "Kommentar-Modus" if self.art == KOMMENTAR else "Like-Modus"
        box.add_widget(label(titel, fett=True, groesse="18sp"))
        if not eintraege:
            box.add_widget(label("Noch keine Daten. Lade einen Instagram-Export, bei dem „Kommentare“ bzw. "
                                 "„Likes“ ausgewählt waren (siehe Anleitung).", TEXT_SCHWACH, groesse="14sp"))
            box.add_widget(Factory.DezentKnopf(text="Anleitung öffnen", size_hint_y=None, height=dp(44),
                                               on_release=lambda *_: self._anleitung()))
            return
        vorher = self._vorher()
        self._erneut = Factory.CheckBox(size_hint_x=None, width=dp(40), color=BLAU)
        if self.art == KOMMENTAR:
            stat = kommentar_statistik(eintraege)
            box.add_widget(label(f"{len(eintraege)} eigene Kommentare · {len(vorher)} schon entschieden",
                                 TEXT_SCHWACH, groesse="13sp"))
            box.add_widget(label(f"Kritisch: {stat[KRITISCH]}   Prüfen: {stat[PRUEFEN]}   Harmlos: {stat[HARMLOS]}",
                                 fett=True, groesse="14sp"))
            box.add_widget(label("Einstufung per neuronalem Netz auf dem Handy – lernt aus deinen "
                                 "Entscheidungen dazu. Du entscheidest.",
                                 TEXT_SCHWACH, groesse="12sp"))
            for text, wert, knopf in (("Nur kritische", FILTER_KRITISCH, "GefahrKnopf"),
                                      ("Kritische + zu prüfende (empfohlen)", FILTER_RISKANT, "WarnungKnopf"),
                                      ("Alle nacheinander", FILTER_ALLE, "DezentKnopf")):
                box.add_widget(getattr(Factory, knopf)(text=text, size_hint_y=None, height=dp(46),
                                                       on_release=lambda *_, w=wert: self.starten(filter=w)))
        else:
            box.add_widget(label(f"{len(eintraege)} Likes · {len(vorher)} schon entschieden",
                                 TEXT_SCHWACH, groesse="13sp"))
            box.add_widget(Factory.PrimaerKnopf(text="Alle Likes durchgehen", size_hint_y=None, height=dp(46),
                                                on_release=lambda *_: self.starten()))
            box.add_widget(label("Oder nur Likes bei einem Account (meiste zuerst):", fett=True, groesse="14sp"))
            for name, anzahl, letzter in like_statistik(eintraege)[:15]:
                box.add_widget(Factory.DezentKnopf(text=f"@{name}  ·  {anzahl} Likes  ·  zuletzt {letzter}",
                                                   size_hint_y=None, height=dp(42), font_size="13sp",
                                                   on_release=lambda *_, n=name: self.starten(account=n)))
        zeile = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        zeile.add_widget(self._erneut)
        zeile.add_widget(label("Schon entschiedene erneut zeigen", groesse="13sp"))
        box.add_widget(zeile)
        anzahl_weg = len(alle_zum_entfernen(App.get_running_app().db, App.get_running_app().besitzer, self.art))
        box.add_widget(Factory.DezentKnopf(text=f"Liste „Zum Entfernen“ ({anzahl_weg})", size_hint_y=None,
                                           height=dp(44), on_release=lambda *_: self.liste()))

    def _anleitung(self):
        hilfe = self.manager.get_screen("hilfe")
        self.manager.current = "hilfe"
        Clock.schedule_once(lambda _dt: hilfe.zeigen("kommentare-likes"), 0)

    # ---- 2. Durchgang
    def starten(self, filter: str = FILTER_RISKANT, account: str | None = None):
        app = App.get_running_app()
        erneut = bool(self._erneut.active)
        if self.art == KOMMENTAR:
            self.ablauf = AktivitaetAblauf.fuer_kommentare(app.besitzer, self._eintraege(), self._vorher(), filter, erneut)
        else:
            self.ablauf = AktivitaetAblauf.fuer_likes(app.besitzer, self._eintraege(), self._vorher(), account, erneut)
        if not self.ablauf.reihenfolge:
            box = self._inhalt()
            box.add_widget(label("Mit dieser Auswahl gibt es nichts Offenes.", fett=True))
            box.add_widget(Factory.DezentKnopf(text="< Zurück", size_hint_y=None, height=dp(44),
                                               on_release=lambda *_: self.uebersicht()))
            return
        self.durchgang()

    def durchgang(self):
        if self.ablauf.ist_fertig():
            self.liste(fertig=True)
            return
        db = App.get_running_app().db
        box = self._inhalt()
        e = self.ablauf.aktueller()
        erledigt, gesamt = self.ablauf.fortschritt()
        box.add_widget(label(f"{erledigt} von {gesamt} bearbeitet", TEXT_SCHWACH, groesse="13sp"))
        box.add_widget(Factory.ProgressBar(max=max(gesamt, 1), value=erledigt, size_hint_y=None, height=dp(12)))
        if self.art == KOMMENTAR:
            b = self.ablauf.bewertung(e)
            box.add_widget(label(f"{b.stufe.upper()} · {b.empfehlung}", STUFEN_FARBE[b.stufe], fett=True, groesse="16sp"))
            box.add_widget(label("Warum: " + "; ".join(b.gruende), TEXT_SCHWACH, groesse="12sp"))
            box.add_widget(label(f"{e.datum} · {e.quelle} von @{e.medien_owner or '?'}", TEXT_SCHWACH, groesse="13sp"))
            text = f"„{e.text}“"
            if not re.search(r"[A-Za-zÄÖÜäöüß0-9]", e.text or ""):
                text += "  (nur Emojis/Zeichen – die App kann Emojis nicht farbig anzeigen)"
            box.add_widget(label(text, groesse="16sp", hoehe=40))
        else:
            box.add_widget(label(f"@{e.owner or '?'}", fett=True, groesse="20sp", hoehe=40))
            box.add_widget(label(f"{e.art} geliked am {e.datum}", TEXT_SCHWACH, groesse="13sp"))
        link = such_link(e)
        box.add_widget(label(link or "(kein Link im Export)", BLAU, groesse="12sp"))

        def entscheiden(wert):
            self.ablauf.entscheide(db, wert)
            self.durchgang()

        zeile = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        zeile.add_widget(Factory.GefahrKnopf(text="Löschen" if self.art == KOMMENTAR else "Entfernen",
                                             on_release=lambda *_: entscheiden(ENTFERNEN)))
        zeile.add_widget(Factory.ErfolgKnopf(text="Behalten", on_release=lambda *_: entscheiden(BEHALTEN)))
        box.add_widget(zeile)
        zeile2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        zeile2.add_widget(Factory.DezentKnopf(text="< Zurück", disabled=not self.ablauf.kann_zurueck(),
                                              on_release=lambda *_: self._zurueck()))
        zeile2.add_widget(Factory.DezentKnopf(text="Link öffnen", disabled=not link,
                                              on_release=lambda *_: self._oeffnen(link)))
        zeile2.add_widget(Factory.DezentKnopf(text="Beenden", on_release=lambda *_: self.liste()))
        box.add_widget(zeile2)

    def _zurueck(self):
        if self.ablauf and self.ablauf.zurueck(App.get_running_app().db):
            self.durchgang()

    # ---- 3. Liste zum Entfernen
    def liste(self, fertig: bool = False):
        app = App.get_running_app()
        box = self._inhalt()
        eintraege = alle_zum_entfernen(app.db, app.besitzer, self.art)
        was = "Kommentare zum Löschen" if self.art == KOMMENTAR else "Likes zum Entfernen"
        box.add_widget(label(("Fertig! " if fertig else "") + f"{was} ({len(eintraege)})", fett=True, groesse="17sp"))
        box.add_widget(label("Gelöscht wird in Instagram: Profil > Menü > „Deine Aktivität“ > „Interaktionen“. "
                             "Dort kannst du auch mehrere auf einmal löschen.", TEXT_SCHWACH, groesse="12sp"))
        box.add_widget(Factory.PrimaerKnopf(text="Instagram-Aktivitätsseite öffnen", size_hint_y=None, height=dp(44),
                                            on_release=lambda *_: self._oeffnen(AKTIVITAET_URL[self.art])))
        for e in sorted(eintraege, key=lambda x: -(x.zeitstempel or 0))[:200]:
            if self.art == KOMMENTAR:
                text = f"{e.datum} · @{e.medien_owner or '?'}: {e.text[:80]}"
            else:
                text = f"{e.datum} · {e.art} von @{e.owner or '?'}"
            knopf = Factory.DezentKnopf(text=text, size_hint_y=None, height=dp(42), font_size="12sp",
                                        shorten=True, halign="left", valign="middle", padding=(dp(10), 0),
                                        on_release=lambda *_, u=such_link(e): self._oeffnen(u))
            knopf.bind(size=lambda k, groesse: setattr(k, "text_size", groesse))   # einzeilig, mit „…“ gekürzt
            box.add_widget(knopf)
        if eintraege:
            box.add_widget(Factory.DezentKnopf(text="Als TXT speichern", size_hint_y=None, height=dp(44),
                                               on_release=lambda *_: self._speichern(eintraege)))
        if self.ablauf and self.ablauf.kann_zurueck():
            box.add_widget(Factory.DezentKnopf(text="< Letzte Entscheidung korrigieren", size_hint_y=None,
                                               height=dp(44), on_release=lambda *_: self._zurueck()))
        box.add_widget(Factory.DezentKnopf(text="Zur Übersicht", size_hint_y=None, height=dp(44),
                                           on_release=lambda *_: self.uebersicht()))

    def _speichern(self, eintraege):
        app = App.get_running_app()
        name = "kommentare_zum_loeschen.txt" if self.art == KOMMENTAR else "likes_zum_entfernen.txt"
        if platform == "android":
            ordner = Path(app.user_data_dir)
        else:                                          # PC-Test: in Downloads (oder Home) speichern
            ordner = Path.home() / "Downloads" if (Path.home() / "Downloads").exists() else Path.home()
        ziel = ordner / name
        ziel.write_text(aktivitaet_bericht(self.art, eintraege), encoding="utf-8")
        if platform == "android":
            try:
                from androidstorage4kivy import SharedStorage  # type: ignore
                SharedStorage().copy_to_shared(str(ziel))
                ziel = f"Downloads/{name}"
            except Exception:  # noqa: BLE001
                pass
        self._inhalt().add_widget(label(f"Gespeichert: {ziel}", GRUEN, groesse="13sp"))
        Clock.schedule_once(lambda _dt: self.liste(), 2.5)


# ============================================================ Hilfe
class HilfeScreen(UnterScreen):
    """Übersicht aller Anleitungen; Antippen zeigt die Schritte."""

    def on_pre_enter(self, *_):
        self.uebersicht()

    def uebersicht(self):
        box = self._inhalt()
        box.add_widget(label("Anleitungen – Schritt für Schritt", fett=True, groesse="18sp"))
        kategorie = None
        for a in ANLEITUNGEN:
            if a.kategorie != kategorie:
                kategorie = a.kategorie
                box.add_widget(label(kategorie.upper(), TEXT_SCHWACH, fett=True, groesse="12sp"))
            box.add_widget(Factory.DezentKnopf(text=a.titel, size_hint_y=None, height=dp(48),
                                               on_release=lambda *_, i=a.id: self.zeigen(i)))

    def zeigen(self, id: str):
        a = anleitung(id)
        box = self._inhalt()
        box.add_widget(Factory.DezentKnopf(text="< Alle Anleitungen", size_hint_y=None, height=dp(40),
                                           on_release=lambda *_: self.uebersicht()))
        box.add_widget(label(a.titel, fett=True, groesse="18sp"))
        box.add_widget(label(a.kurz, TEXT_SCHWACH, groesse="14sp"))
        for i, schritt in enumerate(a.schritte, start=1):
            box.add_widget(label(f"{i}. {schritt}", groesse="15sp"))
        if a.tipps:
            box.add_widget(label("Tipps", GRUEN, fett=True))
            for tipp in a.tipps:
                box.add_widget(label(f"• {tipp}", GRUEN, groesse="14sp"))


# ============================================================ App
class InstagramAuswerterApp(App):
    logo = StringProperty(str(_HIER / "icon.png"))
    # Nur EINMAL laden: explizit per kv_file statt Auto-Laden + Builder.load_file
    kv_file = str(_HIER / "instagramauswerter.kv")
    title = "Follower-Auswertung"

    def build(self):
        self.follower_daten: dict[str, str] = {}
        self.following_daten: dict[str, str] = {}
        self.blockiert_aus_zip: dict[str, str] = {}
        self.enge_freunde_aus_zip: dict[str, str] = {}
        self.letzter_snapshot_id: int | None = None
        self.plattform = Plattform.INSTAGRAM
        self.naechstes_label: str | None = None
        self.aktivitaet_art = KOMMENTAR
        self.icon = str(_HIER / "icon.png")

        if platform in ("android", "ios"):
            db_pfad = Path(self.user_data_dir) / "verlauf.sqlite3"
            if platform == "android":
                self._android_berechtigungen()
        else:
            db_pfad = history_store.STANDARD_DB_PFAD   # gleiche DB wie die Desktop-App
        self.db = history_store.init_db(db_pfad)

        manager = ScreenManager()
        manager.add_widget(HauptScreen(name="haupt"))
        manager.add_widget(EntfolgenScreen(name="entfolgen"))
        manager.add_widget(FreundeScreen(name="freunde"))
        manager.add_widget(ListenScreen(name="listen"))
        manager.add_widget(EditorScreen(name="editor"))
        manager.add_widget(AktivitaetScreen(name="aktivitaet"))
        manager.add_widget(HilfeScreen(name="hilfe"))
        return manager

    @property
    def besitzer(self) -> str:
        """Instagram-Daten unter "lokal", TikTok-Daten unter "lokal#tiktok"."""
        return bereich(BESITZER, self.plattform)

    @staticmethod
    def _android_berechtigungen():
        try:
            from android.permissions import Permission, request_permissions  # type: ignore
            request_permissions([Permission.READ_EXTERNAL_STORAGE])
        except Exception:  # noqa: BLE001 – ab Android 13 nicht mehr nötig/vorhanden
            pass

    def on_stop(self):
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    InstagramAuswerterApp().run()
